from __future__ import annotations

from dataclasses import dataclass
import math
import struct
from typing import Any, Iterable, Sequence

BUNDLE_TAG = 0x47727562  # Grub
MESH_TAG = 0x4D657368  # Mesh
MORPH_BUFFER_TAG = 0x4D427566  # MBuf
ID_METADATA_TAG = 0x49642020  # "Id  "

DXGI_R16G16B16A16_FLOAT = 10
DXGI_R16G16B16A16_SNORM = 13


class ModelbinMorphError(RuntimeError):
    """Raised when modelbin morph data cannot be decoded safely."""


@dataclass(frozen=True)
class BlobRecord:
    blob_index: int
    tag: int
    version_major: int
    version_minor: int
    metadata_count: int
    metadata_offset: int
    data_offset: int
    data_size: int


@dataclass(frozen=True)
class MorphBufferInfo:
    blob_index: int
    identifier_id: int | None
    version_major: int
    version_minor: int
    length: int
    size: int
    stride: int
    sub_element_count: int
    format: int
    raw_data: bytes

    def as_dict(self) -> dict[str, Any]:
        return {
            "blob_index": self.blob_index,
            "identifier_id": self.identifier_id,
            "version": f"{self.version_major}.{self.version_minor}",
            "length": self.length,
            "size": self.size,
            "stride": self.stride,
            "sub_element_count": self.sub_element_count,
            "format": self.format,
            "raw_data_size": len(self.raw_data),
        }


@dataclass(frozen=True)
class MeshMorphBinding:
    blob_index: int
    version_major: int
    version_minor: int
    morph_target_count: int
    is_morph_damage: bool
    indexed_vertex_offset: int
    morph_data_buffer_index: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "blob_index": self.blob_index,
            "version": f"{self.version_major}.{self.version_minor}",
            "morph_target_count": self.morph_target_count,
            "is_morph_damage": self.is_morph_damage,
            "indexed_vertex_offset": self.indexed_vertex_offset,
            "morph_data_buffer_index": self.morph_data_buffer_index,
        }


@dataclass(frozen=True)
class MorphBindingResolution:
    mesh_blob_index: int
    morph_data_buffer_index: int
    morph_buffer_blob_index: int | None
    resolved_by: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "mesh_blob_index": self.mesh_blob_index,
            "morph_data_buffer_index": self.morph_data_buffer_index,
            "morph_buffer_blob_index": self.morph_buffer_blob_index,
            "resolved_by": self.resolved_by,
        }


@dataclass(frozen=True)
class ModelbinMorphInventory:
    bundle_version_major: int
    bundle_version_minor: int
    morph_buffers: tuple[MorphBufferInfo, ...]
    mesh_bindings: tuple[MeshMorphBinding, ...]
    resolutions: tuple[MorphBindingResolution, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "fh6_modelbin_morph_inventory_v1",
            "bundle_version": f"{self.bundle_version_major}.{self.bundle_version_minor}",
            "morph_buffers": [item.as_dict() for item in self.morph_buffers],
            "mesh_bindings": [item.as_dict() for item in self.mesh_bindings],
            "resolutions": [item.as_dict() for item in self.resolutions],
        }


@dataclass(frozen=True)
class MorphDeltaRecord:
    dx: float
    dy: float
    dz: float
    target_index: int | None


@dataclass(frozen=True)
class WeightedVertexMorph:
    position_delta: tuple[float, float, float]
    normal_delta: tuple[float, float, float] | None


def _version_at_least(major: int, minor: int, want_major: int, want_minor: int) -> bool:
    return major > want_major or (major == want_major and minor >= want_minor)


def _require_range(data: bytes, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ModelbinMorphError(f"{label} is outside the modelbin")


def _iter_bundle_blobs(data: bytes) -> tuple[int, int, tuple[BlobRecord, ...]]:
    if len(data) < 0x14 or struct.unpack_from("<I", data, 0)[0] != BUNDLE_TAG:
        raise ModelbinMorphError("modelbin is not a supported Grub bundle")

    bundle_major, bundle_minor = data[4], data[5]
    modern = _version_at_least(bundle_major, bundle_minor, 1, 1)
    if modern:
        blob_count = struct.unpack_from("<I", data, 0x10)[0]
        headers_start = 0x14
    else:
        blob_count = struct.unpack_from("<H", data, 0x06)[0]
        headers_start = 0x10

    if blob_count > 100000:
        raise ModelbinMorphError(f"modelbin has implausible blob count {blob_count}")
    _require_range(data, headers_start, blob_count * 0x18, "blob table")

    records: list[BlobRecord] = []
    for blob_index in range(blob_count):
        header = headers_start + blob_index * 0x18
        tag = struct.unpack_from("<I", data, header)[0]
        major, minor = data[header + 4], data[header + 5]
        metadata_count = struct.unpack_from("<H", data, header + 6)[0]
        metadata_offset, data_offset, compressed_size, uncompressed_size = struct.unpack_from(
            "<IIII", data, header + 8
        )
        payload_size = int(uncompressed_size or compressed_size)
        _require_range(data, data_offset, payload_size, f"blob {blob_index} payload")
        if metadata_count:
            _require_range(
                data,
                metadata_offset,
                metadata_count * 8,
                f"blob {blob_index} metadata table",
            )
        records.append(
            BlobRecord(
                blob_index=blob_index,
                tag=tag,
                version_major=major,
                version_minor=minor,
                metadata_count=metadata_count,
                metadata_offset=metadata_offset,
                data_offset=data_offset,
                data_size=payload_size,
            )
        )
    return bundle_major, bundle_minor, tuple(records)


def _metadata_identifier(data: bytes, blob: BlobRecord) -> int | None:
    for metadata_index in range(blob.metadata_count):
        header = blob.metadata_offset + metadata_index * 8
        tag, flags, relative = struct.unpack_from("<IHH", data, header)
        if tag != ID_METADATA_TAG:
            continue
        size = flags >> 4
        if size < 4:
            raise ModelbinMorphError(
                f"blob {blob.blob_index} identifier metadata is shorter than 4 bytes"
            )
        value_offset = header + relative
        _require_range(
            data,
            value_offset,
            size,
            f"blob {blob.blob_index} identifier metadata data",
        )
        return struct.unpack_from("<i", data, value_offset)[0]
    return None


def _parse_morph_buffer(data: bytes, blob: BlobRecord) -> MorphBufferInfo:
    header_size = 16 if blob.version_major >= 1 else 12
    if blob.data_size < header_size:
        raise ModelbinMorphError(f"MBuf blob {blob.blob_index} header is truncated")

    base = blob.data_offset
    length, size = struct.unpack_from("<ii", data, base)
    stride = struct.unpack_from("<H", data, base + 8)[0]
    if length < 0 or size < 0:
        raise ModelbinMorphError(f"MBuf blob {blob.blob_index} has negative header values")

    if blob.version_major >= 1:
        sub_element_count = data[base + 10]
        fmt = struct.unpack_from("<i", data, base + 12)[0]
    else:
        sub_element_count = 1
        fmt = 0

    inferred_size = length * stride if size == 0 and length > 0 and stride > 0 else size
    if size > 0 and stride > 0 and length > 0 and size < length * stride:
        raise ModelbinMorphError(
            f"MBuf blob {blob.blob_index} size {size} is smaller than length*stride "
            f"({length * stride})"
        )
    if inferred_size < 0:
        raise ModelbinMorphError(f"MBuf blob {blob.blob_index} has invalid data size")
    if header_size + inferred_size > blob.data_size:
        raise ModelbinMorphError(
            f"MBuf blob {blob.blob_index} raw buffer exceeds blob payload"
        )

    raw_start = base + header_size
    raw = bytes(data[raw_start : raw_start + inferred_size])
    return MorphBufferInfo(
        blob_index=blob.blob_index,
        identifier_id=_metadata_identifier(data, blob),
        version_major=blob.version_major,
        version_minor=blob.version_minor,
        length=length,
        size=size,
        stride=stride,
        sub_element_count=sub_element_count,
        format=fmt,
        raw_data=raw,
    )


def _parse_mesh_binding(data: bytes, blob: BlobRecord) -> MeshMorphBinding:
    start = blob.data_offset
    end = start + blob.data_size
    cursor = start

    def need(size: int, label: str) -> None:
        if cursor + size > end or cursor + size > len(data):
            raise ModelbinMorphError(f"Mesh blob {blob.blob_index} {label} is truncated")

    if _version_at_least(blob.version_major, blob.version_minor, 1, 13):
        need(4, "material-group count")
        material_group_count = struct.unpack_from("<i", data, cursor)[0]
        cursor += 4
    else:
        material_group_count = 1
    if material_group_count < 0 or material_group_count > 4096:
        raise ModelbinMorphError(
            f"Mesh blob {blob.blob_index} has invalid material-group count "
            f"{material_group_count}"
        )
    group_size = 8 if _version_at_least(blob.version_major, blob.version_minor, 1, 9) else 2
    need(material_group_count * group_size, "material groups")
    cursor += material_group_count * group_size

    need(2 + 2 + 2 + 2 + 1, "fixed pre-morph fields")
    cursor += 2
    cursor += 2
    cursor += 2
    cursor += 2
    cursor += 1

    morph_target_count = 1
    if _version_at_least(blob.version_major, blob.version_minor, 1, 2):
        need(1, "skinning element count")
        cursor += 1
        if _version_at_least(blob.version_major, blob.version_minor, 1, 10):
            need(4, "morph target count")
            morph_target_count = struct.unpack_from("<I", data, cursor)[0]
            cursor += 4
        else:
            need(1, "morph target count")
            morph_target_count = data[cursor]
            cursor += 1

    is_morph_damage = True
    if _version_at_least(blob.version_major, blob.version_minor, 1, 3):
        need(1, "IsMorphDamage")
        is_morph_damage = bool(data[cursor])
        cursor += 1

    need(1 + 2 + 24, "index fields")
    cursor += 1
    cursor += 2
    index_fields = struct.unpack_from("<iiiiii", data, cursor)
    indexed_vertex_offset = int(index_fields[3])
    cursor += 24

    if _version_at_least(blob.version_major, blob.version_minor, 1, 6):
        need(8, "ACMR/referenced vertex count")
        cursor += 8
    if _version_at_least(blob.version_major, blob.version_minor, 1, 11):
        need(4, "referenced vertex index count")
        ref_count = struct.unpack_from("<I", data, cursor)[0]
        cursor += 4
        if ref_count > 10_000_000:
            raise ModelbinMorphError(
                f"Mesh blob {blob.blob_index} has implausible referenced vertex count {ref_count}"
            )
        need(ref_count * 4, "referenced vertex indices")
        cursor += ref_count * 4

    need(8, "vertex-layout/VB count")
    cursor += 4
    vb_count = struct.unpack_from("<i", data, cursor)[0]
    cursor += 4
    if vb_count < 0 or vb_count > 4096:
        raise ModelbinMorphError(
            f"Mesh blob {blob.blob_index} has invalid vertex-buffer usage count {vb_count}"
        )
    vb_record_size = 20 if _version_at_least(blob.version_major, blob.version_minor, 1, 12) else 16
    need(vb_count * vb_record_size, "vertex-buffer usages")
    cursor += vb_count * vb_record_size

    morph_data_buffer_index: int | None = None
    if _version_at_least(blob.version_major, blob.version_minor, 1, 4):
        need(8, "morph/skinning buffer indices")
        morph_data_buffer_index = struct.unpack_from("<i", data, cursor)[0]
        cursor += 8

    return MeshMorphBinding(
        blob_index=blob.blob_index,
        version_major=blob.version_major,
        version_minor=blob.version_minor,
        morph_target_count=int(morph_target_count),
        is_morph_damage=is_morph_damage,
        indexed_vertex_offset=indexed_vertex_offset,
        morph_data_buffer_index=morph_data_buffer_index,
    )


def parse_modelbin_morph_inventory(data: bytes) -> ModelbinMorphInventory:
    bundle_major, bundle_minor, blobs = _iter_bundle_blobs(data)
    morph_buffers = tuple(
        _parse_morph_buffer(data, blob) for blob in blobs if blob.tag == MORPH_BUFFER_TAG
    )
    mesh_bindings = tuple(
        _parse_mesh_binding(data, blob) for blob in blobs if blob.tag == MESH_TAG
    )

    by_identifier = {
        item.identifier_id: item
        for item in morph_buffers
        if item.identifier_id is not None
    }
    resolutions: list[MorphBindingResolution] = []
    for mesh in mesh_bindings:
        ref = mesh.morph_data_buffer_index
        if ref is None or ref < 0 or mesh.morph_target_count <= 0:
            continue
        match = by_identifier.get(ref)
        if match is not None:
            resolutions.append(
                MorphBindingResolution(mesh.blob_index, ref, match.blob_index, "identifier")
            )
        elif 0 <= ref < len(morph_buffers):
            resolutions.append(
                MorphBindingResolution(
                    mesh.blob_index,
                    ref,
                    morph_buffers[ref].blob_index,
                    "ordinal_fallback",
                )
            )
        else:
            resolutions.append(
                MorphBindingResolution(mesh.blob_index, ref, None, "unresolved")
            )

    return ModelbinMorphInventory(
        bundle_version_major=bundle_major,
        bundle_version_minor=bundle_minor,
        morph_buffers=morph_buffers,
        mesh_bindings=mesh_bindings,
        resolutions=tuple(resolutions),
    )


def _half_to_float(raw: bytes, offset: int) -> float:
    try:
        value = struct.unpack_from("<e", raw, offset)[0]
    except (struct.error, OverflowError) as exc:
        raise ModelbinMorphError("half-float morph record is truncated") from exc
    if not math.isfinite(value):
        raise ModelbinMorphError(f"morph record contains non-finite half float {value!r}")
    return float(value)


def decode_half4_record(raw: bytes, offset: int = 0) -> MorphDeltaRecord:
    if offset < 0 or offset + 8 > len(raw):
        raise ModelbinMorphError("half4 morph record is outside the buffer")
    dx = _half_to_float(raw, offset)
    dy = _half_to_float(raw, offset + 2)
    dz = _half_to_float(raw, offset + 4)
    target_raw = _half_to_float(raw, offset + 6)
    target_index = int(round(target_raw))
    if target_index < 0 or abs(target_raw - target_index) > 1e-3:
        raise ModelbinMorphError(
            f"morph target selector must be a non-negative integer, got {target_raw}"
        )
    return MorphDeltaRecord(dx, dy, dz, target_index)


def decode_snorm16_delta(raw: bytes, offset: int = 0) -> MorphDeltaRecord:
    if offset < 0 or offset + 6 > len(raw):
        raise ModelbinMorphError("SNORM16 morph record is outside the buffer")

    def snorm(value: int) -> float:
        return max(-1.0, min(1.0, value / 32767.0))

    dx, dy, dz = struct.unpack_from("<hhh", raw, offset)
    return MorphDeltaRecord(snorm(dx), snorm(dy), snorm(dz), None)


def _weighted_sum(records: Iterable[MorphDeltaRecord], weights: Sequence[float]) -> tuple[float, float, float]:
    x = y = z = 0.0
    for record in records:
        if record.target_index is None:
            if not weights:
                raise ModelbinMorphError("morph weights are required")
            target = 0
        else:
            target = record.target_index
        if target >= len(weights):
            raise ModelbinMorphError(
                f"morph target index {target} is outside supplied weights ({len(weights)})"
            )
        weight = float(weights[target])
        if not math.isfinite(weight):
            raise ModelbinMorphError(f"morph weight {target} is not finite")
        x += record.dx * weight
        y += record.dy * weight
        z += record.dz * weight
    return (x, y, z)


def decode_weighted_vertex_morph(
    buffer: MorphBufferInfo,
    vertex_index: int,
    morph_target_count: int,
    weights: Sequence[float],
    *,
    include_normals: bool = True,
) -> WeightedVertexMorph:
    if vertex_index < 0:
        raise ModelbinMorphError(f"vertex index must be non-negative: {vertex_index}")
    if morph_target_count <= 0:
        return WeightedVertexMorph((0.0, 0.0, 0.0), (0.0, 0.0, 0.0) if include_normals else None)
    if buffer.stride <= 0:
        raise ModelbinMorphError("morph buffer stride must be positive")
    if buffer.length > 0 and vertex_index >= buffer.length:
        raise ModelbinMorphError(
            f"vertex index {vertex_index} is outside morph buffer length {buffer.length}"
        )

    base = vertex_index * buffer.stride
    if base + buffer.stride > len(buffer.raw_data):
        raise ModelbinMorphError("vertex morph record is outside raw morph buffer")

    if buffer.format == DXGI_R16G16B16A16_FLOAT:
        position_bytes = morph_target_count * 8
        required = position_bytes * (2 if include_normals else 1)
        if buffer.stride < required:
            raise ModelbinMorphError(
                f"morph stride {buffer.stride} is too small for {morph_target_count} "
                f"target(s); need at least {required}"
            )
        position_records = [
            decode_half4_record(buffer.raw_data, base + i * 8)
            for i in range(morph_target_count)
        ]
        position_delta = _weighted_sum(position_records, weights)
        normal_delta: tuple[float, float, float] | None = None
        if include_normals:
            normal_base = base + position_bytes
            normal_records = [
                decode_half4_record(buffer.raw_data, normal_base + i * 8)
                for i in range(morph_target_count)
            ]
            normal_delta = _weighted_sum(normal_records, weights)
        return WeightedVertexMorph(position_delta, normal_delta)

    if buffer.format == DXGI_R16G16B16A16_SNORM:
        if morph_target_count != 1:
            raise ModelbinMorphError(
                "multi-target SNORM16 morph layout is not verified; refusing to guess"
            )
        if include_normals:
            raise ModelbinMorphError(
                "SNORM16 normal-target layout is not verified; decode position only"
            )
        if buffer.stride < 6:
            raise ModelbinMorphError("SNORM16 morph stride is shorter than one delta")
        record = decode_snorm16_delta(buffer.raw_data, base)
        return WeightedVertexMorph(_weighted_sum((record,), weights), None)

    raise ModelbinMorphError(
        f"unsupported morph buffer DXGI format {buffer.format}; expected 10 or 13"
    )


def decode_damage_delta(buffer: MorphBufferInfo, vertex_index: int) -> tuple[float, float, float]:
    """Decode the single unweighted position delta used by FTS damage preview."""
    if vertex_index < 0:
        raise ModelbinMorphError(f"vertex index must be non-negative: {vertex_index}")
    if buffer.stride <= 0:
        raise ModelbinMorphError("morph buffer stride must be positive")
    if buffer.length > 0 and vertex_index >= buffer.length:
        raise ModelbinMorphError(
            f"vertex index {vertex_index} is outside morph buffer length {buffer.length}"
        )
    base = vertex_index * buffer.stride
    if base + min(buffer.stride, 6) > len(buffer.raw_data):
        raise ModelbinMorphError("damage morph record is outside raw morph buffer")
    if buffer.format == DXGI_R16G16B16A16_FLOAT:
        return (
            _half_to_float(buffer.raw_data, base),
            _half_to_float(buffer.raw_data, base + 2),
            _half_to_float(buffer.raw_data, base + 4),
        )
    if buffer.format == DXGI_R16G16B16A16_SNORM:
        record = decode_snorm16_delta(buffer.raw_data, base)
        return (record.dx, record.dy, record.dz)
    raise ModelbinMorphError(
        f"unsupported damage morph DXGI format {buffer.format}; expected 10 or 13"
    )


def _vec3(value: Sequence[float], label: str) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ModelbinMorphError(f"{label} must contain exactly 3 components")
    result = (float(value[0]), float(value[1]), float(value[2]))
    if not all(math.isfinite(component) for component in result):
        raise ModelbinMorphError(f"{label} contains a non-finite component")
    return result


def _normalize(value: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(value[0] ** 2 + value[1] ** 2 + value[2] ** 2)
    if length <= 1e-20:
        raise ModelbinMorphError("morphed normal has zero length")
    return (value[0] / length, value[1] / length, value[2] / length)


def resolve_morph_vertex_start(min_vertex_index: int, indexed_vertex_offset: int) -> int:
    """Resolve a mesh-local morph start using ForzaTech base-vertex semantics.

    IndexedVertexOffset is a signed BaseVertexLocation.  It is therefore valid for
    the serialized offset itself to be negative; only min_vertex_index plus that
    offset must resolve to a non-negative MBuf vertex index.
    """
    if min_vertex_index < 0:
        raise ModelbinMorphError(
            f"min_vertex_index must be non-negative: {min_vertex_index}"
        )
    resolved = min_vertex_index + indexed_vertex_offset
    if resolved < 0:
        raise ModelbinMorphError(
            "resolved morph vertex start must be non-negative: "
            f"min_vertex_index={min_vertex_index}, indexed_vertex_offset={indexed_vertex_offset}, "
            f"resolved={resolved}"
        )
    return resolved


def apply_weighted_morph(
    base_positions: Sequence[Sequence[float]],
    buffer: MorphBufferInfo,
    indexed_vertex_offset: int,
    morph_target_count: int,
    weights: Sequence[float],
    *,
    min_vertex_index: int = 0,
    base_normals: Sequence[Sequence[float]] | None = None,
) -> tuple[tuple[tuple[float, float, float], ...], tuple[tuple[float, float, float], ...] | None]:
    morph_vertex_start = resolve_morph_vertex_start(
        min_vertex_index,
        indexed_vertex_offset,
    )
    if len(weights) < morph_target_count:
        raise ModelbinMorphError(
            f"need at least {morph_target_count} morph weights, got {len(weights)}"
        )
    if base_normals is not None and len(base_normals) != len(base_positions):
        raise ModelbinMorphError("base normal count must match base position count")

    include_normals = base_normals is not None
    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] | None = [] if include_normals else None

    for local_index, source_position in enumerate(base_positions):
        position = _vec3(source_position, f"base position {local_index}")
        decoded = decode_weighted_vertex_morph(
            buffer,
            morph_vertex_start + local_index,
            morph_target_count,
            weights,
            include_normals=include_normals,
        )
        positions.append(
            (
                position[0] + decoded.position_delta[0],
                position[1] + decoded.position_delta[1],
                position[2] + decoded.position_delta[2],
            )
        )
        if normals is not None and base_normals is not None:
            normal = _vec3(base_normals[local_index], f"base normal {local_index}")
            delta = decoded.normal_delta
            if delta is None:
                raise ModelbinMorphError("normal morph delta is missing")
            normals.append(
                _normalize(
                    (
                        normal[0] + delta[0],
                        normal[1] + delta[1],
                        normal[2] + delta[2],
                    )
                )
            )

    return tuple(positions), tuple(normals) if normals is not None else None
