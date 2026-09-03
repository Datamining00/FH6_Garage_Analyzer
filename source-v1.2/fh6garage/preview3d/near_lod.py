from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

BUNDLE_TAG = 1198683490
MESH_TAG = 1298494312
NAME_TAG = 1315007845
NORMALIZATION_REVISION = 2
_MODEL_PATH_RE = re.compile(rb"game:\\[^\x00]{1,512}?\.modelbin", re.IGNORECASE)
_LOD_SUFFIX_RE = re.compile(r"_lod(?:s|[0-5])\d*(?:\|.*)?$", re.IGNORECASE)
_SLOD_RE = re.compile(r"__slod", re.IGNORECASE)


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
    raw = raw.rstrip(b"\x00")
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace")


def mesh_family(name: str) -> str:
    value = (name or "").strip().casefold()
    return _LOD_SUFFIX_RE.sub("", value)


def parse_modelbin_mesh_lods(data: bytes) -> list[MeshLodRecord]:
    if len(data) < 20 or struct.unpack_from("<I", data, 0)[0] != BUNDLE_TAG:
        raise NearLodNormalizationError("modelbin is not a supported Grub bundle")
    bundle_major, bundle_minor = data[4], data[5]
    modern = _version_at_least(bundle_major, bundle_minor, 1, 1)
    if modern:
        blob_count = struct.unpack_from("<I", data, 16)[0]
        headers_start = 20
    else:
        blob_count = struct.unpack_from("<H", data, 6)[0]
        headers_start = 16
    if blob_count > 100000 or headers_start + blob_count * 24 > len(data):
        raise NearLodNormalizationError("modelbin blob table is outside the file")

    result: list[MeshLodRecord] = []
    for blob_index in range(blob_count):
        header = headers_start + blob_index * 24
        tag = struct.unpack_from("<I", data, header)[0]
        if tag != MESH_TAG:
            continue
        mesh_major = data[header + 4]
        mesh_minor = data[header + 5]
        metadata_count = struct.unpack_from("<H", data, header + 6)[0]
        metadata_offset, data_offset, compressed_size, uncompressed_size = struct.unpack_from(
            "<IIII", data, header + 8
        )
        payload_size = uncompressed_size or compressed_size
        if data_offset > len(data) or data_offset + payload_size > len(data):
            raise NearLodNormalizationError(f"Mesh blob {blob_index} payload is outside the file")
        if metadata_count and metadata_offset + metadata_count * 8 > len(data):
            raise NearLodNormalizationError(f"Mesh blob {blob_index} metadata is outside the file")

        name = ""
        for metadata_index in range(metadata_count):
            metadata_header = metadata_offset + metadata_index * 8
            metadata_tag, flags, relative = struct.unpack_from("<IHH", data, metadata_header)
            if metadata_tag != NAME_TAG:
                continue
            size = flags >> 4
            name_offset = metadata_header + relative
            if name_offset > len(data) or name_offset + size > len(data):
                raise NearLodNormalizationError(f"Mesh blob {blob_index} Name metadata is outside the file")
            name = _decode_name(data[name_offset : name_offset + size])
            break

        cursor = data_offset
        if _version_at_least(mesh_major, mesh_minor, 1, 13):
            if cursor + 4 > len(data):
                raise NearLodNormalizationError(f"Mesh blob {blob_index} material-group count is truncated")
            material_group_count = struct.unpack_from("<i", data, cursor)[0]
            cursor += 4
        else:
            material_group_count = 1
        if material_group_count < 0 or material_group_count > 4096:
            raise NearLodNormalizationError(
                f"Mesh blob {blob_index} has invalid material-group count {material_group_count}"
            )
        material_group_bytes = 8 if _version_at_least(mesh_major, mesh_minor, 1, 9) else 2
        cursor += material_group_count * material_group_bytes
        cursor += 2
        if cursor + 2 > data_offset + payload_size or cursor + 2 > len(data):
            raise NearLodNormalizationError(f"Mesh blob {blob_index} LODFlags field is truncated")
        lod_flags = struct.unpack_from("<H", data, cursor)[0]
        result.append(
            MeshLodRecord(
                name=name,
                family=mesh_family(name),
                lod_flags=lod_flags,
                lod_offset=cursor,
                blob_index=blob_index,
            )
        )
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
        if flags & 2 and not (flags & 1):
            struct.pack_into("<H", mutable, record.lod_offset, flags | 1)
            changed += 1
    return bytes(mutable), changed, old_selected, conceptual_near, families


def _filter_slod_to_unique_families(data: bytes, allowed_families: set[str]) -> tuple[bytes, int, set[str]]:
    records = parse_modelbin_mesh_lods(data)
    mutable = bytearray(data)
    selected = 0
    selected_families: set[str] = set()
    for record in records:
        flags = record.lod_flags
        near = bool(flags & 3)
        keep = near and bool(record.family) and record.family in allowed_families
        new_flags = flags
        if keep:
            new_flags |= 1
            selected += 1
            selected_families.add(record.family)
        else:
            new_flags &= ~1
        if new_flags != flags:
            struct.pack_into("<H", mutable, record.lod_offset, new_flags)
    if allowed_families and not selected:
        raise NearLodNormalizationError("SLOD supplement had no selectable mesh after structural filtering")
    return bytes(mutable), selected, selected_families


def _referenced_model_paths(
    carbin: bytes,
    archive_names: dict[str, str],
    model_code: str,
) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...]]:
    output: dict[str, str] = {}
    discovered: set[str] = set()
    unresolved: set[str] = set()
    model_marker = f"/{model_code.casefold()}/"
    for match in _MODEL_PATH_RE.finditer(carbin):
        raw = match.group(0)
        try:
            game_path = raw.decode("ascii")
        except UnicodeDecodeError:
            unresolved.add(raw.decode("ascii", errors="replace"))
            continue
        normalized = game_path.replace("\\", "/").casefold()
        discovered.add(normalized)
        candidates: list[str] = []
        idx = normalized.find(model_marker)
        if idx >= 0:
            candidates.append(normalized[idx + len(model_marker) :].lstrip("/"))
        scene_idx = normalized.find("/scene/")
        if scene_idx >= 0:
            candidates.append(normalized[scene_idx + 1 :].lstrip("/"))
        exact = next((archive_names[candidate] for candidate in candidates if candidate in archive_names), None)
        if exact is None:
            file_name = normalized.rsplit("/", 1)[-1]
            matches = [
                name
                for key, name in archive_names.items()
                if key.rsplit("/", 1)[-1] == file_name
            ]
            if len(matches) == 1:
                exact = matches[0]
        if exact is not None:
            output[normalized] = exact
        else:
            unresolved.add(normalized)
    return output, tuple(sorted(discovered)), tuple(sorted(unresolved))


def _rewrite_selected_slod_paths(
    carbin: bytes,
    selected_entries: set[str],
    model_code: str,
) -> tuple[bytes, int, set[str]]:
    if not selected_entries:
        return carbin, 0, set()
    selected = {entry.replace("\\", "/").casefold() for entry in selected_entries}
    mutable = bytearray(carbin)
    rewritten = 0
    rewritten_entries: set[str] = set()
    for match in list(_MODEL_PATH_RE.finditer(carbin)):
        raw = match.group(0)
        try:
            game_path = raw.decode("ascii")
        except UnicodeDecodeError:
            continue
        normalized = game_path.replace("\\", "/").casefold()
        marker = f"/{model_code.casefold()}/"
        idx = normalized.find(marker)
        rel = normalized[idx + len(marker) :].lstrip("/") if idx >= 0 else ""
        if rel not in selected:
            continue
        relative_slod = raw.lower().find(b"__slod")
        if relative_slod < 0:
            continue
        absolute = match.start() + relative_slod
        mutable[absolute : absolute + 6] = b"__nlod"
        rewritten += 1
        rewritten_entries.add(rel)
    return bytes(mutable), rewritten, rewritten_entries


def _renamed_slod_entry(name: str) -> str:
    return _SLOD_RE.sub("__NLOD", name, count=1)


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


def _copy_archive_with_sha256(source: Path, target: Path) -> str:
    """Copy the source archive byte-for-byte while hashing the same read pass."""
    digest = hashlib.sha256()
    with source.open("rb") as src, target.open("wb") as dst:
        while True:
            block = src.read(4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
            dst.write(block)
    return digest.hexdigest()


def _rewrite_copied_zip_entries(
    archive_path: Path,
    replacements: dict[str, tuple[str, bytes]],
) -> None:
    """Replace selected entries without decompressing/recompressing unrelated ZIP members.

    The archive must already be a disposable byte-for-byte copy of the read-only game ZIP.
    Existing local file records for replaced members are left orphaned; the rewritten central
    directory points only at retained originals plus the newly written replacement records.
    """
    if not replacements:
        return
    with zipfile.ZipFile(archive_path, "a", allowZip64=True) as archive:
        original_order = list(archive.filelist)
        original_by_name = {info.filename: info for info in original_order}
        missing = sorted(set(replacements) - set(original_by_name), key=str.casefold)
        if missing:
            raise NearLodNormalizationError(
                "Selective ZIP rewrite could not find replacement source entry: " + missing[0]
            )

        retained = [info for info in original_order if info.filename not in replacements]
        retained_cf = {info.filename.replace("\\", "/").casefold() for info in retained}
        output_cf: set[str] = set()
        for old_name, (new_name, _) in replacements.items():
            normalized = new_name.replace("\\", "/").casefold()
            if normalized in retained_cf or normalized in output_cf:
                raise NearLodNormalizationError(
                    f"Selective ZIP rewrite output path collides with an existing entry: {new_name}"
                )
            output_cf.add(normalized)

        archive.filelist = list(retained)
        archive.NameToInfo = {info.filename: info for info in retained}
        replacement_infos: dict[str, zipfile.ZipInfo] = {}
        for original in original_order:
            replacement = replacements.get(original.filename)
            if replacement is None:
                continue
            output_name, data = replacement
            archive.writestr(_copy_zipinfo(original, output_name), data)
            replacement_infos[original.filename] = archive.NameToInfo[output_name]

        final_order: list[zipfile.ZipInfo] = []
        for original in original_order:
            replacement_info = replacement_infos.get(original.filename)
            final_order.append(replacement_info if replacement_info is not None else original)
        archive.filelist = final_order
        archive.NameToInfo = {info.filename: info for info in final_order}


def discard_near_lod_archive(path: str | Path) -> None:
    target = Path(path)
    for candidate in (target, target.with_suffix(".json")):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_near_lod_derivatives(cache_root: str | Path, older_than_seconds: int = 24 * 60 * 60) -> int:
    import time

    directory = Path(cache_root).resolve() / "near_lod_archives"
    if not directory.is_dir():
        return 0
    cutoff_ns = time.time_ns() - max(60, int(older_than_seconds)) * 1_000_000_000
    removed = 0
    for pattern in ("*.zip", "*.json", "*.tmp"):
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

    return format(time.time_ns(), "x")


def prepare_near_lod_archive(
    source_archive: str | Path,
    carbin_entry: str,
    model_code: str,
    cache_root: str | Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, NearLodNormalizationReport]:
    source = Path(source_archive).resolve()
    cache = Path(cache_root).resolve() / "near_lod_archives"
    cache.mkdir(parents=True, exist_ok=True)
    source_stat = source.stat()
    safe_model = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in model_code)
    source_identity = hashlib.sha256(
        f"{source}|{source_stat.st_size}|{source_stat.st_mtime_ns}|{carbin_entry}|{model_code}|r{NORMALIZATION_REVISION}".encode(
            "utf-8", errors="surrogatepass"
        )
    ).hexdigest()[:12]
    token = f"{os.getpid()}_{time_ns_token()}"
    output = cache / f"car_{safe_model}_{source_identity}_r{NORMALIZATION_REVISION}_{token}.zip"
    sidecar = output.with_suffix(".json")

    try:
        if output == source or output.is_relative_to(source.parent):
            raise NearLodNormalizationError(
                "Safety check refused near-LOD normalization because the derived archive overlaps the game-data directory."
            )
    except AttributeError:
        source_parent = os.path.normcase(str(source.parent)).rstrip("\\/") + os.sep
        if os.path.normcase(str(output)).startswith(source_parent):
            raise NearLodNormalizationError(
                "Safety check refused near-LOD normalization because the derived archive overlaps the game-data directory."
            )

    if progress:
        progress("M6.23: auditing carbin/modelbin LODFlags from read-only game data...")

    replacements: dict[str, tuple[str, bytes]] = {}
    with zipfile.ZipFile(source, "r") as src:
        infos = src.infolist()
        names = [info.filename for info in infos]
        names_cf = {name.replace("\\", "/").casefold(): name for name in names}
        carbin_exact = names_cf.get(carbin_entry.replace("\\", "/").casefold())
        if carbin_exact is None:
            raise NearLodNormalizationError(f"carbin entry not found in archive: {carbin_entry}")

        carbin = src.read(carbin_exact)
        references, discovered_refs, unresolved_refs = _referenced_model_paths(carbin, names_cf, model_code)
        if not discovered_refs:
            raise NearLodNormalizationError(
                "carbin contained no modelbin references; refusing to build an unverified chassis assembly"
            )
        referenced_entries = sorted(set(references.values()), key=str.casefold)
        if not referenced_entries:
            raise NearLodNormalizationError(
                "No carbin modelbin reference could be resolved inside the vehicle archive"
            )

        parsed: dict[str, list[MeshLodRecord]] = {}
        unparsed: list[str] = []
        normal_family_keys: set[tuple[str, str]] = set()
        for entry in referenced_entries:
            if not entry.casefold().endswith(".modelbin"):
                continue
            try:
                records = parse_modelbin_mesh_lods(src.read(entry))
            except (OSError, KeyError, NearLodNormalizationError):
                unparsed.append(entry)
                continue
            parsed[entry] = records
            if "__slod" not in entry.casefold():
                parent = str(Path(entry.replace("\\", "/")).parent).casefold()
                for record in records:
                    if record.lod_flags & 3 and record.family:
                        normal_family_keys.add((parent, record.family))

        if unparsed:
            raise NearLodNormalizationError(
                "Near-LOD normalization could not structurally parse every referenced modelbin; "
                "refusing a partial chassis assembly. First unsupported entry: "
                + sorted(unparsed, key=str.casefold)[0]
            )

        supplemented: set[tuple[str, str]] = set()
        slod_allowed: dict[str, set[str]] = {}
        slod_refs = [entry for entry in referenced_entries if "__slod" in entry.casefold()]
        for entry in sorted(slod_refs, key=str.casefold):
            records = parsed.get(entry)
            if not records:
                continue
            families = {record.family for record in records if record.lod_flags & 3 and record.family}
            parent = str(Path(entry.replace("\\", "/")).parent).casefold()
            unique = {
                family
                for family in families
                if (parent, family) not in normal_family_keys and (parent, family) not in supplemented
            }
            if unique:
                slod_allowed[entry] = unique
                supplemented.update((parent, family) for family in unique)

        selected_slod = set(slod_allowed)
        patched_carbin, rewritten_count, rewritten_entries = _rewrite_selected_slod_paths(
            carbin, selected_slod, model_code
        )
        selected_cf = {entry.replace("\\", "/").casefold() for entry in selected_slod}
        if rewritten_entries != selected_cf:
            missing = sorted(selected_cf - rewritten_entries)
            raise NearLodNormalizationError(
                "SLOD supplement path rewrite did not cover every selected modelbin: " + ", ".join(missing)
            )
        if patched_carbin != carbin:
            replacements[carbin_exact] = (carbin_exact, patched_carbin)

        patched_modelbins = 0
        patched_flags = 0
        old_near = 0
        normalized_near = 0
        recovered = 0

        for entry, records in parsed.items():
            if "__slod" in entry.casefold():
                continue
            old_count = sum(1 for record in records if record.lod_flags & 1)
            near_count = sum(1 for record in records if record.lod_flags & 3)
            expected_changes = sum(1 for record in records if record.lod_flags & 2 and not (record.lod_flags & 1))
            old_near += old_count
            normalized_near += near_count
            recovered += near_count - old_count
            if not expected_changes:
                continue
            patched, changed, verify_old, verify_near, _ = _patch_modelbin_near_lod(src.read(entry))
            if changed != expected_changes or verify_old != old_count or verify_near != near_count:
                raise NearLodNormalizationError(f"Near-LOD patch accounting mismatch for {entry}")
            replacements[entry] = (entry, patched)
            patched_modelbins += 1
            patched_flags += changed

        for entry, allowed in slod_allowed.items():
            data, _, actual = _filter_slod_to_unique_families(src.read(entry), allowed)
            if actual != allowed:
                raise NearLodNormalizationError(f"SLOD family filter mismatch for {entry}")
            output_name = _renamed_slod_entry(entry)
            if output_name.replace("\\", "/").casefold() in names_cf:
                raise NearLodNormalizationError(
                    f"SLOD normalized path collides with an existing entry: {output_name}"
                )
            replacements[entry] = (output_name, data)

    if progress:
        progress(
            f"M6.23: Near-LOD 파생 ZIP 빠른 준비 중... 변경 entry {len(replacements)}개만 재작성합니다."
        )

    fd, temp_name = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=cache)
    os.close(fd)
    temp = Path(temp_name)
    try:
        source_hash = _copy_archive_with_sha256(source, temp)
        _rewrite_copied_zip_entries(temp, replacements)
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)

    report = NearLodNormalizationReport(
        revision=NORMALIZATION_REVISION,
        source_archive=str(source),
        normalized_archive=str(output),
        source_sha256=source_hash,
        source_archive_size=source_stat.st_size,
        source_archive_mtime_ns=source_stat.st_mtime_ns,
        carbin_entry=carbin_entry,
        discovered_modelbin_references=len(discovered_refs),
        resolved_modelbin_references=len(references),
        unresolved_modelbin_references=tuple(unresolved_refs),
        referenced_modelbins=len(referenced_entries),
        parsed_modelbins=len(parsed),
        normal_modelbins_patched=patched_modelbins,
        mesh_lod_flags_patched=patched_flags,
        old_selector_near_meshes=old_near,
        normalized_near_meshes=normalized_near,
        recovered_lod0_specific_meshes=recovered,
        slod_references=len(slod_refs),
        slod_supplement_files=len(slod_allowed),
        slod_supplement_families=tuple(
            sorted(f"{parent}|{family}" for parent, family in supplemented)
        ),
        slod_carbin_paths_rewritten=rewritten_count,
        unparsed_referenced_modelbins=tuple(sorted(unparsed, key=str.casefold)),
        game_data_modified=False,
    )
    sidecar.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    if progress:
        progress(
            f"M6.23 near-LOD normalization PASS: {patched_flags} LOD0-specific mesh flag(s) exposed; "
            f"{len(supplemented)} SLOD family supplement(s); {len(replacements)} ZIP entry rewrite(s)."
        )
    return output, report
