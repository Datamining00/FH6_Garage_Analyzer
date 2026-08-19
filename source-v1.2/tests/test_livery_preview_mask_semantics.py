from __future__ import annotations

import unittest

from fh6garage.livery_preview import LiveryPreviewError
from fh6garage.livery_preview_mask_semantics import validate_exact_assets_and_filter_noops


class FakeRenderer:
    def _shape_mask_flag(self, shape, data):
        return bool(shape.get("mask"))

    def _resolve_vinyl_resource(self, type_code, shape):
        if type_code == 999:
            return None
        return ("Primitives", int(type_code or 1))

    def _resource_alpha_triangles(self, family, index):
        if index == 3:
            return [([(0, 0), (1, 0), (0, 1)], (255, 128, 0))]
        if index == 4:
            return [([(0, 0), (1, 0), (0, 1)], (0, 0, 0))]
        return [([(0, 0), (1, 0), (0, 1)], (255, 255, 255))]

    def _shape_word_from_shape(self, shape, type_code):
        return int(type_code) & 0xFFFF


class MaskSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.renderer = FakeRenderer()

    def test_zero_color_alpha_ordinary_native_mask_is_preserved(self):
        layer = {
            "type": 1,
            "data": [0, 0, 1, 1, 0, 0, 1],
            "color": [0, 0, 0, 0],
            "mask": True,
        }
        visible, skipped = validate_exact_assets_and_filter_noops(
            self.renderer, [layer], None
        )
        self.assertEqual(visible, [layer])
        self.assertEqual(skipped, 0)

    def test_zero_color_alpha_gradient_mask_is_real_noop(self):
        layer = {
            "type": 3,
            "data": [0, 0, 1, 1, 0, 0, 1],
            "color": [0, 0, 0, 0],
            "mask": True,
        }
        visible, skipped = validate_exact_assets_and_filter_noops(
            self.renderer, [layer], None
        )
        self.assertEqual(visible, [])
        self.assertEqual(skipped, 1)

    def test_zero_alpha_visible_layer_is_removed(self):
        layer = {
            "type": 1,
            "data": [0, 0, 1, 1, 0, 0, 0],
            "color": [255, 0, 0, 0],
            "mask": False,
        }
        visible, skipped = validate_exact_assets_and_filter_noops(
            self.renderer, [layer], None
        )
        self.assertEqual(visible, [])
        self.assertEqual(skipped, 1)

    def test_native_zero_opacity_is_removed_even_for_mask(self):
        layer = {
            "type": 4,
            "data": [0, 0, 1, 1, 0, 0, 1],
            "color": [255, 255, 255, 255],
            "mask": True,
        }
        visible, skipped = validate_exact_assets_and_filter_noops(
            self.renderer, [layer], None
        )
        self.assertEqual(visible, [])
        self.assertEqual(skipped, 1)

    def test_missing_native_resource_still_fails_closed(self):
        layer = {
            "type": 999,
            "data": [0, 0, 1, 1, 0, 0, 0],
            "color": [255, 255, 255, 255],
            "mask": False,
        }
        with self.assertRaises(LiveryPreviewError):
            validate_exact_assets_and_filter_noops(self.renderer, [layer], None)


if __name__ == "__main__":
    unittest.main()
