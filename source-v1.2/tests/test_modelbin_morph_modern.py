from __future__ import annotations

import struct
import unittest

from fh6garage.preview3d.modelbin_morph import (
    BUNDLE_TAG,
    DXGI_R16G16B16A16_FLOAT,
    ID_METADATA_TAG,
    MESH_TAG,
    MORPH_BUFFER_TAG,
    parse_modelbin_morph_inventory,
)


def _half4(x: float, y: float, z: float, target: float) -> bytes:
    return struct.pack("<eeee", x, y, z, target)


def _modern_mesh_payload(morph_index: int) -> bytes:
    data = bytearray()
    data += struct.pack("<i", 1)
    data += struct.pack("<hhhh", -1, 0, -1, -1)
    data += struct.pack("<h", 1)
    data += struct.pack("<H", 3)
    data += bytes((0, 255))
    data += struct.pack("<H", 1)
    data += bytes((0,))
    data += bytes((0,))
    data += struct.pack("<I", 2)
    data += bytes((0,))
    data += bytes((1,))
    data += struct.pack("<H", 4)
    data += struct.pack("<iiiiii", 0, 0, 0, 5, 6, 2)
    data += struct.pack("<fI", 0.65, 2)
    data += struct.pack("<I", 2)
    data += struct.pack("<II", 5, 6)
    data += struct.pack("<i", 3)
    data += struct.pack("<i", 1)
    data += struct.pack("<iIIII", 9, 0, 28, 0, 0)
    data += struct.pack("<i", morph_index)
    data += struct.pack("<i", -1)
    return bytes(data)


def _modern_bundle(morph_index: int = 301, identifier_id: int = 301) -> bytes:
    raw = (
        _half4(1, 0, 0, 0)
        + _half4(0, 1, 0, 1)
        + _half4(0, 0, 1, 0)
        + _half4(0, 0, 1, 1)
    )
    mbuf_payload = struct.pack(
        "<iiHBBi", 8, len(raw) * 8, len(raw), 4, 0, DXGI_R16G16B16A16_FLOAT
    ) + raw * 8
    mesh_payload = _modern_mesh_payload(morph_index)

    metadata_offset = 0x14 + 2 * 0x18
    id_data_offset = metadata_offset + 8
    mbuf_data_offset = id_data_offset + 4
    mesh_data_offset = mbuf_data_offset + len(mbuf_payload)
    data = bytearray(mesh_data_offset + len(mesh_payload))

    struct.pack_into("<I", data, 0, BUNDLE_TAG)
    data[4], data[5] = 1, 1
    struct.pack_into("<I", data, 0x10, 2)

    mbuf_header = 0x14
    struct.pack_into("<I", data, mbuf_header, MORPH_BUFFER_TAG)
    data[mbuf_header + 4], data[mbuf_header + 5] = 1, 0
    struct.pack_into("<H", data, mbuf_header + 6, 1)
    struct.pack_into(
        "<IIII",
        data,
        mbuf_header + 8,
        metadata_offset,
        mbuf_data_offset,
        0,
        len(mbuf_payload),
    )

    mesh_header = 0x14 + 0x18
    struct.pack_into("<I", data, mesh_header, MESH_TAG)
    data[mesh_header + 4], data[mesh_header + 5] = 1, 13
    struct.pack_into("<H", data, mesh_header + 6, 0)
    struct.pack_into(
        "<IIII",
        data,
        mesh_header + 8,
        0,
        mesh_data_offset,
        0,
        len(mesh_payload),
    )

    struct.pack_into("<IHH", data, metadata_offset, ID_METADATA_TAG, 4 << 4, 8)
    struct.pack_into("<I", data, id_data_offset, identifier_id)
    data[mbuf_data_offset : mbuf_data_offset + len(mbuf_payload)] = mbuf_payload
    data[mesh_data_offset : mesh_data_offset + len(mesh_payload)] = mesh_payload
    return bytes(data)


class ModernModelbinMorphTests(unittest.TestCase):
    def test_v113_mesh_wire_layout_reaches_morph_binding(self):
        inventory = parse_modelbin_morph_inventory(_modern_bundle())
        mesh = inventory.mesh_bindings[0]
        self.assertEqual(mesh.version_major, 1)
        self.assertEqual(mesh.version_minor, 13)
        self.assertEqual(mesh.morph_target_count, 2)
        self.assertEqual(mesh.indexed_vertex_offset, 5)
        self.assertEqual(mesh.morph_data_buffer_index, 301)
        self.assertEqual(inventory.resolutions[0].resolved_by, "identifier")

    def test_v113_mesh_still_uses_fts_ordinal_fallback(self):
        inventory = parse_modelbin_morph_inventory(
            _modern_bundle(morph_index=0, identifier_id=301)
        )
        self.assertEqual(inventory.resolutions[0].resolved_by, "ordinal_fallback")
        self.assertEqual(inventory.resolutions[0].morph_buffer_blob_index, 0)


if __name__ == "__main__":
    unittest.main()
