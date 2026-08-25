from __future__ import annotations

import inspect
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGridLayout, QWidget

from fh6garage import change_dialog_responsive as patch
from fh6garage import change_dialog_cards as feature

ROOT = Path(__file__).resolve().parents[1]


class ChangeDialogResponsiveUiFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_main_grid_contract_is_reused_for_dialog_widths(self) -> None:
        columns, width = patch._dialog_grid_metrics(1100, 8)
        self.assertEqual(columns, 2)
        self.assertGreater(width, 500)

        columns, width = patch._dialog_grid_metrics(1500, 8)
        self.assertEqual(columns, 3)
        self.assertGreater(width, 450)

        columns, width = patch._dialog_grid_metrics(2300, 8)
        self.assertEqual(columns, 4)
        self.assertGreater(width, 550)

    def test_dialog_uses_its_own_viewport_not_hidden_main_grid_width(self) -> None:
        source = inspect.getsource(patch._open_responsive_change_dialog)
        self.assertIn("scroll.viewport()", source)
        self.assertIn("viewport.width()", source)
        self.assertNotIn("_main_livery_card_width", source)
        self.assertNotIn("_main_livery_columns", source)

    def test_theme_explicitly_covers_dialog_scroll_viewport_and_host(self) -> None:
        source = inspect.getsource(patch._apply_dialog_theme)
        self.assertEqual(patch._DIALOG_BACKGROUND, "#f7f8fb")
        self.assertIn("APP_STYLE", source)
        self.assertIn("QDialog#fh6ChangeDialog", source)
        self.assertIn("QScrollArea#fh6ChangeScroll", source)
        self.assertIn("scroll.viewport().setStyleSheet", source)
        self.assertIn("QWidget#fh6ChangeHost", source)
        self.assertIn("_DIALOG_BACKGROUND", source)

    def test_runtime_dialog_card_width_tracks_actual_dialog_viewport(self) -> None:
        class DummyWindow(QWidget):
            def __init__(self) -> None:
                super().__init__()
                self.resize(1180, 880)
                self._fh6_latest_livery_diff = SimpleNamespace(
                    baseline=False,
                    total=1,
                    added=[SimpleNamespace(status="added")],
                    removed=[],
                    changed=[],
                )
                self.livery_grid_layout = QGridLayout()
                self.livery_grid_layout.setHorizontalSpacing(8)
                self.livery_grid_layout.setVerticalSpacing(10)

        original_single = feature._single_change_item
        original_pair = feature._changed_pair_item

        def fake_single(_window, change, card_width):
            widget = QWidget()
            widget.setFixedWidth(card_width)
            widget.setProperty("runtimeCardWidth", card_width)
            return widget, change.status, 1

        def fake_pair(_window, change, card_width, gap):
            widget = QWidget()
            widget.setFixedWidth(card_width * 2 + gap)
            widget.setProperty("runtimeCardWidth", card_width)
            return widget, change.status, 2

        feature._single_change_item = fake_single
        feature._changed_pair_item = fake_pair
        owner = DummyWindow()
        try:
            patch._open_responsive_change_dialog(owner)
            self.app.processEvents()
            dialog = owner._fh6_change_dialog
            dialog._fh6_change_render(force=True)
            self.app.processEvents()

            scroll = dialog._fh6_change_scroll
            grid = dialog._fh6_change_grid
            first = grid.itemAt(0).widget()
            columns, expected = patch._dialog_grid_metrics(
                scroll.viewport().width(),
                grid.horizontalSpacing(),
            )
            self.assertEqual(first.width(), expected)
            self.assertEqual(first.property("runtimeCardWidth"), expected)
            self.assertIn(columns, (2, 3, 4))
            self.assertIn("#f7f8fb", scroll.viewport().styleSheet())

            dialog.resize(1900, 900)
            self.app.processEvents()
            dialog._fh6_change_render(force=True)
            self.app.processEvents()
            first_after = grid.itemAt(0).widget()
            columns_after, expected_after = patch._dialog_grid_metrics(
                scroll.viewport().width(),
                grid.horizontalSpacing(),
            )
            self.assertEqual(first_after.width(), expected_after)
            self.assertEqual(first_after.property("runtimeCardWidth"), expected_after)
            self.assertGreaterEqual(columns_after, columns)
        finally:
            feature._single_change_item = original_single
            feature._changed_pair_item = original_pair
            dialog = getattr(owner, "_fh6_change_dialog", None)
            if dialog is not None:
                dialog.close()
            owner.close()
            self.app.processEvents()

    def test_no_global_delayed_render_survives_dialog_close(self) -> None:
        source = inspect.getsource(patch._open_responsive_change_dialog)
        self.assertNotIn("QTimer.singleShot", source)
        self.assertIn("controller.request_now()", source)
        controller_source = inspect.getsource(patch._ViewportResizeController)
        self.assertIn("QTimer(self)", controller_source)

    def test_runtime_patch_is_removed(self) -> None:
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "apply_v1_3_2_change_dialog_responsive_ui_fix(MainWindow)",
            app,
        )
        self.assertFalse(
            (ROOT / "fh6garage" / "v1_3_2_change_dialog_responsive_ui_fix.py").exists()
        )


if __name__ == "__main__":
    unittest.main()
