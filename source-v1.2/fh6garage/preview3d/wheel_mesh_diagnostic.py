from __future__ import annotations

import json
import struct
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path

BUNDLE_TAG = 0x47727562  # Grub
MESH_TAG = 0x4D657368    # Mesh
NAME_TAG = 0x4E616D65    # Name


class WheelMeshDiagnosticError(RuntimeError):
    pass


@dataclass(frozen=True)
class MeshStructureRecord:
    blob_index: int
    mesh_name: str
    mesh_version: str
    material_groups: tuple[tuple[int, ...], ...]
    primary_material_id: int | None
    rigid_bone_index: int
    lod_flags: int
    lod_min: int
    lod_max: int
    bucket_flags_raw: int
    is_opaque: bool
    is_decal: bool
    is_transparent: bool
    is_shadow: bool
    is_not_shadow: bool
    is_alpha_to_coverage: bool
    bucket_order: int
    skinning_elements_count: int | None
    morph_target_count: int | None
    is_morph_damage: bool | None
    is_32_bit_indices: bool
    topology: int
    index_buffer_index: int
    index_buffer_offset: int
    index_buffer_draw_offset: int
    indexed_vertex_offset: int
    index_count: int
    primitive_count: int
    acmr: float | None
    referenced_vertex_count: int | None
    referenced_vertex_index_count: int | None
    vertex_layout_index: int
    vertex_buffer_count: int
    vertex_buffer_reserved_values: tuple[int, ...]
    morph_data_buffer_index: int | None
    skinning_data_buffer_index: int | None
    constant_buffer_indices: tuple[int, ...]
    source_mesh_index: int | None
    position_scale: tuple[float, float, float, float] | None
    position_translate: tuple[float, float, float, float] | None


def _version_at_least(major: int, minor: int, want_major: int, want_minor: int) -> bool:
    return major > want_major or (major == want_major and minor >= want_minor)


def _need(cursor: int, size: int, end: int, label: str) -> None:
    if size < 0 or cursor < 0 or cursor + size > end:
        raise WheelMeshDiagnosticError(f"{label} is truncated")


def _decode_name(raw: bytes) -> str:
    return raw.rstrip(b"\x00").decode("utf-8", errors="replace")


def _mesh_name(data: bytes, metadata_offset: int, metadata_count: int, blob_index: int) -> str:
    if metadata_count <= 0:
        return ""
    table_end = metadata_offset + metadata_count * 8
    if metadata_offset < 0 or table_end > len(data):
        raise WheelMeshDiagnosticError(f"Mesh blob {blob_index} metadata table is outside the modelbin")
    for metadata_index in range(metadata_count):
        metadata_header = metadata_offset + metadata_index * 8
        metadata_tag, flags, relative = struct.unpack_from("<IHH", data, metadata_header)
        if metadata_tag != NAME_TAG:
            continue
        size = flags >> 4
        name_offset = metadata_header + relative
        if name_offset < 0 or name_offset + size > len(data):
            raise WheelMeshDiagnosticError(f"Mesh blob {blob_index} Name metadata is outside the modelbin")
        return _decode_name(data[name_offset:name_offset + size])
    return ""


def parse_modelbin_mesh_structures(data: bytes) -> list[MeshStructureRecord]:
    """Read MeshBlob structural metadata only; vertex/index payloads are not decoded."""
    if len(data) < 0x14 or struct.unpack_from("<I", data, 0)[0] != BUNDLE_TAG:
        raise WheelMeshDiagnosticError("modelbin is not a supported Grub bundle")

    bundle_major, bundle_minor = int(data[4]), int(data[5])
    modern = _version_at_least(bundle_major, bundle_minor, 1, 1)
    if modern:
        blob_count = struct.unpack_from("<I", data, 0x10)[0]
        headers_start = 0x14
    else:
        blob_count = struct.unpack_from("<H", data, 0x06)[0]
        headers_start = 0x10
    if blob_count > 100000 or headers_start + blob_count * 0x18 > len(data):
        raise WheelMeshDiagnosticError("modelbin blob table is outside the file")

    result: list[MeshStructureRecord] = []
    for blob_index in range(blob_count):
        header = headers_start + blob_index * 0x18
        tag = struct.unpack_from("<I", data, header)[0]
        if tag != MESH_TAG:
            continue

        major, minor = int(data[header + 4]), int(data[header + 5])
        metadata_count = struct.unpack_from("<H", data, header + 6)[0]
        metadata_offset, data_offset, compressed_size, uncompressed_size = struct.unpack_from("<IIII", data, header + 8)
        payload_size = int(uncompressed_size or compressed_size)
        end = int(data_offset) + payload_size
        if data_offset < 0 or end > len(data):
            raise WheelMeshDiagnosticError(f"Mesh blob {blob_index} payload is outside the modelbin")
        name = _mesh_name(data, metadata_offset, metadata_count, blob_index)
        cursor = int(data_offset)

        if _version_at_least(major, minor, 1, 13):
            _need(cursor, 4, end, f"Mesh blob {blob_index} material-group count")
            material_group_count = struct.unpack_from("<i", data, cursor)[0]
            cursor += 4
        else:
            material_group_count = 1
        if material_group_count < 0 or material_group_count > 4096:
            raise WheelMeshDiagnosticError(f"Mesh blob {blob_index} has invalid material-group count {material_group_count}")

        groups: list[tuple[int, ...]] = []
        group_width = 4 if _version_at_least(major, minor, 1, 9) else 1
        group_bytes = group_width * 2
        for _ in range(material_group_count):
            _need(cursor, group_bytes, end, f"Mesh blob {blob_index} material group")
            values = struct.unpack_from("<" + "h" * group_width, data, cursor)
            groups.append(tuple(int(v) for v in values))
            cursor += group_bytes
        if groups:
            primary_material_id = groups[0][1] if group_width >= 4 else groups[0][0]
        else:
            primary_material_id = None

        _need(cursor, 2 + 2 + 1 + 1 + 2 + 1, end, f"Mesh blob {blob_index} fixed render header")
        rigid_bone_index = struct.unpack_from("<h", data, cursor)[0]; cursor += 2
        lod_flags = struct.unpack_from("<H", data, cursor)[0]; cursor += 2
        lod_min = data[cursor]; cursor += 1
        lod_max = data[cursor]; cursor += 1
        bucket_flags_raw = struct.unpack_from("<H", data, cursor)[0]; cursor += 2
        bucket_order = data[cursor]; cursor += 1

        skinning_elements_count = None
        morph_target_count = None
        if _version_at_least(major, minor, 1, 2):
            _need(cursor, 1, end, f"Mesh blob {blob_index} skinning count")
            skinning_elements_count = int(data[cursor]); cursor += 1
            if _version_at_least(major, minor, 1, 10):
                _need(cursor, 4, end, f"Mesh blob {blob_index} morph target count")
                morph_target_count = struct.unpack_from("<I", data, cursor)[0]; cursor += 4
            else:
                _need(cursor, 1, end, f"Mesh blob {blob_index} morph target count")
                morph_target_count = int(data[cursor]); cursor += 1

        is_morph_damage = None
        if _version_at_least(major, minor, 1, 3):
            _need(cursor, 1, end, f"Mesh blob {blob_index} damage flag")
            is_morph_damage = bool(data[cursor]); cursor += 1

        _need(cursor, 1 + 2 + 6 * 4, end, f"Mesh blob {blob_index} draw fields")
        is_32_bit_indices = bool(data[cursor]); cursor += 1
        topology = struct.unpack_from("<H", data, cursor)[0]; cursor += 2
        (
            index_buffer_index,
            index_buffer_offset,
            index_buffer_draw_offset,
            indexed_vertex_offset,
            index_count,
            primitive_count,
        ) = struct.unpack_from("<iiiiii", data, cursor)
        cursor += 24

        acmr = None
        referenced_vertex_count = None
        referenced_vertex_index_count = None
        if _version_at_least(major, minor, 1, 6):
            _need(cursor, 8, end, f"Mesh blob {blob_index} ACMR/reference count")
            acmr, referenced_vertex_count = struct.unpack_from("<fI", data, cursor); cursor += 8
        if _version_at_least(major, minor, 1, 11):
            _need(cursor, 4, end, f"Mesh blob {blob_index} referenced-index count")
            referenced_vertex_index_count = struct.unpack_from("<I", data, cursor)[0]; cursor += 4
            if referenced_vertex_index_count > 100000000:
                raise WheelMeshDiagnosticError(f"Mesh blob {blob_index} has implausible referenced-index count")
            skip = int(referenced_vertex_index_count) * 4
            _need(cursor, skip, end, f"Mesh blob {blob_index} referenced-index array")
            cursor += skip

        _need(cursor, 8, end, f"Mesh blob {blob_index} vertex layout/list header")
        vertex_layout_index = struct.unpack_from("<i", data, cursor)[0]; cursor += 4
        vertex_buffer_count = struct.unpack_from("<i", data, cursor)[0]; cursor += 4
        if vertex_buffer_count < 0 or vertex_buffer_count > 4096:
            raise WheelMeshDiagnosticError(f"Mesh blob {blob_index} has invalid vertex-buffer count {vertex_buffer_count}")
        reserved_values: list[int] = []
        for _ in range(vertex_buffer_count):
            entry_size = 20 if _version_at_least(major, minor, 1, 12) else 16
            _need(cursor, entry_size, end, f"Mesh blob {blob_index} vertex-buffer usage")
            if entry_size == 20:
                _, _, _, _, reserved = struct.unpack_from("<iIIII", data, cursor)
                reserved_values.append(int(reserved))
            cursor += entry_size

        morph_data_buffer_index = None
        skinning_data_buffer_index = None
        if _version_at_least(major, minor, 1, 4):
            _need(cursor, 8, end, f"Mesh blob {blob_index} morph/skinning buffer indices")
            morph_data_buffer_index, skinning_data_buffer_index = struct.unpack_from("<ii", data, cursor)
            cursor += 8

        _need(cursor, 4, end, f"Mesh blob {blob_index} constant-buffer count")
        constant_buffer_count = struct.unpack_from("<i", data, cursor)[0]; cursor += 4
        if constant_buffer_count < 0 or constant_buffer_count > 4096:
            raise WheelMeshDiagnosticError(f"Mesh blob {blob_index} has invalid constant-buffer count {constant_buffer_count}")
        _need(cursor, constant_buffer_count * 4, end, f"Mesh blob {blob_index} constant-buffer list")
        constant_buffer_indices = tuple(
            int(v) for v in struct.unpack_from("<" + "i" * constant_buffer_count, data, cursor)
        ) if constant_buffer_count else ()
        cursor += constant_buffer_count * 4

        source_mesh_index = None
        if _version_at_least(major, minor, 1, 1):
            _need(cursor, 4, end, f"Mesh blob {blob_index} source-mesh index")
            source_mesh_index = struct.unpack_from("<I", data, cursor)[0]; cursor += 4

        if _version_at_least(major, minor, 1, 5):
            _need(cursor, 80, end, f"Mesh blob {blob_index} texcoord transforms")
            cursor += 80

        position_scale = None
        position_translate = None
        if _version_at_least(major, minor, 1, 8):
            _need(cursor, 32, end, f"Mesh blob {blob_index} position scale/translate")
            position_scale = tuple(float(v) for v in struct.unpack_from("<ffff", data, cursor)); cursor += 16
            position_translate = tuple(float(v) for v in struct.unpack_from("<ffff", data, cursor)); cursor += 16

        result.append(MeshStructureRecord(
            blob_index=blob_index,
            mesh_name=name,
            mesh_version=f"{major}.{minor}",
            material_groups=tuple(groups),
            primary_material_id=int(primary_material_id) if primary_material_id is not None else None,
            rigid_bone_index=int(rigid_bone_index),
            lod_flags=int(lod_flags),
            lod_min=int(lod_min),
            lod_max=int(lod_max),
            bucket_flags_raw=int(bucket_flags_raw),
            is_opaque=bool(bucket_flags_raw & 0x01),
            is_decal=bool(bucket_flags_raw & 0x02),
            is_transparent=bool(bucket_flags_raw & 0x04),
            is_shadow=bool(bucket_flags_raw & 0x08),
            is_not_shadow=bool(bucket_flags_raw & 0x10),
            is_alpha_to_coverage=bool(bucket_flags_raw & 0x20),
            bucket_order=int(bucket_order),
            skinning_elements_count=skinning_elements_count,
            morph_target_count=int(morph_target_count) if morph_target_count is not None else None,
            is_morph_damage=is_morph_damage,
            is_32_bit_indices=is_32_bit_indices,
            topology=int(topology),
            index_buffer_index=int(index_buffer_index),
            index_buffer_offset=int(index_buffer_offset),
            index_buffer_draw_offset=int(index_buffer_draw_offset),
            indexed_vertex_offset=int(indexed_vertex_offset),
            index_count=int(index_count),
            primitive_count=int(primitive_count),
            acmr=float(acmr) if acmr is not None else None,
            referenced_vertex_count=int(referenced_vertex_count) if referenced_vertex_count is not None else None,
            referenced_vertex_index_count=int(referenced_vertex_index_count) if referenced_vertex_index_count is not None else None,
            vertex_layout_index=int(vertex_layout_index),
            vertex_buffer_count=int(vertex_buffer_count),
            vertex_buffer_reserved_values=tuple(reserved_values),
            morph_data_buffer_index=int(morph_data_buffer_index) if morph_data_buffer_index is not None else None,
            skinning_data_buffer_index=int(skinning_data_buffer_index) if skinning_data_buffer_index is not None else None,
            constant_buffer_indices=constant_buffer_indices,
            source_mesh_index=int(source_mesh_index) if source_mesh_index is not None else None,
            position_scale=position_scale,
            position_translate=position_translate,
        ))
    return result


def _read_glb_document(path: Path) -> dict:
    with path.open("rb") as source:
        header = source.read(12)
        if len(header) != 12 or header[:4] != b"glTF":
            raise WheelMeshDiagnosticError("cached output is not a GLB file")
        version, total = struct.unpack_from("<II", header, 4)
        if version != 2:
            raise WheelMeshDiagnosticError(f"unsupported GLB version {version}")
        consumed = 12
        while consumed + 8 <= total:
            chunk_header = source.read(8)
            if len(chunk_header) != 8:
                break
            length, chunk_type = struct.unpack("<II", chunk_header)
            consumed += 8
            chunk = source.read(length)
            consumed += length
            if len(chunk) != length:
                raise WheelMeshDiagnosticError("GLB JSON chunk is truncated")
            if chunk_type == 0x4E4F534A:
                value = json.loads(chunk.rstrip(b" \x00").decode("utf-8"))
                if not isinstance(value, dict):
                    raise WheelMeshDiagnosticError("GLB JSON root is not an object")
                return value
    raise WheelMeshDiagnosticError("GLB has no JSON document")


def _normalize_part_type(value: object) -> str:
    return str(value or "").casefold().replace(" ", "").replace("-", "").replace("_", "")


def _wheel_glb_entries(document: dict) -> tuple[list[dict], list[str]]:
    primitives: list[dict] = []
    sources: set[str] = set()
    for mesh_index, mesh in enumerate(document.get("meshes") or []):
        if not isinstance(mesh, dict):
            continue
        extras = mesh.get("extras") if isinstance(mesh.get("extras"), dict) else {}
        if _normalize_part_type(extras.get("kfps_part_type")) != "wheelstyle":
            continue
        source_entry = str(extras.get("kfps_source_entry") or "").replace("\\", "/")
        if source_entry:
            sources.add(source_entry)
        primitives.append({
            "mesh_index": mesh_index,
            "mesh_name": str(mesh.get("name") or ""),
            "source_entry": source_entry,
            "material_name": str(extras.get("kfps_material_name") or ""),
            "part_type": str(extras.get("kfps_part_type") or ""),
            "instance_identity": str(extras.get("kfps_instance_identity") or ""),
            "draw_groups": extras.get("kfps_draw_groups"),
            "role": str(extras.get("kfps_role") or ""),
            "neutral_visibility_basis": str(extras.get("kfps_neutral_visibility_basis") or ""),
        })
    return primitives, sorted(sources, key=str.casefold)


def write_wheel_mesh_diagnostic(glb_path: str | Path, converter_archive: str | Path) -> tuple[Path, dict]:
    """Write read-only structural wheel diagnostics beside the cached GLB.

    The converter archive is the LocalAppData near-LOD derivative, not the original game ZIP.
    No game/save file is modified. Names are recorded for diagnostics only and are never used
    to decide production visibility.
    """
    glb = Path(glb_path)
    archive_path = Path(converter_archive)
    document = _read_glb_document(glb)
    glb_primitives, wheel_sources = _wheel_glb_entries(document)

    role_counts: dict[str, int] = {}
    for item in glb_primitives:
        role = str(item.get("role") or "<empty>")
        role_counts[role] = role_counts.get(role, 0) + 1
    hidden_count = int(role_counts.get("hidden", 0))
    structural_hidden_count = sum(
        1 for item in glb_primitives if str(item.get("neutral_visibility_basis") or "")
    )

    modelbins: list[dict] = []
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = {name.replace("\\", "/").casefold(): name for name in archive.namelist()}
        for source_entry in wheel_sources:
            actual = names.get(source_entry.replace("\\", "/").casefold())
            if actual is None:
                modelbins.append({
                    "source_entry": source_entry,
                    "status": "missing_from_converter_archive",
                    "meshes": [],
                })
                continue
            data = archive.read(actual)
            records = parse_modelbin_mesh_structures(data)
            modelbins.append({
                "source_entry": source_entry,
                "status": "parsed",
                "mesh_count": len(records),
                "meshes": [asdict(record) for record in records],
            })

    payload = {
        "format": "fh6_wheel_mesh_structure_diagnostic_v1",
        "purpose": "Structural comparison of WheelStyle meshes; no visibility rule is applied here.",
        "glb": str(glb),
        "converter_archive": str(archive_path),
        "converter_archive_retained": False,
        "wheel_part_type": "WheelStyle",
        "glb_wheel_primitive_count": len(glb_primitives),
        "glb_wheel_visible_primitive_count": len(glb_primitives) - hidden_count,
        "glb_wheel_hidden_primitive_count": hidden_count,
        "glb_wheel_role_counts": role_counts,
        "wheel_source_count": len(wheel_sources),
        "wheel_sources": wheel_sources,
        "glb_wheel_primitives": glb_primitives,
        "modelbins": modelbins,
        "candidate_structural_fields": [
            "lod_flags", "lod_min", "lod_max", "bucket_flags_raw", "is_opaque", "is_decal",
            "is_transparent", "is_shadow", "is_not_shadow", "is_alpha_to_coverage", "bucket_order",
            "rigid_bone_index", "source_mesh_index", "primary_material_id", "material_groups",
            "vertex_layout_index", "vertex_buffer_reserved_values", "constant_buffer_indices",
        ],
        "production_visibility_changed": structural_hidden_count > 0,
        "structural_wheel_motion_primitives_hidden": structural_hidden_count,
        "game_data_modified": False,
        "save_data_modified": False,
    }
    output = glb.with_suffix(".wheel-mesh-diagnostic.json")
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    summary = {
        "path": str(output),
        "wheel_primitives": len(glb_primitives),
        "wheel_sources": len(wheel_sources),
        "parsed_modelbins": sum(1 for item in modelbins if item.get("status") == "parsed"),
        "structural_wheel_motion_primitives_hidden": structural_hidden_count,
    }
    return output, summary
