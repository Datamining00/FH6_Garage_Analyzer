from __future__ import annotations

import struct
import unittest

from fh6garage.preview3d.modelbin_index_range import (
    BUNDLE_TAG,
    INDEX_BUFFER_TAG,
    ModelbinIndexRangeError,
    resolve_modelbin_draw_index_range,
)


def _index_bundle(indices: list[int], *, stride: int) -> bytes:
    if stride not in (2, 4):
        raise ValueError("test stride must be 2 or 4")
    fmt = "H" if stride == 2 else "I"
    raw = struct.pack("<" + fmt * len(indices), *indices)
    payload = struct.pack("<iiHBBi", len(indices), len(raw), stride, 1, 0, 0) + raw

    data_offset = 0x14 + 0x18
    source = bytearray(data_offset + len(payload))
    struct.pack_into("<I", source, 0, BUNDLE_TAG)
    source[4] = 1
    source[5] = 1
    struct.pack_into("<I", source, 0x10, 1)

    struct.pack_into("<I", source, 0x14, INDEX_BUFFER_TAG)
    source[0x18] = 1
    source[0x19] = 0
    struct.pack_into("<H", source, 0x1A, 0)
    struct.pack_into("<IIII", source, 0x1C, 0, data_offset, 0, len(payload))
    source[data_offset:] = payload
    return bytes(source)


class ModelbinIndexRangeTests(unittest.TestCase):
    def test_fxx_style_negative_base_vertex_resolves_from_draw_minimum(self):
        source = _index_bundle([999, 3214, 3212, 3213, 888], stride=2)
        before = bytes(source)
        report = resolve_modelbin_draw_index_range(
            source,
            is_32_bit_indices=False,
            index_buffer_offset=0,
            index_buffer_draw_offset=1,
            index_count=3,
            indexed_vertex_offset=-3212,
        )
        self.assertEqual(source, before)
        self.assertEqual(report.min_index, 3212)
        self.assertEqual(report.max_index, 3214)
        self.assertEqual(report.resolved_morph_vertex_start, 0)
        self.assertEqual(report.start_byte, 2)
        self.assertEqual(report.end_byte, 8)

    def test_index_buffer_offset_is_bytes_and_draw_offset_is_indices(self):
        source = _index_bundle([10, 20, 30, 40, 50], stride=2)
        report = resolve_modelbin_draw_index_range(
            source,
            is_32_bit_indices=False,
            index_buffer_offset=2,
            index_buffer_draw_offset=1,
            index_count=2,
            indexed_vertex_offset=-20,
        )
        self.assertEqual(report.start_byte, 4)
        self.assertEqual(report.min_index, 30)
        self.assertEqual(report.max_index, 40)
        self.assertEqual(report.resolved_morph_vertex_start, 10)

    def test_32_bit_indices_use_four_byte_stride(self):
        source = _index_bundle([70000, 70005, 70002], stride=4)
        report = resolve_modelbin_draw_index_range(
            source,
            is_32_bit_indices=True,
            index_buffer_offset=0,
            index_buffer_draw_offset=0,
            index_count=3,
            indexed_vertex_offset=-70000,
        )
        self.assertEqual(report.index_stride, 4)
        self.assertEqual(report.min_index, 70000)
        self.assertEqual(report.max_index, 70005)
        self.assertEqual(report.resolved_morph_vertex_start, 0)

    def test_mesh_and_indb_stride_mismatch_fails_closed(self):
        source = _index_bundle([1, 2, 3], stride=4)
        with self.assertRaises(ModelbinIndexRangeError):
            resolve_modelbin_draw_index_range(
                source,
                is_32_bit_indices=False,
                index_buffer_offset=0,
                index_buffer_draw_offset=0,
                index_count=3,
                indexed_vertex_offset=0,
            )

    def test_draw_outside_indb_fails_closed(self):
        source = _index_bundle([1, 2, 3], stride=2)
        with self.assertRaises(ModelbinIndexRangeError):
            resolve_modelbin_draw_index_range(
                source,
                is_32_bit_indices=False,
                index_buffer_offset=0,
                index_buffer_draw_offset=2,
                index_count=2,
                indexed_vertex_offset=0,
            )

    def test_negative_resolved_morph_address_fails_closed(self):
        source = _index_bundle([100, 101, 102], stride=2)
        with self.assertRaises(ModelbinIndexRangeError):
            resolve_modelbin_draw_index_range(
                source,
                is_32_bit_indices=False,
                index_buffer_offset=0,
                index_buffer_draw_offset=0,
                index_count=3,
                indexed_vertex_offset=-101,
            )


if __name__ == "__main__":
    unittest.main()
