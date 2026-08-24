from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QWidget

from fh6garage.v1_3_2_card_parent_safety_patch import (
    apply_v1_3_2_card_parent_safety_patch,
)


ROOT = Path(__file__).resolve().parents[1]


class _FakeMainWindow:
    def __init__(self) -> None:
        self.livery_grid_host = QWidget()
        self.tuning_grid_host = QWidget()

    def _make_saved_content_card(self, content_type: str, record, key: str):
        card = QFrame()
        # Regression precondition: the legacy constructor returns a parentless
        # top-level-capable QFrame.
        self.assert_parentless = card.parentWidget() is None
        return card


class V132CardParentSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_livery_card_is_parented_and_hidden_before_later_visual_patches(self) -> None:
        apply_v1_3_2_card_parent_safety_patch(_FakeMainWindow)
        window = _FakeMainWindow()
        card = window._make_saved_content_card("livery", object(), "key")

        self.assertTrue(window.assert_parentless)
        self.assertIs(card.parentWidget(), window.livery_grid_host)
        self.assertFalse(card.isVisible())
        self.assertTrue(bool(card.property("fh6ParentSafeBeforeRails")))

    def test_tuning_card_uses_tuning_grid_host(self) -> None:
        window = _FakeMainWindow()
        card = window._make_saved_content_card("tuning", object(), "key")
        self.assertIs(card.parentWidget(), window.tuning_grid_host)
        self.assertFalse(card.isVisible())

    def test_patch_order_is_global_then_parent_safety_then_rails_then_thread_fix(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        global_ui = "apply_v1_3_2_global_ui_patch(MainWindow)"
        parent_safety = "apply_v1_3_2_card_parent_safety_patch(MainWindow)"
        rails = "apply_v1_3_2_card_rail_patch(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"

        for token in (global_ui, parent_safety, rails, thread_fix):
            self.assertIn(token, source)
        self.assertLess(source.index(global_ui), source.index(parent_safety))
        self.assertLess(source.index(parent_safety), source.index(rails))
        self.assertLess(source.index(rails), source.index(thread_fix))


if __name__ == "__main__":
    unittest.main()
