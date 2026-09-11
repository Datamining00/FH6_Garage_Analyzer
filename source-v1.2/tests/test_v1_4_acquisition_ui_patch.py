from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage.acquisition_db import AcquisitionInfo
from fh6garage.v1_4_acquisition_ui_patch import _acquisition_text, _acquisition_tooltip


class V14AcquisitionUiTests(unittest.TestCase):
    def test_multiple_methods_are_preserved_for_tooltip(self):
        info = AcquisitionInfo(
            247,
            "1969 Toyota 2000 GT",
            "Autoshow, Collection Journal, Wheelspin",
            "",
        )
        self.assertEqual(_acquisition_text(info), "Autoshow, Collection Journal, Wheelspin")
        tooltip = _acquisition_tooltip(info)
        self.assertIn("Autoshow\nCollection Journal\nWheelspin", tooltip)

    def test_dlc_is_shown_separately_in_tooltip(self):
        info = AcquisitionInfo(1, "Example", "Autoshow DLC", "Car Pass")
        tooltip = _acquisition_tooltip(info)
        self.assertIn("Autoshow DLC", tooltip)
        self.assertIn("DLC:", tooltip)
        self.assertIn("Car Pass", tooltip)

    def test_card_path_uses_existing_reserved_source_label_and_elide(self):
        text = Path("fh6garage/v1_4_acquisition_ui_patch.py").read_text(encoding="utf-8")
        self.assertIn('findChild(QLabel, "fh6AcquisitionPlaceholder")', text)
        self.assertIn("elidedText", text)
        self.assertIn('from .acquisition_db import DATA_DIR_NAME, AcquisitionDatabase, AcquisitionInfo', text)
        self.assertIn('self.project_root / "data" / DATA_DIR_NAME', text)
        self.assertIn("AcquisitionDatabase(self.project_root / \"data\" / DATA_DIR_NAME)", text)
        self.assertNotIn('self.project_root / "data" / "fh6_cars.json"', text)
        self.assertIn("dataset_name", text)
        self.assertIn("_install_change_dialog_first_layout_fix", text)

    def test_cached_card_source_metadata_can_be_refreshed_without_recreating_cards(self):
        text = Path("fh6garage/v1_4_acquisition_ui_patch.py").read_text(encoding="utf-8")
        self.assertIn("def _refresh_cached_acquisition_labels(window: Any)", text)
        self.assertIn('window.findChildren(QLabel, "fh6AcquisitionPlaceholder")', text)
        self.assertIn('label.property("fh6AcquisitionCarId")', text)
        self.assertIn("_apply_acquisition_label(window, label", text)
        self.assertIn("MainWindow._refresh_cached_acquisition_labels = _refresh_cached_acquisition_labels", text)


if __name__ == "__main__":
    unittest.main()
