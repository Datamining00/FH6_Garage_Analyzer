from __future__ import annotations
import json, mmap, struct
from dataclasses import dataclass
from pathlib import Path
import numpy as np

class GlbViewerError(RuntimeError): pass

def normalize_livery_eligibility_policy(value: str | None) -> str:
    key=str(value or 'strict').strip().casefold()
    if key not in {'strict','legacy'}: raise GlbViewerError(f'Unsupported livery eligibility policy {value!r}; expected strict or legacy.')
    return key

def _excluded(extras: dict, cleanup_c: bool) -> bool:
    return str(extras.get('kfps_role') or 'trim').casefold()=='hidden' or bool(extras.get('kfps_neutral_ab_hidden')) or (cleanup_c and bool(extras.get('kfps_neutral_c_candidate')))

@dataclass(frozen=True)
class GlbSceneData:
    positions: np.ndarray; normals: np.ndarray; colors: np.ndarray; uv3: np.ndarray
    allowed_sides: np.ndarray; projection_sides: np.ndarray; direct_uv: np.ndarray; indices: np.ndarray
    projection_minimum: np.ndarray; projection_maximum: np.ndarray; projection_valid: np.ndarray
    bounds_min: np.ndarray; bounds_max: np.ndarray

_DT={5120:np.int8,5121:np.uint8,5122:np.int16,5123:np.uint16,5125:np.uint32,5126:np.float32}
_W={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}

def _read_glb(path: Path):
    try: source=path.open('rb')
    except OSError as exc: raise GlbViewerError(f'Could not open GLB: {exc}') from exc
    try: mapped=mmap.mmap(source.fileno(),0,access=mmap.ACCESS_READ); source.close(); root=memoryview(mapped)
    except (OSError,ValueError): source.close(); root=memoryview(path.read_bytes())
    if len(root)<20 or bytes(root[:4])!=b'glTF': raise GlbViewerError('Not a GLB file.')
    version,total=struct.unpack_from('<II',root,4)
    if version!=2 or total>len(root): raise GlbViewerError('Unsupported or truncated GLB.')
    document=binary=None; offset=12
    while offset+8<=total:
        length,kind=struct.unpack_from('<II',root,offset); offset+=8
        if offset+length>total: raise GlbViewerError('Truncated GLB chunk.')
        chunk=root[offset:offset+length]; offset+=length
        if kind==0x4E4F534A: document=json.loads(bytes(chunk).rstrip(b' \x00').decode('utf-8'))
        elif kind==0x004E4942 and binary is None: binary=chunk
    if not isinstance(document,dict) or binary is None: raise GlbViewerError('GLB has no JSON or BIN chunk.')
    return document,binary

def _acc(doc:dict,binary:memoryview,index:int)->np.ndarray:
    try:
        a=doc['accessors'][index]; v=doc['bufferViews'][a['bufferView']]; dt=_DT[int(a['componentType'])]; width=_W[str(a['type'])]; count=int(a['count'])
    except (KeyError,IndexError,TypeError,ValueError) as exc: raise GlbViewerError(f'Invalid accessor {index}.') from exc
    if a.get('sparse') is not None: raise GlbViewerError('Sparse accessors are unsupported.')
    size=np.dtype(dt).itemsize; elem=size*width; stride=int(v.get('byteStride',elem)); start=int(v.get('byteOffset',0))+int(a.get('byteOffset',0)); end=start+(count-1)*stride+elem if count else start
    if start<0 or end>len(binary): raise GlbViewerError(f'Accessor {index} exceeds BIN chunk.')
    if stride==elem: return np.frombuffer(binary,dtype=dt,count=count*width,offset=start).reshape(count,width).copy()
    return np.ndarray((count,width),dtype=dt,buffer=binary,offset=start,strides=(stride,size)).copy()

def _uv_candidates(doc,binary,attrs,count,channels=None):
    out=[]
    for semantic,index in attrs.items():
        if not isinstance(semantic,str) or not semantic.startswith('TEXCOORD_'): continue
        try:
            ch=int(semantic.split('_',1)[1])
            if channels is not None and ch not in channels: continue
            arr=_acc(doc,binary,int(index)).astype(np.float32,copy=False)
        except Exception: continue
        if arr.shape==(count,2) and np.isfinite(arr).all(): out.append((ch,arr))
    return sorted(out,key=lambda x:x[0])

def _mask_evidence(uv,indices,pages)->int:
    if pages is None: return 0
    pages=np.asarray(pages)
    if pages.shape!=(3,1024,2048,4) or uv.ndim!=2 or uv.shape[1]!=2: return 0
    raw=np.asarray(indices,dtype=np.int64).reshape(-1)
    if len(raw)<3 or len(raw)%3: return 0
    tri=raw.reshape(-1,3)
    if int(tri.max(initial=0))>=len(uv): return 0
    tuv=np.asarray(uv[tri],dtype=np.float64); tuv=tuv[np.isfinite(tuv).all(axis=(1,2))]
    if not len(tuv): return 0
    h,w=pages.shape[1:3]; pixel=np.empty_like(tuv); pixel[:,:,0]=tuv[:,:,0]*0.5*(w-1); pixel[:,:,1]=tuv[:,:,1]*(h-1)
    mn=pixel.min(axis=1); mx=pixel.max(axis=1); pixel=pixel[(mx[:,0]>=0)&(mn[:,0]<=w-1)&(mx[:,1]>=0)&(mn[:,1]<=h-1)]
    if not len(pixel): return 0
    x0=max(0,int(np.floor(pixel[:,:,0].min()))); y0=max(0,int(np.floor(pixel[:,:,1].min()))); x1=min(w-1,int(np.ceil(pixel[:,:,0].max()))); y1=min(h-1,int(np.ceil(pixel[:,:,1].max())))
    if x1<x0 or y1<y0: return 0
    from PIL import Image,ImageDraw
    img=Image.new('1',(x1-x0+1,y1-y0+1),0); draw=ImageDraw.Draw(img)
    for t in pixel:
        pts=[(float(x-x0),float(y-y0)) for x,y in t]; draw.polygon(pts,fill=1,outline=1)
    coverage=np.asarray(img,dtype=bool); bits=0
    for slot in range(11):
        page,ch=divmod(slot,4); section=pages[page,y0:y1+1,x0:x1+1,ch]!=0
        if section.shape==coverage.shape and np.any(section&coverage): bits|=1<<slot
    return bits

def _projection_bounds(reference_by_slot,fallback,livery):
    mn=np.zeros((11,2),np.float32); mx=np.ones((11,2),np.float32); valid=np.zeros(11,np.float32)
    if livery is None: return mn,mx,valid
    for slot in range(11):
        rows=reference_by_slot[slot]; values=np.concatenate(rows,axis=0) if rows else fallback
        if values.ndim!=2 or values.shape[1]!=3 or not len(values): continue
        axis=np.asarray(livery.projection_axes[slot],dtype=np.float64); ax,ay=int(round(axis[0])),int(round(axis[1])); sx,sy=float(axis[2]),float(axis[3])
        if ax not in (0,1,2) or ay not in (0,1,2) or sx==0 or sy==0: continue
        x=values[:,ax]*sx; y=values[:,ay]*sy; finite=np.isfinite(x)&np.isfinite(y)
        if not np.any(finite): continue
        lo=np.array([x[finite].min(),y[finite].min()]); hi=np.array([x[finite].max(),y[finite].max()])
        if np.any(hi<=lo): continue
        mn[slot]=lo; mx[slot]=hi; valid[slot]=1
    return mn,mx,valid

def load_kfps_glb(path:Path|str,livery=None,*,livery_uv_channel:int=3,livery_eligibility:str='strict',neutral_cleanup_c:bool=False,**_ignored)->GlbSceneData:
    if int(livery_uv_channel)!=3: raise GlbViewerError('Assistant 3D preview uses TEXCOORD_3 only.')
    policy=normalize_livery_eligibility_policy(livery_eligibility); doc,binary=_read_glb(Path(path)); meshes=doc.get('meshes') or []
    if not meshes: raise GlbViewerError('GLB contains no meshes.')
    node_extras={}
    for node in doc.get('nodes') or []:
        if isinstance(node,dict) and isinstance(node.get('mesh'),int): node_extras[int(node['mesh'])]=dict(node.get('extras') or {})
    pages=livery.mask_pages if livery is not None else None
    refs=[[] for _ in range(11)]; fallback=[]
    if livery is not None:
        for mi,mesh in enumerate(meshes):
            extras=dict(node_extras.get(mi) or {}); extras.update(mesh.get('extras') or {})
            if _excluded(extras,neutral_cleanup_c): continue
            for primitive in mesh.get('primitives') or []:
                attrs=primitive.get('attributes') or {}
                if 'POSITION' not in attrs: continue
                try:
                    pos=_acc(doc,binary,int(attrs['POSITION'])).astype(np.float32,copy=False); idx=_acc(doc,binary,int(primitive['indices'])).reshape(-1).astype(np.uint32) if 'indices' in primitive else np.arange(len(pos),dtype=np.uint32)
                except Exception: continue
                if pos.ndim!=2 or pos.shape[1]!=3 or not np.isfinite(pos).all(): continue
                fallback.append(pos)
                uv=next((v for ch,v in _uv_candidates(doc,binary,attrs,len(pos),{3}) if ch==3),None)
                if uv is None: continue
                bits=_mask_evidence(uv,idx,pages)
                for slot in range(11):
                    if bits&(1<<slot): refs[slot].append(pos)
    fallback_positions=np.concatenate(fallback,axis=0) if fallback else np.zeros((0,3),np.float32)
    pmin,pmax,pvalid=_projection_bounds(refs,fallback_positions,livery)
    pos_rows=[]; norm_rows=[]; color_rows=[]; uv_rows=[]; allowed_rows=[]; projection_rows=[]; direct_rows=[]; index_rows=[]; vertex_base=0
    role_color={'paint':np.array([.72,.75,.78],np.float32),'glass':np.array([.25,.43,.55],np.float32),'dark':np.array([.1,.11,.12],np.float32),'trim':np.array([.36,.38,.4],np.float32)}
    for mi,mesh in enumerate(meshes):
        extras=dict(node_extras.get(mi) or {}); extras.update(mesh.get('extras') or {})
        if _excluded(extras,neutral_cleanup_c): continue
        if extras.get('kfps_part_option_ids') and extras.get('kfps_stock_part') is not True: continue
        role=str(extras.get('kfps_role') or 'trim').casefold()
        for primitive in mesh.get('primitives') or []:
            if int(primitive.get('mode',4))!=4: continue
            attrs=primitive.get('attributes') or {}
            if 'POSITION' not in attrs: continue
            pos=_acc(doc,binary,int(attrs['POSITION'])).astype(np.float32,copy=False)
            if pos.ndim!=2 or pos.shape[1]!=3 or not len(pos): continue
            if 'NORMAL' in attrs:
                normal=_acc(doc,binary,int(attrs['NORMAL'])).astype(np.float32,copy=False)
                if normal.shape!=pos.shape: normal=np.tile(np.array([[0,1,0]],np.float32),(len(pos),1))
            else: normal=np.tile(np.array([[0,1,0]],np.float32),(len(pos),1))
            idx=_acc(doc,binary,int(primitive['indices'])).reshape(-1).astype(np.uint32) if 'indices' in primitive else np.arange(len(pos),dtype=np.uint32)
            if len(idx)<3 or int(idx.max(initial=0))>=len(pos): continue
            uv=np.zeros((len(pos),2),np.float32); allowed=projection=0; direct=0.0
            if role in {'paint','glass'}:
                default=63 if role=='paint' else 1984
                try: allowed=int(extras.get('kfps_allowed_sides',default))&default
                except Exception: allowed=default
                try: projection=int(extras.get('kfps_projection_sides',0))&default
                except Exception: projection=0
            uv3=next((v for ch,v in _uv_candidates(doc,binary,attrs,len(pos),{3}) if ch==3),None)
            evidence=_mask_evidence(uv3,idx,pages) if uv3 is not None else 0
            if policy=='legacy':
                if evidence: allowed|=evidence
                if (role in {'paint','glass'} or evidence) and uv3 is not None: uv=uv3; direct=1.; projection=0
            else:
                if role not in {'paint','glass'}: allowed=projection=0
                elif uv3 is not None: uv=uv3; direct=1.; projection=0
            if role in {'paint','glass'} and direct==0 and not projection: allowed=0
            color=np.repeat(role_color.get(role,role_color['trim'])[None,:],len(pos),axis=0)
            pos_rows.append(pos); norm_rows.append(normal); color_rows.append(color); uv_rows.append(uv); allowed_rows.append(np.full((len(pos),1),float(allowed),np.float32)); projection_rows.append(np.full((len(pos),1),float(projection),np.float32)); direct_rows.append(np.full((len(pos),1),direct,np.float32)); index_rows.append(idx+np.uint32(vertex_base)); vertex_base+=len(pos)
    if not pos_rows: raise GlbViewerError('No visible triangle geometry was found in the GLB.')
    positions=np.ascontiguousarray(np.concatenate(pos_rows),np.float32); normals=np.ascontiguousarray(np.concatenate(norm_rows),np.float32)
    return GlbSceneData(positions,normals,np.ascontiguousarray(np.concatenate(color_rows),np.float32),np.ascontiguousarray(np.concatenate(uv_rows),np.float32),np.ascontiguousarray(np.concatenate(allowed_rows),np.float32),np.ascontiguousarray(np.concatenate(projection_rows),np.float32),np.ascontiguousarray(np.concatenate(direct_rows),np.float32),np.ascontiguousarray(np.concatenate(index_rows),np.uint32),np.ascontiguousarray(pmin),np.ascontiguousarray(pmax),np.ascontiguousarray(pvalid),positions.min(axis=0),positions.max(axis=0))
