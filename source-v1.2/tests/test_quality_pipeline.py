from __future__ import annotations

import unittest

from fh6garage.livery_preview_quality_pipeline import (
    FULL_CANVAS_MAX_AXIS,
    FUTURE_MAX_SCALE,
    RenderConfig,
    _detail_sample_count,
    build_render_plan,
)


class QualityPipelinePlanningTests(unittest.TestCase):
    def test_four_x_stays_on_full_canvas(self) -> None:
        plan = build_render_plan(4)
        self.assertEqual(plan.scale, 4)
        self.assertEqual((plan.width, plan.height), (8192, 4096))
        self.assertEqual(plan.strategy, "full")
        self.assertEqual(plan.tiles, ())

    def test_sixteen_x_is_structurally_planned_as_tiles(self) -> None:
        plan = build_render_plan(16)
        self.assertEqual(FUTURE_MAX_SCALE, 16)
        self.assertEqual((plan.width, plan.height), (32768, 16384))
        self.assertEqual(plan.strategy, "tiled")
        self.assertGreater(len(plan.tiles), 1)
        self.assertTrue(all(tile.render_x1 - tile.render_x0 <= FULL_CANVAS_MAX_AXIS for tile in plan.tiles))
        self.assertTrue(all(tile.render_y1 - tile.render_y0 <= FULL_CANVAS_MAX_AXIS for tile in plan.tiles))

    def test_tile_overlap_extends_internal_render_rect(self) -> None:
        plan = build_render_plan(8, tile_size=4096, overlap=24)
        interior = next(tile for tile in plan.tiles if tile.x0 > 0 and tile.y0 > 0)
        self.assertLess(interior.render_x0, interior.x0)
        self.assertLess(interior.render_y0, interior.y0)
        self.assertGreaterEqual(interior.render_x1, interior.x1)
        self.assertGreaterEqual(interior.render_y1, interior.y1)


class QualityPipelineCoverageTests(unittest.TestCase):
    def test_small_or_thin_geometry_receives_more_local_samples(self) -> None:
        config = RenderConfig(scale=4, base_samples=2, detail_samples=4).normalized()
        detail = _detail_sample_count((0, 0, 80, 24), 4, config)
        large = _detail_sample_count((0, 0, 1600, 800), 4, config)
        self.assertEqual(detail, 4)
        self.assertEqual(large, 2)

    def test_config_caps_future_scale_at_sixteen(self) -> None:
        config = RenderConfig(scale=100, base_samples=0, detail_samples=99).normalized()
        self.assertEqual(config.scale, 16)
        self.assertGreaterEqual(config.base_samples, 1)
        self.assertLessEqual(config.detail_samples, 8)


if __name__ == "__main__":
    unittest.main()
