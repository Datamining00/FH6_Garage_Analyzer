from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QToolButton

from fh6garage.v1_3_2_card_width_overlay_patch import (
    ACTION_BUTTON_SIZE,
    ACTION_ICON_SIZE,
    ACTIVE_BACKGROUND,
    CARD_MIN_WIDTH,
    CARD_TARGET_WIDTH,
    GRID_MIN_COLUMNS,
    INACTIVE_BACKGROUND,
    THUMBNAIL_SIDE_SAFE_PX,
    _apply_button_visual,
    _columns_for_inner_width,
    _safe_thumbnail_render_width,
)


ROOT = Path(__file__).resolve().parents[1]

# Validation branch only: implementation assertions are unchanged.


class V132CardWidthOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_grid_never_drops_below_two_columns(self) -> None:
        self.assertEqual(GRID_MIN_COLUMNS, 2)
        self.assertEqual(_columns_for_inner_width(1), 2)
        self.assertEqual(_columns_for_inner_width(CARD_TARGET_WIDTH), 2)
        self.assertEqual(_columns_for_inner_width(CARD_TARGET_WIDTH * 2 - 1), 2)

    def test_grid_has_no_hard_upper_column_cap(self) -> None:
        self.assertEqual(_columns_for_inner_width(CARD_TARGET_WIDTH * 3), 3)
        self.assertEqual(_columns_for_inner_width(CARD_TARGET_WIDTH * 6), 6)
        self.assertEqual(_columns_for_inner_width(CARD_TARGET_WIDTH * 10), 10)

    def test_thumbnail_keeps_symmetric_overlay_safe_zone(self) -> None:
        raw = 360
        self.assertEqual(THUMBNAIL_SIDE_SAFE_PX, 48)
        self.assertEqual(
            _safe_thumbnail_render_width(raw),
            raw - THUMBNAIL_SIDE_SAFE_PX * 2,
        )
        self.assertGreater(_safe_thumbnail_render_width(raw), 0)

    def test_card_minimum_stays_compatible_with_half_width_two_column_view(self) -> None:
        self.assertLessEqual(CARD_MIN_WIDTH, 340)

    def test_overlay_actions_keep_shared_20px_geometry_and_state_colors(self) -> None:
        button = QToolButton()
        _apply_button_visual(button, "search", False)
        self.assertEqual(button.width(), ACTION_BUTTON_SIZE)
        self.assertEqual(button.height(), ACTION_BUTTON_SIZE)
        self.assertEqual(ACTION_BUTTON_SIZE, 20)
        self.assertEqual(button.iconSize().width(), ACTION_ICON_SIZE)
        self.assertEqual(button.iconSize().height(), ACTION_ICON_SIZE)
        self.assertEqual(ACTION_ICON_SIZE, 14)
        self.assertIn(INACTIVE_BACKGROUND, button.styleSheet())

        _apply_button_visual(button, "search", True)
        self.assertTrue(bool(button.property("fh6OverlayActive")))
        self.assertIn(ACTIVE_BACKGROUND, button.styleSheet())

    def test_overlay_patch_replaces_rail_patch_and_thread_fix_remains_last(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        global_ui = "apply_v1_3_2_global_ui_patch(MainWindow)"
        overlay = "apply_v1_3_2_card_width_overlay_patch(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"
        self.assertIn(global_ui, source)
        self.assertIn(overlay, source)
        self.assertIn(thread_fix, source)
        self.assertNotIn("apply_v1_3_2_card_rail_patch(MainWindow)", source)
        self.assertLess(source.index(global_ui), source.index(overlay))
        self.assertLess(source.index(overlay), source.index(thread_fix))


if __name__ == "__main__":
    unittest.main()
