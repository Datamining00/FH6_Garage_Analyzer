from __future__ import annotations

import unittest

from fh6garage import livery_preview_tiled_quality as tiled
from fh6garage.livery_render_acceleration_patch import (
    _subset_layers,
    choose_tile_worker_count,
)


class LiveryRenderAccelerationTests(unittest.TestCase):
    def test_worker_count_is_memory_aware_and_conservative(self) -> None:
        eight_gib = 8 * 1024**3
        self.assertEqual(
            choose_tile_worker_count(16, has_raster=False, cpu_count=16, available_bytes=eight_gib),
            2,
        )
        self.assertEqual(
            choose_tile_worker_count(8, has_raster=False, cpu_count=16, available_bytes=eight_gib),
            3,
        )
        self.assertEqual(
            choose_tile_worker_count(16, has_raster=False, cpu_count=16, available_bytes=500 * 1024**2),
            1,
        )

    def test_raster_archive_path_stays_single_threaded(self) -> None:
        self.assertEqual(
            choose_tile_worker_count(8, has_raster=True, cpu_count=32, available_bytes=32 * 1024**3),
            1,
        )

    def test_tile_subset_preserves_order_and_uncullable_layers(self) -> None:
        first = {"name": "first"}
        outside = {"name": "outside"}
        raster = {"name": "raster"}
        last = {"name": "last"}
        indexed = [
            (first, (0, 0, 100, 100)),
            (outside, (500, 500, 600, 600)),
            (raster, None),
            (last, (90, 90, 130, 130)),
        ]
        selected = _subset_layers(tiled, indexed, (50, 50, 120, 120))
        self.assertEqual(selected, [first, raster, last])


if __name__ == "__main__":
    unittest.main()
