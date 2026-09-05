from __future__ import annotations

import unittest

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QLabel,
    QStackedLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fh6garage.v1_3_4_card_action_layout_patch import (
    _arrange_card,
    _remove_recent_deleted_heading,
)


_APP = QApplication.instance() or QApplication([])


class V134AuctionCardRecentCleanupTests(unittest.TestCase):
    @staticmethod
    def _auction_card_without_move() -> QFrame:
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
        card._fh6_game_move_button = None
        for attribute in (
            "_fh6_zoom_button",
            "_fh6_memo_button",
            "_fh6_info_button",
            "_fh6_folder_button",
            "_fh6_applied_state_button",
            "_fh6_hide_button",
            "_fh6_check_box",
            "_fh6_triangle_box",
            "_fh6_excluded_box",
        ):
            button = QToolButton(overlay)
            button.setFixedSize(34, 34)
            setattr(card, attribute, button)
        return card

    def test_auction_card_without_move_still_receives_v134_layout(self) -> None:
        card = self._auction_card_without_move()
        _arrange_card(card)
        _APP.processEvents()

        grid = card._fh6_v134_action_grid
        self.assertIs(grid, card._fh6_action_grid)
        self.assertIsInstance(card._fh6_export_placeholder_button, QToolButton)
        self.assertFalse(hasattr(card, "_fh6_lock_placeholder_button"))

        expected = (
            (card._fh6_applied_state_button, 0, 1),
            (card._fh6_zoom_button, 1, 0),
            (card._fh6_memo_button, 2, 0),
            (card._fh6_hide_button, 2, 1),
            (card._fh6_info_button, 3, 0),
            (card._fh6_check_box, 3, 1),
            (card._fh6_folder_button, 4, 0),
            (card._fh6_triangle_box, 4, 1),
            (card._fh6_export_placeholder_button, 5, 0),
            (card._fh6_excluded_box, 5, 1),
        )
        for widget, expected_row, expected_column in expected:
            index = grid.indexOf(widget)
            self.assertGreaterEqual(index, 0)
            row, column, _row_span, _column_span = grid.getItemPosition(index)
            self.assertEqual((row, column), (expected_row, expected_column))

    def test_recent_removed_root_card_loses_before_removal_strip(self) -> None:
        card = QFrame()
        layout = QVBoxLayout(card)
        image = QLabel("image")
        heading = QLabel("삭제 전")
        layout.addWidget(image)
        layout.addWidget(heading)
        card.show()
        heading.show()

        _remove_recent_deleted_heading(card)
        self.assertFalse(heading.isVisible())

    def test_english_before_removal_strip_is_also_removed(self) -> None:
        card = QFrame()
        layout = QVBoxLayout(card)
        heading = QLabel("Before removal")
        layout.addWidget(heading)
        card.show()
        heading.show()

        _remove_recent_deleted_heading(card)
        self.assertFalse(heading.isVisible())


if __name__ == "__main__":
    unittest.main()
