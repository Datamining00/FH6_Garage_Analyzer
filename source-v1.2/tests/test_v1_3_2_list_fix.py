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

    def test_synchronous_livery_build_is_my_designs_only(self) -> None:
        source = self._source()
        self.assertIn('record.kind == "Livery"', source)
        self.assertIn("combined_sorted_saved_content", source)
        self.assertIn("original_populate_livery_table(self)", source)

    def test_auction_cards_are_appended_after_original_build(self) -> None:
        source = self._source()
        original_call = source.index("original_populate_livery_table(self)")
        schedule_call = source.index("schedule_auction_cards(self)", original_call)
        self.assertLess(original_call, schedule_call)
        self.assertIn("QTimer.singleShot(0, append_next)", source)
        self.assertIn('record.kind == "SoulBoundLivery"', source)

    def test_only_auction_cards_use_deferred_construction(self) -> None:
        source = self._source()
        # The v1.3.1 grid constructor itself must remain untouched. The deferred
        # path adds only SoulBound cards after My Designs has completed.
        self.assertNotIn("MainWindow._populate_livery_grid =", source)
        self.assertIn("self._make_livery_card(record, key)", source)
        self.assertIn("Exactly one auction card per event-loop turn", source)

    def test_bad_auction_record_cannot_abort_complete_list(self) -> None:
        source = self._source()
        self.assertIn("except Exception as exc:", source)
        self.assertIn("_fh6_v132_auction_card_errors", source)
        self.assertIn("QTimer.singleShot(0, append_next)", source)


if __name__ == "__main__":
    unittest.main()
