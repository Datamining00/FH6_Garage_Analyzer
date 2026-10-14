from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from fh6garage.i18n import set_language
from fh6garage.ui import MainWindow
from fh6garage.v1_3_ui_patch import (
    GRID_MAX_COLUMNS,
    IMAGE_MIN_HEIGHT,
    apply_v1_3_ui_patches,
)


ROOT = Path(__file__).resolve().parents[1]
apply_v1_3_ui_patches(MainWindow)


class V13FollowupUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setOrganizationName("FH6AssistantTests")
        cls.app.setApplicationName("FH6AssistantV13Followup")
        set_language("ko")

    def setUp(self) -> None:
        set_language("ko")
        self.window = MainWindow(project_root=ROOT)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_thumbnail_minimum_height_is_260(self) -> None:
        self.assertEqual(IMAGE_MIN_HEIGHT, 260)

    def test_language_text_is_replaced_by_icon(self) -> None:
        self.assertEqual(self.window.language_label.text(), "")
        pixmap = self.window.language_label.pixmap()
        self.assertIsNotNone(pixmap)
        self.assertFalse(pixmap.isNull())

    def test_restart_button_tracks_pending_language_change(self) -> None:
        self.assertTrue(self.window.language_restart_button.isHidden())
        english = self.window.language_combo.findData("en")
        korean = self.window.language_combo.findData("ko")
        self.window.language_combo.setCurrentIndex(english)
        self.app.processEvents()
        self.assertTrue(self.window.language_restart_button.isVisible())
        self.window.language_combo.setCurrentIndex(korean)
        self.app.processEvents()
        self.assertFalse(self.window.language_restart_button.isVisible())

    def test_wide_window_allows_up_to_four_columns(self) -> None:
        self.window.pages.setCurrentIndex(1)
        self.window.resize(2200, 900)
        self.app.processEvents()
        columns = self.window._fh6_grid_column_count("livery")
        self.assertGreaterEqual(columns, 3)
        self.assertLessEqual(columns, GRID_MAX_COLUMNS)

    def test_grid_never_exceeds_four_columns(self) -> None:
        self.window.pages.setCurrentIndex(1)
        self.window.resize(4000, 900)
        self.app.processEvents()
        self.assertEqual(self.window._fh6_grid_column_count("livery"), 4)


if __name__ == "__main__":
    unittest.main()
