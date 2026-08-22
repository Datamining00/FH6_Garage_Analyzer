from __future__ import annotations

import unittest
from pathlib import Path


class V132CardParentContractTests(unittest.TestCase):
    def test_app_applies_card_parent_patch_after_list_fix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app.py").read_text(encoding="utf-8")
        list_pos = source.index("apply_v1_3_2_list_fixes(MainWindow)")
        parent_pos = source.index("apply_v1_3_2_card_parent_patches(MainWindow)")
        self.assertLess(list_pos, parent_pos)

    def test_every_livery_card_is_parented_before_factory_returns(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "fh6garage" / "v1_3_2_card_parent_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn("original_make_livery_card(self, record, key)", source)
        self.assertIn("card.setParent(host)", source)
        self.assertIn("card.hide()", source)
        self.assertIn("MainWindow._make_livery_card = patched_make_livery_card", source)


if __name__ == "__main__":
    unittest.main()
