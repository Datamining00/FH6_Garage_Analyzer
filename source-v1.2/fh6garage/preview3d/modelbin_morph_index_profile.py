from __future__ import annotations

from dataclasses import asdict, dataclass
import struct
from typing import Any

from .modelbin_morph import (
    MESH_TAG,
    BlobRecord,
    ModelbinMorphError,
    _iter_bundle_blobs,
    _version_at_least,
    resolve_morph_vertex_start,
)

INDEX_BUFFER_TAG = 0x496E6442  # IndB


@dataclass(frozen=True)
class IndexBufferInfo:
    blob_index: int
    version_major: int
    version_minor: int
    length: int
    size: int
    stride: int
    format: int
    raw_data: bytes

    def as_dict(self) -> dict[str, Any]:
        return {
            "blob_index": self.blob_index,
            "version": f"{self.version_major}.{self.version_minor}",
            "length": self.length,
            "size": self.size,
            "stride": self.stride,
            "format": self.format,
            "raw_data_size": len(self.raw_data),
        }


@dataclass(frozen=True)
class MeshIndexAddressingProfile:
    mesh_blob_index: int
    mesh_version: str
    index_buffer_blob_index: int
    index_buffer_blob_count: int
    index_buffer_resolution: str
    index_buffer_index: int
    index_buffer_offset_bytes: int
    index_buffer_draw_offset: int
    indexed_vertex_offset: int
    index_count: int
    primitive_count: int
    is_32bit_indices: bool
    index_stride: int
    serialized_index_buffer_stride: int
    stride_matches_mesh: bool
    index_byte_start: int
    index_byte_end: int
    min_vertex_index: int | None
    max_vertex_index: int | None
    resolved_vertex_start: int | None
    resolved_vertex_end: int | None
    resolved_vertex_count: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _MeshIndexFields:
    blob_index: int
    version_major: int
    version_minor: int
    is_32bit_indices: bool
    index_buffer_index: int
    index_buffer_offset: int
    index_buffer_draw_offset: int
    indexed_vertex_offset: int
    index_count: int
    primitive_count: int


def _parse_index_buffer(data: bytes, blob: BlobRecord) -> IndexBufferInfo:
    header_size = 16 if blob.version_major >= 1 else 12
    if blob.data_size < header_size:
        raise ModelbinMorphError(f"IndB blob {blob.blob_index} header is truncated")

    base = blob.data_offset
    length, size = struct.unpack_from("<ii", data, base)
    stride = struct.unpack_from("<H", data, base + 8)[0]
    if length < 0 or size < 0 or stride <= 0:
        raise ModelbinMorphError(
            f"IndB blob {blob.blob_index} has invalid header values: "
            f"length={length}, size={size}, stride={stride}"
        )

    fmt = struct.unpack_from("<i", data, base + 12)[0] if blob.version_major >= 1 else 0
    inferred_size = length * stride if size == 0 and length > 0 else size
    if inferred_size < 0 or header_size + inferred_size > blob.data_size:
        raise ModelbinMorphError(f"IndB blob {blob.blob_index} raw buffer exceeds blob payload")

    raw_start = base + header_size
    raw = bytes(data[raw_start : raw_start + inferred_size])
    return IndexBufferInfo(
        blob_index=blob.blob_index,
        version_major=blob.version_major,
        version_minor=blob.version_minor,
        length=length,
        size=size,
        stride=stride,
        format=fmt,
        raw_data=raw,
    )


def _parse_mesh_index_fields(data: bytes, blob: BlobRecord) -> _MeshIndexFields:
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
            f"Mesh blob {blob.blob_index} has invalid material-group count {material_group_count}"
        )

    material_group_size = 8 if _version_at_least(blob.version_major, blob.version_minor, 1, 9) else 2
    need(material_group_count * material_group_size, "material groups")
    cursor += material_group_count * material_group_size

    # RigidBoneIndex, LODFlags, min/max LOD, bucket flags, bucket order.
    need(9, "fixed pre-morph fields")
    cursor += 9

    if _version_at_least(blob.version_major, blob.version_minor, 1, 2):
        need(1, "skinning element count")
        cursor += 1
        morph_count_size = 4 if _version_at_least(blob.version_major, blob.version_minor, 1, 10) else 1
        need(morph_count_size, "morph target count")
        cursor += morph_count_size

    if _version_at_least(blob.version_major, blob.version_minor, 1, 3):
        need(1, "IsMorphDamage")
        cursor += 1

    need(1 + 2 + 24, "index fields")
    is_32bit_indices = bool(data[cursor])
    cursor += 1
    cursor += 2  # topology
    (
        index_buffer_index,
        index_buffer_offset,
        index_buffer_draw_offset,
        indexed_vertex_offset,
        index_count,
        primitive_count,
    ) = struct.unpack_from("<iiiiii", data, cursor)

    if index_count < 0:
        raise ModelbinMorphError(
            f"Mesh blob {blob.blob_index} has negative index count {index_count}"
        )

    return _MeshIndexFields(
        blob_index=blob.blob_index,
        version_major=blob.version_major,
        version_minor=blob.version_minor,
        is_32bit_indices=is_32bit_indices,
        index_buffer_index=int(index_buffer_index),
        index_buffer_offset=int(index_buffer_offset),
        index_buffer_draw_offset=int(index_buffer_draw_offset),
        indexed_vertex_offset=int(indexed_vertex_offset),
        index_count=int(index_count),
        primitive_count=int(primitive_count),
    )


def _decode_mesh_indices(
    index_buffer: IndexBufferInfo,
    mesh: _MeshIndexFields,
) -> tuple[tuple[int, ...], int, int, int]:
    index_stride = 4 if mesh.is_32bit_indices else 2
    start = mesh.index_buffer_offset + mesh.index_buffer_draw_offset * index_stride
    end = start + mesh.index_count * index_stride
    if start < 0 or end < start or end > len(index_buffer.raw_data):
        raise ModelbinMorphError(
            f"Mesh blob {mesh.blob_index} index range is outside IndB: "
            f"start={start}, end={end}, raw_size={len(index_buffer.raw_data)}"
        )

    if mesh.index_count == 0:
        return (), start, end, index_stride

    values: list[int] = []
    if index_stride == 4:
        for offset in range(start, end, 4):
            value = struct.unpack_from("<i", index_buffer.raw_data, offset)[0]
            if value < 0:
                raise ModelbinMorphError(
                    f"Mesh blob {mesh.blob_index} contains negative 32-bit vertex index {value}"
                )
            values.append(value)
    else:
        for offset in range(start, end, 2):
            values.append(struct.unpack_from("<H", index_buffer.raw_data, offset)[0])
    return tuple(values), start, end, index_stride


def profile_modelbin_index_addressing(data: bytes) -> tuple[MeshIndexAddressingProfile, ...]:
    """Profile FTS-compatible mesh index/base-vertex addressing without modifying geometry.

    ForzaTechStudio resolves mesh indices from the first IndB blob, using
    IndexBufferOffset (bytes) plus IndexBufferDrawOffset (indices), then computes
    the vertex-buffer/morph-buffer start as minIndex + IndexedVertexOffset.
    This profiler preserves those serialized values and reports the resolved range;
    it does not apply morph weights or alter source bytes.
    """
    _, _, blobs = _iter_bundle_blobs(data)
    index_blobs = tuple(blob for blob in blobs if blob.tag == INDEX_BUFFER_TAG)
    if not index_blobs:
        raise ModelbinMorphError("modelbin has no IndB index buffer")

    # Match FTS ModelImporter: the first IndB is the global index buffer.
    index_buffer = _parse_index_buffer(data, index_blobs[0])
    mesh_fields = tuple(
        _parse_mesh_index_fields(data, blob) for blob in blobs if blob.tag == MESH_TAG
    )

    profiles: list[MeshIndexAddressingProfile] = []
    for mesh in mesh_fields:
        indices, byte_start, byte_end, index_stride = _decode_mesh_indices(index_buffer, mesh)
        if indices:
            min_index = min(indices)
            max_index = max(indices)
            resolved_start = resolve_morph_vertex_start(min_index, mesh.indexed_vertex_offset)
            resolved_end = resolve_morph_vertex_start(max_index, mesh.indexed_vertex_offset)
            resolved_count = max_index - min_index + 1
        else:
            min_index = None
            max_index = None
            resolved_start = None
            resolved_end = None
            resolved_count = 0

        profiles.append(
            MeshIndexAddressingProfile(
                mesh_blob_index=mesh.blob_index,
                mesh_version=f"{mesh.version_major}.{mesh.version_minor}",
                index_buffer_blob_index=index_buffer.blob_index,
                index_buffer_blob_count=len(index_blobs),
                index_buffer_resolution="fts_first_indb",
                index_buffer_index=mesh.index_buffer_index,
                index_buffer_offset_bytes=mesh.index_buffer_offset,
                index_buffer_draw_offset=mesh.index_buffer_draw_offset,
                indexed_vertex_offset=mesh.indexed_vertex_offset,
                index_count=mesh.index_count,
                primitive_count=mesh.primitive_count,
                is_32bit_indices=mesh.is_32bit_indices,
                index_stride=index_stride,
                serialized_index_buffer_stride=index_buffer.stride,
                stride_matches_mesh=index_buffer.stride == index_stride,
                index_byte_start=byte_start,
                index_byte_end=byte_end,
                min_vertex_index=min_index,
                max_vertex_index=max_index,
                resolved_vertex_start=resolved_start,
                resolved_vertex_end=resolved_end,
                resolved_vertex_count=resolved_count,
            )
        )
    return tuple(profiles)
