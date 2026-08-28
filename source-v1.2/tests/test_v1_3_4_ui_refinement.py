from __future__ import annotations

import unittest

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout

from fh6garage.i18n import set_language, tr
from fh6garage.ui import CopyValueLabel
from fh6garage.v1_3_4_card_action_layout_patch import (
    BUTTON_GAP,
    CLASSIFICATION_ACTIVE_COLORS,
    LOCK_ACTIVE_BACKGROUND,
    LOCK_ACTIVE_BORDER,
    LOCK_ACTIVE_ICON,
    _normalize_metadata,
    _placeholder_button,
    _run_busy,
)


_APP = QApplication.instance() or QApplication([])


class V134UiRefinementTests(unittest.TestCase):
    def setUp(self) -> None:
        set_language("ko")

    def test_classification_colors_are_non_neon_contrast_colors(self) -> None:
        self.assertEqual(CLASSIFICATION_ACTIVE_COLORS["check"], "#16a34a")
        self.assertEqual(CLASSIFICATION_ACTIVE_COLORS["triangle"], "#d97706")
        self.assertEqual(CLASSIFICATION_ACTIVE_COLORS["excluded"], "#dc2626")

    def test_lock_checked_style_is_high_contrast(self) -> None:
        host = QFrame()
        button = _placeholder_button(host, "lock", QIcon(), "lock")
        style = button.styleSheet()
        self.assertIn(LOCK_ACTIVE_BACKGROUND, style)
        self.assertIn(LOCK_ACTIVE_BORDER, style)
        self.assertEqual(LOCK_ACTIVE_ICON, "#ffffff")

    def test_metadata_labels_and_bottom_gap_are_normalized(self) -> None:
        card = QFrame()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        vehicle = CopyValueLabel(tr("card.vehicle_label"), "1969 Toyota 2000GT", card)
        creator = CopyValueLabel(tr("card.creator_label"), "guutara1158", card)
        title = CopyValueLabel(tr("card.title_label"), "hokusai", card)
        source = QLabel("", card)
        source.setObjectName("fh6AcquisitionPlaceholder")
        outer.addWidget(vehicle)
        outer.addWidget(creator)
        outer.addWidget(title)
        outer.addWidget(source)

        _normalize_metadata(card)

        self.assertEqual(vehicle.text(), "차량: 1969 Toyota 2000GT")
        self.assertEqual(creator.text(), "제작: guutara1158")
        self.assertEqual(title.text(), "제목: hokusai")
        self.assertEqual(source.text(), "출처:")
        self.assertEqual(outer.spacing(), BUTTON_GAP)
        self.assertEqual(outer.contentsMargins().bottom(), BUTTON_GAP)

    def test_busy_wrapper_uses_exact_processing_text_and_always_closes(self) -> None:
        events: list[str] = []

        class Owner:
            def _begin_busy(self, message: str) -> None:
                events.append(f"begin:{message}")

            def _end_busy(self) -> None:
                events.append("end")

        def action(value: int) -> int:
            events.append(f"action:{value}")
            return value + 1

        result = _run_busy(Owner(), action, 4)
        self.assertEqual(result, 5)
        self.assertEqual(events, ["begin:처리 중", "action:4", "end"])


if __name__ == "__main__":
    unittest.main()
