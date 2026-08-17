from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from fh6garage.i18n import set_language
from fh6garage.ui import MainWindow


ROOT = Path(__file__).resolve().parents[1]


class V13RuntimeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setOrganizationName("FH6AssistantTests")
        cls.app.setApplicationName("FH6AssistantV13Runtime")
        set_language("ko")

    def setUp(self) -> None:
        self.window = MainWindow(project_root=ROOT)

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_v13_window_and_group_controls_exist(self) -> None:
        self.assertEqual(self.window.windowTitle(), "FH6 Assistant v1.3")
        self.assertEqual(self.window.livery_creator_group_button.text(), "동일 제작자로 묶기")
        self.assertEqual(self.window.tuning_creator_group_button.text(), "동일 제작자로 묶기")

    def test_group_modes_are_mutually_exclusive(self) -> None:
        vehicle = self.window.livery_group_button
        creator = self.window.livery_creator_group_button
        vehicle.setChecked(True)
        creator.setChecked(True)
        self.assertTrue(creator.isChecked())
        self.assertFalse(vehicle.isChecked())
        vehicle.setChecked(True)
        self.assertTrue(vehicle.isChecked())
        self.assertFalse(creator.isChecked())

    def test_dashboard_vehicle_instant_move_sets_livery_search(self) -> None:
        table = self.window.car_table
        table.setRowCount(1)
        car_id = 1229
        for col, text in enumerate((str(car_id), "vehicle", "1", "1")):
            item = QTableWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, car_id)
            table.setItem(0, col, item)
        table.selectRow(0)
        self.window.dashboard_content_stack.setCurrentIndex(0)
        expected = self.window._car_label(car_id)
        self.window._jump_to_dashboard_selection("livery")
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.assertEqual(self.window.livery_search.text(), expected)

    def test_dashboard_creator_instant_move_sets_tuning_search(self) -> None:
        table = self.window.creator_table
        table.setRowCount(1)
        creator = "RuntimeCreator"
        for col, text in enumerate(("2", creator, "1", "1")):
            item = QTableWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, creator)
            table.setItem(0, col, item)
        table.selectRow(0)
        self.window.dashboard_content_stack.setCurrentIndex(1)
        self.window._jump_to_dashboard_selection("tuning")
        self.assertEqual(self.window.pages.currentIndex(), 2)
        self.assertEqual(self.window.tuning_search.text(), creator)


if __name__ == "__main__":
    unittest.main()
