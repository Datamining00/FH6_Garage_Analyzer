from __future__ import annotations

import unittest
from pathlib import Path


class V132ListFixContractTests(unittest.TestCase):
    def _source(self) -> str:
        root = Path(__file__).resolve().parents[1]
        return (root / "fh6garage" / "auction_card_loader.py").read_text(
            encoding="utf-8"
        )

    def test_runtime_list_fix_is_removed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_list_fixes(MainWindow)", source)
        self.assertFalse((root / "fh6garage" / "v1_3_2_list_fix.py").exists())

    def test_initial_scan_build_is_my_designs_only(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("_fh6_v132_initial_scan_build", source)
        self.assertIn('record.kind == "Livery"', source)
        self.assertIn("sorted_records", source)

    def test_scan_finished_slot_is_not_runtime_replaced(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertNotIn("def patched_scan_finished", source)
        self.assertIn("def _fh6_v132_schedule_auction_cards", source)

    def test_populate_livery_view_does_not_schedule_auction_reentrantly(self) -> None:
        root = Path(__file__).resolve().parents[1]
        ui_source = (root / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        start = ui_source.index("def _populate_livery_view")
        block = ui_source[start:ui_source.index("def _populate_livery_grid", start)]
        self.assertIn("self._populate_livery_grid()", block)
        self.assertNotIn("schedule_auction_cards", block)
        self.assertNotIn("QTimer.singleShot", block)

    def test_deferred_auction_card_is_parented_before_event_loop_returns(self) -> None:
        source = self._source()
        make = source.index("card = owner._make_livery_card(record, key)")
        parent = source.index("card.setParent(owner.livery_grid_host)", make)
        next_timer = source.index("QTimer.singleShot(0, append_next)", parent)
        self.assertLess(make, parent)
        self.assertLess(parent, next_timer)
        self.assertIn("card.hide()", source[parent:next_timer])

    def test_bad_auction_record_cannot_abort_complete_list(self) -> None:
        source = self._source()
        self.assertIn("except Exception as exc:", source)
        self.assertIn("_fh6_v132_auction_card_errors", source)
        self.assertIn("card.deleteLater()", source)


if __name__ == "__main__":
    unittest.main()
