from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from PIL import Image

from fh6garage.livery_preview_tiled_quality import (
    RETAINED_SCALE_LIMIT,
    SUPPORTED_SCALES,
    _intersect,
    _source_region_for_output,
    _tiled_projection,
    normalize_scale,
)


class _FakeRenderContract:
    @staticmethod
    def _projection_pixel_bounds(projection):
        # At 16x this becomes 9600x512, forcing three horizontal tiles while
        # keeping the regression test lightweight.
        return (0, 0, 600, 32)


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

    def test_sixteen_x_stitching_has_no_transparent_tile_seam(self):
        def fake_projection_record(section, car_id, game_folder):
            return (
                _FakeRenderContract,
                "Left",
                Image.new("L", (2048, 1024), 255),
                {},
                "mask-hash",
            )

        def fake_project_tile(
            renderer,
            prepared_layers,
            *,
            slot,
            projection,
            base_mask,
            scale,
            output_box,
            raster_resolver=None,
        ):
            x0, y0, x1, y1 = output_box
            size = (x1 - x0, y1 - y0)
            art = Image.new("RGBA", size, (240, 100, 50, 255))
            mask = Image.new("L", size, 255)
            return art, mask

        with patch(
            "fh6garage.livery_preview_tiled_quality._projection_record",
            side_effect=fake_projection_record,
        ), patch(
            "fh6garage.livery_preview_tiled_quality._project_tile",
            side_effect=fake_project_tile,
        ):
            png = _tiled_projection(
                [],
                object(),
                section="Left",
                car_id=3107,
                game_folder=".",
                scale=16,
                raster_resolver=None,
            )

        with Image.open(io.BytesIO(png)) as image:
            rgba = image.convert("RGBA")
            self.assertEqual(rgba.size, (600 * 4, 32 * 4))
            # High-res tile boundaries are 4096 and 8192, retained at /4.
            for seam_x in (1024, 2048):
                for x in (seam_x - 1, seam_x, seam_x + 1):
                    self.assertEqual(rgba.getpixel((x, 64)), (240, 100, 50, 255))


if __name__ == "__main__":
    unittest.main()
