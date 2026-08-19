from __future__ import annotations

import unittest

from fh6garage.livery_preview_tiled_quality import (
    RETAINED_SCALE_LIMIT,
    SUPPORTED_SCALES,
    _intersect,
    _source_region_for_output,
    normalize_scale,
)


class TiledQualityTests(unittest.TestCase):
    def test_all_requested_scales_are_supported(self):
        self.assertEqual(SUPPORTED_SCALES, (1, 2, 4, 8, 16))
        for scale in SUPPORTED_SCALES:
            self.assertEqual(normalize_scale(scale), scale)
        self.assertEqual(RETAINED_SCALE_LIMIT, 4)

    def test_invalid_scale_falls_back_to_four(self):
        self.assertEqual(normalize_scale(3), 4)
        self.assertEqual(normalize_scale("bad"), 4)

    def test_intersection_clips_to_tile(self):
        self.assertEqual(_intersect((0, 0, 100, 100), (50, 20, 150, 80)), (50, 20, 100, 80))
        self.assertIsNone(_intersect((0, 0, 10, 10), (20, 20, 30, 30)))

    def test_identity_affine_source_region_tracks_output_box(self):
        region = _source_region_for_output(
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            (100, 200, 500, 700),
            (32768, 16384),
            margin=8,
        )
        self.assertEqual(region, (92, 192, 508, 708))

    def test_source_region_is_clamped_at_canvas_edge(self):
        region = _source_region_for_output(
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            (0, 0, 100, 100),
            (32768, 16384),
            margin=12,
        )
        self.assertEqual(region, (0, 0, 112, 112))


if __name__ == "__main__":
    unittest.main()
