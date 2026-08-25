from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QToolButton, QWidget

from fh6garage.card_action_alignment import (
    LiveryCardActionAligner,
    _eye_slash_pixmap,
)
from fh6garage.ui import _classification_pixmap


def _alpha_bounds(image) -> tuple[int, int]:
    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                xs.append(x)
                ys.append(y)
    if not xs:
        return (0, 0)
    return (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


class CardActionAlignmentV132Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv[:1])

    def test_runtime_alignment_patch_is_removed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_v1_3_2_card_alignment_patch(MainWindow)", app_source)
        self.assertFalse(
            (root / "fh6garage" / "v1_3_2_card_alignment_patch.py").exists()
        )

    def test_left_actions_lock_to_right_fourth_and_fifth_centers(self) -> None:
        overlay = QWidget()
        overlay.resize(500, 260)

        move = QToolButton(overlay)
        move.setGeometry(8, 10, 38, 38)
        hide = QToolButton(overlay)
        hide.setGeometry(8, 130, 38, 38)
        info = QToolButton(overlay)
        info.setGeometry(8, 210, 38, 38)
        fourth = QToolButton(overlay)
        fourth.setGeometry(454, 130, 38, 38)
        fifth = QToolButton(overlay)
        fifth.setGeometry(454, 174, 38, 38)

        card = QWidget()
        card._fh6_game_move_button = move
        card._fh6_hide_button = hide
        card._fh6_info_button = info
        card._fh6_check_box = QToolButton(overlay)
        card._fh6_check_box.setGeometry(454, 86, 38, 38)
        card._fh6_triangle_box = fourth
        card._fh6_excluded_box = fifth
        card._fh6_folder_button = QToolButton(overlay)
        card._fh6_zoom_button = QToolButton(overlay)
        card._fh6_zoom_button.setGeometry(454, 218, 38, 38)
        aligner = LiveryCardActionAligner(card, overlay)
        aligner.reposition()

        self.assertEqual(hide.geometry().center().y(), fourth.geometry().center().y())
        self.assertEqual(info.geometry().center().y(), fifth.geometry().center().y())
        self.assertEqual(hide.geometry().center().x(), move.geometry().center().x())
        self.assertEqual(info.geometry().center().x(), move.geometry().center().x())

        overlay.resize(500, 330)
        info.move(8, 280)
        aligner.reposition()
        self.assertEqual(info.geometry().center().y(), fifth.geometry().center().y())
        overlay.close()

    def test_checked_hide_icon_has_identical_alpha_geometry(self) -> None:
        off = _eye_slash_pixmap(False, 22).toImage()
        on = _eye_slash_pixmap(True, 22).toImage()
        self.assertEqual(off.size(), on.size())

        off_mask = []
        on_mask = []
        for y in range(off.height()):
            for x in range(off.width()):
                off_mask.append(off.pixelColor(x, y).alpha() > 0)
                on_mask.append(on.pixelColor(x, y).alpha() > 0)
        self.assertEqual(off_mask, on_mask)

    def test_hide_icon_matches_existing_card_icon_visual_scale(self) -> None:
        hide_image = _eye_slash_pixmap(False, 22).toImage()
        info_icon = QIcon(_classification_pixmap("livery_info", True, 24))
        info_image = info_icon.pixmap(QSize(22, 22)).toImage()

        hide_w, hide_h = _alpha_bounds(hide_image)
        info_w, info_h = _alpha_bounds(info_image)
        measured = f"hide={hide_w}x{hide_h}, info={info_w}x{info_h}"
        print(f"CARD_ICON_BOUNDS {measured}")

        self.assertLessEqual(
            abs(max(hide_w, hide_h) - max(info_w, info_h)), 1, measured
        )
        self.assertLessEqual(abs(hide_w - info_w), 2, measured)
        self.assertLessEqual(abs(hide_h - info_h), 2, measured)


if __name__ == "__main__":
    unittest.main()
