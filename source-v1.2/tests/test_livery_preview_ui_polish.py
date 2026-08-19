from __future__ import annotations

import unittest

from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QToolButton,
)

from fh6garage.livery_preview_ui_polish import _polish_preview_dialog


_APP = QApplication.instance() or QApplication([])


class PreviewUiPolishTests(unittest.TestCase):
    def _dialog(self, *, fast_selected: bool = False):
        dialog = QDialog()
        top = QFrame(dialog)
        top.setObjectName("liveryPreviewTopBar")
        layout = QHBoxLayout(top)
        scroll = QScrollArea(top)
        layout.addWidget(scroll)
        fast = QPushButton("빠르게 보기", top)
        quality = QPushButton("품질 모드", top)
        group = QButtonGroup(dialog)
        group.setExclusive(True)
        for button in (fast, quality):
            button.setCheckable(True)
            group.addButton(button)
        fast.setChecked(bool(fast_selected))
        quality.setChecked(not fast_selected)
        combo = QComboBox(top)
        combo.addItem("2×", 2)
        combo.addItem("4× · 기본", 4)
        combo.addItem("8×", 8)
        combo.addItem("16×", 16)
        combo.setCurrentIndex(combo.findData(4))
        combo.setEnabled(not fast_selected)
        folder = QPushButton("FH6 폴더", top)
        layout.addWidget(fast)
        layout.addWidget(quality)
        layout.addWidget(combo)
        layout.addWidget(folder)
        return dialog, top, scroll, fast, quality, combo, folder

    def test_polish_replaces_dark_bar_and_legacy_scrollbar_style(self) -> None:
        dialog, top, scroll, fast, quality, combo, folder = self._dialog()
        self.assertTrue(_polish_preview_dialog(dialog))
        self.assertIn("background:#ffffff", top.styleSheet())
        self.assertIn("QScrollBar:horizontal", scroll.styleSheet())
        self.assertIn("height:8px", scroll.styleSheet())
        self.assertIn("QComboBox::drop-down", combo.styleSheet())
        self.assertTrue(folder.isHidden())
        self.assertTrue(fast.isHidden())
        self.assertTrue(quality.isHidden())

    def test_quick_view_is_unified_as_one_x_scale(self) -> None:
        dialog, _top, _scroll, fast, quality, combo, _folder = self._dialog(fast_selected=True)
        self.assertTrue(_polish_preview_dialog(dialog))
        self.assertTrue(fast.isHidden())
        self.assertTrue(quality.isHidden())
        self.assertTrue(quality.isChecked())
        self.assertEqual(combo.currentData(), 1)
        self.assertGreaterEqual(combo.findData(1), 0)
        self.assertTrue(combo.isEnabled())

    def test_quality_selection_is_preserved_when_modes_are_removed(self) -> None:
        dialog, _top, _scroll, _fast, _quality, combo, _folder = self._dialog(fast_selected=False)
        self.assertEqual(combo.currentData(), 4)
        self.assertTrue(_polish_preview_dialog(dialog))
        self.assertEqual(combo.currentData(), 4)
        self.assertEqual([combo.itemData(index) for index in range(combo.count())], [1, 2, 4, 8, 16])

    def test_folder_control_moves_under_more_menu(self) -> None:
        dialog, top, _scroll, _fast, _quality, _combo, folder = self._dialog()
        _polish_preview_dialog(dialog)
        more = top.findChild(QToolButton, "liveryPreviewMoreButton")
        self.assertIsNotNone(more)
        self.assertEqual(more.text(), "⋯")
        self.assertIsNotNone(more.menu())
        self.assertEqual(len(more.menu().actions()), 1)
        self.assertIn("FH6", more.menu().actions()[0].text())
        self.assertTrue(folder.isHidden())

    def test_polish_is_idempotent(self) -> None:
        dialog, top, _scroll, _fast, _quality, _combo, _folder = self._dialog()
        self.assertTrue(_polish_preview_dialog(dialog))
        self.assertTrue(_polish_preview_dialog(dialog))
        buttons = top.findChildren(QToolButton, "liveryPreviewMoreButton")
        self.assertEqual(len(buttons), 1)


if __name__ == "__main__":
    unittest.main()
