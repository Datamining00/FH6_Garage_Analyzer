from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from fh6garage.i18n import set_language
from fh6garage.ui import MainWindow
from fh6garage.v1_3_ui_patch import apply_v1_3_ui_patches
from fh6garage.v1_3_1_patch import apply_v1_3_1_patches
from fh6garage.v1_3_2_unbounded_grid_patch import apply_v1_3_2_unbounded_grid_patch


ROOT = Path(__file__).resolve().parents[1]
apply_v1_3_ui_patches(MainWindow)
apply_v1_3_1_patches(MainWindow)
apply_v1_3_2_unbounded_grid_patch(MainWindow)


class V132UnboundedGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setOrganizationName("FH6AssistantTests")
        cls.app.setApplicationName("FH6AssistantV132UnboundedGrid")
        set_language("ko")

    def setUp(self) -> None:
        self.window = MainWindow(project_root=ROOT)
        self.window.show()
        self.window.pages.setCurrentIndex(1)
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_half_hd_sized_window_never_drops_below_two_columns(self) -> None:
        # 1920x1080 snapped to half is roughly a 960 px top-level width before
        # borders/sidebar. Regardless of usable viewport width, the grid floor
        # is two columns rather than collapsing to one oversized card.
        self.window.resize(960, 900)
        self.app.processEvents()
        self.assertEqual(self.window._fh6_grid_column_count("livery"), 2)

    def test_very_narrow_window_still_keeps_two_columns(self) -> None:
        self.window.resize(self.window.minimumWidth(), 800)
        self.app.processEvents()
        self.assertGreaterEqual(self.window._fh6_grid_column_count("livery"), 2)

    def test_wide_window_has_no_four_column_ceiling(self) -> None:
        self.window.resize(4000, 1000)
        self.app.processEvents()
        columns = self.window._fh6_grid_column_count("livery")
        self.assertGreater(columns, 4)

    def test_wider_viewport_never_reduces_column_count(self) -> None:
        self.window.resize(1800, 900)
        self.app.processEvents()
        medium = self.window._fh6_grid_column_count("livery")

        self.window.resize(3200, 900)
        self.app.processEvents()
        wide = self.window._fh6_grid_column_count("livery")
        self.assertGreaterEqual(wide, medium)

    def test_release_patch_order_applies_unbounded_grid_before_first_paint(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        unbounded = "apply_v1_3_2_unbounded_grid_patch(MainWindow)"
        first_paint = "apply_v1_3_2_first_paint_patch(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"
        self.assertIn(unbounded, source)
        self.assertIn(first_paint, source)
        self.assertIn(thread_fix, source)
        self.assertLess(source.index(unbounded), source.index(first_paint))
        self.assertLess(source.index(first_paint), source.index(thread_fix))


if __name__ == "__main__":
    unittest.main()
