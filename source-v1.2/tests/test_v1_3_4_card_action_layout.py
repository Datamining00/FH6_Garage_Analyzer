from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QStackedLayout, QToolButton, QVBoxLayout, QWidget

from fh6garage.v1_3_4_card_action_layout_patch import (
    BUTTON_GAP,
    CARD_METADATA_HEIGHT,
    CARD_MIN_HEIGHT,
    EDGE_MARGIN,
    ICON_SIZE,
    ROW_HEIGHT,
    THUMBNAIL_MIN_HEIGHT,
    _arrange_card,
)


_APP = QApplication.instance() or QApplication([])


class V134CardActionLayoutTests(unittest.TestCase):
    @staticmethod
    def _card_with_complete_actions() -> QFrame:
        card = QFrame()
        QVBoxLayout(card)
        host = QWidget(card)
        stack = QStackedLayout(host)
        image = QLabel(host)
        overlay = QWidget(host)
        overlay_layout = QVBoxLayout(overlay)
        action_grid = QGridLayout()
        overlay_layout.addLayout(action_grid)
        stack.addWidget(image)
        stack.addWidget(overlay)
        stack.setCurrentWidget(overlay)
        card._fh6_image_label = image
        card._fh6_action_grid = action_grid
        for attribute in (
            "_fh6_game_move_button", "_fh6_zoom_button", "_fh6_memo_button",
            "_fh6_info_button", "_fh6_folder_button", "_fh6_applied_state_button",
            "_fh6_hide_button", "_fh6_check_box", "_fh6_triangle_box", "_fh6_excluded_box",
        ):
            button = QToolButton(overlay)
            button.setFixedSize(34, 34)
            setattr(card, attribute, button)
        return card

    def test_requested_geometry_constants(self) -> None:
        self.assertEqual(ICON_SIZE, 20)
        self.assertEqual(BUTTON_GAP, 5)
        self.assertEqual(EDGE_MARGIN, 5)
        self.assertGreaterEqual(THUMBNAIL_MIN_HEIGHT, 263)
        self.assertGreaterEqual(CARD_MIN_HEIGHT, 340)
        self.assertGreaterEqual(CARD_METADATA_HEIGHT, 75)

    def test_layout_contains_requested_six_rows(self) -> None:
        source = (Path(__file__).parents[1] / "fh6garage" / "v1_3_4_card_action_layout_patch.py").read_text(encoding="utf-8")
        self.assertIn('(\"move\", \"zoom\", \"memo\", \"info\", \"folder\")', source)
        self.assertIn('(\"hide\", \"check\", \"triangle\", \"excluded\")', source)
        self.assertIn('lock.setCheckable(True)', source)
        self.assertIn('export.setEnabled(False)', source)
        self.assertIn('aligner.reposition = lambda: None', source)
        self.assertIn('host_height + CARD_METADATA_HEIGHT', source)
        self.assertIn('grid.addWidget(left_button, row, 0', source)
        self.assertIn('grid.addWidget(right_button, row, 1', source)
        self.assertIn('grid = getattr(card, "_fh6_action_grid", None)', source)
        self.assertIn('_legacy_runtime._force_card_action_geometry = lambda _card: None', source)
        self.assertNotIn('isinstance(root_layout, QVBoxLayout)', source)

    def test_patch_runs_before_thread_affinity_finalizer(self) -> None:
        source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        layout = source.index("apply_v1_3_4_card_action_layout_patch(MainWindow)")
        finalizer = source.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(layout, finalizer)

    def test_arrange_card_fills_the_original_card_grid(self) -> None:
        card = self._card_with_complete_actions()
        _arrange_card(card)
        _APP.processEvents()

        grid = card._fh6_v134_action_grid
        left = (
            card._fh6_game_move_button, card._fh6_zoom_button, card._fh6_memo_button,
            card._fh6_info_button, card._fh6_folder_button, card._fh6_export_placeholder_button,
        )
        right = (
            card._fh6_applied_state_button, card._fh6_lock_placeholder_button, card._fh6_hide_button,
            card._fh6_check_box, card._fh6_triangle_box, card._fh6_excluded_box,
        )
        for row, (left_button, right_button) in enumerate(zip(left, right)):
            self.assertEqual(grid.indexOf(left_button), row * 2)
            self.assertEqual(grid.indexOf(right_button), row * 2 + 1)
        overlay = card._fh6_image_label.parentWidget().layout().currentWidget()
        self.assertEqual(len(overlay.findChildren(QToolButton, "fh6LockPlaceholderButton")), 1)
        self.assertEqual(len(overlay.findChildren(QToolButton, "fh6ExportPlaceholderButton")), 1)

    def test_original_card_constructor_owns_the_six_row_grid(self) -> None:
        source = (Path(__file__).parents[1] / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertIn('card_action_grid = QGridLayout()', source)
        self.assertIn('card._fh6_action_grid = card_action_grid', source)
        self.assertIn('card_action_grid.addWidget(game_move_button, 0, 0', source)
        self.assertIn('card_action_grid.addWidget(excluded_box, 5, 1', source)


if __name__ == "__main__":
    unittest.main()
