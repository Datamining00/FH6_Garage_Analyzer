from __future__ import annotations

from dataclasses import asdict, dataclass
import struct
from typing import Any

from .modelbin_morph import ModelbinMorphError, resolve_morph_vertex_start

BUNDLE_TAG = 0x47727562  # Grub
INDEX_BUFFER_TAG = 0x496E6442  # IndB


@dataclass(frozen=True)
class IndexDrawRange:
    index_buffer_blob_index: int
    buffer_version: str
    buffer_length: int
    buffer_size: int
    buffer_stride: int
    index_stride: int
    start_byte: int
    end_byte: int
    index_count: int
    min_index: int
    max_index: int
    indexed_vertex_offset: int
    resolved_morph_vertex_start: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _IndexBuffer:
    blob_index: int
    version_major: int
    version_minor: int
    length: int
    size: int
    stride: int
    raw_data: bytes


class ModelbinIndexRangeError(ModelbinMorphError):
    """Raised when a mesh draw range cannot be resolved without guessing."""


def _version_at_least(major: int, minor: int, want_major: int, want_minor: int) -> bool:
    return major > want_major or (major == want_major and minor >= want_minor)


def _require_range(data: bytes, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ModelbinIndexRangeError(f"{label} is outside the modelbin")


def _first_index_buffer(data: bytes) -> _IndexBuffer:
    if len(data) < 0x14 or struct.unpack_from("<I", data, 0)[0] != BUNDLE_TAG:
        raise ModelbinIndexRangeError("modelbin is not a supported Grub bundle")

    bundle_major, bundle_minor = int(data[4]), int(data[5])
    modern = _version_at_least(bundle_major, bundle_minor, 1, 1)
    if modern:
        blob_count = struct.unpack_from("<I", data, 0x10)[0]
        headers_start = 0x14
    else:
        blob_count = struct.unpack_from("<H", data, 0x06)[0]
        headers_start = 0x10
    if blob_count > 100000:
        raise ModelbinIndexRangeError(f"modelbin has implausible blob count {blob_count}")
    _require_range(data, headers_start, blob_count * 0x18, "blob table")

    for blob_index in range(blob_count):
        header = headers_start + blob_index * 0x18
        tag = struct.unpack_from("<I", data, header)[0]
        if tag != INDEX_BUFFER_TAG:
            continue
        major, minor = int(data[header + 4]), int(data[header + 5])
        _, data_offset, compressed_size, uncompressed_size = struct.unpack_from(
            "<IIII", data, header + 8
        )
        payload_size = int(uncompressed_size or compressed_size)
        _require_range(data, data_offset, payload_size, f"IndB blob {blob_index} payload")

        header_size = 16 if major >= 1 else 12
        if payload_size < header_size:
            raise ModelbinIndexRangeError(f"IndB blob {blob_index} header is truncated")
        length, size = struct.unpack_from("<ii", data, data_offset)
        stride = struct.unpack_from("<H", data, data_offset + 8)[0]
        if length < 0 or size < 0 or stride <= 0:
            raise ModelbinIndexRangeError(
                f"IndB blob {blob_index} has invalid length/size/stride"
            )
        inferred_size = size if size > 0 else length * stride
        if length > 0 and inferred_size < length * stride:
            raise ModelbinIndexRangeError(
                f"IndB blob {blob_index} size {inferred_size} is smaller than length*stride "
                f"({length * stride})"
            )
        if header_size + inferred_size > payload_size:
            raise ModelbinIndexRangeError(
                f"IndB blob {blob_index} raw buffer exceeds blob payload"
            )
        raw_start = data_offset + header_size
        raw_data = bytes(data[raw_start : raw_start + inferred_size])
        return _IndexBuffer(
            blob_index=blob_index,
            version_major=major,
            version_minor=minor,
            length=length,
            size=size,
            stride=stride,
            raw_data=raw_data,
        )

    raise ModelbinIndexRangeError("modelbin has no IndB index buffer")


def resolve_modelbin_draw_index_range(
    data: bytes,
    *,
    is_32_bit_indices: bool,
    index_buffer_offset: int,
    index_buffer_draw_offset: int,
    index_count: int,
    indexed_vertex_offset: int,
) -> IndexDrawRange:
    """Resolve the draw's min/max index and signed morph-buffer start.

    This mirrors the audited ForzaTech addressing contract:
      start byte = IndexBufferOffset + IndexBufferDrawOffset * index_stride
      morph start = min_index + IndexedVertexOffset

    The first IndB is used because that is the standard Forza model importer path.
    No vehicle-specific correction or offset clamping is performed.
    """
    if index_buffer_offset < 0:
        raise ModelbinIndexRangeError(
            f"index_buffer_offset must be non-negative: {index_buffer_offset}"
        )
    if index_buffer_draw_offset < 0:
        raise ModelbinIndexRangeError(
            f"index_buffer_draw_offset must be non-negative: {index_buffer_draw_offset}"
        )
    if index_count <= 0:
        raise ModelbinIndexRangeError(f"index_count must be positive: {index_count}")

    buffer = _first_index_buffer(data)
    index_stride = 4 if is_32_bit_indices else 2
    if buffer.stride != index_stride:
        raise ModelbinIndexRangeError(
            f"IndB stride {buffer.stride} does not match mesh index stride {index_stride}"
        )

    start_byte = index_buffer_offset + index_buffer_draw_offset * index_stride
    byte_count = index_count * index_stride
    end_byte = start_byte + byte_count
    if start_byte < 0 or end_byte > len(buffer.raw_data):
        raise ModelbinIndexRangeError(
            f"mesh index draw [{start_byte}, {end_byte}) is outside IndB raw buffer "
            f"({len(buffer.raw_data)} bytes)"
        )

    if is_32_bit_indices:
        values = struct.unpack_from(f"<{index_count}I", buffer.raw_data, start_byte)
    else:
        values = struct.unpack_from(f"<{index_count}H", buffer.raw_data, start_byte)
    min_index = int(min(values))
    max_index = int(max(values))
    resolved_start = resolve_morph_vertex_start(min_index, indexed_vertex_offset)

    return IndexDrawRange(
        index_buffer_blob_index=buffer.blob_index,
        buffer_version=f"{buffer.version_major}.{buffer.version_minor}",
        buffer_length=buffer.length,
        buffer_size=buffer.size,
        buffer_stride=buffer.stride,
        index_stride=index_stride,
        start_byte=start_byte,
        end_byte=end_byte,
        index_count=index_count,
        min_index=min_index,
        max_index=max_index,
        indexed_vertex_offset=indexed_vertex_offset,
        resolved_morph_vertex_start=resolved_start,
    )
