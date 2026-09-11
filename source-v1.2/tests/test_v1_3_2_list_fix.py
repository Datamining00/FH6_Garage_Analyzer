from __future__ import annotations

import unittest
from pathlib import Path


class V132ListFixContractTests(unittest.TestCase):
    def _source(self) -> str:
        root = Path(__file__).resolve().parents[1]
        return (
            root / "fh6garage" / "v1_3_2_list_fix.py"
        ).read_text(encoding="utf-8")

    def test_app_installs_list_fix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn("apply_v1_3_2_list_fixes(MainWindow)", source)

    def test_initial_scan_build_is_my_designs_only(self) -> None:
        source = self._source()
        self.assertIn("_fh6_v132_initial_scan_build", source)
        self.assertIn('record.kind == "Livery"', source)
        self.assertIn("combined_sorted_saved_content", source)

    def test_auction_schedule_occurs_after_scan_finished_returns(self) -> None:
        source = self._source()
        start = source.index("def patched_scan_finished")
        original_call = source.index("original_scan_finished(self, result)", start)
        schedule_call = source.index("schedule_auction_cards(owner)", original_call)
        self.assertLess(original_call, schedule_call)
        self.assertIn("QTimer.singleShot(", source[schedule_call - 120:schedule_call + 120])

    def test_populate_livery_table_does_not_schedule_auction_reentrantly(self) -> None:
        source = self._source()
        start = source.index("def patched_populate_livery_table")
        end = source.index("def patched_scan_finished", start)
        block = source[start:end]
        self.assertIn("original_populate_livery_table(self)", block)
        self.assertNotIn("schedule_auction_cards", block)
        self.assertNotIn("QTimer.singleShot", block)

    def test_deferred_auction_card_is_parented_before_event_loop_returns(self) -> None:
        source = self._source()
        make = source.index("card = self._make_livery_card(record, key)")
        parent = source.index("card.setParent(self.livery_grid_host)", make)
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
