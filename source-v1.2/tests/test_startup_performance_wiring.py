from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StartupPerformanceWiringTests(unittest.TestCase):
    def test_app_wires_startup_hash_optimization_and_render_acceleration(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_livery_startup_performance_patch(MainWindow)", source)
        self.assertIn("apply_livery_render_acceleration_patch()", source)
        self.assertLess(
            source.index("apply_livery_tiled_runtime_patch()"),
            source.index("apply_livery_render_acceleration_patch()"),
        )
        self.assertLess(
            source.index("apply_livery_render_acceleration_patch()"),
            source.index("apply_livery_raster_runtime_patch()"),
        )

    def test_startup_patch_replaces_blocking_hash_with_profiled_cache_lookup(self) -> None:
        source = (ROOT / "fh6garage" / "livery_startup_performance_patch.py").read_text(encoding="utf-8")
        self.assertIn("scanner._file_sha256 = cached_hash_only", source)
        self.assertIn("return lookup_cached_sha256(path)", source)
        self.assertIn("QTimer.singleShot(500", source)
        self.assertIn("QThread.Priority.LowPriority", source)

    def test_existing_thumbnail_path_is_already_viewport_lazy(self) -> None:
        source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("_refresh_visible_livery_thumbnails", source)
        self.assertIn("_unload_livery_card_thumbnail", source)


if __name__ == "__main__":
    unittest.main()
