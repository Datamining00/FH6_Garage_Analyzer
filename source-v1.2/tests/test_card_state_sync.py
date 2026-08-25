from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFrame, QToolButton

from fh6garage.card_state_sync import (
    _sync_cached_annotation_card,
    _sync_cached_hidden_card,
)


_APP = QApplication.instance() or QApplication([])


class _Annotations:
    def __init__(self):
        self.value = SimpleNamespace(
            checked=True,
            triangle=False,
            excluded=True,
            note="memo",
        )

    def get(self, key):
        return self.value


class _Window:
    def __init__(self):
        self.annotations = _Annotations()
        self._livery_card_by_key = {}
        self._tuning_card_by_key = {}

    @staticmethod
    def _detail_memo_icon(active: bool):
        return QIcon()


class CardStateSyncTests(unittest.TestCase):
    @staticmethod
    def _card():
        card = QFrame()
        card._fh6_check_box = QToolButton(card)
        card._fh6_check_box.setCheckable(True)
        card._fh6_triangle_box = QToolButton(card)
        card._fh6_triangle_box.setCheckable(True)
        card._fh6_excluded_box = QToolButton(card)
        card._fh6_excluded_box.setCheckable(True)
        card._fh6_hide_button = QToolButton(card)
        card._fh6_hide_button.setCheckable(True)
        card._fh6_memo_button = QToolButton(card)
        return card

    def test_duplicate_action_syncs_main_cached_annotation_card(self):
        window = _Window()
        card = self._card()
        window._livery_card_by_key["k"] = card

        _sync_cached_annotation_card(window, "livery", "k")

        self.assertTrue(card._fh6_check_box.isChecked())
        self.assertFalse(card._fh6_triangle_box.isChecked())
        self.assertTrue(card._fh6_excluded_box.isChecked())
        self.assertTrue(bool(card.property("checked")))
        self.assertFalse(bool(card.property("triangle")))
        self.assertTrue(bool(card.property("excluded")))
        self.assertIn("memo", card._fh6_memo_button.toolTip())
        card.deleteLater()

    def test_duplicate_hide_action_syncs_main_cached_card(self):
        window = _Window()
        card = self._card()
        window._livery_card_by_key["k"] = card

        _sync_cached_hidden_card(window, "k", True)
        self.assertTrue(card._fh6_hide_button.isChecked())
        _sync_cached_hidden_card(window, "k", False)
        self.assertFalse(card._fh6_hide_button.isChecked())
        card.deleteLater()

    def test_runtime_patch_is_removed(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        source = app_path.read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_change_view_alias_sync_patch", source)


if __name__ == "__main__":
    unittest.main()
