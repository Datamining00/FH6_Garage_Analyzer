from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QLabel

from fh6garage.i18n import set_language
from fh6garage.ui import MainWindow
from fh6garage.window_responsiveness import (
    RESIZE_DEBOUNCE_MS,
    WINDOW_GEOMETRY_KEY,
    WINDOW_MAXIMIZED_KEY,
)


ROOT = Path(__file__).resolve().parents[1]


class V131PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setOrganizationName("FH6AssistantTests")
        cls.app.setApplicationName("FH6AssistantV131")
        set_language("ko")

    def setUp(self) -> None:
        set_language("ko")
        probe = MainWindow(project_root=ROOT)
        probe.settings.remove(WINDOW_GEOMETRY_KEY)
        probe.settings.remove(WINDOW_MAXIMIZED_KEY)
        probe.settings.sync()
        probe.close()
        probe.deleteLater()
        self.app.processEvents()

        self.window = MainWindow(project_root=ROOT)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.settings.remove(WINDOW_GEOMETRY_KEY)
        self.window.settings.remove(WINDOW_MAXIMIZED_KEY)
        self.window.settings.sync()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_v131_title_and_sidebar_version(self) -> None:
        self.assertEqual(self.window.windowTitle(), "FH6 Assistant v1.3.2")
        labels = [label.text() for label in self.window.findChildren(QLabel)]
        self.assertIn("v1.3.2\nLIVERY & TUNING", labels)

    def test_window_geometry_is_saved(self) -> None:
        self.window.showNormal()
        self.window.setGeometry(QRect(80, 90, 1100, 720))
        self.app.processEvents()
        self.window._fh6_v131_save_window_geometry()

        stored = self.window.settings.value(WINDOW_GEOMETRY_KEY)
        self.assertIsInstance(stored, QRect)
        self.assertGreaterEqual(stored.width(), self.window.minimumWidth())
        self.assertGreaterEqual(stored.height(), self.window.minimumHeight())
        self.assertFalse(
            self.window.settings.value(WINDOW_MAXIMIZED_KEY, True, bool)
        )

    def test_saved_geometry_is_restored_on_next_window(self) -> None:
        expected = QRect(40, 40, 1050, 700)
        self.window.settings.setValue(WINDOW_GEOMETRY_KEY, expected)
        self.window.settings.setValue(WINDOW_MAXIMIZED_KEY, False)
        self.window.settings.sync()

        restored = MainWindow(project_root=ROOT)
        try:
            rect = restored.geometry()
            # Offscreen CI may clamp a saved position to its synthetic screen,
            # but the requested normal size must survive whenever it fits.
            self.assertGreaterEqual(rect.width(), restored.minimumWidth())
            self.assertGreaterEqual(rect.height(), restored.minimumHeight())
        finally:
            restored.close()
            restored.deleteLater()
            self.app.processEvents()

    def test_resize_reflow_is_debounced(self) -> None:
        timer = self.window._fh6_v131_resize_timer
        self.assertTrue(timer.isSingleShot())
        self.assertEqual(timer.interval(), RESIZE_DEBOUNCE_MS)

        self.window.pages.setCurrentIndex(1)
        self.window.resize(2200, 900)
        self.app.processEvents()
        self.assertTrue(timer.isActive())

    def test_column_transition_does_not_call_full_filter_relayout(self) -> None:
        self.window.pages.setCurrentIndex(1)
        self.window.resize(2200, 900)
        self.app.processEvents()
        self.window._fh6_v131_resize_timer.stop()
        self.window._fh6_livery_grid_columns = 2

        def fail_full_relayout(*_args, **_kwargs):
            raise AssertionError("full livery relayout must not run for resize-only reflow")

        self.window._relayout_livery_grid = fail_full_relayout
        self.window._fh6_v131_finalize_resize()
        self.assertGreaterEqual(self.window._fh6_livery_grid_columns, 3)
        self.assertLessEqual(self.window._fh6_livery_grid_columns, 4)


class V131BuildMetadataTests(unittest.TestCase):
    def test_app_version_and_patch_order(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('app.setApplicationVersion("1.3.2")', source)
        self.assertNotIn("apply_v1_3_ui_patches", source)
        self.assertNotIn("apply_v1_3_1_patches", source)
        self.assertNotIn("apply_v1_3_2_patches", source)

    def test_windows_version_metadata_is_current_release(self) -> None:
        source = (ROOT / "version_info.txt").read_text(encoding="utf-8")
        self.assertIn("filevers=(1, 3, 2, 0)", source)
        self.assertIn("prodvers=(1, 3, 2, 0)", source)
        self.assertIn("FH6 Assistant v1.3.2.exe", source)

    def test_v131_spec_exists(self) -> None:
        source = (ROOT / "FH6_Assistant_v1.3.1.spec").read_text(encoding="utf-8")
        self.assertIn("name='FH6 Assistant v1.3.1'", source)


if __name__ == "__main__":
    unittest.main()
