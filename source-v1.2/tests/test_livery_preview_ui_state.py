from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage

from fh6garage.livery_preview_ui_state import (
    SECTION_DISPLAY_ROTATION_DEGREES,
    load_view_mode,
    normalize_view_mode,
    rotate_section_image,
    save_view_mode,
)


class PreviewUiStateTests(unittest.TestCase):
    def test_requested_section_rotations_are_fixed(self):
        self.assertEqual(SECTION_DISPLAY_ROTATION_DEGREES["Right"], 180)
        self.assertEqual(SECTION_DISPLAY_ROTATION_DEGREES["RightWindow"], 180)
        self.assertEqual(SECTION_DISPLAY_ROTATION_DEGREES["FrontWindshield"], -90)
        self.assertEqual(SECTION_DISPLAY_ROTATION_DEGREES["BackWindshield"], 90)

    def test_quarter_turn_swaps_image_dimensions(self):
        image = QImage(10, 20, QImage.Format.Format_ARGB32)
        rotated = rotate_section_image(image, "FrontWindshield")
        self.assertEqual((rotated.width(), rotated.height()), (20, 10))

    def test_non_rotated_section_keeps_dimensions(self):
        image = QImage(10, 20, QImage.Format.Format_ARGB32)
        rotated = rotate_section_image(image, "Left")
        self.assertEqual((rotated.width(), rotated.height()), (10, 20))

    def test_view_mode_normalization(self):
        self.assertEqual(normalize_view_mode("actual"), "actual")
        self.assertEqual(normalize_view_mode("fit"), "fit")
        self.assertEqual(normalize_view_mode("unknown"), "fit")

    def test_view_mode_persists_in_qsettings(self):
        settings = QSettings("FH6AssistantTests", "PreviewUiState")
        settings.clear()
        try:
            self.assertEqual(load_view_mode(settings), "fit")
            save_view_mode(settings, "actual")
            self.assertEqual(load_view_mode(settings), "actual")
            save_view_mode(settings, "fit")
            self.assertEqual(load_view_mode(settings), "fit")
        finally:
            settings.clear()
            settings.sync()


if __name__ == "__main__":
    unittest.main()
