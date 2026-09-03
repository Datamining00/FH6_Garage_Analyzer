from __future__ import annotations
import hashlib, importlib, io, os, shutil, sys, tempfile, urllib.request, zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from PIL import Image
KFPS_COMMIT = "6f53ca3c584d78659d06d4b4a39561db67d79345"
RUNTIME_REVISION = "assistant-3d-v1"
KFPS_ARCHIVE_URL = "https://codeload.github.com/heyitshestia/kloudys-forza-painter-suite/zip/" + KFPS_COMMIT
SECTION_NAMES = ["Front","Back","Top","Left","Right","Spoiler","FrontWindshield","BackWindshield","TopWindow","LeftWindow","RightWindow"]

class KfpsRenderError(RuntimeError):
    pass

@dataclass(frozen=True)
class RenderResult:
    source_path: Path
    output_dir: Path
    car_id: int
    layer_count: int
    section_counts: dict[str, int]
    png_paths: dict[str, Path]
    decoder_warnings: list[str]
    canvas_size: tuple[int, int] = (2048, 1024)
    resolution_name: str = 'normal'
    raster_ids: tuple[int, ...] = ()
    raster_skipped_ids: tuple[int, ...] = ()
    raster_skipped_layer_count: int = 0

def _app_root() -> Path:
    local = os.environ.get('LOCALAPPDATA')
    if local:
        return Path(local) / 'FH6 Assistant' / '3d_preview'
    return Path.home() / '.fh6_assistant' / '3d_preview'

def runtime_dir() -> Path:
    return _app_root() / 'third_party' / f'kfps-renderer-{KFPS_COMMIT[:12]}'

def render_cache_root() -> Path:
    return _app_root() / 'livery_sections'

def _apply_decoder_nested_group_patch(root: Path, log: Callable[[str], None] | None=None) -> None:
    path = root / 'tools' / 'cgroup' / 'forza_source_decoder.py'
    if not path.is_file(): raise KfpsRenderError('Pinned decoder source is missing before compatibility patch.')
    text = path.read_text(encoding='utf-8')
    patched = 'if (state.pending_transform or expected_group is True) and may_decode_group'
    if patched in text: return
    original = 'if state.pending_transform and may_decode_group'
    if original not in text: raise KfpsRenderError('Pinned decoder nested-group probe no longer matches the audited source; refusing an unverified runtime rewrite.')
    path.write_text(text.replace(original, patched, 1), encoding='utf-8')
    if log: log('Nested-group compatibility patch active.')

def _apply_decoder_no_skew_cutoff_patch(root: Path, log: Callable[[str], None] | None=None) -> None:
    path = root / 'tools' / 'cgroup' / 'forza_source_decoder.py'
    if not path.is_file(): raise KfpsRenderError('Pinned decoder source is missing before no-skew-cutoff patch.')
    text = path.read_text(encoding='utf-8')
    import re
    patterns = ['and\\s*\\(abs\\(skew\\)\\s*<\\s*[0-9.]+\\s*or\\s*abs\\(sy\\s*\\*\\s*skew\\)\\s*<\\s*[0-9.]+\\)', 'and\\s+abs\\(skew\\)\\s*<\\s*[0-9.]+']
    changed = False
    for pattern in patterns:
        text, count = re.subn(pattern, '', text, count=1)
        if count: changed = True; break
    if not changed and 'and math.isfinite(skew)' not in text: raise KfpsRenderError('Pinned decoder shape validator no longer matches the audited source; refusing an unverified runtime rewrite.')
    path.write_text(text, encoding='utf-8')
    if log: log('No empirical skew cutoff compatibility patch active.')

def _fh6_shape_validator_source(text: str) -> str | None:
    start = text.find('def is_valid_shape_at(')
    if start < 0: return None
    end = text.find('\ndef is_fm8_legacy_shape_at(', start)
    return text[start:end] if end >= 0 else None

def _decoder_no_skew_cutoff_patch_present(root: Path) -> bool:
    path = root / 'tools' / 'cgroup' / 'forza_source_decoder.py'
    try: text = path.read_text(encoding='utf-8')
    except OSError: return False
    validator = _fh6_shape_validator_source(text)
    if validator is None: return False
    import re
    return 'math.isfinite(skew)' in validator and re.search('abs\\(skew\\)\\s*<\\s*[0-9.]|abs\\(sy\\s*\\*\\s*skew\\)\\s*<\\s*[0-9.]', validator) is None

def _decoder_nested_group_patch_present(root: Path) -> bool:
    try: text = (root / 'tools' / 'cgroup' / 'forza_source_decoder.py').read_text(encoding='utf-8')
    except OSError: return False
    return 'if (state.pending_transform or expected_group is True) and may_decode_group' in text

def _apply_raster_inventory_patch(root: Path, log: Callable[[str], None] | None=None) -> None:
    path = root / 'tools' / 'livery' / 'raster_decals.py'
    if not path.is_file(): raise KfpsRenderError('Pinned raster decoder source is missing before inventory patch.')
    text = path.read_text(encoding='utf-8')
    if 'self._members_by_id' in text and '_DECAL_MEMBER_RE' in text: return
    if 'import re\n' not in text: text = text.replace('import io\n', 'import io\nimport re\n', 1)
    anchor = 'class FH6RasterDecalResolver:\n'
    if anchor not in text: raise KfpsRenderError('Pinned raster resolver class no longer matches audited source.')
    text = text.replace(anchor, '_DECAL_MEMBER_RE = re.compile(r"^textures/decal(\\d+)\\.swatchbin$", re.IGNORECASE)\n\n\n' + anchor, 1)
    old_members = '                self._members = {name.casefold(): name for name in bundle.namelist()}\n'
    new_members = '                self._members_by_id: dict[int, str] = {}\n                for name in bundle.namelist():\n                    match = _DECAL_MEMBER_RE.fullmatch(name.replace("\\\\", "/"))\n                    if match is None:\n                        continue\n                    decal_id = int(match.group(1), 10)\n                    if decal_id in self._members_by_id:\n                        raise RasterDecalError(f"The FH6 built-in decal archive contains duplicate numeric ID {decal_id}.")\n                    self._members_by_id[decal_id] = name\n'
    if old_members not in text: raise KfpsRenderError('Pinned raster inventory initialization no longer matches audited source.')
    text = text.replace(old_members, new_members, 1)
    old_lookup = '        candidates = [\n            f"textures/decal{raster_id}.swatchbin",\n            f"textures/decal{raster_id:03d}.swatchbin",\n        ]\n        member = next((self._members[name] for name in candidates if name in self._members), "")\n'
    if old_lookup not in text: raise KfpsRenderError('Pinned raster ID lookup no longer matches audited source.')
    path.write_text(text.replace(old_lookup, '        member = self._members_by_id.get(raster_id, "")\n', 1), encoding='utf-8')
    if log: log('Raster inventory patch active: numeric IDs are indexed from actual Decals.zip entries.')

def _raster_inventory_patch_present(root: Path) -> bool:
    try: text = (root / 'tools' / 'livery' / 'raster_decals.py').read_text(encoding='utf-8')
    except OSError: return False
    return '_DECAL_MEMBER_RE' in text and 'self._members_by_id' in text and 'member = self._members_by_id.get(raster_id' in text

def _safe_extract_subset(archive: zipfile.ZipFile, destination: Path) -> None:
    members = archive.infolist()
    if not members: raise KfpsRenderError('Downloaded KFPS source archive is empty.')
    top = members[0].filename.split('/', 1)[0]
    exact = {'json_preview_renderer.py','geometry_json.py','tools/__init__.py','tools/cgroup/__init__.py','tools/cgroup/forza_source_decoder.py','tools/cgroup/shape_identity.py','tools/livery/render_contract.py','tools/livery/vehicle_assets.py','tools/livery/raster_decals.py','tools/fabric-editor/shape-words.json'}
    prefixes = ('kfps_shapes/','tools/fabric-editor/Resources/Vinyls/')
    copied = 0
    for info in members:
        name = info.filename.replace('\\','/'); prefix = top + '/'
        if not name.startswith(prefix): continue
        rel = name[len(prefix):]
        if not rel or (rel not in exact and not any(rel.startswith(p) for p in prefixes)): continue
        target = (destination / rel).resolve()
        if destination.resolve() not in target.parents and target != destination.resolve(): raise KfpsRenderError(f'Unsafe archive member: {rel}')
        if info.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as src, target.open('wb') as dst: shutil.copyfileobj(src,dst)
        copied += 1
    if copied < 8: raise KfpsRenderError('Pinned KFPS archive did not contain the expected renderer files.')

def _runtime_self_test(root: Path) -> None:
    if not _decoder_nested_group_patch_present(root): raise KfpsRenderError('Pinned KFPS decoder nested-group compatibility patch is not active.')
    if not _decoder_no_skew_cutoff_patch_present(root): raise KfpsRenderError('Pinned KFPS no-skew-cutoff patch is not active.')
    if not _raster_inventory_patch_present(root): raise KfpsRenderError('Pinned KFPS raster inventory patch is not active.')
    root_str = str(root)
    if root_str not in sys.path: sys.path.insert(0,root_str)
    try:
        decoder=importlib.import_module('tools.cgroup.forza_source_decoder'); renderer=importlib.import_module('json_preview_renderer'); raster=importlib.import_module('tools.livery.raster_decals'); projection=importlib.import_module('tools.livery.render_contract'); vehicle_assets=importlib.import_module('tools.livery.vehicle_assets')
        required=((decoder,'clivery_to_layers'),(renderer,'render_typecode_layers_canvas'),(raster,'FH6RasterDecalResolver'),(projection,'_projection_pixel_bounds'),(projection,'_projection_axis'),(projection,'_projection_mask_region'),(projection,'_pack_paint_tiles'),(vehicle_assets,'VehicleAsset'))
        missing=[f'{m.__name__}.{n}' for m,n in required if not hasattr(m,n)]
        if missing: raise RuntimeError('missing capability: '+', '.join(missing))
    except Exception as exc: raise KfpsRenderError(f'Pinned KFPS runtime capability self-test failed: {exc}') from exc

def _load_backend(root: Path):
    root_str=str(root)
    if root_str not in sys.path: sys.path.insert(0,root_str)
    try: return (importlib.import_module('tools.cgroup.forza_source_decoder'),importlib.import_module('json_preview_renderer'),importlib.import_module('tools.livery.raster_decals'))
    except Exception as exc: raise KfpsRenderError(f'Could not import the pinned KFPS renderer runtime: {exc}') from exc

def _prepare_raster_layers(json_layers: list[dict], raster_backend, game_folder: str | Path | None, log: Callable[[str], None] | None=None):
    raster_ids=sorted({int(layer.get('raster_id') or 0) for layer in json_layers if layer.get('is_raster_logo') and int(layer.get('raster_id') or 0)>0})
    resolver=None; skipped:set[int]=set(); skip_all=False
    if any(layer.get('is_raster_logo') for layer in json_layers):
        if not game_folder:
            skip_all=True; skipped.update(raster_ids)
            if log: log('No FH6 game folder for raster/logo resources; raster layers will be skipped and rendering will continue.')
        else:
            try: resolver=raster_backend.FH6RasterDecalResolver(game_folder)
            except Exception as exc:
                skip_all=True; skipped.update(raster_ids)
                if log: log(f'Could not open built-in raster decals ({exc}); raster layers will be skipped and rendering will continue.')
            if resolver is not None:
                for raster_id in raster_ids:
                    try:
                        if resolver(raster_id) is None: skipped.add(raster_id)
                    except Exception: skipped.add(raster_id)
                if log and skipped: log('Raster/logo resource absent or undecodable; skipping ID(s) and continuing: '+', '.join(map(str,sorted(skipped))))
    def keep(layer:dict)->bool:
        if not layer.get('is_raster_logo'): return True
        rid=int(layer.get('raster_id') or 0)
        return not skip_all and rid>0 and rid not in skipped and resolver is not None
    render_layers=[layer for layer in json_layers if keep(layer)]
    skipped_count=sum(1 for layer in json_layers if layer.get('is_raster_logo') and not keep(layer))
    return render_layers,resolver,tuple(raster_ids),tuple(sorted(skipped)),skipped_count

def _section_layers(layers:list[dict])->dict[str,list[dict]]:
    result={name:[] for name in SECTION_NAMES}
    for layer in layers:
        name=str(layer.get('source_section') or '')
        if name in result: result[name].append(layer)
    return result

def _decode_livery_sections_boundary_aware(decoder,payload:bytes):
    body,counts,meta=decoder.extract_livery_payload(payload); names=list(decoder.LIVERY_SECTION_NAMES); empty_size=int(decoder.LIVERY_EMPTY_SLOT_SIZE); remnant_size=int(decoder.LIVERY_POPULATED_REMNANT_SIZE); layers=[]; warnings=[]; physical_counts={}; raster_counts={}; logical_deltas={}; pos=0; end=len(body)
    for slot,name in enumerate(names):
        target=int(counts[slot] if slot<len(counts) else 0)
        if target<=0:
            physical_counts[name]=raster_counts[name]=logical_deltas[name]=0; pos=min(end,pos+empty_size); continue
        section_start=pos; section_root=decoder.GroupNode(source='livery_section',offset=pos,section=name); holder=decoder.GroupNode(source='livery_holder'); holder.items.append(section_root); state=decoder.WalkState(stack=[holder,section_root]); reserved_tail=remnant_size
        for later_slot in range(slot+1,len(names)):
            later_target=int(counts[later_slot] if later_slot<len(counts) else 0); reserved_tail += empty_size if later_target<=0 else later_target*32
        walk_limit=max(pos,end-reserved_tail); next_populated=None; empty_between=0
        for later_slot in range(slot+1,len(names)):
            later_target=int(counts[later_slot] if later_slot<len(counts) else 0)
            if later_target>0: next_populated=later_slot; break
            empty_between+=1
        guard=0; ended=False
        while state.decoded_shapes<target and pos<end and guard<end+4096:
            guard+=1; decoder.close_complete_stack(state.stack)
            if len(state.stack)<2: warnings.append(f'{name}: parser stack closed before section boundary'); break
            at_root=state.stack[-1] is section_root
            if at_root and not state.pending_transform and state.decoded_shapes>0:
                if next_populated is not None:
                    candidate_pos=pos+remnant_size+empty_between*empty_size
                    if candidate_pos<end and decoder.valid_markerless_group_at(body,candidate_pos,end,allow_count_one=True,livery=True) is not None: ended=True; break
                elif end-pos<=remnant_size+(len(names)-slot-1)*empty_size: ended=True; break
            if at_root and not state.pending_transform:
                markerless=decoder.valid_markerless_group_at(body,pos,end,allow_count_one=True,livery=True)
                if markerless: pos=decoder.push_markerless_group(body,pos,end,markerless,state,livery=True); continue
            if pos>=walk_limit and next_populated is None: ended=True; break
            next_pos=decoder.walk_step(body,pos,end,state,livery=True,livery_invert_odd_rotation=slot!=2)
            if next_pos<=pos: warnings.append(f'{name}: decoder made no progress at body offset 0x{pos:x}'); break
            pos=next_pos
        decoder.close_complete_stack(state.stack)
        if pos<end and body[pos]==1: decoder.mark_previous_terminal_shape_as_mask(state)
        decoded=decoder.flatten_tree(section_root,layer_start=0,section=name)
        if slot==5:
            for layer in decoded:
                data=layer.get('data') or []
                if len(data)>=5: data[0]=-float(data[0]); data[1]=-float(data[1]); data[4]=decoder.normalize_rotation(float(data[4])+180.0)
        physical=len(decoded); rasters=sum(1 for layer in decoded if layer.get('is_raster_logo')); delta=target-physical; physical_counts[name]=physical; raster_counts[name]=rasters; logical_deltas[name]=delta
        if delta<0: warnings.append(f'{name}: physical decode exceeded stats target by {-delta}')
        elif delta>0 and rasters==0: warnings.append(f'{name}: physical decode is {delta} below stats target without raster/logo records')
        elif delta>0: warnings.append(f'{name}: stats target exceeds physical placements by {delta}; {rasters} raster/logo record(s) present')
        if next_populated is not None and not ended and physical<target: warnings.append(f'{name}: next-section structural boundary was not proven')
        for layer in decoded: layer['section_start']=section_start; layers.append(layer)
        pos=min(end,pos+remnant_size)
    return layers,{'source_kind':'clivery','payload_size':len(payload),'section_counts':dict(zip(names,counts)),'decoded_layers':len(layers),'physical_section_counts':physical_counts,'raster_section_counts':raster_counts,'logical_count_deltas':logical_deltas,'boundary_aware':True,'warnings':warnings,**meta}

def _runtime_complete(root: Path) -> bool:
    required=[root/'json_preview_renderer.py',root/'geometry_json.py',root/'kfps_shapes'/'__init__.py',root/'tools'/'cgroup'/'forza_source_decoder.py',root/'tools'/'cgroup'/'shape_identity.py',root/'tools'/'livery'/'render_contract.py',root/'tools'/'livery'/'vehicle_assets.py',root/'tools'/'livery'/'raster_decals.py',root/'RUNTIME_REVISION.txt',root/'tools'/'fabric-editor'/'shape-words.json',root/'tools'/'fabric-editor'/'Resources'/'Vinyls',root/'PINNED_COMMIT.txt']
    if not all(p.exists() for p in required): return False
    try: return (root/'RUNTIME_REVISION.txt').read_text(encoding='ascii').strip()==RUNTIME_REVISION and _decoder_nested_group_patch_present(root) and _decoder_no_skew_cutoff_patch_present(root) and _raster_inventory_patch_present(root)
    except OSError: return False

def _repair_existing_runtime(root: Path, log: Callable[[str],None]|None=None)->bool:
    core=[root/'json_preview_renderer.py',root/'geometry_json.py',root/'kfps_shapes'/'__init__.py',root/'tools'/'cgroup'/'forza_source_decoder.py',root/'tools'/'cgroup'/'shape_identity.py',root/'tools'/'livery'/'render_contract.py',root/'tools'/'livery'/'vehicle_assets.py',root/'tools'/'livery'/'raster_decals.py',root/'tools'/'fabric-editor'/'shape-words.json',root/'tools'/'fabric-editor'/'Resources'/'Vinyls',root/'PINNED_COMMIT.txt']
    if not root.exists() or not all(p.exists() for p in core): return False
    try:
        if (root/'PINNED_COMMIT.txt').read_text(encoding='ascii').strip()!=KFPS_COMMIT: return False
        init=root/'tools'/'livery'/'__init__.py'; init.write_text('"""Minimal read-only projection runtime package."""\n',encoding='utf-8')
        _apply_decoder_nested_group_patch(root,log); _apply_decoder_no_skew_cutoff_patch(root,log); _apply_raster_inventory_patch(root,log); (root/'RUNTIME_REVISION.txt').write_text(RUNTIME_REVISION+'\n',encoding='ascii')
    except OSError: return False
    return _runtime_complete(root)

def ensure_runtime(log: Callable[[str],None]|None=None)->Path:
    root=runtime_dir()
    if _runtime_complete(root): _runtime_self_test(root); return root
    if _repair_existing_runtime(root,log): _runtime_self_test(root); return root
    if log: log('Downloading pinned KFPS MIT renderer runtime...')
    root.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fh6_assistant_kfps_') as td:
        tmp=Path(td); archive_path=tmp/'kfps.zip'
        try:
            req=urllib.request.Request(KFPS_ARCHIVE_URL,headers={'User-Agent':'FH6-Assistant-3D-Preview/1.0'})
            with urllib.request.urlopen(req,timeout=60) as response, archive_path.open('wb') as out: shutil.copyfileobj(response,out,1024*1024)
        except Exception as exc: raise KfpsRenderError(f'Could not download pinned KFPS renderer runtime: {exc}') from exc
        if archive_path.stat().st_size<100000: raise KfpsRenderError('Downloaded KFPS source archive is unexpectedly small.')
        staging=tmp/'runtime'; staging.mkdir()
        try:
            with zipfile.ZipFile(archive_path) as bundle: _safe_extract_subset(bundle,staging)
        except zipfile.BadZipFile as exc: raise KfpsRenderError('Downloaded KFPS source archive is not a valid ZIP.') from exc
        init=staging/'tools'/'livery'/'__init__.py'; init.parent.mkdir(parents=True,exist_ok=True); init.write_text('"""Minimal read-only projection runtime package."""\n',encoding='utf-8')
        _apply_decoder_nested_group_patch(staging,log); _apply_decoder_no_skew_cutoff_patch(staging,log); _apply_raster_inventory_patch(staging,log)
        (staging/'PINNED_COMMIT.txt').write_text(KFPS_COMMIT+'\n',encoding='ascii'); (staging/'RUNTIME_REVISION.txt').write_text(RUNTIME_REVISION+'\n',encoding='ascii')
        if not _runtime_complete(staging): raise KfpsRenderError('KFPS renderer runtime extraction is incomplete.')
        if root.exists(): shutil.rmtree(root,ignore_errors=True)
        shutil.move(str(staging),str(root))
    _runtime_self_test(root)
    return root

def render_clivery_sections(source: str|Path, *, game_folder: str|Path|None=None, resolution=None, log: Callable[[str],None]|None=None)->RenderResult:
    source_path=Path(source)
    if not source_path.is_file(): raise KfpsRenderError('C_livery file does not exist.')
    canvas_w,canvas_h=2048,1024
    root=ensure_runtime(log); decoder,renderer,raster_backend=_load_backend(root)
    try:
        payload=decoder.unwrap_forza_container(source_path)
        if len(payload)<26 or payload[:4]!=b'vlrc': raise KfpsRenderError('The selected source is not an FH6 C_livery payload.')
        layers,report=decoder.clivery_to_layers(payload); warnings=list((report or {}).get('warnings') or []); has_raster=any(layer.get('is_raster_logo') for layer in layers)
        if has_raster and any('stats target' in str(w) for w in warnings):
            boundary_layers,boundary_report=_decode_livery_sections_boundary_aware(decoder,payload)
            if len(boundary_layers)>=len(layers): layers,report=boundary_layers,boundary_report
        json_layers,identity_warnings=decoder.layers_to_kfps_json_layers(layers,game='fh6')
    except KfpsRenderError: raise
    except Exception as exc: raise KfpsRenderError(f'KFPS C_livery decode failed: {exc}') from exc
    car_id=int.from_bytes(payload[16:20],'little'); digest=hashlib.sha256(source_path.read_bytes()).hexdigest()[:16]; out_dir=render_cache_root()/f'car_{car_id}'/f'{digest}_normal'; out_dir.mkdir(parents=True,exist_ok=True)
    render_layers,resolver,raster_ids,skipped_ids,skipped_count=_prepare_raster_layers(json_layers,raster_backend,game_folder,log); by_section=_section_layers(render_layers); png_paths={}; section_counts={}
    for section in SECTION_NAMES:
        current=by_section[section]; section_counts[section]=len(current); path=out_dir/f'{section}.png'
        if current:
            try: png=renderer.render_typecode_layers_canvas(current,width=canvas_w,height=canvas_h,transparent_background=True,strict_assets=True,raster_resolver=resolver)
            except TypeError: png=renderer.render_typecode_layers_canvas(current,width=canvas_w,height=canvas_h,strict_assets=True,raster_resolver=resolver)
            except Exception as exc: raise KfpsRenderError(f'Could not render {section}: {exc}') from exc
            if not png: raise KfpsRenderError(f'The {section} renderer returned no PNG data.')
        else:
            b=io.BytesIO(); Image.new('RGBA',(canvas_w,canvas_h),(0,0,0,0)).save(b,format='PNG'); png=b.getvalue()
        path.write_bytes(png)
        try:
            with Image.open(path) as image:
                if image.size!=(canvas_w,canvas_h): raise KfpsRenderError(f'{section} output has invalid size {image.size}.')
                image.verify()
        except KfpsRenderError: raise
        except Exception as exc: raise KfpsRenderError(f'{section} output PNG is unreadable: {exc}') from exc
        png_paths[section]=path
    warnings=list((report or {}).get('warnings') or []); warnings.extend(identity_warnings or [])
    return RenderResult(source_path,out_dir,car_id,len(json_layers),section_counts,png_paths,warnings,(canvas_w,canvas_h),'normal',tuple(raster_ids),tuple(skipped_ids),int(skipped_count))
