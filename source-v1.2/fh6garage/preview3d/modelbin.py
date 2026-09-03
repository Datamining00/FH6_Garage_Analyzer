from __future__ import annotations
import struct
from dataclasses import dataclass
BUNDLE_TAG = 1198683490
MESH_TAG = 1298494312
NAME_TAG = 1315007845

class ModelbinStructureError(RuntimeError):
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
        raise ModelbinStructureError(f'{label} is truncated')

def _decode_name(raw: bytes) -> str:
    return raw.rstrip(b'\x00').decode('utf-8', errors='replace')

def _mesh_name(data: bytes, metadata_offset: int, metadata_count: int, blob_index: int) -> str:
    if metadata_count <= 0:
        return ''
    table_end = metadata_offset + metadata_count * 8
    if metadata_offset < 0 or table_end > len(data):
        raise ModelbinStructureError(f'Mesh blob {blob_index} metadata table is outside the modelbin')
    for metadata_index in range(metadata_count):
        metadata_header = metadata_offset + metadata_index * 8
        metadata_tag, flags, relative = struct.unpack_from('<IHH', data, metadata_header)
        if metadata_tag != NAME_TAG:
            continue
        size = flags >> 4
        name_offset = metadata_header + relative
        if name_offset < 0 or name_offset + size > len(data):
            raise ModelbinStructureError(f'Mesh blob {blob_index} Name metadata is outside the modelbin')
        return _decode_name(data[name_offset:name_offset + size])
    return ''

def parse_modelbin_mesh_structures(data: bytes) -> list[MeshStructureRecord]:
    if len(data) < 20 or struct.unpack_from('<I', data, 0)[0] != BUNDLE_TAG:
        raise ModelbinStructureError('modelbin is not a supported Grub bundle')
    bundle_major, bundle_minor = (int(data[4]), int(data[5]))
    modern = _version_at_least(bundle_major, bundle_minor, 1, 1)
    if modern:
        blob_count = struct.unpack_from('<I', data, 16)[0]
        headers_start = 20
    else:
        blob_count = struct.unpack_from('<H', data, 6)[0]
        headers_start = 16
    if blob_count > 100000 or headers_start + blob_count * 24 > len(data):
        raise ModelbinStructureError('modelbin blob table is outside the file')
    result: list[MeshStructureRecord] = []
    for blob_index in range(blob_count):
        header = headers_start + blob_index * 24
        tag = struct.unpack_from('<I', data, header)[0]
        if tag != MESH_TAG:
            continue
        major, minor = (int(data[header + 4]), int(data[header + 5]))
        metadata_count = struct.unpack_from('<H', data, header + 6)[0]
        metadata_offset, data_offset, compressed_size, uncompressed_size = struct.unpack_from('<IIII', data, header + 8)
        payload_size = int(uncompressed_size or compressed_size)
        end = int(data_offset) + payload_size
        if data_offset < 0 or end > len(data):
            raise ModelbinStructureError(f'Mesh blob {blob_index} payload is outside the modelbin')
        name = _mesh_name(data, metadata_offset, metadata_count, blob_index)
        cursor = int(data_offset)
        if _version_at_least(major, minor, 1, 13):
            _need(cursor, 4, end, f'Mesh blob {blob_index} material-group count')
            material_group_count = struct.unpack_from('<i', data, cursor)[0]
            cursor += 4
        else:
            material_group_count = 1
        if material_group_count < 0 or material_group_count > 4096:
            raise ModelbinStructureError(f'Mesh blob {blob_index} has invalid material-group count {material_group_count}')
        groups: list[tuple[int, ...]] = []
        group_width = 4 if _version_at_least(major, minor, 1, 9) else 1
        group_bytes = group_width * 2
        for _ in range(material_group_count):
            _need(cursor, group_bytes, end, f'Mesh blob {blob_index} material group')
            values = struct.unpack_from('<' + 'h' * group_width, data, cursor)
            groups.append(tuple((int(v) for v in values)))
            cursor += group_bytes
        if groups:
            primary_material_id = groups[0][1] if group_width >= 4 else groups[0][0]
        else:
            primary_material_id = None
        _need(cursor, 2 + 2 + 1 + 1 + 2 + 1, end, f'Mesh blob {blob_index} fixed render header')
        rigid_bone_index = struct.unpack_from('<h', data, cursor)[0]
        cursor += 2
        lod_flags = struct.unpack_from('<H', data, cursor)[0]
        cursor += 2
        lod_min = data[cursor]
        cursor += 1
        lod_max = data[cursor]
        cursor += 1
        bucket_flags_raw = struct.unpack_from('<H', data, cursor)[0]
        cursor += 2
        bucket_order = data[cursor]
        cursor += 1
        skinning_elements_count = None
        morph_target_count = None
        if _version_at_least(major, minor, 1, 2):
            _need(cursor, 1, end, f'Mesh blob {blob_index} skinning count')
            skinning_elements_count = int(data[cursor])
            cursor += 1
            if _version_at_least(major, minor, 1, 10):
                _need(cursor, 4, end, f'Mesh blob {blob_index} morph target count')
                morph_target_count = struct.unpack_from('<I', data, cursor)[0]
                cursor += 4
            else:
                _need(cursor, 1, end, f'Mesh blob {blob_index} morph target count')
                morph_target_count = int(data[cursor])
                cursor += 1
        is_morph_damage = None
        if _version_at_least(major, minor, 1, 3):
            _need(cursor, 1, end, f'Mesh blob {blob_index} damage flag')
            is_morph_damage = bool(data[cursor])
            cursor += 1
        _need(cursor, 1 + 2 + 6 * 4, end, f'Mesh blob {blob_index} draw fields')
        is_32_bit_indices = bool(data[cursor])
        cursor += 1
        topology = struct.unpack_from('<H', data, cursor)[0]
        cursor += 2
        index_buffer_index, index_buffer_offset, index_buffer_draw_offset, indexed_vertex_offset, index_count, primitive_count = struct.unpack_from('<iiiiii', data, cursor)
        cursor += 24
        acmr = None
        referenced_vertex_count = None
        referenced_vertex_index_count = None
        if _version_at_least(major, minor, 1, 6):
            _need(cursor, 8, end, f'Mesh blob {blob_index} ACMR/reference count')
            acmr, referenced_vertex_count = struct.unpack_from('<fI', data, cursor)
            cursor += 8
        if _version_at_least(major, minor, 1, 11):
            _need(cursor, 4, end, f'Mesh blob {blob_index} referenced-index count')
            referenced_vertex_index_count = struct.unpack_from('<I', data, cursor)[0]
            cursor += 4
            if referenced_vertex_index_count > 100000000:
                raise ModelbinStructureError(f'Mesh blob {blob_index} has implausible referenced-index count')
            skip = int(referenced_vertex_index_count) * 4
            _need(cursor, skip, end, f'Mesh blob {blob_index} referenced-index array')
            cursor += skip
        _need(cursor, 8, end, f'Mesh blob {blob_index} vertex layout/list header')
        vertex_layout_index = struct.unpack_from('<i', data, cursor)[0]
        cursor += 4
        vertex_buffer_count = struct.unpack_from('<i', data, cursor)[0]
        cursor += 4
        if vertex_buffer_count < 0 or vertex_buffer_count > 4096:
            raise ModelbinStructureError(f'Mesh blob {blob_index} has invalid vertex-buffer count {vertex_buffer_count}')
        reserved_values: list[int] = []
        for _ in range(vertex_buffer_count):
            entry_size = 20 if _version_at_least(major, minor, 1, 12) else 16
            _need(cursor, entry_size, end, f'Mesh blob {blob_index} vertex-buffer usage')
            if entry_size == 20:
                _, _, _, _, reserved = struct.unpack_from('<iIIII', data, cursor)
                reserved_values.append(int(reserved))
            cursor += entry_size
        morph_data_buffer_index = None
        skinning_data_buffer_index = None
        if _version_at_least(major, minor, 1, 4):
            _need(cursor, 8, end, f'Mesh blob {blob_index} morph/skinning buffer indices')
            morph_data_buffer_index, skinning_data_buffer_index = struct.unpack_from('<ii', data, cursor)
            cursor += 8
        _need(cursor, 4, end, f'Mesh blob {blob_index} constant-buffer count')
        constant_buffer_count = struct.unpack_from('<i', data, cursor)[0]
        cursor += 4
        if constant_buffer_count < 0 or constant_buffer_count > 4096:
            raise ModelbinStructureError(f'Mesh blob {blob_index} has invalid constant-buffer count {constant_buffer_count}')
        _need(cursor, constant_buffer_count * 4, end, f'Mesh blob {blob_index} constant-buffer list')
        constant_buffer_indices = tuple((int(v) for v in struct.unpack_from('<' + 'i' * constant_buffer_count, data, cursor))) if constant_buffer_count else ()
        cursor += constant_buffer_count * 4
        source_mesh_index = None
        if _version_at_least(major, minor, 1, 1):
            _need(cursor, 4, end, f'Mesh blob {blob_index} source-mesh index')
            source_mesh_index = struct.unpack_from('<I', data, cursor)[0]
            cursor += 4
        if _version_at_least(major, minor, 1, 5):
            _need(cursor, 80, end, f'Mesh blob {blob_index} texcoord transforms')
            cursor += 80
        position_scale = None
        position_translate = None
        if _version_at_least(major, minor, 1, 8):
            _need(cursor, 32, end, f'Mesh blob {blob_index} position scale/translate')
            position_scale = tuple((float(v) for v in struct.unpack_from('<ffff', data, cursor)))
            cursor += 16
            position_translate = tuple((float(v) for v in struct.unpack_from('<ffff', data, cursor)))
            cursor += 16
        result.append(MeshStructureRecord(blob_index=blob_index, mesh_name=name, mesh_version=f'{major}.{minor}', material_groups=tuple(groups), primary_material_id=int(primary_material_id) if primary_material_id is not None else None, rigid_bone_index=int(rigid_bone_index), lod_flags=int(lod_flags), lod_min=int(lod_min), lod_max=int(lod_max), bucket_flags_raw=int(bucket_flags_raw), is_opaque=bool(bucket_flags_raw & 1), is_decal=bool(bucket_flags_raw & 2), is_transparent=bool(bucket_flags_raw & 4), is_shadow=bool(bucket_flags_raw & 8), is_not_shadow=bool(bucket_flags_raw & 16), is_alpha_to_coverage=bool(bucket_flags_raw & 32), bucket_order=int(bucket_order), skinning_elements_count=skinning_elements_count, morph_target_count=int(morph_target_count) if morph_target_count is not None else None, is_morph_damage=is_morph_damage, is_32_bit_indices=is_32_bit_indices, topology=int(topology), index_buffer_index=int(index_buffer_index), index_buffer_offset=int(index_buffer_offset), index_buffer_draw_offset=int(index_buffer_draw_offset), indexed_vertex_offset=int(indexed_vertex_offset), index_count=int(index_count), primitive_count=int(primitive_count), acmr=float(acmr) if acmr is not None else None, referenced_vertex_count=int(referenced_vertex_count) if referenced_vertex_count is not None else None, referenced_vertex_index_count=int(referenced_vertex_index_count) if referenced_vertex_index_count is not None else None, vertex_layout_index=int(vertex_layout_index), vertex_buffer_count=int(vertex_buffer_count), vertex_buffer_reserved_values=tuple(reserved_values), morph_data_buffer_index=int(morph_data_buffer_index) if morph_data_buffer_index is not None else None, skinning_data_buffer_index=int(skinning_data_buffer_index) if skinning_data_buffer_index is not None else None, constant_buffer_indices=constant_buffer_indices, source_mesh_index=int(source_mesh_index) if source_mesh_index is not None else None, position_scale=position_scale, position_translate=position_translate))
    return result
