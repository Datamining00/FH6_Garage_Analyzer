from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from fh6garage import card_icons, ui


class StartupPerformanceOptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_card_png_pixmaps_are_cached(self) -> None:
        first = card_icons.pixmap("move", "#555a68", 20)
        second = card_icons.pixmap("move", "#555a68", 20)
        self.assertIs(first, second)

    def test_card_toggle_icons_are_cached(self) -> None:
        first = card_icons.toggle_icon("circle", on_color="#39e75f")
        second = card_icons.toggle_icon("circle", on_color="#39e75f")
        self.assertIs(first, second)

    def test_painted_classification_assets_are_cached(self) -> None:
        first = ui._classification_pixmap("search", True, 24)
        second = ui._classification_pixmap("search", True, 24)
        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
