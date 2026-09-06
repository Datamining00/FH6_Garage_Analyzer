from __future__ import annotations

import math
import struct
import unittest

from fh6garage.preview3d.modelbin_morph import (
    BUNDLE_TAG,
    DXGI_R16G16B16A16_FLOAT,
    DXGI_R16G16B16A16_SNORM,
    ID_METADATA_TAG,
    MESH_TAG,
    MORPH_BUFFER_TAG,
    ModelbinMorphError,
    MorphBufferInfo,
    apply_weighted_morph,
    decode_half4_record,
    decode_snorm16_delta,
    decode_weighted_vertex_morph,
    parse_modelbin_morph_inventory,
)


def _half4(x: float, y: float, z: float, target: float) -> bytes:
    return struct.pack("<eeee", x, y, z, target)


def _buffer(raw: bytes, *, stride: int, length: int, fmt: int = DXGI_R16G16B16A16_FLOAT) -> MorphBufferInfo:
    return MorphBufferInfo(
        blob_index=0,
        identifier_id=77,
        version_major=1,
        version_minor=0,
        length=length,
        size=len(raw),
        stride=stride,
        sub_element_count=4,
        format=fmt,
        raw_data=raw,
    )


def _mesh_payload(*, morph_index: int, target_count: int = 2, indexed_vertex_offset: int = 0) -> bytes:
    data = bytearray()
    data += struct.pack("<h", 0)
    data += struct.pack("<h", 1)
    data += struct.pack("<H", 3)
    data += bytes((0, 255))
    data += struct.pack("<H", 1)
    data += bytes((0,))
    data += bytes((0,))
    data += bytes((target_count,))
    data += bytes((0,))
    data += bytes((1,))
    data += struct.pack("<H", 4)
    data += struct.pack("<iiiiii", 0, 0, 0, indexed_vertex_offset, 3, 1)
    data += struct.pack("<i", 0)
    data += struct.pack("<i", 0)
    data += struct.pack("<i", morph_index)
    data += struct.pack("<i", -1)
    return bytes(data)


def _mbuf_payload(raw: bytes, *, stride: int, length: int) -> bytes:
    return struct.pack("<iiHBBi", length, len(raw), stride, 4, 0, DXGI_R16G16B16A16_FLOAT) + raw


def _bundle(*, morph_index: int, identifier_id: int = 77, target_count: int = 2, raw: bytes | None = None) -> bytes:
    if raw is None:
        raw = _half4(1, 0, 0, 0) + _half4(0, 2, 0, 1) + _half4(0, 0, 1, 0) + _half4(0, 1, 0, 1)
    mbuf_payload = _mbuf_payload(raw, stride=len(raw), length=1)
    mesh_payload = _mesh_payload(morph_index=morph_index, target_count=target_count)

    header_size = 0x14
    blob_table_size = 2 * 0x18
    metadata_offset = header_size + blob_table_size
    id_data_offset = metadata_offset + 8
    mbuf_data_offset = id_data_offset + 4
    mesh_data_offset = mbuf_data_offset + len(mbuf_payload)
    data = bytearray(mesh_data_offset + len(mesh_payload))

    struct.pack_into("<I", data, 0, BUNDLE_TAG)
    data[4] = 1
    data[5] = 1
    struct.pack_into("<I", data, 0x10, 2)

    struct.pack_into("<I", data, 0x14, MORPH_BUFFER_TAG)
    data[0x18] = 1
    data[0x19] = 0
    struct.pack_into("<H", data, 0x1A, 1)
    struct.pack_into("<IIII", data, 0x1C, metadata_offset, mbuf_data_offset, 0, len(mbuf_payload))

    mesh_header = 0x14 + 0x18
    struct.pack_into("<I", data, mesh_header, MESH_TAG)
    data[mesh_header + 4] = 1
    data[mesh_header + 5] = 4
    struct.pack_into("<H", data, mesh_header + 6, 0)
    struct.pack_into("<IIII", data, mesh_header + 8, 0, mesh_data_offset, 0, len(mesh_payload))

    struct.pack_into("<IHH", data, metadata_offset, ID_METADATA_TAG, 4 << 4, 8)
    struct.pack_into("<I", data, id_data_offset, identifier_id & 0xFFFFFFFF)
    data[mbuf_data_offset : mbuf_data_offset + len(mbuf_payload)] = mbuf_payload
    data[mesh_data_offset : mesh_data_offset + len(mesh_payload)] = mesh_payload
    return bytes(data)


class ModelbinMorphTests(unittest.TestCase):
    def test_half4_record_decodes_target_selector(self):
        record = decode_half4_record(_half4(1.5, -2.0, 0.25, 3.0))
        self.assertAlmostEqual(record.dx, 1.5)
        self.assertAlmostEqual(record.dy, -2.0)
        self.assertAlmostEqual(record.dz, 0.25)
        self.assertEqual(record.target_index, 3)

    def test_half4_target_selector_must_be_integral(self):
        with self.assertRaises(ModelbinMorphError):
            decode_half4_record(_half4(0, 0, 0, 1.5))

    def test_snorm16_clamps_negative_full_scale(self):
        record = decode_snorm16_delta(struct.pack("<hhh", -32768, 32767, 0))
        self.assertEqual(record.dx, -1.0)
        self.assertEqual(record.dy, 1.0)
        self.assertEqual(record.dz, 0.0)

    def test_general_half_morph_accumulates_position_and_normal_targets(self):
        raw = _half4(1, 0, 0, 0) + _half4(0, 2, 0, 1) + _half4(0, 0, 1, 0) + _half4(0, 1, 0, 1)
        decoded = decode_weighted_vertex_morph(_buffer(raw, stride=32, length=1), 0, 2, [0.5, 2.0])
        self.assertEqual(decoded.position_delta, (0.5, 4.0, 0.0))
        self.assertEqual(decoded.normal_delta, (0.0, 2.0, 0.5))

    def test_indexed_vertex_offset_selects_absolute_morph_record(self):
        zero = b"\x00" * 32
        second = _half4(2, 0, 0, 0) + _half4(0, 0, 0, 1) + _half4(0, 0, 0, 0) + _half4(0, 0, 0, 1)
        positions, normals = apply_weighted_morph(
            [(10, 0, 0)],
            _buffer(zero + second, stride=32, length=2),
            indexed_vertex_offset=1,
            morph_target_count=2,
            weights=[0.5, 0],
        )
        self.assertEqual(positions, ((11.0, 0.0, 0.0),))
        self.assertIsNone(normals)

    def test_weight_target_out_of_range_fails_closed(self):
        raw = _half4(1, 0, 0, 2)
        with self.assertRaises(ModelbinMorphError):
            decode_weighted_vertex_morph(_buffer(raw, stride=8, length=1), 0, 1, [1.0], include_normals=False)

    def test_general_morph_rejects_short_stride(self):
        raw = _half4(1, 0, 0, 0) * 2
        with self.assertRaises(ModelbinMorphError):
            decode_weighted_vertex_morph(_buffer(raw, stride=16, length=1), 0, 2, [1, 1], include_normals=True)

    def test_snorm16_multi_target_layout_is_not_guessed(self):
        raw = struct.pack("<hhhh", 100, 0, 0, 0)
        with self.assertRaises(ModelbinMorphError):
            decode_weighted_vertex_morph(
                _buffer(raw, stride=8, length=1, fmt=DXGI_R16G16B16A16_SNORM),
                0,
                2,
                [1, 1],
                include_normals=False,
            )

    def test_apply_weighted_morph_normalizes_normal(self):
        raw = _half4(1, 0, 0, 0) + _half4(0, 1, 0, 0)
        positions, normals = apply_weighted_morph(
            [(2, 0, 0)],
            _buffer(raw, stride=16, length=1),
            indexed_vertex_offset=0,
            morph_target_count=1,
            weights=[0.5],
            base_normals=[(1, 0, 0)],
        )
        self.assertEqual(positions, ((2.5, 0.0, 0.0),))
        self.assertIsNotNone(normals)
        nx, ny, nz = normals[0]
        self.assertAlmostEqual(math.sqrt(nx * nx + ny * ny + nz * nz), 1.0)
        self.assertGreater(ny, 0.0)

    def test_inventory_resolves_mbuf_by_identifier_before_ordinal(self):
        source = _bundle(morph_index=77, identifier_id=77)
        before = bytes(source)
        inventory = parse_modelbin_morph_inventory(source)
        self.assertEqual(source, before)
        self.assertEqual(len(inventory.morph_buffers), 1)
        self.assertEqual(len(inventory.mesh_bindings), 1)
        self.assertEqual(inventory.mesh_bindings[0].morph_target_count, 2)
        self.assertEqual(inventory.resolutions[0].resolved_by, "identifier")
        self.assertEqual(inventory.resolutions[0].morph_buffer_blob_index, 0)

    def test_inventory_uses_fts_ordinal_fallback(self):
        inventory = parse_modelbin_morph_inventory(_bundle(morph_index=0, identifier_id=77))
        self.assertEqual(inventory.resolutions[0].resolved_by, "ordinal_fallback")
        self.assertEqual(inventory.resolutions[0].morph_buffer_blob_index, 0)

    def test_inventory_reports_unresolved_binding(self):
        inventory = parse_modelbin_morph_inventory(_bundle(morph_index=9, identifier_id=77))
        self.assertEqual(inventory.resolutions[0].resolved_by, "unresolved")
        self.assertIsNone(inventory.resolutions[0].morph_buffer_blob_index)

    def test_malformed_blob_offset_fails_closed(self):
        source = bytearray(_bundle(morph_index=77))
        struct.pack_into("<I", source, 0x14 + 12, len(source) + 100)
        with self.assertRaises(ModelbinMorphError):
            parse_modelbin_morph_inventory(bytes(source))


if __name__ == "__main__":
    unittest.main()
