"""Resolve the installed client's blockstates, inherited models and face textures."""
from __future__ import annotations
import hashlib, io, json, math, threading, zipfile
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image

NORMALS={'up':(0,1,0),'down':(0,-1,0),'north':(0,0,-1),'south':(0,0,1),'west':(-1,0,0),'east':(1,0,0)}

def face_vertices(direction,a,b):
    x,y,z=a; X,Y,Z=b
    return {
        'up':[(x,Y,Z),(X,Y,Z),(X,Y,z),(x,Y,z)],
        'down':[(x,y,z),(X,y,z),(X,y,Z),(x,y,Z)],
        'north':[(X,y,z),(x,y,z),(x,Y,z),(X,Y,z)],
        'south':[(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)],
        'west':[(x,y,z),(x,y,Z),(x,Y,Z),(x,Y,z)],
        'east':[(X,y,Z),(X,y,z),(X,Y,z),(X,Y,Z)]}[direction]

def rotation(axis,angle):
    a=math.radians(angle); c,s=math.cos(a),math.sin(a)
    if axis=='x':return np.array([[1,0,0],[0,c,-s],[0,s,c]])
    if axis=='z':return np.array([[c,-s,0],[s,c,0],[0,0,1]])
    return np.array([[c,0,s],[0,1,0],[-s,0,c]])

def matches(condition,props):
    if not condition:return True
    if 'OR' in condition:return any(matches(x,props) for x in condition['OR'])
    if 'AND' in condition:return all(matches(x,props) for x in condition['AND'])
    return all(props.get(k,'') in str(v).split('|') for k,v in condition.items())

class Assets:
    def __init__(self,jar,output,pack=None):
        self.jar=Path(jar).resolve(); self.pack=Path(pack).resolve() if pack else None
        self._lock=threading.RLock(); self.sources=[zipfile.ZipFile(self.jar)]
        if self.pack:self.sources.append(zipfile.ZipFile(self.pack))
        self.files={}
        for z in self.sources:
            for name in z.namelist():self.files[name]=z
        if 'assets/minecraft/blockstates/stone.json' not in self.files:raise ValueError('that jar has no vanilla block models (not a Minecraft client jar)')
        signature='models-v8'+''.join(f'{p}:{p.stat().st_mtime_ns}:{p.stat().st_size}' for p in [self.jar]+([self.pack] if self.pack else []))
        self.id=hashlib.sha256(signature.encode()).hexdigest()[:16]
        self.output=Path(output)/self.id; self.output.mkdir(parents=True,exist_ok=True)
        self.tiles={'missingno':0}; self.averages={}; self.alphas={}; self.unsupported=set()
        paths=sorted(p for p in self.files if p.startswith('assets/') and '/textures/block/' in p and p.endswith('.png'))
        size=16; cell=18; cols=64; rows=math.ceil((len(paths)+1)/cols)
        atlas=Image.new('RGBA',(cols*cell,rows*cell))
        missing=Image.new('RGBA',(16,16),'#100f16')
        for x in range(16):
            for y in range(16):
                if (x//8+y//8)%2:missing.putpixel((x,y),(205,55,179,255))
        images=[('missingno',missing)]
        for path in paths:
            namespace=path.split('/')[1]; key=namespace+':'+path.split('/textures/',1)[1][:-4]
            img=Image.open(io.BytesIO(self.read(path))).convert('RGBA')
            # Animation metadata's first frame; frames always share the source's width.
            meta=self.json(path+'.mcmeta',{})
            anim=meta.get('animation',{}); frame=anim.get('frames',[0])[0]
            frame=int(frame.get('index',0) if isinstance(frame,dict) else frame)
            w=img.width; fy=frame*w
            if fy+w>img.height:fy=0
            img=img.crop((0,fy,w,fy+w)).resize((size,size),Image.Resampling.NEAREST)
            self.tiles[key]=len(images); images.append((key,img))
        for idx,(key,img) in enumerate(images):
            x=(idx%cols)*cell+1; y=(idx//cols)*cell+1
            atlas.paste(img,(x,y)); atlas.paste(img.crop((0,0,1,16)),(x-1,y)); atlas.paste(img.crop((15,0,16,16)),(x+16,y))
            atlas.paste(img.crop((0,0,16,1)),(x,y-1)); atlas.paste(img.crop((0,15,16,16)),(x,y+16))
            arr=np.array(img); valid=arr[:,:,3]>40
            self.averages[idx]=(arr[:,:,:3][valid].mean(axis=0)/255).tolist() if valid.any() else [.2,.2,.2]
            self.alphas[idx]=bool((arr[:,:,3]==255).all())
        self.width,self.height=atlas.size
        self.atlas_path=self.output/'atlas.png'
        if not self.atlas_path.is_file():atlas.save(self.atlas_path)
        self.colormaps={}
        for typ in ['grass','foliage']:
            p=f'assets/minecraft/textures/colormap/{typ}.png'
            if p in self.files:self.colormaps[typ]=np.array(Image.open(io.BytesIO(self.read(p))).convert('RGB'))/255

    def read(self,path):
        with self._lock:return self.files[path].read(path)

    def json(self,path,default=None):
        try:return json.loads(self.read(path))
        except (KeyError,ValueError):return default if default is not None else {}

    @lru_cache(maxsize=8192)
    def model(self,name):
        ns,loc=name.split(':',1) if ':' in name else ('minecraft',name)
        own=self.json(f'assets/{ns}/models/{loc}.json')
        parent=own.get('parent','')
        base=self.model(parent) if parent and not parent.startswith('builtin/') else {}
        return {**base,**own,'textures':{**base.get('textures',{}),**own.get('textures',{})}}

    def tile(self,texture,textures):
        seen=set()
        while texture.startswith('#') and texture not in seen:
            seen.add(texture); texture=textures.get(texture[1:],'missingno')
        if ':' not in texture:texture='minecraft:'+texture
        return self.tiles.get(texture,0)

    def faces(self,state):
        return self._faces(state['Name'],tuple(sorted(state.get('Properties',{}).items())))

    @lru_cache(maxsize=16384)
    def _faces(self,name,properties):
        props=dict(properties); ns,block=name.split(':',1) if ':' in name else ('minecraft',name)
        bs=self.json(f'assets/{ns}/blockstates/{block}.json'); applies=[]
        for variant,model in bs.get('variants',{}).items():
            cond=dict(p.split('=',1) for p in variant.split(',') if '=' in p)
            if matches(cond,props):applies.append(model);break
        for part in bs.get('multipart',[]):
            if matches(part.get('when',{}),props):applies.append(part['apply'])
        liquid=block in {'water','lava'}
        if liquid:
            texture=f'minecraft:block/{block}_still'
            tile=self.tiles.get(texture,0); h=1 if int(props.get('level','0'))>=8 else .875
            return tuple((np.array(face_vertices(d,(0,0,0),(1,h,1)),np.float32),np.array(n,np.float32),np.array([[0,1],[1,1],[1,0],[0,0]],np.float32),tile,d,block=='water') for d,n in NORMALS.items())
        faces=[]
        for app in applies:
            if isinstance(app,list):app=app[0]
            model=self.model(app.get('model','')); textures=model.get('textures',{})
            transform=rotation('y',-app.get('y',0))@rotation('x',-app.get('x',0))
            for element in model.get('elements',[]):
                a=np.array(element.get('from',[0,0,0]),np.float32)/16
                b=np.array(element.get('to',[16,16,16]),np.float32)/16
                for direction,f in element.get('faces',{}).items():
                    verts=np.array(face_vertices(direction,a,b),np.float32); normal=np.array(NORMALS[direction],np.float32)
                    er=element.get('rotation')
                    if er:
                        mat=rotation(er['axis'],er['angle']); origin=np.array(er.get('origin',[8,8,8]))/16
                        verts=(verts-origin)@mat.T+origin; normal=mat@normal
                        if er.get('rescale'):
                            scale=np.ones(3)/max(.01,math.cos(math.radians(er['angle']))); scale['xyz'.index(er['axis'])]=1
                            verts=(verts-origin)*scale+origin
                    original=verts.copy(); verts=(verts-.5)@transform.T+.5; normal=transform@normal
                    uv=f.get('uv')
                    if uv is None:
                        x,y,z=a*16; X,Y,Z=b*16
                        uv={'up':[x,z,X,Z],'down':[x,16-Z,X,16-z],'north':[16-X,16-Y,16-x,16-y],'south':[x,16-Y,X,16-y],'west':[z,16-Y,Z,16-y],'east':[16-Z,16-Y,16-z,16-y]}[direction]
                    u,v,U,V=np.array(uv,np.float32)/16
                    uv=np.array([[u,V],[U,V],[U,v],[u,v]],np.float32)
                    uv=np.roll(uv,-int(f.get('rotation',0))//90,axis=0)
                    if app.get('uvlock') and not er:
                        # Lock textures to world axes after the blockstate transform.
                        # The common quarter-turn case is solved by matching transformed corners.
                        nn=tuple(np.rint(normal).astype(int)); dest=next((d for d,n in NORMALS.items() if n==nn),direction)
                        standard=np.array(face_vertices(dest,verts.min(axis=0),verts.max(axis=0)))
                        order=[int(np.argmin(np.linalg.norm(standard-p,axis=1))) for p in verts]
                        if len(set(order))==4:uv=uv[order]
                    cull=f.get('cullface')
                    if cull:
                        cn=tuple(np.rint(transform@NORMALS[cull]).astype(int)); cull=next((d for d,n in NORMALS.items() if n==cn),None)
                    tile=self.tile(f.get('texture','missingno'),textures)
                    faces.append((verts.astype(np.float32),normal.astype(np.float32),uv,tile,cull,'tintindex' in f))
        if not faces and block not in {'air','cave_air','void_air','structure_void','light','barrier'}:
            # Special entity renderers (chests, signs) are explicit unsupported markers.
            self.unsupported.add(name)
            tile=self.tiles.get(f'{ns}:block/{block}',0)
            faces=[(np.array(face_vertices(d,(0,0,0),(1,1,1)),np.float32),np.array(n,np.float32),np.array([[0,1],[1,1],[1,0],[0,0]],np.float32),tile,d,False) for d,n in NORMALS.items()]
        return tuple(faces)

    @lru_cache(maxsize=16384)
    def opaque_key(self,name,properties):
        faces=self._faces(name,properties)
        # Exact full cubes can hide a neighbouring cullface; partial models cannot.
        directions=set()
        for f in faces:
            if not self.alphas.get(f[3],False) or not f[4]:continue
            if np.isclose(f[0],np.rint(f[0])).all() and np.isclose(np.ptp(f[0],axis=0).sum(),2):directions.add(f[4])
        return len(directions)==6

    def opaque(self,state):return self.opaque_key(state['Name'],tuple(sorted(state.get('Properties',{}).items())))

    def tint(self,state,biome):
        name=state['Name']; bio=biome.split(':')[-1]
        if name.endswith('water'):
            return {'swamp':(.38,.48,.36),'mangrove_swamp':(.23,.46,.39),'warm_ocean':(.26,.83,.82),'lukewarm_ocean':(.27,.67,.82),'cold_ocean':(.24,.34,.71),'frozen_ocean':(.22,.30,.61)}.get(bio,(.247,.463,.894))
        if name.endswith('redstone_wire'):
            p=int(state.get('Properties',{}).get('power',0)); return (.3+p/22,.02+p/180,.01)
        if name.endswith('spruce_leaves'):return (.38,.60,.38)
        if name.endswith('birch_leaves'):return (.50,.65,.33)
        if bio in ('swamp','mangrove_swamp'):return (.42,.50,.22)
        if bio=='dark_forest' and not name.endswith('leaves'):return (.30,.45,.15)
        climates={'plains':(.8,.4),'forest':(.7,.8),'flower_forest':(.7,.8),'birch_forest':(.6,.6),'dark_forest':(.7,.8),'jungle':(.95,.9),'sparse_jungle':(.95,.8),'savanna':(1.0,0),'desert':(1.0,0),'badlands':(1.0,0),'taiga':(.25,.8),'snowy_plains':(0,.5),'cherry_grove':(.5,.8),'meadow':(.5,.8)}
        t,r=climates.get(bio,(.7,.8)); cmap=self.colormaps.get('foliage' if name.endswith('leaves') or name.endswith('vine') else 'grass')
        if cmap is None:return (.5,.7,.3)
        return tuple(cmap[int((1-r*t)*255),int((1-t)*255)])

    def top(self,state,biome):
        faces=self.faces(state); top=next((f for f in faces if f[1][1]>.9),faces[0] if faces else None)
        if not top:return 0,[.3,.3,.3],1
        tile=top[3]; color=np.array(self.averages[tile])
        if top[5]:color*=self.tint(state,biome)
        return tile,color.tolist(),float(top[0][:,1].max())

    def metadata(self):
        return {'id':self.id,'source':str(self.jar),'pack':str(self.pack) if self.pack else None,'tiles':len(self.tiles),'width':self.width,'height':self.height,'columns':64,'cell':18,'unsupported':sorted(self.unsupported),'atlas':f'/api/atlas/{self.id}.png'}
