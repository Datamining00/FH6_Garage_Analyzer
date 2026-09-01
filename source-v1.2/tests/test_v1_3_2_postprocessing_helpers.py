from __future__ import annotations

import unittest
from pathlib import Path


class V132PostprocessingHelperContractTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.source = (
            root / "fh6garage" / "v1_3_2_thread_affinity_patch.py"
        ).read_text(encoding="utf-8")

    def test_thumbnail_preparation_is_a_module_level_helper(self) -> None:
        helper = "def _prepare_v132_auction_thumbnails(self, result) -> None:"
        populate = "def apply_v1_3_2_scan_postprocessing(MainWindow) -> None:"
        self.assertIn(helper, self.source)
        self.assertLess(self.source.index(helper), self.source.index(populate))

    def test_auction_card_scheduling_is_a_module_level_helper(self) -> None:
        helper = "def _schedule_v132_auction_cards(self) -> None:"
        populate = "def apply_v1_3_2_scan_postprocessing(MainWindow) -> None:"
        self.assertIn(helper, self.source)
        self.assertIn("QTimer.singleShot(0, scheduler)", self.source)
        self.assertLess(self.source.index(helper), self.source.index(populate))

    def test_populate_orchestration_keeps_phase_order(self) -> None:
        start = self.source.index("def patched_populate_all(self) -> None:")
        end = self.source.index("MainWindow._populate_all = patched_populate_all", start)
        body = self.source[start:end]
        self.assertLess(
            body.index("_prepare_v132_auction_thumbnails(self, result)"),
            body.index("_rebuild_v132_indexes(self)"),
        )
        self.assertLess(
            body.index("_rebuild_v132_indexes(self)"),
            body.index("current_populate_all(self)"),
        )
        self.assertLess(
            body.index("current_populate_all(self)"),
            body.index("_schedule_v132_auction_cards(self)"),
        )


if __name__ == "__main__":
    unittest.main()
