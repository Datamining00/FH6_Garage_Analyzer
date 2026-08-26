from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QLabel, QStackedLayout, QToolButton, QVBoxLayout, QWidget

from fh6garage.ui import BusyOverlay
from fh6garage.card_visuals import (
    CARD_ACTION_BUTTON_SIZE,
    CARD_ACTION_ICON_SIZE,
    CARD_ACTION_RADIUS,
    _fix_busy_overlay,
    _normalize_card_actions,
)


ROOT = Path(__file__).resolve().parents[1]


class V132IconOverlayFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_all_card_actions_use_30px_outer_and_20px_inner(self) -> None:
        card = QWidget()
        names = (
            "_fh6_game_move_button",
            "_fh6_hide_button",
            "_fh6_info_button",
            "_fh6_check_box",
            "_fh6_triangle_box",
            "_fh6_excluded_box",
            "_fh6_zoom_button",
            "_fh6_memo_button",
        )
        buttons = []
        for name in names:
            button = QToolButton(card)
            button.setFixedSize(38, 38)
            button.setIconSize(QSize(23, 23))
            setattr(card, name, button)
            buttons.append(button)

        _normalize_card_actions(card)

        self.assertEqual(CARD_ACTION_BUTTON_SIZE, 30)
        self.assertEqual(CARD_ACTION_ICON_SIZE, 20)
        self.assertEqual(CARD_ACTION_RADIUS, 8)
        for button in buttons:
            self.assertEqual(button.size(), QSize(30, 30))
            self.assertEqual(button.iconSize(), QSize(20, 20))
            self.assertIn("border-radius: 8px", button.styleSheet())

    def test_thumbnail_action_overlay_is_explicitly_transparent(self) -> None:
        card = QWidget()
        host = QWidget(card)
        stack = QStackedLayout(host)
        image = QLabel(host)
        overlay = QWidget(host)
        stack.addWidget(image)
        stack.addWidget(overlay)
        stack.setCurrentWidget(overlay)
        card._fh6_image_label = image

        _normalize_card_actions(card)

        self.assertEqual(overlay.objectName(), "fh6ThumbnailActionOverlay")
        self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground))
        self.assertIn("background: transparent", overlay.styleSheet())
        self.assertIn("color:#737787", image.styleSheet())

    def test_busy_overlay_qss_is_scoped_and_message_has_explicit_contrast(self) -> None:
        parent = QWidget()
        busy = BusyOverlay(parent)
        window = SimpleNamespace(_busy_overlay=busy)

        _fix_busy_overlay(window)

        self.assertEqual(busy.objectName(), "fh6BusyOverlay")
        self.assertEqual(busy.message.objectName(), "fh6BusyMessage")
        self.assertEqual(busy.progress.objectName(), "fh6BusyProgress")
        self.assertIn("QWidget#fh6BusyOverlay", busy.styleSheet())
        self.assertIn("QFrame#fh6BusyPanel", busy.styleSheet())
        self.assertIn("background: #ffffff", busy.styleSheet())
        self.assertIn("color: #20232d", busy.styleSheet())
        self.assertNotIn("background:rgba(23,24,33,145);", busy.styleSheet())

    def test_global_ui_icon_overlay_and_scan_processing_are_integrated(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        global_ui = "apply_v1_3_2_global_ui_patch(MainWindow)"
        icon_overlay = "apply_v1_3_2_icon_overlay_fix(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"
        self.assertNotIn(global_ui, source)
        self.assertNotIn(icon_overlay, source)
        self.assertNotIn(thread_fix, source)
        ui_source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("populate_scan_result_ui(self, self._populate_all_content)", ui_source)
        self.assertIn("_fix_busy_overlay(self)", ui_source)
        factory_source = (ROOT / "fh6garage" / "saved_content_card_factory.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("_normalize_card_actions(card)", factory_source)
        self.assertNotIn("apply_v1_3_2_card_width_overlay_patch(MainWindow)", source)
        self.assertNotIn("apply_v1_3_2_card_rail_patch(MainWindow)", source)


if __name__ == "__main__":
    unittest.main()
