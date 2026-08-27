from __future__ import annotations

import types
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QLabel, QWidget

from fh6garage.memory_applied_state import PersistedAppliedState
from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.v1_3_2_dashboard_change_group_patch import _normalize_page_titles
from fh6garage.v1_3_2_memory_state_patch import (
    _PAINT_ICON_COLORS,
    _paint_state_for_record,
)


class RequestedV134ChangesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_saved_page_titles_are_hidden(self) -> None:
        window = QWidget()
        livery = QLabel("리버리", window)
        livery.setObjectName("pageTitle")
        tuning = QLabel("튜닝", window)
        tuning.setObjectName("pageTitle")
        dashboard = QLabel("대시보드", window)
        dashboard.setObjectName("pageTitle")

        _normalize_page_titles(window)

        self.assertTrue(livery.isHidden())
        self.assertTrue(tuning.isHidden())
        self.assertFalse(dashboard.isHidden())

    def test_unapplied_record_is_yellow_when_same_car_has_applied_livery(self) -> None:
        applied = LiveryRecord(
            "Livery_0001_20260101000000", Path("."), "Livery", HeaderInfo(car_id=1)
        )
        other = LiveryRecord(
            "Livery_0001_20260102000000", Path("."), "Livery", HeaderInfo(car_id=1)
        )
        window = types.SimpleNamespace(
            result=types.SimpleNamespace(liveries=[applied, other]),
            _fh6_memory_state=PersistedAppliedState(
                scanned_at="2026-08-27T00:00:00Z",
                pid=1234,
                active_livery_names=frozenset({"Livery_0001_20260101000000"}),
                consensus_status="HIGH",
            ),
        )

        self.assertEqual(_paint_state_for_record(window, applied), "applied")
        self.assertEqual(_paint_state_for_record(window, other), "same_car_applied")

    def test_paint_colors_have_white_background_contrast(self) -> None:
        self.assertEqual(_PAINT_ICON_COLORS["applied"].name(), "#16a34a")
        self.assertEqual(_PAINT_ICON_COLORS["same_car_applied"].name(), "#d97706")
        self.assertEqual(_PAINT_ICON_COLORS["unapplied"].name(), "#6b7280")

    def test_classification_icons_use_matching_contrast_colors(self) -> None:
        source = (Path(__file__).parents[1] / "fh6garage" / "ui.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"check": (QColor("#16a34a")', source)
        self.assertIn('"triangle": (QColor("#d97706")', source)
        self.assertIn('"excluded": (QColor("#dc2626")', source)


if __name__ == "__main__":
    unittest.main()
