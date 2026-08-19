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

    def test_startup_patch_uses_cache_and_never_auto_hashes_after_scan(self) -> None:
        source = (ROOT / "fh6garage" / "livery_startup_performance_patch.py").read_text(encoding="utf-8")
        self.assertIn("scanner._file_sha256 = cached_hash_only", source)
        self.assertIn("return lookup_cached_sha256(path)", source)
        self.assertNotIn("QTimer.singleShot(500", source)
        self.assertIn("_fh6_request_livery_hash_enrichment", source)
        self.assertIn("QThread.Priority.LowPriority", source)
        self.assertIn("_fh6_livery_grid_building", source)
        self.assertIn("_fh6_thumbnail_queue_busy", source)

    def test_thumbnail_decode_is_viewport_lazy_and_queued(self) -> None:
        ui_source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        patch_source = (ROOT / "fh6garage" / "livery_list_rebuild_performance_patch.py").read_text(encoding="utf-8")
        self.assertIn("_refresh_visible_livery_thumbnails", ui_source)
        self.assertIn("_unload_livery_card_thumbnail", ui_source)
        self.assertIn("_queue_thumbnail_load", patch_source)
        self.assertIn("_drain_thumbnail_queue", patch_source)
        self.assertIn("_THUMBNAIL_BATCH = 1", patch_source)


if __name__ == "__main__":
    unittest.main()
