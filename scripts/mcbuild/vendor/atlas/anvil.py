"""Read-only Java Anvil reader. File handles never survive a chunk read."""
from __future__ import annotations
import gzip, hashlib, io, math, re, struct, threading, zlib
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from ... import nbt as _nbt

AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air", "minecraft:structure_void"}
REGION = re.compile(r"r\.(-?\d+)\.(-?\d+)\.mca$")

def read_nbt(data: bytes):
    """Root compound of an (optionally gzip/zlib-compressed) NBT blob, using the kit's own reader."""
    return _nbt.loads(data)[0]

def unpack(data, count, bits, padded=True):
    """Unsigned vectorized decoding also handles negative NBT LongArray entries."""
    if data is None or len(data) == 0:
        return np.zeros(count, dtype=np.uint16)
    words = np.asarray(data, dtype=np.int64).astype(np.uint64)
    indexes = np.arange(count, dtype=np.uint64)
    if padded:
        per = 64 // bits
        return ((words[(indexes // np.uint64(per)).astype(np.intp)] >>
                 ((indexes % np.uint64(per)) * np.uint64(bits))) & np.uint64((1 << bits)-1)).astype(np.uint16)
    bit = indexes * np.uint64(bits)
    wi, shift = (bit // np.uint64(64)).astype(np.intp), bit % np.uint64(64)
    out = words[wi] >> shift
    cross = shift + np.uint64(bits) > 64
    out[cross] |= words[wi[cross]+1] << (np.uint64(64)-shift[cross])
    return (out & np.uint64((1 << bits)-1)).astype(np.uint16)

def lz4_java(data):
    import lz4.block
    out = bytearray(); offset = 0
    while offset < len(data):
        if data[offset:offset+8] != b'LZ4Block':
            raise ValueError('Invalid Minecraft LZ4 block header')
        token, compressed, size, _checksum = struct.unpack_from('<BIII', data, offset+8)
        offset += 21
        if size == compressed == 0: break
        if size > 32 * 1024 * 1024 or compressed > len(data)-offset:
            raise ValueError('Invalid LZ4 block length')
        block = data[offset:offset+compressed]; offset += compressed
        out.extend(block if token & 0xf0 == 0x10 else lz4.block.decompress(block, uncompressed_size=size))
        if len(out) > 64 * 1024 * 1024: raise ValueError('Oversized chunk')
    return bytes(out)

@dataclass
class Chunk:
    blocks: np.ndarray
    states: list
    y0: int
    biomes: dict
    surface: np.ndarray
    ground: np.ndarray

def decode_chunk(nbt) -> Chunk:
    root = nbt.get('Level', nbt)
    version = int(nbt.get('DataVersion', 0))
    sections = root.get('sections', root.get('Sections', []))
    usable = [s for s in sections if 'block_states' in s or 'Palette' in s]
    if not usable:
        if any('Blocks' in s for s in sections):
            raise ValueError('Worlds from 1.12 or older (numeric block ids) are not supported: open a copy in a newer Minecraft first.')
        return Chunk(np.zeros((16,16,16),np.uint16), [{'Name':'minecraft:air'}], 0, {}, np.full((16,16),-1),np.full((16,16),-1))
    y0 = min(int(s['Y']) for s in usable)*16
    y1 = (max(int(s['Y']) for s in usable)+1)*16
    if y1-y0 > 4096: raise ValueError('Unsupported dimension height')
    blocks = np.zeros((y1-y0,16,16),np.uint16)
    states=[{'Name':'minecraft:air'}]; ids={'minecraft:air':0}; biomes={}
    for sec in usable:
        sy=int(sec['Y']); state=sec.get('block_states',{})
        palette=state.get('palette',sec.get('Palette',[]))
        table=[]
        for entry in palette:
            name=str(entry['Name']); props={str(k):str(v) for k,v in entry.get('Properties',{}).items()}
            key=name+str(sorted(props.items()))
            if name in AIR: table.append(0); continue
            if key not in ids:
                ids[key]=len(states); states.append({'Name':name,'Properties':props})
            table.append(ids[key])
        if not table: continue
        data=state.get('data',sec.get('BlockStates'))
        index=unpack(data,4096,max(4,(len(table)-1).bit_length()),version>=2529)
        if index.max(initial=0)>=len(table): raise ValueError('Corrupt block palette')
        slab=np.asarray(table,np.uint16)[index].reshape(16,16,16)
        blocks[sy*16-y0:sy*16-y0+16]=slab
        bio=sec.get('biomes')
        if bio:
            bp=[str(v) for v in bio.get('palette',[])]; bd=bio.get('data')
            if bp:
                bi=unpack(bd,64,max(1,(len(bp)-1).bit_length()))
                biomes[sy]=(bp,bi.reshape(4,4,4))
    occupied=blocks!=0
    surface=np.where(occupied.any(axis=0),len(blocks)-1-np.argmax(occupied[::-1],axis=0),-1)
    nonground=np.array([s['Name'].endswith(('_leaves','_log','_wood')) or s['Name'] in {'minecraft:water','minecraft:lava','minecraft:short_grass','minecraft:tall_grass','minecraft:fern','minecraft:large_fern','minecraft:vine','minecraft:snow'} for s in states])
    solid=occupied & ~nonground[blocks]
    ground=np.where(solid.any(axis=0),len(blocks)-1-np.argmax(solid[::-1],axis=0),surface)
    return Chunk(blocks,states,y0,biomes,surface,ground)

class World:
    """A save folder (with level.dat), or a bare folder of region files (r.X.Z.mca, e.g. a Bobby chunk cache or a
    region backup from a server) which is read as the overworld."""
    def __init__(self,path):
        self.path=Path(path).expanduser().resolve()
        if not (self.path/'level.dat').is_file():
            for folder in (self.path,self.path/'region'):
                if any(folder.glob('r.*.*.mca')):
                    self.name=self.path.name;self.version='unknown';self.data_version=0;self.spawn=[0,64,0]
                    self.id=hashlib.sha256(str(self.path).casefold().encode()).hexdigest()[:20]
                    self.dimensions={'overworld':folder}
                    self.regions={};self.chunks={};self.bounds={};self._cache=OrderedDict();self._lock=threading.RLock()
                    self.errors=[];self.revision='';self.scan()
                    return
            raise ValueError(f'Not a Java Edition world folder (no level.dat) and no region files (r.X.Z.mca): {self.path}')
        level=read_nbt(gzip.decompress((self.path/'level.dat').read_bytes())).get('Data',{})
        self.name=str(level.get('LevelName',self.path.name))
        self.version=str(level.get('Version',{}).get('Name','unknown'))
        self.data_version=int(level.get('DataVersion',0))
        if self.data_version and self.data_version<1451: raise ValueError('Only Java Edition 1.13+ worlds are supported: open a copy in a newer Minecraft first.')
        sp=level.get('spawn',{})
        pos=sp.get('pos',[level.get('SpawnX',0),level.get('SpawnY',64),level.get('SpawnZ',0)])
        self.spawn=[int(v) for v in pos]
        self.id=hashlib.sha256(str(self.path).casefold().encode()).hexdigest()[:20]
        self.dimensions={'overworld':self.path/'region'}
        for key,folder in [('the_nether','DIM-1'),('the_end','DIM1')]:
            if (self.path/folder/'region').is_dir():self.dimensions[key]=self.path/folder/'region'
        custom=self.path/'dimensions'
        if custom.is_dir():
            for p in custom.glob('**/region'):
                self.dimensions['custom:'+p.parent.relative_to(custom).as_posix()]=p
        self.regions={}; self.chunks={}; self.bounds={}; self._cache=OrderedDict(); self._lock=threading.RLock()
        self.errors=[]; self.revision=''; self.scan()

    def scan(self):
        regions={}; chunks={}; bounds={}; signature=[]
        for dim,folder in self.dimensions.items():
            regions[dim]={}; chunks[dim]=set()
            if not folder.is_dir():continue
            for p in folder.glob('r.*.*.mca'):
                m=REGION.match(p.name)
                if not m:continue
                st=p.stat(); rx,rz=map(int,m.groups())
                stamp=f'{st.st_mtime_ns}-{st.st_size}'
                old=self.regions.get(dim,{}).get((rx,rz))
                if old and old[1]==stamp:header=old[2]
                else:
                    with p.open('rb') as f:header=f.read(8192)
                if len(header)<8192:continue
                regions[dim][(rx,rz)]=(p,stamp,header)
                signature.append(f'{dim}:{rx}:{rz}:{stamp}')
                loc=np.frombuffer(header[:4096],dtype='>u4')
                for idx in np.flatnonzero(loc >> 8):chunks[dim].add((rx*32+int(idx)%32,rz*32+int(idx)//32))
            pts=chunks[dim]
            bounds[dim]=[min(x for x,z in pts)*16,min(z for x,z in pts)*16,(max(x for x,z in pts)+1)*16,(max(z for x,z in pts)+1)*16] if pts else [0,0,16,16]
        rev=hashlib.sha256('|'.join(sorted(signature)).encode()).hexdigest()[:16]
        with self._lock:
            changed=rev!=self.revision
            self.regions,self.chunks,self.bounds=regions,chunks,bounds
            self.revision=rev
            if changed:self._cache.clear()
        return changed

    def metadata(self):
        return {'id':self.id,'name':self.name,'path':str(self.path),'version':self.version,'spawn':self.spawn,'revision':self.revision,'dimensions':[{'id':d,'chunks':len(self.chunks[d]),'regions':len(self.regions[d]),'bounds':self.bounds[d]} for d in self.dimensions],'errors':self.errors[-5:]}

    def chunk_stamp(self,dim,cx,cz):
        reg=self.regions[dim].get((cx//32,cz//32))
        return reg[1] if reg else 'empty'

    def chunk(self,dim,cx,cz):
        if (cx,cz) not in self.chunks.get(dim,set()):return None
        reg=self.regions[dim].get((cx//32,cz//32))
        key=(dim,cx,cz,reg[1])
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key); return self._cache[key]
        path,stamp,header=reg; idx=(cx%32)+(cz%32)*32
        location=int.from_bytes(header[idx*4:idx*4+4],'big'); offset=location>>8
        with path.open('rb') as f:
            f.seek(offset*4096); lead=f.read(5)
            if len(lead)<5:raise ValueError('Truncated chunk')
            length,ctype=struct.unpack('>IB',lead)
            if not 1<=length<=32*1024*1024:raise ValueError('Invalid chunk length')
            if ctype & 128:
                payload=(path.parent/f'c.{cx}.{cz}.mcc').read_bytes(); ctype &=127
            else:payload=f.read(length-1)
        if ctype==1:raw=gzip.decompress(payload)
        elif ctype==2:raw=zlib.decompress(payload)
        elif ctype==3:raw=payload
        elif ctype==4:raw=lz4_java(payload)
        else:raise ValueError(f'Unsupported compression {ctype}')
        result=decode_chunk(read_nbt(raw))
        with self._lock:
            self._cache[key]=result
            while len(self._cache)>48:self._cache.popitem(last=False)
        return result

    def sample(self,dim,x,z,ceiling=None):
        c=self.chunk(dim,math.floor(x/16),math.floor(z/16))
        if c is None:return None
        ix,iz=int(x)%16,int(z)%16
        iy=int(c.surface[iz,ix])
        if ceiling is not None:
            col=c.blocks[:max(0,min(len(c.blocks),ceiling-c.y0+1)),iz,ix]
            nz=np.flatnonzero(col); iy=int(nz[-1]) if len(nz) else -1
        if iy<0:return None
        return c.y0+iy,c.states[int(c.blocks[iy,iz,ix])],self.biome(c,ix,iy+c.y0,iz)

    @staticmethod
    def biome(c,x,y,z):
        b=c.biomes.get(y//16)
        if not b:return 'minecraft:plains'
        p,a=b; i=int(a[(y%16)//4,z//4,x//4]); return p[i] if i<len(p) else p[0]
