from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SequentialStartupBaselineTests(unittest.TestCase):
    def test_startup_optimization_patches_are_not_wired(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("livery_startup_performance_patch", source)
        self.assertNotIn("apply_livery_startup_performance_patch", source)
        self.assertNotIn("livery_list_rebuild_performance_patch", source)
        self.assertNotIn("apply_livery_list_rebuild_performance_patch", source)
        self.assertNotIn("livery_hash_cache", source)

    def test_scanner_keeps_original_synchronous_content_hash_path(self) -> None:
        source = (ROOT / "fh6garage" / "scanner.py").read_text(encoding="utf-8")
        self.assertIn("def _file_sha256(path: Path) -> str:", source)
        self.assertIn("_file_sha256(livery_path)", source)
        self.assertNotIn("lookup_cached_sha256", source)
        self.assertNotIn("enrich_sha256", source)

    def test_livery_ui_keeps_original_direct_grid_and_thumbnail_path(self) -> None:
        source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("for index, record in enumerate(self._sorted_liveries()):", source)
        self.assertIn("self._load_livery_card_thumbnail(card)", source)
        self.assertNotIn("_fh6_livery_grid_generation", source)
        self.assertNotIn("_fh6_thumbnail_decode_queue", source)

    def test_render_acceleration_remains_separate(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_livery_render_acceleration_patch()", source)


if __name__ == "__main__":
    unittest.main()
