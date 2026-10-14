from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any, Sequence
import zipfile

from .modelbin_morph import (
    MESH_TAG,
    ModelbinMorphError,
    _iter_bundle_blobs,
    _metadata_identifier,
    _version_at_least,
    apply_weighted_morph,
    parse_modelbin_morph_inventory,
)

INDEX_BUFFER_TAG = 0x496E6442  # IndB
VERTEX_BUFFER_TAG = 0x42726556  # VerB
VERTEX_LAYOUT_TAG = 0x79614C56  # VLay
INPUT_LAYOUT_TAG = 0x79614C49  # ILay

DXGI_R32G32B32_FLOAT = 6
DXGI_R16G16B16A16_SNORM = 13


class TireMorphGeometryError(RuntimeError):
    """Raised when native tire geometry cannot be characterized without guessing."""


@dataclass(frozen=True)
class Aabb:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    center: tuple[float, float, float]
    span: tuple[float, float, float]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class VertexBufferUsage:
    index: int
    input_slot: int
    stride: int
    offset: int


@dataclass(frozen=True)
class MeshGeometryInfo:
    blob_index: int
    version_major: int
    version_minor: int
    lod_flags: int
    is_32bit_indices: bool
    index_buffer_offset: int
    index_buffer_draw_offset: int
    indexed_vertex_offset: int
    index_count: int
    vertex_layout_index: int
    vertex_buffers: tuple[VertexBufferUsage, ...]
    morph_target_count: int
    is_morph_damage: bool
    morph_data_buffer_index: int | None
    position_scale: tuple[float, float, float, float]
    position_translate: tuple[float, float, float, float]


@dataclass(frozen=True)
class LayoutElement:
    semantic_name: str
    semantic_index: int
    input_slot: int
    input_slot_class: int
    format: int
    computed_offset: int


@dataclass(frozen=True)
class VertexLayoutInfo:
    blob_index: int
    identifier_id: int | None
    elements: tuple[LayoutElement, ...]


@dataclass(frozen=True)
class VertexBufferInfo:
    blob_index: int
    identifier_id: int | None
    length: int
    stride: int
    format: int
    raw_data: bytes


@dataclass(frozen=True)
class MeshBakeEvidence:
    mesh_blob_index: int
    lod_flags: int
    min_vertex_index: int
    max_vertex_index: int
    indexed_vertex_offset: int
    resolved_vertex_start: int
    vertex_layout_resolution: str
    vertex_buffer_resolution: str
    position_format: int
    position_scale: tuple[float, float, float]
    position_translate: tuple[float, float, float]
    morph_target_count: int
    morph_buffer_resolution: str | None
    morph_buffer_blob_index: int | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ModelbinSelectorBakeReport:
    entry: str
    modelbin_sha256: str
    selected_mesh_count: int
    mesh_evidence: tuple[MeshBakeEvidence, ...]
    states: dict[str, dict[str, object]]
    glb_files: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "modelbin_sha256": self.modelbin_sha256,
            "selected_mesh_count": self.selected_mesh_count,
            "mesh_evidence": [item.as_dict() for item in self.mesh_evidence],
            "states": self.states,
            "glb_files": self.glb_files,
        }


@dataclass(frozen=True)
class TireSelectorBakeReport:
    archive_path: str
    archive_sha256: str
    archive_read_only_unchanged: bool
    selector_weights: dict[str, list[float]]
    post_morph_scale_applied: bool
    modelbins: tuple[ModelbinSelectorBakeReport, ...]
    left_right_comparison: dict[str, object] | None

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fh6_native_tire_selector_geometry_bake_v1",
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "archive_read_only_unchanged": self.archive_read_only_unchanged,
            "selector_weights": self.selector_weights,
            "post_morph_scale_applied": self.post_morph_scale_applied,
            "modelbins": [item.as_dict() for item in self.modelbins],
            "left_right_comparison": self.left_right_comparison,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _need(data: bytes, cursor: int, end: int, size: int, label: str) -> None:
    if size < 0 or cursor < 0 or cursor + size > end or cursor + size > len(data):
        raise TireMorphGeometryError(f"{label} is truncated")


def _parse_mesh(data: bytes, blob: Any) -> MeshGeometryInfo:
    cursor = blob.data_offset
    end = cursor + blob.data_size

    if _version_at_least(blob.version_major, blob.version_minor, 1, 13):
        _need(data, cursor, end, 4, f"Mesh {blob.blob_index} material-group count")
        material_group_count = struct.unpack_from("<i", data, cursor)[0]
        cursor += 4
    else:
        material_group_count = 1
    if material_group_count < 0 or material_group_count > 4096:
        raise TireMorphGeometryError(
            f"Mesh {blob.blob_index} has invalid material-group count {material_group_count}"
        )
    group_size = 8 if _version_at_least(blob.version_major, blob.version_minor, 1, 9) else 2
    _need(data, cursor, end, material_group_count * group_size, f"Mesh {blob.blob_index} materials")
    cursor += material_group_count * group_size

    _need(data, cursor, end, 9, f"Mesh {blob.blob_index} fixed fields")
    cursor += 2  # RigidBoneIndex
    lod_flags = struct.unpack_from("<H", data, cursor)[0]
    cursor += 2
    cursor += 2  # min/max LOD
    cursor += 2  # bucket flags
    cursor += 1  # bucket order

    morph_target_count = 1
    if _version_at_least(blob.version_major, blob.version_minor, 1, 2):
        _need(data, cursor, end, 1, f"Mesh {blob.blob_index} skinning count")
        cursor += 1
        if _version_at_least(blob.version_major, blob.version_minor, 1, 10):
            _need(data, cursor, end, 4, f"Mesh {blob.blob_index} morph count")
            morph_target_count = struct.unpack_from("<I", data, cursor)[0]
            cursor += 4
        else:
            _need(data, cursor, end, 1, f"Mesh {blob.blob_index} morph count")
            morph_target_count = data[cursor]
            cursor += 1

    is_morph_damage = True
    if _version_at_least(blob.version_major, blob.version_minor, 1, 3):
        _need(data, cursor, end, 1, f"Mesh {blob.blob_index} damage flag")
        is_morph_damage = bool(data[cursor])
        cursor += 1

    _need(data, cursor, end, 27, f"Mesh {blob.blob_index} index fields")
    is_32bit_indices = bool(data[cursor])
    cursor += 1
    cursor += 2  # topology
    (
        _index_buffer_index,
        index_buffer_offset,
        index_buffer_draw_offset,
        indexed_vertex_offset,
        index_count,
        _primitive_count,
    ) = struct.unpack_from("<iiiiii", data, cursor)
    cursor += 24
    if index_count < 0:
        raise TireMorphGeometryError(f"Mesh {blob.blob_index} has negative index count")

    if _version_at_least(blob.version_major, blob.version_minor, 1, 6):
        _need(data, cursor, end, 8, f"Mesh {blob.blob_index} ACMR/reference count")
        cursor += 8
    if _version_at_least(blob.version_major, blob.version_minor, 1, 11):
        _need(data, cursor, end, 4, f"Mesh {blob.blob_index} referenced index count")
        ref_count = struct.unpack_from("<I", data, cursor)[0]
        cursor += 4
        if ref_count > 10_000_000:
            raise TireMorphGeometryError(
                f"Mesh {blob.blob_index} has implausible referenced index count {ref_count}"
            )
        _need(data, cursor, end, ref_count * 4, f"Mesh {blob.blob_index} referenced indices")
        cursor += ref_count * 4

    _need(data, cursor, end, 8, f"Mesh {blob.blob_index} layout/VB header")
    vertex_layout_index = struct.unpack_from("<i", data, cursor)[0]
    cursor += 4
    vb_count = struct.unpack_from("<i", data, cursor)[0]
    cursor += 4
    if vb_count < 0 or vb_count > 4096:
        raise TireMorphGeometryError(
            f"Mesh {blob.blob_index} has invalid vertex-buffer usage count {vb_count}"
        )
    vertex_buffers: list[VertexBufferUsage] = []
    for _ in range(vb_count):
        size = 20 if _version_at_least(blob.version_major, blob.version_minor, 1, 12) else 16
        _need(data, cursor, end, size, f"Mesh {blob.blob_index} vertex-buffer usage")
        index, input_slot, stride, offset = struct.unpack_from("<iIII", data, cursor)
        cursor += 16
        if size == 20:
            cursor += 4
        vertex_buffers.append(VertexBufferUsage(index, int(input_slot), int(stride), int(offset)))

    morph_data_buffer_index: int | None = None
    if _version_at_least(blob.version_major, blob.version_minor, 1, 4):
        _need(data, cursor, end, 8, f"Mesh {blob.blob_index} morph/skinning references")
        morph_data_buffer_index = struct.unpack_from("<i", data, cursor)[0]
        cursor += 8

    _need(data, cursor, end, 4, f"Mesh {blob.blob_index} constant-buffer count")
    cb_count = struct.unpack_from("<i", data, cursor)[0]
    cursor += 4
    if cb_count < 0 or cb_count > 100000:
        raise TireMorphGeometryError(
            f"Mesh {blob.blob_index} has invalid constant-buffer count {cb_count}"
        )
    _need(data, cursor, end, cb_count * 4, f"Mesh {blob.blob_index} constant buffers")
    cursor += cb_count * 4

    if _version_at_least(blob.version_major, blob.version_minor, 1, 1):
        _need(data, cursor, end, 4, f"Mesh {blob.blob_index} source mesh index")
        cursor += 4
    if _version_at_least(blob.version_major, blob.version_minor, 1, 5):
        _need(data, cursor, end, 80, f"Mesh {blob.blob_index} texcoord transforms")
        cursor += 80

    position_scale = (1.0, 1.0, 1.0, 1.0)
    position_translate = (0.0, 0.0, 0.0, 0.0)
    if _version_at_least(blob.version_major, blob.version_minor, 1, 8):
        _need(data, cursor, end, 32, f"Mesh {blob.blob_index} position transform")
        position_scale = tuple(float(v) for v in struct.unpack_from("<4f", data, cursor))
        cursor += 16
        position_translate = tuple(float(v) for v in struct.unpack_from("<4f", data, cursor))

    return MeshGeometryInfo(
        blob_index=blob.blob_index,
        version_major=blob.version_major,
        version_minor=blob.version_minor,
        lod_flags=int(lod_flags),
        is_32bit_indices=is_32bit_indices,
        index_buffer_offset=int(index_buffer_offset),
        index_buffer_draw_offset=int(index_buffer_draw_offset),
        indexed_vertex_offset=int(indexed_vertex_offset),
        index_count=int(index_count),
        vertex_layout_index=int(vertex_layout_index),
        vertex_buffers=tuple(vertex_buffers),
        morph_target_count=int(morph_target_count),
        is_morph_damage=is_morph_damage,
        morph_data_buffer_index=morph_data_buffer_index,
        position_scale=position_scale,
        position_translate=position_translate,
    )


def _read_int32_char_string(data: bytes, cursor: int, end: int, label: str) -> tuple[str, int]:
    _need(data, cursor, end, 4, label)
    count = struct.unpack_from("<i", data, cursor)[0]
    cursor += 4
    if count < 0 or count > 4096:
        raise TireMorphGeometryError(f"{label} has invalid character count {count}")
    _need(data, cursor, end, count, label)
    raw = bytes(data[cursor : cursor + count])
    cursor += count
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TireMorphGeometryError(f"{label} is not UTF-8") from exc
    return value, cursor


def _format_size(fmt: int) -> int:
    return {6: 12, 10: 8, 13: 8, 16: 8, 24: 4, 28: 4, 35: 4, 37: 4}.get(fmt, 4)


def _parse_layout(data: bytes, blob: Any) -> VertexLayoutInfo:
    cursor = blob.data_offset
    end = cursor + blob.data_size
    _need(data, cursor, end, 2, f"Layout {blob.blob_index} semantic count")
    semantic_count = struct.unpack_from("<H", data, cursor)[0]
    cursor += 2
    if semantic_count > 4096:
        raise TireMorphGeometryError(f"Layout {blob.blob_index} has implausible semantic count")
    semantics: list[str] = []
    for index in range(semantic_count):
        value, cursor = _read_int32_char_string(
            data, cursor, end, f"Layout {blob.blob_index} semantic {index}"
        )
        semantics.append(value)

    _need(data, cursor, end, 2, f"Layout {blob.blob_index} element count")
    element_count = struct.unpack_from("<H", data, cursor)[0]
    cursor += 2
    if element_count > 4096:
        raise TireMorphGeometryError(f"Layout {blob.blob_index} has implausible element count")

    raw_elements: list[tuple[int, int, int, int, int]] = []
    for index in range(element_count):
        _need(data, cursor, end, 20, f"Layout {blob.blob_index} element {index}")
        semantic_name_index, semantic_index, input_slot, input_slot_class = struct.unpack_from(
            "<hhhh", data, cursor
        )
        fmt = struct.unpack_from("<i", data, cursor + 8)[0]
        cursor += 20
        if semantic_name_index < 0 or semantic_name_index >= len(semantics):
            raise TireMorphGeometryError(
                f"Layout {blob.blob_index} element {index} has invalid semantic index"
            )
        raw_elements.append(
            (semantic_name_index, semantic_index, input_slot, input_slot_class, fmt)
        )

    slot_offsets: dict[int, int] = {}
    elements: list[LayoutElement] = []
    for semantic_name_index, semantic_index, input_slot, input_slot_class, fmt in raw_elements:
        offset = slot_offsets.get(input_slot, 0)
        elements.append(
            LayoutElement(
                semantic_name=semantics[semantic_name_index],
                semantic_index=int(semantic_index),
                input_slot=int(input_slot),
                input_slot_class=int(input_slot_class),
                format=int(fmt),
                computed_offset=offset,
            )
        )
        slot_offsets[input_slot] = offset + _format_size(int(fmt))

    return VertexLayoutInfo(
        blob_index=blob.blob_index,
        identifier_id=_metadata_identifier(data, blob),
        elements=tuple(elements),
    )


def _parse_vertex_buffer(data: bytes, blob: Any) -> VertexBufferInfo:
    header_size = 16 if blob.version_major >= 1 else 12
    if blob.data_size < header_size:
        raise TireMorphGeometryError(f"VerB blob {blob.blob_index} header is truncated")
    base = blob.data_offset
    length, size = struct.unpack_from("<ii", data, base)
    stride = struct.unpack_from("<H", data, base + 8)[0]
    fmt = struct.unpack_from("<i", data, base + 12)[0] if blob.version_major >= 1 else 0
    if length < 0 or size < 0 or stride <= 0:
        raise TireMorphGeometryError(
            f"VerB blob {blob.blob_index} has invalid header length={length}, size={size}, stride={stride}"
        )
    inferred_size = length * stride if size == 0 and length > 0 else size
    if inferred_size < 0 or header_size + inferred_size > blob.data_size:
        raise TireMorphGeometryError(f"VerB blob {blob.blob_index} raw buffer exceeds payload")
    raw_start = base + header_size
    return VertexBufferInfo(
        blob_index=blob.blob_index,
        identifier_id=_metadata_identifier(data, blob),
        length=int(length),
        stride=int(stride),
        format=int(fmt),
        raw_data=bytes(data[raw_start : raw_start + inferred_size]),
    )


def _parse_global_indices(data: bytes, blob: Any) -> tuple[bytes, int]:
    header_size = 16 if blob.version_major >= 1 else 12
    if blob.data_size < header_size:
        raise TireMorphGeometryError("global IndB header is truncated")
    base = blob.data_offset
    length, size = struct.unpack_from("<ii", data, base)
    stride = struct.unpack_from("<H", data, base + 8)[0]
    if length < 0 or size < 0 or stride not in (2, 4):
        raise TireMorphGeometryError(
            f"global IndB has invalid header length={length}, size={size}, stride={stride}"
        )
    inferred_size = length * stride if size == 0 and length > 0 else size
    if header_size + inferred_size > blob.data_size:
        raise TireMorphGeometryError("global IndB raw buffer exceeds payload")
    start = base + header_size
    return bytes(data[start : start + inferred_size]), int(stride)


def _mesh_indices(index_raw: bytes, mesh: MeshGeometryInfo) -> tuple[int, ...]:
    stride = 4 if mesh.is_32bit_indices else 2
    start = mesh.index_buffer_offset + mesh.index_buffer_draw_offset * stride
    end = start + mesh.index_count * stride
    if start < 0 or end < start or end > len(index_raw):
        raise TireMorphGeometryError(
            f"Mesh {mesh.blob_index} index range is outside global IndB: {start}:{end}"
        )
    if stride == 4:
        values = tuple(struct.unpack_from("<I", index_raw, offset)[0] for offset in range(start, end, 4))
    else:
        values = tuple(struct.unpack_from("<H", index_raw, offset)[0] for offset in range(start, end, 2))
    return tuple(int(value) for value in values)


def _resolve_layout(
    mesh: MeshGeometryInfo,
    layouts: Sequence[VertexLayoutInfo],
) -> tuple[VertexLayoutInfo, str]:
    for layout in layouts:
        if layout.identifier_id is not None and layout.identifier_id == mesh.vertex_layout_index:
            return layout, "identifier"
    if 0 <= mesh.vertex_layout_index < len(layouts):
        return layouts[mesh.vertex_layout_index], "ordinal_fallback"
    if layouts:
        return layouts[0], "fts_first_layout_fallback"
    raise TireMorphGeometryError(f"Mesh {mesh.blob_index} has no vertex layout")


def _resolve_vertex_buffer(
    usage: VertexBufferUsage,
    buffers: Sequence[VertexBufferInfo],
    by_blob_index: dict[int, VertexBufferInfo],
) -> tuple[VertexBufferInfo, str]:
    for buffer in buffers:
        if buffer.identifier_id is not None and buffer.identifier_id == usage.index:
            return buffer, "identifier"
    fallback = by_blob_index.get(usage.index)
    if fallback is not None:
        return fallback, "blob_index_fallback"
    raise TireMorphGeometryError(
        f"vertex buffer reference {usage.index} cannot be resolved using FTS rules"
    )


def _snorm16(value: int) -> float:
    return max(-1.0, min(1.0, value / 32767.0))


def _decode_positions(
    mesh: MeshGeometryInfo,
    layout: VertexLayoutInfo,
    buffers: Sequence[VertexBufferInfo],
    by_blob_index: dict[int, VertexBufferInfo],
    min_index: int,
    max_index: int,
) -> tuple[tuple[tuple[float, float, float], ...], int, str]:
    position_elements = [item for item in layout.elements if item.semantic_name == "POSITION"]
    if len(position_elements) != 1:
        raise TireMorphGeometryError(
            f"Mesh {mesh.blob_index} expected exactly one POSITION element, got {len(position_elements)}"
        )
    element = position_elements[0]
    usage = next((item for item in mesh.vertex_buffers if item.input_slot == element.input_slot), None)
    if usage is None:
        raise TireMorphGeometryError(
            f"Mesh {mesh.blob_index} has no VB usage for POSITION slot {element.input_slot}"
        )
    buffer, resolution = _resolve_vertex_buffer(usage, buffers, by_blob_index)
    stride = buffer.stride if buffer.stride > 0 else usage.stride
    if stride <= 0:
        raise TireMorphGeometryError(f"Mesh {mesh.blob_index} POSITION stride is zero")
    if usage.stride and buffer.stride and usage.stride != buffer.stride:
        raise TireMorphGeometryError(
            f"Mesh {mesh.blob_index} POSITION stride mismatch: usage={usage.stride}, VerB={buffer.stride}"
        )
    if element.format not in (DXGI_R16G16B16A16_SNORM, DXGI_R32G32B32_FLOAT):
        raise TireMorphGeometryError(
            f"Mesh {mesh.blob_index} unsupported POSITION DXGI format {element.format}; expected 13 or 6"
        )

    scale = mesh.position_scale
    translate = mesh.position_translate
    scale_enabled = any(component != 0.0 for component in scale[:3])
    positions: list[tuple[float, float, float]] = []
    for source_index in range(min_index, max_index + 1):
        vertex_id = source_index + mesh.indexed_vertex_offset
        if vertex_id < 0:
            raise TireMorphGeometryError(
                f"Mesh {mesh.blob_index} resolved POSITION vertex id is negative: {vertex_id}"
            )
        addr = usage.offset + vertex_id * stride + element.computed_offset
        required = 8 if element.format == DXGI_R16G16B16A16_SNORM else 12
        if addr < 0 or addr + required > len(buffer.raw_data):
            raise TireMorphGeometryError(
                f"Mesh {mesh.blob_index} POSITION address {addr}:{addr + required} is outside VerB {buffer.blob_index}"
            )
        if element.format == DXGI_R16G16B16A16_SNORM:
            rx, ry, rz = (_snorm16(value) for value in struct.unpack_from("<hhh", buffer.raw_data, addr))
            if scale_enabled:
                positions.append(
                    (
                        rx * scale[0] + translate[0],
                        ry * scale[1] + translate[1],
                        rz * scale[2] + translate[2],
                    )
                )
            else:
                positions.append((rx, ry, rz))
        else:
            x, y, z = struct.unpack_from("<fff", buffer.raw_data, addr)
            if not all(math.isfinite(value) for value in (x, y, z)):
                raise TireMorphGeometryError(f"Mesh {mesh.blob_index} POSITION contains non-finite float")
            positions.append((float(x), float(y), float(z)))
    return tuple(positions), element.format, resolution


def _aabb(positions: Sequence[Sequence[float]]) -> Aabb:
    if not positions:
        raise TireMorphGeometryError("cannot calculate AABB from an empty position set")
    mins = [min(float(point[axis]) for point in positions) for axis in range(3)]
    maxs = [max(float(point[axis]) for point in positions) for axis in range(3)]
    center = [(mins[axis] + maxs[axis]) * 0.5 for axis in range(3)]
    span = [maxs[axis] - mins[axis] for axis in range(3)]
    return Aabb(tuple(mins), tuple(maxs), tuple(center), tuple(span))


def _delta3(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [float(a[index]) - float(b[index]) for index in range(3)]


def _pad4(raw: bytes, padding: bytes = b"\x00") -> bytes:
    return raw + padding * ((-len(raw)) % 4)


def _glb_bytes(positions: Sequence[Sequence[float]], indices: Sequence[int]) -> bytes:
    if not positions or not indices:
        raise TireMorphGeometryError("GLB output requires positions and indices")
    pos_raw = b"".join(struct.pack("<fff", *map(float, point)) for point in positions)
    pos_raw = _pad4(pos_raw)
    index_offset = len(pos_raw)
    idx_raw = b"".join(struct.pack("<I", int(index)) for index in indices)
    binary = _pad4(pos_raw + idx_raw)
    bounds = _aabb(positions)
    document = {
        "asset": {"version": "2.0", "generator": "FH6 Assistant native tire selector diagnostic"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pos_raw), "target": 34962},
            {"buffer": 0, "byteOffset": index_offset, "byteLength": len(idx_raw), "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(positions),
                "type": "VEC3",
                "min": list(bounds.minimum),
                "max": list(bounds.maximum),
            },
            {
                "bufferView": 1,
                "componentType": 5125,
                "count": len(indices),
                "type": "SCALAR",
            },
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    json_raw = _pad4(json.dumps(document, separators=(",", ":")).encode("utf-8"), b" ")
    total = 12 + 8 + len(json_raw) + 8 + len(binary)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(json_raw), b"JSON")
        + json_raw
        + struct.pack("<I4s", len(binary), b"BIN\x00")
        + binary
    )


def _selector_states() -> dict[str, tuple[float, float, float, float, float]]:
    states: dict[str, tuple[float, float, float, float, float]] = {
        "baseline": (0.0, 0.0, 0.0, 0.0, 0.0)
    }
    for selector in range(5):
        values = [0.0] * 5
        values[selector] = 1.0
        states[f"selector{selector}"] = tuple(values)  # type: ignore[assignment]
    return states


def _compact_geometry(
    full_positions: Sequence[Sequence[float]],
    source_indices: Sequence[int],
    min_index: int,
) -> tuple[list[tuple[float, float, float]], list[int]]:
    mapping: dict[int, int] = {}
    compact_positions: list[tuple[float, float, float]] = []
    compact_indices: list[int] = []
    for source_index in source_indices:
        local = source_index - min_index
        if local < 0 or local >= len(full_positions):
            raise TireMorphGeometryError("mesh index is outside decoded POSITION range")
        compact = mapping.get(local)
        if compact is None:
            compact = len(compact_positions)
            mapping[local] = compact
            point = full_positions[local]
            compact_positions.append((float(point[0]), float(point[1]), float(point[2])))
        compact_indices.append(compact)
    return compact_positions, compact_indices


def bake_modelbin_selector_geometry(
    data: bytes,
    *,
    entry: str = "modelbin",
    output_dir: Path | None = None,
    write_glb: bool = True,
) -> ModelbinSelectorBakeReport:
    try:
        _bundle_major, _bundle_minor, blobs = _iter_bundle_blobs(data)
        index_blobs = [blob for blob in blobs if blob.tag == INDEX_BUFFER_TAG]
        if not index_blobs:
            raise TireMorphGeometryError("modelbin has no IndB")
        index_raw, _serialized_index_stride = _parse_global_indices(data, index_blobs[0])
        layouts = tuple(
            _parse_layout(data, blob)
            for blob in blobs
            if blob.tag in (VERTEX_LAYOUT_TAG, INPUT_LAYOUT_TAG)
        )
        buffers = tuple(
            _parse_vertex_buffer(data, blob) for blob in blobs if blob.tag == VERTEX_BUFFER_TAG
        )
        by_buffer_blob = {item.blob_index: item for item in buffers}
        meshes = tuple(_parse_mesh(data, blob) for blob in blobs if blob.tag == MESH_TAG)
        inventory = parse_modelbin_morph_inventory(data)
    except ModelbinMorphError as exc:
        raise TireMorphGeometryError(str(exc)) from exc

    morph_buffers = {item.blob_index: item for item in inventory.morph_buffers}
    morph_resolutions = {item.mesh_blob_index: item for item in inventory.resolutions}
    states = _selector_states()
    state_geometry: dict[str, tuple[list[tuple[float, float, float]], list[int]]] = {
        state: ([], []) for state in states
    }
    evidence: list[MeshBakeEvidence] = []

    for mesh in meshes:
        if (mesh.lod_flags & 3) == 0 or mesh.index_count <= 0:
            continue
        source_indices = _mesh_indices(index_raw, mesh)
        if not source_indices:
            continue
        min_index = min(source_indices)
        max_index = max(source_indices)
        resolved_start = min_index + mesh.indexed_vertex_offset
        if resolved_start < 0:
            raise TireMorphGeometryError(
                f"Mesh {mesh.blob_index} signed base vertex resolves negative: {resolved_start}"
            )
        layout, layout_resolution = _resolve_layout(mesh, layouts)
        base_positions, position_format, vb_resolution = _decode_positions(
            mesh, layout, buffers, by_buffer_blob, min_index, max_index
        )

        morph_buffer = None
        morph_resolution_name: str | None = None
        morph_buffer_blob_index: int | None = None
        if mesh.morph_target_count > 0 and not mesh.is_morph_damage:
            if mesh.morph_target_count != 5:
                raise TireMorphGeometryError(
                    f"Mesh {mesh.blob_index} has {mesh.morph_target_count} weighted targets; "
                    "five-target tire selector diagnostic refuses to guess"
                )
            resolution = morph_resolutions.get(mesh.blob_index)
            if resolution is None or resolution.morph_buffer_blob_index is None:
                raise TireMorphGeometryError(
                    f"Mesh {mesh.blob_index} weighted morph buffer cannot be resolved"
                )
            morph_buffer_blob_index = resolution.morph_buffer_blob_index
            morph_resolution_name = resolution.resolved_by
            morph_buffer = morph_buffers.get(morph_buffer_blob_index)
            if morph_buffer is None:
                raise TireMorphGeometryError(
                    f"Mesh {mesh.blob_index} resolved MBuf {morph_buffer_blob_index} is missing"
                )

        evidence.append(
            MeshBakeEvidence(
                mesh_blob_index=mesh.blob_index,
                lod_flags=mesh.lod_flags,
                min_vertex_index=min_index,
                max_vertex_index=max_index,
                indexed_vertex_offset=mesh.indexed_vertex_offset,
                resolved_vertex_start=resolved_start,
                vertex_layout_resolution=layout_resolution,
                vertex_buffer_resolution=vb_resolution,
                position_format=position_format,
                position_scale=tuple(mesh.position_scale[:3]),
                position_translate=tuple(mesh.position_translate[:3]),
                morph_target_count=mesh.morph_target_count,
                morph_buffer_resolution=morph_resolution_name,
                morph_buffer_blob_index=morph_buffer_blob_index,
            )
        )

        for state, weights in states.items():
            positions: Sequence[Sequence[float]] = base_positions
            if morph_buffer is not None and state != "baseline":
                try:
                    positions, _ = apply_weighted_morph(
                        base_positions,
                        morph_buffer,
                        mesh.indexed_vertex_offset,
                        mesh.morph_target_count,
                        weights,
                        min_vertex_index=min_index,
                    )
                except ModelbinMorphError as exc:
                    raise TireMorphGeometryError(
                        f"Mesh {mesh.blob_index} {state} morph failed: {exc}"
                    ) from exc
            compact_positions, compact_indices = _compact_geometry(
                positions, source_indices, min_index
            )
            aggregate_positions, aggregate_indices = state_geometry[state]
            vertex_base = len(aggregate_positions)
            aggregate_positions.extend(compact_positions)
            aggregate_indices.extend(vertex_base + index for index in compact_indices)

    if not evidence:
        raise TireMorphGeometryError("modelbin has no decodable LOD0 tire meshes")

    report_states: dict[str, dict[str, object]] = {}
    glb_files: dict[str, str] = {}
    baseline_aabb: Aabb | None = None
    safe_stem = Path(entry.replace("\\", "/")).stem
    for state, (positions, indices) in state_geometry.items():
        bounds = _aabb(positions)
        if state == "baseline":
            baseline_aabb = bounds
        if baseline_aabb is None:
            raise TireMorphGeometryError("baseline state was not produced first")
        report_states[state] = {
            "weights": list(states[state]),
            "vertex_count": len(positions),
            "index_count": len(indices),
            "aabb": bounds.as_dict(),
            "center_delta_vs_baseline": _delta3(bounds.center, baseline_aabb.center),
            "span_delta_vs_baseline": _delta3(bounds.span, baseline_aabb.span),
            "minimum_delta_vs_baseline": _delta3(bounds.minimum, baseline_aabb.minimum),
            "maximum_delta_vs_baseline": _delta3(bounds.maximum, baseline_aabb.maximum),
        }
        if output_dir is not None and write_glb:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{safe_stem}__{state}.glb"
            output_path.write_bytes(_glb_bytes(positions, indices))
            glb_files[state] = str(output_path)

    return ModelbinSelectorBakeReport(
        entry=entry.replace("\\", "/"),
        modelbin_sha256=hashlib.sha256(data).hexdigest(),
        selected_mesh_count=len(evidence),
        mesh_evidence=tuple(evidence),
        states=report_states,
        glb_files=glb_files,
    )


def _left_right_comparison(
    modelbins: Sequence[ModelbinSelectorBakeReport],
) -> dict[str, object] | None:
    if len(modelbins) != 2:
        return None
    left, right = modelbins
    states: dict[str, object] = {}
    common_states = sorted(set(left.states) & set(right.states))
    for state in common_states:
        left_aabb = left.states[state]["aabb"]
        right_aabb = right.states[state]["aabb"]
        if not isinstance(left_aabb, dict) or not isinstance(right_aabb, dict):
            continue
        left_span = left_aabb["span"]
        right_span = right_aabb["span"]
        left_center = left_aabb["center"]
        right_center = right_aabb["center"]
        states[state] = {
            "span_left_minus_right": _delta3(left_span, right_span),
            "center_left_minus_right": _delta3(left_center, right_center),
        }
    return {
        "left_entry": left.entry,
        "right_entry": right.entry,
        "note": "Numeric comparison only; no semantic symmetry pass/fail is inferred.",
        "states": states,
    }


def bake_tire_morph_selectors(
    archive_path: str | Path,
    output_dir: str | Path,
    *,
    write_glb: bool = True,
) -> TireSelectorBakeReport:
    """Bake baseline and five one-hot selector states from a native tire ZIP read-only.

    This is diagnostic-only. It does not apply the historical tire physical-dimension
    formula or scale_x, and it does not assign production semantics to selectors 0..4.
    """
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file():
        raise TireMorphGeometryError(f"native tire archive does not exist: {archive}")
    destination = Path(output_dir).expanduser().resolve()
    before = _sha256(archive)
    reports: list[ModelbinSelectorBakeReport] = []
    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            entries = [
                item
                for item in bundle.infolist()
                if not item.is_dir() and item.filename.casefold().endswith(".modelbin")
            ]
            if not entries:
                raise TireMorphGeometryError("native tire archive contains no modelbin")
            for item in sorted(entries, key=lambda entry: entry.filename.casefold()):
                reports.append(
                    bake_modelbin_selector_geometry(
                        bundle.read(item),
                        entry=item.filename,
                        output_dir=destination,
                        write_glb=write_glb,
                    )
                )
    except (OSError, zipfile.BadZipFile) as exc:
        raise TireMorphGeometryError(f"could not read native tire archive: {exc}") from exc

    after = _sha256(archive)
    if before != after:
        raise TireMorphGeometryError("read-only tire selector bake changed the source archive")
    selector_weights = {state: list(weights) for state, weights in _selector_states().items()}
    return TireSelectorBakeReport(
        archive_path=str(archive),
        archive_sha256=before,
        archive_read_only_unchanged=True,
        selector_weights=selector_weights,
        post_morph_scale_applied=False,
        modelbins=tuple(reports),
        left_right_comparison=_left_right_comparison(reports),
    )
