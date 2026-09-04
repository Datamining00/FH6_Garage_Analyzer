from __future__ import annotations
import hashlib
import json
import os
import re
import struct
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

from .carbin import CarbinStructuralError, parse_fh6_carbin

BUNDLE_TAG = 1198683490
MESH_TAG = 1298494312
NAME_TAG = 1315007845
NORMALIZATION_REVISION = 3
_MODEL_PATH_RE = re.compile(b'game:\\[^\x00]{1,512}?\.modelbin', re.IGNORECASE)
_LOD_SUFFIX_RE = re.compile('_lod(?:s|[0-5])\d*(?:\|.*)?$', re.IGNORECASE)
_SLOD_RE = re.compile('__slod', re.IGNORECASE)

class NearLodNormalizationError(RuntimeError):
    pass

@dataclass(frozen=True)
class MeshLodRecord:
    name: str
    family: str
    lod_flags: int
    lod_offset: int
    blob_index: int

@dataclass(frozen=True)
class NearLodNormalizationReport:
    revision: int
    source_archive: str
    normalized_archive: str
    source_sha256: str
    source_archive_size: int
    source_archive_mtime_ns: int
    carbin_entry: str
    discovered_modelbin_references: int
    resolved_modelbin_references: int
    unresolved_modelbin_references: tuple[str, ...]
    referenced_modelbins: int
    parsed_modelbins: int
    normal_modelbins_patched: int
    mesh_lod_flags_patched: int
    old_selector_near_meshes: int
    normalized_near_meshes: int
    recovered_lod0_specific_meshes: int
    slod_references: int
    slod_supplement_files: int
    slod_supplement_families: tuple[str, ...]
    slod_carbin_paths_rewritten: int
    unparsed_referenced_modelbins: tuple[str, ...]
    game_data_modified: bool = False

def _version_at_least(major: int, minor: int, want_major: int, want_minor: int) -> bool:
    return major > want_major or (major == want_major and minor >= want_minor)

def _decode_name(raw: bytes) -> str:
    raw = raw.rstrip(b'\x00')
    if not raw:
        return ''
    return raw.decode('utf-8', errors='replace')

def mesh_family(name: str) -> str:
    value = (name or '').strip().casefold()
    return _LOD_SUFFIX_RE.sub('', value)

def parse_modelbin_mesh_lods(data: bytes) -> list[MeshLodRecord]:
    if len(data) < 20 or struct.unpack_from('<I', data, 0)[0] != BUNDLE_TAG:
        raise NearLodNormalizationError('modelbin is not a supported Grub bundle')
    bundle_major, bundle_minor = (data[4], data[5])
    modern = _version_at_least(bundle_major, bundle_minor, 1, 1)
    if modern:
        if len(data) < 20:
            raise NearLodNormalizationError('modelbin bundle header is truncated')
        blob_count = struct.unpack_from('<I', data, 16)[0]
        headers_start = 20
    else:
        blob_count = struct.unpack_from('<H', data, 6)[0]
        headers_start = 16
    if blob_count > 100000 or headers_start + blob_count * 24 > len(data):
        raise NearLodNormalizationError('modelbin blob table is outside the file')
    result: list[MeshLodRecord] = []
    for blob_index in range(blob_count):
        header = headers_start + blob_index * 24
        tag = struct.unpack_from('<I', data, header)[0]
        if tag != MESH_TAG:
            continue
        mesh_major = data[header + 4]
        mesh_minor = data[header + 5]
        metadata_count = struct.unpack_from('<H', data, header + 6)[0]
        metadata_offset, data_offset, compressed_size, uncompressed_size = struct.unpack_from('<IIII', data, header + 8)
        payload_size = uncompressed_size or compressed_size
        if data_offset > len(data) or data_offset + payload_size > len(data):
            raise NearLodNormalizationError(f'Mesh blob {blob_index} payload is outside the file')
        if metadata_count and metadata_offset + metadata_count * 8 > len(data):
            raise NearLodNormalizationError(f'Mesh blob {blob_index} metadata is outside the file')
        name = ''
        for metadata_index in range(metadata_count):
            metadata_header = metadata_offset + metadata_index * 8
            metadata_tag, flags, relative = struct.unpack_from('<IHH', data, metadata_header)
            if metadata_tag != NAME_TAG:
                continue
            size = flags >> 4
            name_offset = metadata_header + relative
            if name_offset > len(data) or name_offset + size > len(data):
                raise NearLodNormalizationError(f'Mesh blob {blob_index} Name metadata is outside the file')
            name = _decode_name(data[name_offset:name_offset + size])
            break
        cursor = data_offset
        if _version_at_least(mesh_major, mesh_minor, 1, 13):
            if cursor + 4 > len(data):
                raise NearLodNormalizationError(f'Mesh blob {blob_index} material-group count is truncated')
            material_group_count = struct.unpack_from('<i', data, cursor)[0]
            cursor += 4
        else:
            material_group_count = 1
        if material_group_count < 0 or material_group_count > 4096:
            raise NearLodNormalizationError(f'Mesh blob {blob_index} has invalid material-group count {material_group_count}')
        material_group_bytes = 8 if _version_at_least(mesh_major, mesh_minor, 1, 9) else 2
        cursor += material_group_count * material_group_bytes
        cursor += 2
        if cursor + 2 > data_offset + payload_size or cursor + 2 > len(data):
            raise NearLodNormalizationError(f'Mesh blob {blob_index} LODFlags field is truncated')
        lod_flags = struct.unpack_from('<H', data, cursor)[0]
        result.append(MeshLodRecord(name=name, family=mesh_family(name), lod_flags=lod_flags, lod_offset=cursor, blob_index=blob_index))
    return result

def _patch_modelbin_near_lod(data: bytes) -> tuple[bytes, int, int, int, set[str]]:
    records = parse_modelbin_mesh_lods(data)
    mutable = bytearray(data)
    changed = 0
    old_selected = 0
    conceptual_near = 0
    families: set[str] = set()
    for record in records:
        flags = record.lod_flags
        if flags & 1:
            old_selected += 1
        if flags & 3:
            conceptual_near += 1
            if record.family:
                families.add(record.family)
        if flags & 2 and (not flags & 1):
            struct.pack_into('<H', mutable, record.lod_offset, flags | 1)
            changed += 1
    return (bytes(mutable), changed, old_selected, conceptual_near, families)

def _filter_slod_to_unique_families(data: bytes, allowed_families: set[str]) -> tuple[bytes, int, set[str]]:
    records = parse_modelbin_mesh_lods(data)
    mutable = bytearray(data)
    selected = 0
    selected_families: set[str] = set()
    for record in records:
        flags = record.lod_flags
        near = bool(flags & 3)
        keep = near and bool(record.family) and (record.family in allowed_families)
        new_flags = flags
        if keep:
            new_flags |= 1
            selected += 1
            selected_families.add(record.family)
        else:
            new_flags &= ~1
        if new_flags != flags:
            struct.pack_into('<H', mutable, record.lod_offset, new_flags)
    if allowed_families and (not selected):
        raise NearLodNormalizationError('SLOD supplement had no selectable mesh after structural filtering')
    return (bytes(mutable), selected, selected_families)

def _archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()

def _structural_resource_paths(carbin: bytes) -> tuple[str, ...]:
    try:
        scene = parse_fh6_carbin(carbin)
    except (CarbinStructuralError, ValueError, TypeError):
        return ()
    paths: set[str] = set()

    def add_model(model: object) -> None:
        if not isinstance(model, dict):
            return
        path = model.get('resource_path')
        if not isinstance(path, str):
            return
        normalized = path.replace('\\', '/').strip().casefold()
        if normalized.endswith('.modelbin'):
            paths.add(path.strip())

    for part in scene.get('standard_parts', ()) if isinstance(scene, dict) else ():
        if not isinstance(part, dict):
            continue
        for model in part.get('models', ()):
            add_model(model)
    for part in scene.get('upgradable_parts', ()) if isinstance(scene, dict) else ():
        if not isinstance(part, dict):
            continue
        for upgrade in part.get('upgrades', ()):
            if not isinstance(upgrade, dict):
                continue
            for model in upgrade.get('legacy_models', ()):
                add_model(model)
        for shared in part.get('shared_models', ()):
            if isinstance(shared, dict):
                add_model(shared.get('model'))
    return tuple(sorted(paths, key=str.casefold))

def _resolve_model_path(game_path: str, archive_names: dict[str, str], model_code: str) -> tuple[str, str | None]:
    normalized = str(game_path or '').replace('\\', '/').strip().casefold()
    if not normalized.endswith('.modelbin'):
        return (normalized, None)
    model_marker = f'/{model_code.casefold()}/'
    candidates: list[str] = []
    if normalized in archive_names:
        candidates.append(normalized)
    idx = normalized.find(model_marker)
    if idx >= 0:
        candidates.append(normalized[idx + len(model_marker):].lstrip('/'))
    scene_idx = normalized.find('/scene/')
    if scene_idx >= 0:
        candidates.append(normalized[scene_idx + 1:].lstrip('/'))
    if normalized.startswith('scene/'):
        candidates.append(normalized)
    exact = next((archive_names[c] for c in candidates if c in archive_names), None)
    if exact is None:
        file_name = normalized.rsplit('/', 1)[-1]
        matches = [name for key, name in archive_names.items() if key.rsplit('/', 1)[-1] == file_name]
        if len(matches) == 1:
            exact = matches[0]
    return (normalized, exact)

def _referenced_model_paths(carbin: bytes, archive_names: dict[str, str], model_code: str) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...]]:
    output: dict[str, str] = {}
    discovered: set[str] = set()
    unresolved: set[str] = set()
    for match in _MODEL_PATH_RE.finditer(carbin):
        raw = match.group(0)
        try:
            game_path = raw.decode('ascii')
        except UnicodeDecodeError:
            unresolved.add(raw.decode('ascii', errors='replace'))
            continue
        normalized, exact = _resolve_model_path(game_path, archive_names, model_code)
        if not normalized:
            continue
        discovered.add(normalized)
        if exact is not None:
            output[normalized] = exact
        else:
            unresolved.add(normalized)
    if discovered:
        return (output, tuple(sorted(discovered)), tuple(sorted(unresolved)))

    # Many FH6 scene-v7 carbin files store model paths as ordinary
    # length-prefixed UTF-8 resource_path fields that do not match the
    # legacy raw "game:\\..." byte pattern. Fall back only to paths that
    # the structural carbin parser explicitly decoded; never enumerate all
    # modelbins in the archive as a guessed chassis assembly.
    for game_path in _structural_resource_paths(carbin):
        normalized, exact = _resolve_model_path(game_path, archive_names, model_code)
        if not normalized:
            continue
        discovered.add(normalized)
        if exact is not None:
            output[normalized] = exact
        else:
            unresolved.add(normalized)
    return (output, tuple(sorted(discovered)), tuple(sorted(unresolved)))

def _selected_entry_for_structural_path(game_path: str, selected: set[str], model_code: str) -> str | None:
    normalized = game_path.replace('\\', '/').strip().casefold()
    candidates: list[str] = []
    if normalized in selected:
        candidates.append(normalized)
    marker = f'/{model_code.casefold()}/'
    idx = normalized.find(marker)
    if idx >= 0:
        candidates.append(normalized[idx + len(marker):].lstrip('/'))
    scene_idx = normalized.find('/scene/')
    if scene_idx >= 0:
        candidates.append(normalized[scene_idx + 1:].lstrip('/'))
    if normalized.startswith('scene/'):
        candidates.append(normalized)
    for candidate in candidates:
        if candidate in selected:
            return candidate
    file_name = normalized.rsplit('/', 1)[-1]
    matches = [entry for entry in selected if entry.rsplit('/', 1)[-1] == file_name]
    return matches[0] if len(matches) == 1 else None

def _rewrite_selected_slod_paths(carbin: bytes, selected_entries: set[str], model_code: str) -> tuple[bytes, int, set[str]]:
    if not selected_entries:
        return (carbin, 0, set())
    selected = {entry.replace('\\', '/').casefold() for entry in selected_entries}
    mutable = bytearray(carbin)
    rewritten = 0
    rewritten_entries: set[str] = set()
    for match in list(_MODEL_PATH_RE.finditer(carbin)):
        raw = match.group(0)
        try:
            game_path = raw.decode('ascii')
        except UnicodeDecodeError:
            continue
        normalized = game_path.replace('\\', '/').casefold()
        marker = f'/{model_code.casefold()}/'
        idx = normalized.find(marker)
        rel = normalized[idx + len(marker):].lstrip('/') if idx >= 0 else ''
        if rel not in selected:
            continue
        relative_slod = raw.lower().find(b'__slod')
        if relative_slod < 0:
            continue
        absolute = match.start() + relative_slod
        mutable[absolute:absolute + 6] = b'__nlod'
        rewritten += 1
        rewritten_entries.add(rel)

    # Structural-only resource paths are length-prefixed UTF-8 strings.
    # Rewrite only an explicitly selected parsed path, preserving its byte
    # length (__slod -> __nlod) and leaving unrelated model references intact.
    missing = selected - rewritten_entries
    if missing:
        for game_path in _structural_resource_paths(carbin):
            selected_entry = _selected_entry_for_structural_path(game_path, missing, model_code)
            if selected_entry is None or '__slod' not in game_path.casefold():
                continue
            raw = game_path.encode('utf-8')
            rel_slod = raw.lower().find(b'__slod')
            if rel_slod < 0:
                continue
            needle = struct.pack('<i', len(raw)) + raw
            search_from = 0
            changed_this_path = 0
            while True:
                pos = carbin.find(needle, search_from)
                if pos < 0:
                    break
                absolute = pos + 4 + rel_slod
                mutable[absolute:absolute + 6] = b'__nlod'
                rewritten += 1
                changed_this_path += 1
                search_from = pos + len(needle)
            if changed_this_path:
                rewritten_entries.add(selected_entry)
                missing.discard(selected_entry)
            if not missing:
                break
    return (bytes(mutable), rewritten, rewritten_entries)

def _renamed_slod_entry(name: str) -> str:
    return _SLOD_RE.sub('__NLOD', name, count=1)

def _copy_zipinfo(source: zipfile.ZipInfo, filename: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=filename, date_time=source.date_time)
    info.compress_type = source.compress_type
    info.comment = source.comment
    info.extra = source.extra
    info.create_system = source.create_system
    info.create_version = source.create_version
    info.extract_version = source.extract_version
    info.flag_bits = source.flag_bits
    info.volume = source.volume
    info.internal_attr = source.internal_attr
    info.external_attr = source.external_attr
    return info

def discard_near_lod_archive(path: str | Path) -> None:
    target = Path(path)
    for candidate in (target, target.with_suffix('.json')):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass

def cleanup_near_lod_derivatives(cache_root: str | Path, older_than_seconds: int=24 * 60 * 60) -> int:
    import time
    directory = Path(cache_root).resolve() / 'near_lod_archives'
    if not directory.is_dir():
        return 0
    cutoff_ns = time.time_ns() - max(60, int(older_than_seconds)) * 1000000000
    removed = 0
    for pattern in ('*.zip', '*.json', '*.tmp'):
        for path in directory.glob(pattern):
            try:
                if path.stat().st_mtime_ns >= cutoff_ns:
                    continue
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed

def time_ns_token() -> str:
    import time
    return format(time.time_ns(), 'x')

def prepare_near_lod_archive(source_archive: str | Path, carbin_entry: str, model_code: str, cache_root: str | Path, progress: Callable[[str], None] | None=None) -> tuple[Path, NearLodNormalizationReport]:
    source = Path(source_archive).resolve()
    cache = Path(cache_root).resolve() / 'near_lod_archives'
    cache.mkdir(parents=True, exist_ok=True)
    source_stat = source.stat()
    source_hash = _archive_sha256(source)
    safe_model = ''.join((ch if ch.isalnum() or ch in '-_' else '_' for ch in model_code))
    token = f'{os.getpid()}_{time_ns_token()}'
    output = cache / f'car_{safe_model}_{source_hash[:12]}_r{NORMALIZATION_REVISION}_{token}.zip'
    sidecar = output.with_suffix('.json')
    try:
        if output == source or output.is_relative_to(source.parent):
            raise NearLodNormalizationError('Safety check refused near-LOD normalization because the derived archive overlaps the game-data directory.')
    except AttributeError:
        source_parent = os.path.normcase(str(source.parent)).rstrip('\\/') + os.sep
        if os.path.normcase(str(output)).startswith(source_parent):
            raise NearLodNormalizationError('Safety check refused near-LOD normalization because the derived archive overlaps the game-data directory.')
    if progress:
        progress('M6.23: auditing carbin/modelbin LODFlags from read-only game data...')
    with zipfile.ZipFile(source, 'r') as src:
        names = src.namelist()
        names_cf = {name.replace('\\', '/').casefold(): name for name in names}
        carbin_exact = names_cf.get(carbin_entry.replace('\\', '/').casefold())
        if carbin_exact is None:
            raise NearLodNormalizationError(f'carbin entry not found in archive: {carbin_entry}')
        carbin = src.read(carbin_exact)
        references, discovered_refs, unresolved_refs = _referenced_model_paths(carbin, names_cf, model_code)
        if not discovered_refs:
            raise NearLodNormalizationError('carbin contained no modelbin references; refusing to build an unverified chassis assembly')
        referenced_entries = sorted(set(references.values()), key=str.casefold)
        if not referenced_entries:
            raise NearLodNormalizationError('No carbin modelbin reference could be resolved inside the vehicle archive')
        parsed: dict[str, list[MeshLodRecord]] = {}
        unparsed: list[str] = []
        normal_family_keys: set[tuple[str, str]] = set()
        for entry in referenced_entries:
            if not entry.casefold().endswith('.modelbin'):
                continue
            try:
                records = parse_modelbin_mesh_lods(src.read(entry))
            except (OSError, KeyError, NearLodNormalizationError):
                unparsed.append(entry)
                continue
            parsed[entry] = records
            if '__slod' not in entry.casefold():
                parent = str(Path(entry.replace('\\', '/')).parent).casefold()
                for record in records:
                    if record.lod_flags & 3 and record.family:
                        normal_family_keys.add((parent, record.family))
        if unparsed:
            raise NearLodNormalizationError('Near-LOD normalization could not structurally parse every referenced modelbin; refusing a partial chassis assembly. First unsupported entry: ' + sorted(unparsed, key=str.casefold)[0])
        supplemented: set[tuple[str, str]] = set()
        slod_allowed: dict[str, set[str]] = {}
        slod_refs = [entry for entry in referenced_entries if '__slod' in entry.casefold()]
        for entry in sorted(slod_refs, key=str.casefold):
            records = parsed.get(entry)
            if not records:
                continue
            families = {record.family for record in records if record.lod_flags & 3 and record.family}
            parent = str(Path(entry.replace('\\', '/')).parent).casefold()
            unique = {family for family in families if (parent, family) not in normal_family_keys and (parent, family) not in supplemented}
            if unique:
                slod_allowed[entry] = unique
                supplemented.update(((parent, family) for family in unique))
        selected_slod = set(slod_allowed)
        patched_carbin, rewritten_count, rewritten_entries = _rewrite_selected_slod_paths(carbin, selected_slod, model_code)
        selected_cf = {entry.replace('\\', '/').casefold() for entry in selected_slod}
        if rewritten_entries != selected_cf:
            missing = sorted(selected_cf - rewritten_entries)
            raise NearLodNormalizationError('SLOD supplement path rewrite did not cover every selected modelbin: ' + ', '.join(missing))
        patched_modelbins = 0
        patched_flags = 0
        old_near = 0
        normalized_near = 0
        recovered = 0
        fd, temp_name = tempfile.mkstemp(prefix=output.name + '.', suffix='.tmp', dir=cache)
        os.close(fd)
        temp = Path(temp_name)
        try:
            with zipfile.ZipFile(temp, 'w', allowZip64=True) as dst:
                dst.comment = src.comment
                for info in src.infolist():
                    original_name = info.filename
                    output_name = original_name
                    data = src.read(info)
                    entry_cf = original_name.replace('\\', '/').casefold()
                    if original_name == carbin_exact:
                        data = patched_carbin
                    if original_name in parsed and '__slod' not in entry_cf:
                        patched, changed, old_count, near_count, _ = _patch_modelbin_near_lod(data)
                        old_near += old_count
                        normalized_near += near_count
                        recovered += near_count - old_count
                        if changed:
                            data = patched
                            patched_modelbins += 1
                            patched_flags += changed
                    elif original_name in slod_allowed:
                        data, _, actual = _filter_slod_to_unique_families(data, slod_allowed[original_name])
                        if actual != slod_allowed[original_name]:
                            raise NearLodNormalizationError(f'SLOD family filter mismatch for {original_name}')
                        output_name = _renamed_slod_entry(original_name)
                        if output_name.replace('\\', '/').casefold() in names_cf:
                            raise NearLodNormalizationError(f'SLOD normalized path collides with an existing entry: {output_name}')
                    out_info = _copy_zipinfo(info, output_name)
                    dst.writestr(out_info, data)
            temp.replace(output)
        finally:
            temp.unlink(missing_ok=True)
    report = NearLodNormalizationReport(revision=NORMALIZATION_REVISION, source_archive=str(source), normalized_archive=str(output), source_sha256=source_hash, source_archive_size=source_stat.st_size, source_archive_mtime_ns=source_stat.st_mtime_ns, carbin_entry=carbin_entry, discovered_modelbin_references=len(discovered_refs), resolved_modelbin_references=len(references), unresolved_modelbin_references=tuple(unresolved_refs), referenced_modelbins=len(referenced_entries), parsed_modelbins=len(parsed), normal_modelbins_patched=patched_modelbins, mesh_lod_flags_patched=patched_flags, old_selector_near_meshes=old_near, normalized_near_meshes=normalized_near, recovered_lod0_specific_meshes=recovered, slod_references=len(slod_refs), slod_supplement_files=len(slod_allowed), slod_supplement_families=tuple(sorted((f'{parent}|{family}' for parent, family in supplemented))), slod_carbin_paths_rewritten=rewritten_count, unparsed_referenced_modelbins=tuple(sorted(unparsed, key=str.casefold)), game_data_modified=False)
    sidecar.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding='utf-8')
    if progress:
        progress(f'M6.23 near-LOD normalization PASS: {patched_flags} LOD0-specific mesh flag(s) exposed to the pinned converter; {len(supplemented)} directory-scoped SLOD family supplement(s).')
    return (output, report)
