from __future__ import annotations

import struct
import unittest

from fh6garage.preview3d.modelbin_morph import BUNDLE_TAG, MESH_TAG, ModelbinMorphError
from fh6garage.preview3d.modelbin_morph_index_profile import (
    INDEX_BUFFER_TAG,
    profile_modelbin_index_addressing,
)


def _index_payload(values: list[int], *, stride: int = 2) -> bytes:
    if stride == 2:
        raw = b"".join(struct.pack("<H", value) for value in values)
        fmt = 57  # DXGI_FORMAT_R16_UINT
    elif stride == 4:
        raw = b"".join(struct.pack("<i", value) for value in values)
        fmt = 42  # DXGI_FORMAT_R32_UINT
    else:
        raise ValueError(stride)
    return struct.pack("<iiHBBi", len(values), len(raw), stride, 1, 0, fmt) + raw


def _mesh_payload(
    *,
    draw_offset: int,
    base_vertex: int,
    index_count: int,
    index_buffer_offset: int = 0,
    is_32bit: bool = False,
) -> bytes:
    data = bytearray()
    data += struct.pack("<h", 0)  # material id, pre-v1.9
    data += struct.pack("<h", 0)  # rigid bone
    data += struct.pack("<H", 3)  # lod flags
    data += bytes((0, 255))        # min/max lod
    data += struct.pack("<H", 1)  # bucket flags
    data += bytes((0,))            # bucket order
    data += bytes((0,))            # skinning element count
    data += bytes((2,))            # morph target count, pre-v1.10
    data += bytes((0,))            # IsMorphDamage
    data += bytes((1 if is_32bit else 0,))
    data += struct.pack("<H", 4)   # triangle list
    data += struct.pack(
        "<iiiiii",
        0,                          # IndexBufferIndex
        index_buffer_offset,        # IndexBufferOffset, bytes
        draw_offset,                # IndexBufferDrawOffset, indices
        base_vertex,                # IndexedVertexOffset / BaseVertexLocation
        index_count,
        index_count // 3,
    )
    return bytes(data)


def _bundle(index_payload: bytes, mesh_payload: bytes) -> bytes:
    header_size = 0x14
    blob_table_size = 2 * 0x18
    index_data_offset = header_size + blob_table_size
    mesh_data_offset = index_data_offset + len(index_payload)
    data = bytearray(mesh_data_offset + len(mesh_payload))

    struct.pack_into("<I", data, 0, BUNDLE_TAG)
    data[4] = 1
    data[5] = 1
    struct.pack_into("<I", data, 0x10, 2)

    struct.pack_into("<I", data, 0x14, INDEX_BUFFER_TAG)
    data[0x18] = 1
    data[0x19] = 0
    struct.pack_into("<H", data, 0x1A, 0)
    struct.pack_into("<IIII", data, 0x1C, 0, index_data_offset, 0, len(index_payload))

    mesh_header = 0x14 + 0x18
    struct.pack_into("<I", data, mesh_header, MESH_TAG)
    data[mesh_header + 4] = 1
    data[mesh_header + 5] = 4
    struct.pack_into("<H", data, mesh_header + 6, 0)
    struct.pack_into("<IIII", data, mesh_header + 8, 0, mesh_data_offset, 0, len(mesh_payload))

    data[index_data_offset : index_data_offset + len(index_payload)] = index_payload
    data[mesh_data_offset : mesh_data_offset + len(mesh_payload)] = mesh_payload
    return bytes(data)


class ModelbinMorphIndexProfileTests(unittest.TestCase):
    def test_signed_base_vertex_resolves_from_actual_index_minimum(self):
        source = _bundle(
            _index_payload([100, 101, 102, 103, 104]),
            _mesh_payload(draw_offset=1, base_vertex=-101, index_count=3),
        )
        before = bytes(source)
        profiles = profile_modelbin_index_addressing(source)
        self.assertEqual(source, before)
        self.assertEqual(len(profiles), 1)
        profile = profiles[0]
        self.assertEqual(profile.min_vertex_index, 101)
        self.assertEqual(profile.max_vertex_index, 103)
        self.assertEqual(profile.indexed_vertex_offset, -101)
        self.assertEqual(profile.resolved_vertex_start, 0)
        self.assertEqual(profile.resolved_vertex_end, 2)
        self.assertEqual(profile.resolved_vertex_count, 3)
        self.assertEqual(profile.index_byte_start, 2)
        self.assertEqual(profile.index_byte_end, 8)
        self.assertTrue(profile.stride_matches_mesh)
        self.assertEqual(profile.index_buffer_resolution, "fts_first_indb")

    def test_index_buffer_offset_is_bytes_and_draw_offset_is_indices(self):
        prefix = struct.pack("<i", 999)
        values = [10, 20, 21, 22]
        raw = prefix + b"".join(struct.pack("<i", value) for value in values)
        index_payload = struct.pack("<iiHBBi", len(raw) // 4, len(raw), 4, 1, 0, 42) + raw
        source = _bundle(
            index_payload,
            _mesh_payload(
                draw_offset=1,
                base_vertex=-20,
                index_count=3,
                index_buffer_offset=4,
                is_32bit=True,
            ),
        )
        profile = profile_modelbin_index_addressing(source)[0]
        self.assertEqual(profile.index_byte_start, 8)
        self.assertEqual(profile.min_vertex_index, 20)
        self.assertEqual(profile.max_vertex_index, 22)
        self.assertEqual(profile.resolved_vertex_start, 0)
        self.assertEqual(profile.resolved_vertex_end, 2)

    def test_negative_resolved_vertex_address_fails_closed(self):
        source = _bundle(
            _index_payload([100, 101, 102]),
            _mesh_payload(draw_offset=0, base_vertex=-101, index_count=3),
        )
        with self.assertRaises(ModelbinMorphError):
            profile_modelbin_index_addressing(source)


if __name__ == "__main__":
    unittest.main()
