from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
I18N = (ROOT / "fh6garage" / "i18n.py").read_text(encoding="utf-8")


class V13FeatureContractTests(unittest.TestCase):
    def test_dashboard_instant_move_contract(self) -> None:
        self.assertIn("def _jump_to_dashboard_selection", UI)
        self.assertIn('tr("dashboard.instant_move")', UI)
        self.assertIn("self.pages.setCurrentIndex(page_index)", UI)
        self.assertIn("search.setText(query)", UI)

    def test_creator_grouping_contract(self) -> None:
        self.assertIn('tr("content.group_creator")', UI)
        self.assertIn('QLabel("││")', UI)
        self.assertIn("def _set_creator_grouping", UI)
        self.assertIn('"creatorGroupKey"', UI)
        self.assertIn('"creatorGroupLabel"', UI)
        self.assertIn('tr(\n                        "content.creator_group_header"', UI)

    def test_livery_memo_creator_tools_contract(self) -> None:
        self.assertIn("def _creator_livery_note_count", UI)
        self.assertIn('tr("memo.add_same_creator")', UI)
        self.assertIn('tr("memo.clear_same_creator")', UI)
        self.assertIn('"memo.append_confirm_message"', UI)
        self.assertIn('self._car_label(livery_record.header.car_id)', UI)
        self.assertIn('tr(\n                    "memo.creator_value"', UI)

    def test_new_i18n_keys_have_korean_and_english(self) -> None:
        for key in (
            "dashboard.instant_move",
            "content.group_creator",
            "content.creator_group_header",
            "memo.creator_note_count",
            "memo.add_same_creator",
            "memo.clear_same_creator",
            "memo.append_confirm_message",
        ):
            self.assertIn(f'"{key}"', I18N)


if __name__ == "__main__":
    unittest.main()
