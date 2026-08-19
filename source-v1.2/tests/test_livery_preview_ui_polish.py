from __future__ import annotations

import unittest

from PySide6.QtWidgets import (
    QApplication,
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
    def _dialog(self):
        dialog = QDialog()
        top = QFrame(dialog)
        top.setObjectName("liveryPreviewTopBar")
        layout = QHBoxLayout(top)
        scroll = QScrollArea(top)
        layout.addWidget(scroll)
        fast = QPushButton("빠르게 보기", top)
        quality = QPushButton("품질 모드", top)
        combo = QComboBox(top)
        combo.addItem("4× · 기본", 4)
        folder = QPushButton("FH6 폴더", top)
        layout.addWidget(fast)
        layout.addWidget(quality)
        layout.addWidget(combo)
        layout.addWidget(folder)
        return dialog, top, scroll, combo, folder

    def test_polish_replaces_dark_bar_and_legacy_scrollbar_style(self) -> None:
        dialog, top, scroll, combo, folder = self._dialog()
        self.assertTrue(_polish_preview_dialog(dialog))
        self.assertIn("background:#ffffff", top.styleSheet())
        self.assertIn("QScrollBar:horizontal", scroll.styleSheet())
        self.assertIn("height:8px", scroll.styleSheet())
        self.assertIn("QComboBox::drop-down", combo.styleSheet())
        self.assertTrue(folder.isHidden())

    def test_folder_control_moves_under_more_menu(self) -> None:
        dialog, top, _scroll, _combo, folder = self._dialog()
        _polish_preview_dialog(dialog)
        more = top.findChild(QToolButton, "liveryPreviewMoreButton")
        self.assertIsNotNone(more)
        self.assertEqual(more.text(), "⋯")
        self.assertIsNotNone(more.menu())
        self.assertEqual(len(more.menu().actions()), 1)
        self.assertIn("FH6", more.menu().actions()[0].text())
        self.assertTrue(folder.isHidden())

    def test_polish_is_idempotent(self) -> None:
        dialog, top, _scroll, _combo, _folder = self._dialog()
        self.assertTrue(_polish_preview_dialog(dialog))
        self.assertTrue(_polish_preview_dialog(dialog))
        buttons = top.findChildren(QToolButton, "liveryPreviewMoreButton")
        self.assertEqual(len(buttons), 1)


if __name__ == "__main__":
    unittest.main()
