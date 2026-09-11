from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QWidget

from fh6garage.v1_3_ui_patch import _grid_column_count
from fh6garage.v1_3_2_responsive_columns_fix import (
    _current_grid_columns,
    _dynamic_layout_visible_grid_cards,
    _dynamic_sync_grid_card_widths,
)


ROOT = Path(__file__).resolve().parents[1]


class _Toggle:
    def __init__(self, checked: bool = False) -> None:
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


class _Scroll:
    def __init__(self, width: int) -> None:
        self._viewport = QWidget()
        self._viewport.resize(width, 900)

    def viewport(self):
        return self._viewport


class _Search:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def text(self) -> str:
        return self._value


class V132ResponsiveColumnsFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_qhd_100_percent_viewport_resolves_to_four_columns(self) -> None:
        host = QWidget()
        layout = QGridLayout(host)
        owner = SimpleNamespace(
            tuning_grid_scroll=_Scroll(2300),
            tuning_grid_layout=layout,
        )
        self.assertEqual(_grid_column_count(owner, "tuning"), 4)

    def test_dynamic_layout_places_cards_across_four_columns(self) -> None:
        host = QWidget()
        layout = QGridLayout(host)
        cards = [QFrame(host) for _ in range(6)]
        owner = SimpleNamespace(
            tuning_grid_layout=layout,
            tuning_group_button=_Toggle(False),
            tuning_creator_group_button=_Toggle(False),
            _fh6_grid_column_count=lambda content_type: 4,
            _busy_depth=0,
        )

        _dynamic_layout_visible_grid_cards(owner, "tuning", cards)

        expected = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1)]
        actual = []
        for card in cards:
            index = layout.indexOf(card)
            row, column, _row_span, _column_span = layout.getItemPosition(index)
            actual.append((row, column))
        self.assertEqual(actual, expected)
        self.assertEqual(owner._fh6_tuning_grid_columns, 4)

    def test_group_header_and_group_cards_use_current_column_count(self) -> None:
        host = QWidget()
        layout = QGridLayout(host)
        cards = [QFrame(host) for _ in range(5)]
        for card in cards:
            card.setProperty("creatorGroupKey", "creator")
            card.setProperty("creatorGroupLabel", "Creator")

        owner = SimpleNamespace(
            tuning_grid_layout=layout,
            tuning_group_button=_Toggle(False),
            tuning_creator_group_button=_Toggle(True),
            _tuning_group_headers={},
            _fh6_grid_column_count=lambda content_type: 4,
            _busy_depth=0,
        )

        _dynamic_layout_visible_grid_cards(owner, "tuning", cards)
        header = owner._tuning_group_headers["creator"]
        header_index = layout.indexOf(header)
        row, column, row_span, column_span = layout.getItemPosition(header_index)
        self.assertEqual((row, column, row_span, column_span), (0, 0, 1, 4))

        card_positions = []
        for card in cards:
            index = layout.indexOf(card)
            card_row, card_column, _rs, _cs = layout.getItemPosition(index)
            card_positions.append((card_row, card_column))
        self.assertEqual(
            card_positions,
            [(1, 0), (1, 1), (1, 2), (1, 3), (2, 0)],
        )

    def test_width_sync_divides_available_space_by_dynamic_columns(self) -> None:
        host = QWidget()
        layout = QGridLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        cards = [QFrame(host) for _ in range(4)]
        owner = SimpleNamespace(
            tuning_grid_scroll=_Scroll(2300),
            tuning_grid_layout=layout,
            _tuning_grid_cards=cards,
            tuning_grid_host=host,
            _fh6_grid_column_count=lambda content_type: 4,
            _fh6_tuning_grid_columns=4,
            _busy_depth=0,
        )

        _dynamic_sync_grid_card_widths(owner, "tuning")
        expected = (2300 - (8 * 3) - 4) // 4
        self.assertTrue(all(card.width() == expected for card in cards))

    def test_column_transition_requests_one_relayout(self) -> None:
        host = QWidget()
        layout = QGridLayout(host)
        calls = []
        owner = SimpleNamespace(
            tuning_grid_scroll=_Scroll(2300),
            tuning_grid_layout=layout,
            _tuning_grid_cards=[QFrame(host)],
            tuning_grid_host=host,
            tuning_search=_Search("needle"),
            _fh6_grid_column_count=lambda content_type: 4,
            _fh6_tuning_grid_columns=2,
            _relayout_tuning_grid=lambda text: calls.append(text),
            _busy_depth=0,
        )

        _dynamic_sync_grid_card_widths(owner, "tuning")
        self.assertEqual(calls, ["needle"])
        self.assertEqual(owner._fh6_tuning_grid_columns, 4)

    def test_column_counter_is_clamped_to_release_contract(self) -> None:
        low = SimpleNamespace(_fh6_grid_column_count=lambda content_type: 1)
        high = SimpleNamespace(_fh6_grid_column_count=lambda content_type: 99)
        self.assertEqual(_current_grid_columns(low, "livery"), 2)
        self.assertEqual(_current_grid_columns(high, "livery"), 4)

    def test_patch_order_is_responsive_then_column_fix_then_thread_finalizer(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        responsive = "apply_v1_3_2_responsiveness_sort_patch(MainWindow)"
        columns_fix = "apply_v1_3_2_responsive_columns_fix(MainWindow)"
        refresh = "apply_v1_3_2_refresh_diff_patch(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"
        self.assertIn(responsive, source)
        self.assertIn(columns_fix, source)
        self.assertIn(refresh, source)
        self.assertIn(thread_fix, source)
        self.assertLess(source.index(responsive), source.index(columns_fix))
        self.assertLess(source.index(columns_fix), source.index(refresh))
        self.assertLess(source.index(refresh), source.index(thread_fix))


if __name__ == "__main__":
    unittest.main()
