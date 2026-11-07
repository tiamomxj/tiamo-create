"""Independent reader for Voxy position-format 1 / section-format 0 caches.

Only original user-owned RocksDB files are read. Native access is delegated to
the installed RocksDB JNI library through our small, read-only Java bridge.
"""
from __future__ import annotations
import atexit, gzip, hashlib, io, json, math, os, shutil, struct, subprocess, sys, threading, time, zipfile, weakref
from collections import OrderedDict
from pathlib import Path
import numpy as np
import zstandard
from .anvil import read_nbt

FORMAT='voxy-pos1-section0-v1'
BRIDGES=weakref.WeakSet()
def close_bridges():
    for bridge in list(BRIDGES):bridge.close()
atexit.register(close_bridges)

def section_key(level,x,y,z):
    return (level<<60)|((y&255)<<52)|((z&0xffffff)<<28)|((x&0xffffff)<<4)

def section_position(key):
    signed=lambda v,b:v-(1<<b) if v&(1<<(b-1)) else v
    return key>>60,signed((key>>4)&0xffffff,24),signed((key>>52)&255,8),signed((key>>28)&0xffffff,24)

def decode_section(blob,expected):
    if blob[:4]==b'\x28\xb5\x2f\xfd':blob=zstandard.ZstdDecompressor().decompress(blob,max_output_size=1024*1024)
    if len(blob)<65560:raise ValueError('Voxy section is truncated or in an unsupported format.')
    key,meta=struct.unpack_from('<QQ',blob);count=meta&65535
    if key!=expected or not 1<=count<=32768 or len(blob)!=65552+count*8:
        raise ValueError('Voxy section version or position mismatch (supported: position format 1 / section format 0).')
    indexes=np.frombuffer(blob,dtype='<u2',count=32768,offset=16)
    if int(indexes.max())>=count:raise ValueError('Voxy section palette index is corrupt.')
    palette=np.frombuffer(blob,dtype='<u8',count=count,offset=65552)
    return palette[indexes].reshape(32,32,32),int((meta>>16)&255)

def file_stamp(folder):
    # CURRENT, manifests and WAL identify committed storage changes. SST files
    # are immutable; avoid statting thousands of them on every tile lookup.
    values=[]
    for p in folder.iterdir():
        if p.name=='CURRENT' or p.name.startswith('MANIFEST-') or p.suffix=='.log':
            s=p.stat();values.append((p.name,s.st_size,s.st_mtime_ns))
    return hashlib.sha256(str(sorted(values)).encode()).hexdigest()[:16]

def runtime_for(path,cache,voxy_jar=None,java=None):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    dependency=cache/'rocksdbjni.jar';source=Path(voxy_jar) if voxy_jar else None
    if source is None:
        for parent in [Path(path),*Path(path).parents]:
            mods=parent/'mods'
            if not mods.is_dir():continue
            for p in mods.glob('*voxy*.jar'):
                try:
                    with zipfile.ZipFile(p) as z:
                        if any('rocksdbjni-' in n and n.endswith('.jar') for n in z.namelist()):source=p;break
                except (OSError,zipfile.BadZipFile):continue
            if source:break
    if source:
        with zipfile.ZipFile(source) as z:
            names=[n for n in z.namelist() if 'rocksdbjni-' in n and n.endswith('.jar')]
            if names:data=z.read(names[0])
            elif 'org/rocksdb/RocksDB.class' in z.namelist():data=source.read_bytes()
            else:raise ValueError('That jar has no RocksDB JNI inside - point to the installed Voxy mod jar.')
        digest=hashlib.sha256(data).hexdigest()
        identity=cache/'dependency.sha256'
        if not dependency.exists() or not identity.exists() or identity.read_text()!=digest:
            dependency.write_bytes(data);identity.write_text(digest)
    if not dependency.exists():raise ValueError('RocksDB (bundled in the Voxy mod jar) not found: the Voxy cache must sit inside a game folder whose mods/ holds the Voxy jar, or set [site] voxy_jar in project.toml.')
    if not java:
        from ...util import find_java
        java,_=find_java(17)
    executable=java
    if not executable:raise ValueError('Reading Voxy caches needs Java 17+: install one, or `mcb config set java <path to java>`.')
    bridge=Path(__file__).resolve().parent/'bridge'
    if not (bridge/'AtlasVoxyReader.class').exists():raise ValueError('The Voxy reader bridge (vendor/atlas/bridge/AtlasVoxyReader.class) is missing.')
    return str(executable),str(bridge),str(dependency),str(source) if source else None

class ReadOnlyDB:
    def __init__(self,path,runtime):
        java,bridge,dependency,_=runtime
        self.path=Path(path);self.lock=threading.RLock();self.process=None
        args=[java,'-Xms16m','-Xmx128m','-cp',bridge+os.pathsep+dependency,'AtlasVoxyReader',str(path)]
        self.process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        magic=self.process.stdout.read(4)
        if magic!=b'ATVX':
            error=self.process.stderr.read(5000).decode(errors='replace');self.close()
            raise ValueError('Cannot open the Voxy RocksDB read-only: '+error[-1600:])
        BRIDGES.add(self)

    def read(self,count):
        result=bytearray()
        while len(result)<count:
            part=self.process.stdout.read(count-len(result))
            if not part:raise ValueError('The Voxy reader bridge process stopped.')
            result.extend(part)
        return bytes(result)

    def call(self,command,payload=b''):
        with self.lock:
            if self.process is None:raise ValueError('The Voxy store is closed.')
            self.process.stdin.write(bytes([command])+payload);self.process.stdin.flush()
            size=struct.unpack('>i',self.read(4))[0]
            if size==-2:
                length=struct.unpack('>i',self.read(4))[0];raise ValueError(self.read(length).decode(errors='replace'))
            if size<0 or size>64*1024*1024:raise ValueError('Invalid bridge response')
            return self.read(size)

    def index(self):
        raw=self.call(1);level=struct.unpack_from('>i',raw)[0]
        return level,np.frombuffer(raw[4:],dtype='>u8').astype(np.uint64)

    def mappings(self):
        raw=self.call(3);offset=0;states={0:{'Name':'minecraft:air'}};biomes={}
        while offset<len(raw):
            identity,size=struct.unpack_from('>II',raw,offset);offset+=8
            item=read_nbt(gzip.decompress(raw[offset:offset+size]));offset+=size
            typ,index=identity>>30,identity&0x3fffffff
            if int(item.get('id',-1))!=index:raise ValueError('Voxy block mapping ids are inconsistent.')
            if typ==1:
                s=item['block_state'];states[index]={'Name':str(s['Name']),'Properties':{str(k):str(v) for k,v in s.get('Properties',{}).items()}}
            elif typ==2:biomes[index]=str(item['biome_id'])
        return states,biomes

    def get_many(self,keys):
        if not keys:return []
        raw=self.call(2,struct.pack('>I',len(keys))+b''.join(int(k).to_bytes(8,'big') for k in keys));offset=0;out=[]
        for _ in keys:
            size=struct.unpack_from('>i',raw,offset)[0];offset+=4
            out.append(raw[offset:offset+size] if size>=0 else None)
            if size>=0:offset+=size
        return out

    def close(self):
        with self.lock:
            p=self.process;self.process=None
            if p is None:return
            try:p.stdin.write(b'\0');p.stdin.flush();p.wait(timeout=3)
            except Exception:p.kill();p.wait(timeout=2)
            for f in [p.stdin,p.stdout,p.stderr]:
                try:f.close()
                except OSError:pass

    def __del__(self):
        try:self.close()
        except Exception:pass

class Store:
    def __init__(self,path,runtime):
        self.path=Path(path);self.db=ReadOnlyDB(path,runtime);self.cache=OrderedDict();self.lock=threading.RLock();self.reads=0;self.hits=0
        self.states,self.biomes=self.db.mappings()
        maxid=max(self.states,default=0)
        if maxid>1_000_000:raise ValueError('Unsupported block mapping range')
        self.palette=[self.states.get(i,{'Name':'minecraft:barrier'}) for i in range(maxid+1)]
        self.max_level,self.keys=self.db.index();self.columns={};self.stamp=file_stamp(self.path)
        for key in self.keys:
            level,x,y,z=section_position(int(key));self.columns.setdefault((x,z),[]).append(y)
        for ys in self.columns.values():ys.sort(reverse=True)
        scale=32*(1<<max(0,self.max_level))
        self.bounds=[min((p[0] for p in self.columns),default=0)*scale,min((p[1] for p in self.columns),default=0)*scale,(max((p[0] for p in self.columns),default=0)+1)*scale,(max((p[1] for p in self.columns),default=0)+1)*scale]
        bs=set(self.biomes.values())
        self.label='the_end' if bs and all('end' in b or 'void' in b for b in bs) else 'the_nether' if bs and any(b.endswith(('nether_wastes','crimson_forest','warped_forest','basalt_deltas','soul_sand_valley')) for b in bs) else 'overworld'

    def fetch(self,keys):
        with self.lock:
            missing=[k for k in dict.fromkeys(keys) if k not in self.cache]
            for key,blob in zip(missing,self.db.get_many(missing)):
                self.cache[key]=decode_section(blob,key) if blob else None
                if blob:self.reads+=1
            result=[]
            for key in keys:
                result.append(self.cache.get(key));self.cache.move_to_end(key);self.hits+=key not in missing
            while len(self.cache)>96:self.cache.popitem(last=False)
            return result

    def column(self,level,x,z):
        if level>self.max_level:return []
        delta=self.max_level-level;rootx,rootz=x>>delta,z>>delta
        ys=self.columns.get((rootx,rootz),[])
        if not ys:return []
        parents=[(self.max_level,rootx,y,rootz) for y in ys]
        for current in range(self.max_level,level,-1):
            entries=self.fetch([section_key(*p) for p in parents]);next_nodes=[]
            childx=(x>>(current-1-level))&1;childz=(z>>(current-1-level))&1
            for node,value in zip(parents,entries):
                if value is None:continue
                mask=value[1]
                for childy in (0,1):
                    index=childx|(childz<<1)|(childy<<2)
                    if mask&(1<<index):next_nodes.append((current-1,node[1]*2+childx,node[2]*2+childy,node[3]*2+childz))
            parents=next_nodes
            if not parents:return []
        entries=self.fetch([section_key(*p) for p in parents])
        return sorted([(p[2],v[0]) for p,v in zip(parents,entries) if v is not None],reverse=True)

    def surface(self,level,x,z,ceiling=None):
        height=np.full((32,32),-32768,np.float32);values=np.zeros((32,32),np.uint64);scale=1<<level
        for sy,voxels in self.column(level,x,z):
            ids=(voxels>>np.uint64(27))&np.uint64(0xfffff);occupied=ids!=0
            if ceiling is not None:occupied &= (np.arange(32)+sy*32)[:,None,None]*scale<=ceiling
            valid=occupied.any(axis=0);top=31-np.argmax(occupied[::-1],axis=0)
            mask=valid&(height<-32000);zz,xx=np.indices((32,32))
            height[mask]=(sy*32+top[mask]+1)*scale;values[mask]=voxels[top[mask],zz[mask],xx[mask]]
        return height,values

def discover_stores(path):
    p=Path(path).expanduser().resolve()
    if p.name=='CURRENT':p=p.parent
    if (p/'CURRENT').is_file():return p.parent,[p]
    if (p/'storage/CURRENT').is_file():return p,[p/'storage']
    root=p/'voxy' if (p/'voxy').is_dir() else p
    found=sorted(q.parent for q in root.glob('*/storage/CURRENT'))
    if not found and (root/'saves').is_dir():found=sorted(q.parent for q in root.glob('saves/*/*/storage/CURRENT'))
    if not found:raise ValueError('No Voxy RocksDB found here: give a server cache folder, the .voxy folder, a dimension folder or a storage folder.')
    return root,found

class VoxyWorld:
    kind='voxy'
    def __init__(self,path,cache,voxy_jar=None,java=None):
        self.path,paths=discover_stores(path);self.id=hashlib.sha256(('voxy:'+str(self.path).casefold()).encode()).hexdigest()[:20]
        self.name=self.path.parent.name if self.path.name=='voxy' else self.path.name
        self.version='Voxy 0.2.x';self.errors=[];self.dimensions={};self.bounds={};self.chunks={};self._cache={};self.regions={}
        self.runtime=runtime_for(self.path,Path(cache)/'voxy-runtime',voxy_jar,java)
        try:
            for p in paths:
                store=Store(p,self.runtime);identity='cache:'+p.parent.name
                self.dimensions[identity]=store;self.bounds[identity]=store.bounds
        except Exception:
            self.close();raise
        if not self.dimensions:raise ValueError('The Voxy cache is empty.')
        # Prefer the overworld while preserving the full, stable cache identity.
        self.dimensions=dict(sorted(self.dimensions.items(),key=lambda p:(p[1].label!='overworld',p[0])))
        b=self.bounds[next(iter(self.dimensions))];self.spawn=[int((b[0]+b[2])/2),80,int((b[1]+b[3])/2)]
        first=next(iter(self.dimensions.values()))
        if (0,0) in first.columns:
            hs,_=first.surface(0,0,0)
            points=np.argwhere(hs>-32000)
            if len(points):
                z,x=points[np.argmin(((points-16)**2).sum(axis=1))];self.spawn=[int(x),int(hs[z,x]),int(z)]
        self._update_revision()

    def _update_revision(self):self.revision=hashlib.sha256(str([(d,s.stamp) for d,s in self.dimensions.items()]).encode()).hexdigest()[:16]
    def scan(self):
        # Refresh only on explicit changes, replacing read-only snapshots safely.
        changed=False
        for d,store in list(self.dimensions.items()):
            stamp=file_stamp(store.path)
            if stamp==store.stamp:continue
            fresh=Store(store.path,self.runtime)
            self.dimensions[d]=fresh;self.bounds[d]=fresh.bounds
            # Old bridge may still be used by an active tile request; GC releases it.
            changed=True
        if changed:self._update_revision()
        return changed

    def metadata(self):
        return {'id':self.id,'name':self.name,'path':str(self.path),'version':self.version,'kind':'voxy','spawn':self.spawn,'revision':self.revision,'dimensions':[{'id':d,'name':s.label+' · '+d.split(':')[-1][:6],'chunks':0,'regions':0,'overviewSections':len(s.keys),'maxLod':s.max_level,'bounds':s.bounds} for d,s in self.dimensions.items()],'errors':self.errors[-5:],'voxyJar':self.runtime[3],'java':self.runtime[0],'coverage':'Only cached (visited) areas exist; the rest is empty.'}

    def sample(self,dim,x,z,ceiling=None):
        store=self.dimensions[dim]
        for level in range(store.max_level+1):
            size=1<<level;heights,values=store.surface(level,x//(32*size),z//(32*size),ceiling)
            ix,iz=(x//size)%32,(z//size)%32;y=float(heights[iz,ix])
            if y<-32000:continue
            value=int(values[iz,ix]);state=store.states.get((value>>27)&0xfffff,{'Name':'minecraft:barrier'});bio=store.biomes.get((value>>47)&511,'minecraft:plains')
            return int(y)-1,state,bio
        return None

    def close(self):
        for store in self.dimensions.values():store.db.close()
