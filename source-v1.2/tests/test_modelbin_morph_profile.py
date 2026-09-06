from __future__ import annotations

import struct
import unittest

from fh6garage.preview3d.modelbin_morph import (
    DXGI_R16G16B16A16_FLOAT,
    DXGI_R16G16B16A16_SNORM,
    ModelbinMorphError,
    MorphBufferInfo,
)
from fh6garage.preview3d.modelbin_morph_profile import profile_weighted_morph_targets


def _half4(x: float, y: float, z: float, selector: float) -> bytes:
    return struct.pack("<eeee", x, y, z, selector)


def _buffer(raw: bytes, *, stride: int, length: int, fmt: int = DXGI_R16G16B16A16_FLOAT) -> MorphBufferInfo:
    return MorphBufferInfo(
        blob_index=5,
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


class ModelbinMorphProfileTests(unittest.TestCase):
    def test_profiles_selectors_from_record_selector_not_slot_order(self):
        vertex0 = (
            _half4(2, 0, 0, 1)
            + _half4(0, 3, 0, 0)
            + _half4(0, 0, 0, 1)
            + _half4(0, 0, 0, 0)
        )
        vertex1 = (
            _half4(0, -1, 0, 0)
            + _half4(-4, 0, 0, 1)
            + _half4(0, 0, 0, 0)
            + _half4(0, 0, 0, 1)
        )
        raw = vertex0 + vertex1
        before = bytes(raw)

        profile = profile_weighted_morph_targets(_buffer(raw, stride=32, length=2), 2)

        self.assertEqual(raw, before)
        self.assertEqual(profile.profiled_vertex_count, 2)
        self.assertEqual(profile.missing_selectors, ())
        self.assertEqual([item.selector for item in profile.selectors], [0, 1])

        selector0, selector1 = profile.selectors
        self.assertEqual(selector0.record_count, 2)
        self.assertEqual(selector0.nonzero_record_count, 2)
        self.assertEqual(selector0.sum_abs_delta, (0.0, 4.0, 0.0))
        self.assertEqual(selector0.mean_abs_delta, (0.0, 2.0, 0.0))
        self.assertEqual(selector0.max_abs_delta, (0.0, 3.0, 0.0))
        self.assertEqual(selector0.min_signed_delta, (0.0, -1.0, 0.0))
        self.assertEqual(selector0.max_signed_delta, (0.0, 3.0, 0.0))

        self.assertEqual(selector1.record_count, 2)
        self.assertEqual(selector1.nonzero_record_count, 2)
        self.assertEqual(selector1.sum_abs_delta, (6.0, 0.0, 0.0))
        self.assertEqual(selector1.mean_abs_delta, (3.0, 0.0, 0.0))
        self.assertEqual(selector1.max_abs_delta, (4.0, 0.0, 0.0))
        self.assertEqual(selector1.min_signed_delta, (-4.0, 0.0, 0.0))
        self.assertEqual(selector1.max_signed_delta, (2.0, 0.0, 0.0))

    def test_rejects_selector_outside_declared_target_count(self):
        raw = _half4(1, 0, 0, 2) + _half4(0, 0, 0, 0)
        with self.assertRaises(ModelbinMorphError):
            profile_weighted_morph_targets(_buffer(raw, stride=16, length=1), 2)

    def test_rejects_unverified_snorm_weighted_layout(self):
        raw = b"\x00" * 16
        with self.assertRaises(ModelbinMorphError):
            profile_weighted_morph_targets(
                _buffer(raw, stride=16, length=1, fmt=DXGI_R16G16B16A16_SNORM),
                2,
            )

    def test_rejects_stride_shorter_than_position_records(self):
        raw = _half4(1, 0, 0, 0)
        with self.assertRaises(ModelbinMorphError):
            profile_weighted_morph_targets(_buffer(raw, stride=8, length=1), 2)


if __name__ == "__main__":
    unittest.main()
