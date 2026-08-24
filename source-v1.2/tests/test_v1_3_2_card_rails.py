from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.v1_3_2_card_rail_patch import (
    ACTION_BUTTON_SIZE,
    ACTION_ICON_SIZE,
    ACTION_RAIL_WIDTH,
    ACTIVE_BACKGROUND,
    INACTIVE_BACKGROUND,
    _configure_card_action_rails,
    _sync_card_rail_states,
)


ROOT = Path(__file__).resolve().parents[1]


class _Annotations:
    def __init__(self) -> None:
        self.note = ""

    def get(self, _key: str):
        return SimpleNamespace(
            note=self.note,
            checked=False,
            triangle=False,
            excluded=False,
        )


class _FakeWindow:
    def __init__(self) -> None:
        self.annotations = _Annotations()


class _Controller:
    def __init__(self) -> None:
        self.calls = 0

    def schedule(self) -> None:
        self.calls += 1


def _button(*, checkable: bool = False) -> QToolButton:
    button = QToolButton()
    button.setCheckable(checkable)
    return button


def _make_card() -> tuple[QFrame, QWidget, QWidget, dict[str, QToolButton]]:
    card = QFrame()
    outer = QVBoxLayout(card)

    image_host = QWidget(card)
    stack = QStackedLayout(image_host)
    stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
    image_label = QLabel()
    overlay = QWidget()
    overlay_layout = QHBoxLayout(overlay)
    stack.addWidget(image_label)
    stack.addWidget(overlay)
    stack.setCurrentWidget(overlay)
    outer.addWidget(image_host)
    outer.addWidget(QLabel("metadata"))

    buttons = {
        "move": _button(),
        "hide": _button(checkable=True),
        "info": _button(),
        "check": _button(checkable=True),
        "triangle": _button(checkable=True),
        "excluded": _button(checkable=True),
        "zoom": _button(),
        "memo": _button(),
    }
    for button in buttons.values():
        overlay_layout.addWidget(button)

    card._fh6_image_label = image_label
    card._fh6_game_move_button = buttons["move"]
    card._fh6_hide_button = buttons["hide"]
    card._fh6_info_button = buttons["info"]
    card._fh6_check_box = buttons["check"]
    card._fh6_triangle_box = buttons["triangle"]
    card._fh6_excluded_box = buttons["excluded"]
    card._fh6_zoom_button = buttons["zoom"]
    card._fh6_memo_button = buttons["memo"]
    card._fh6_aspect_thumbnail_controller = _Controller()
    return card, image_host, overlay, buttons


def _record(kind: str = "Livery") -> LiveryRecord:
    return LiveryRecord(
        container_name="sample",
        container_path=Path("sample"),
        kind=kind,
        header=HeaderInfo(
            name="Sample",
            creator="Painter",
            description="Has metadata",
            car_id=1,
            guid="guid-sample",
        ),
    )


def _position(layout, widget) -> tuple[int, int]:
    index = layout.indexOf(widget)
    row, column, _row_span, _column_span = layout.getItemPosition(index)
    return row, column


class V132CardRailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_actions_are_outside_thumbnail_and_use_shared_20px_geometry(self) -> None:
        window = _FakeWindow()
        card, image_host, overlay, buttons = _make_card()
        controller = card._fh6_aspect_thumbnail_controller

        _configure_card_action_rails(window, card, "livery", _record(), "key")
        QApplication.processEvents()

        shell = card._fh6_media_shell
        left_rail, right_rail = card._fh6_card_action_rails
        self.assertIs(image_host.parentWidget(), shell)
        self.assertFalse(overlay.isVisible())
        self.assertEqual(left_rail.width(), ACTION_RAIL_WIDTH)
        self.assertEqual(right_rail.width(), ACTION_RAIL_WIDTH)
        self.assertGreaterEqual(controller.calls, 1)

        for button in buttons.values():
            self.assertEqual(button.width(), ACTION_BUTTON_SIZE)
            self.assertEqual(button.height(), ACTION_BUTTON_SIZE)
            self.assertEqual(button.iconSize().width(), ACTION_ICON_SIZE)
            self.assertEqual(button.iconSize().height(), ACTION_ICON_SIZE)

    def test_left_and_right_actions_share_five_exact_rows(self) -> None:
        window = _FakeWindow()
        card, _image_host, _overlay, buttons = _make_card()
        _configure_card_action_rails(window, card, "livery", _record(), "key")

        left_rail, right_rail = card._fh6_card_action_rails
        left = left_rail.layout()
        right = right_rail.layout()

        self.assertEqual(_position(left, buttons["move"]), (0, 0))
        self.assertEqual(_position(left, buttons["hide"]), (3, 0))
        self.assertEqual(_position(left, buttons["info"]), (4, 0))
        self.assertEqual(_position(right, buttons["check"]), (0, 0))
        self.assertEqual(_position(right, buttons["triangle"]), (1, 0))
        self.assertEqual(_position(right, buttons["excluded"]), (2, 0))
        self.assertEqual(_position(right, buttons["zoom"]), (3, 0))
        self.assertEqual(_position(right, buttons["memo"]), (4, 0))

    def test_active_and_inactive_controls_share_one_color_system(self) -> None:
        window = _FakeWindow()
        card, _image_host, _overlay, buttons = _make_card()
        _configure_card_action_rails(window, card, "livery", _record(), "key")

        self.assertFalse(bool(buttons["check"].property("fh6RailActive")))
        self.assertIn(INACTIVE_BACKGROUND, buttons["check"].styleSheet())

        buttons["check"].setChecked(True)
        QApplication.processEvents()
        self.assertTrue(bool(buttons["check"].property("fh6RailActive")))
        self.assertIn(ACTIVE_BACKGROUND, buttons["check"].styleSheet())

        window.annotations.note = "memo text"
        _sync_card_rail_states(window, card)
        self.assertTrue(bool(buttons["memo"].property("fh6RailActive")))
        self.assertIn(ACTIVE_BACKGROUND, buttons["memo"].styleSheet())

        # Stateless usable actions use the same active purple treatment.
        self.assertTrue(bool(buttons["zoom"].property("fh6RailActive")))
        self.assertTrue(bool(buttons["move"].property("fh6RailActive")))

    def test_auction_card_keeps_move_slot_empty(self) -> None:
        window = _FakeWindow()
        card, _image_host, _overlay, buttons = _make_card()
        auction = _record("SoulBoundLivery")
        buttons["move"].setEnabled(False)

        _configure_card_action_rails(window, card, "livery", auction, "key")

        left_rail, _right_rail = card._fh6_card_action_rails
        self.assertEqual(left_rail.layout().indexOf(buttons["move"]), -1)
        self.assertFalse(buttons["move"].isVisible())

    def test_patch_order_keeps_global_aspect_before_rails_and_thread_fix_last(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        global_ui = "apply_v1_3_2_global_ui_patch(MainWindow)"
        rails = "apply_v1_3_2_card_rail_patch(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"
        self.assertIn(global_ui, source)
        self.assertIn(rails, source)
        self.assertIn(thread_fix, source)
        self.assertLess(source.index(global_ui), source.index(rails))
        self.assertLess(source.index(rails), source.index(thread_fix))


if __name__ == "__main__":
    unittest.main()
