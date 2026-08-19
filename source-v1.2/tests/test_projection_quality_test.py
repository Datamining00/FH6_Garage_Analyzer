from __future__ import annotations

import unittest

from PIL import Image

from fh6garage.livery_preview_projection_quality_test import (
    _aa_polygon_mask,
    _mask_premultiplied_float,
    _mask_premultiplied_u8,
    _premultiply_rgba,
    mode_label,
    normalize_mode,
)


class ProjectionQualityTestHelpers(unittest.TestCase):
    def test_mode_normalization_and_labels(self) -> None:
        self.assertEqual(normalize_mode("A"), "a")
        self.assertEqual(normalize_mode("d"), "d")
        self.assertEqual(normalize_mode("unknown"), "a")
        self.assertIn("BICUBIC", mode_label("b"))
        self.assertIn("premultiplied", mode_label("c"))
        self.assertIn("subpixel", mode_label("d"))

    def test_local_subpixel_polygon_mask_has_partial_edge_coverage(self) -> None:
        mask = _aa_polygon_mask(
            [[(0.25, 0.25), (7.75, 1.25), (2.25, 7.75)]],
            (0, 0, 8, 8),
            samples=2,
        )
        self.assertIsNotNone(mask)
        values = set(mask.getdata())
        self.assertIn(255, values)
        self.assertTrue(any(0 < value < 255 for value in values))

    def test_premultiplied_mask_paths_keep_visible_color_stable(self) -> None:
        source = Image.new("RGBA", (3, 1), (240, 20, 10, 0))
        source.putpixel((1, 0), (240, 20, 10, 255))
        premultiplied = _premultiply_rgba(source)
        mask = Image.new("L", (3, 1), 128)

        u8 = _mask_premultiplied_u8(premultiplied, mask)
        fp = _mask_premultiplied_float(premultiplied, mask)

        for image in (u8, fp):
            red, green, blue, alpha = image.getpixel((1, 0))
            self.assertGreaterEqual(alpha, 127)
            self.assertLessEqual(alpha, 129)
            self.assertGreater(red, 230)
            self.assertLess(green, 30)
            self.assertLess(blue, 20)


if __name__ == "__main__":
    unittest.main()
