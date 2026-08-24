from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from fh6garage.ui import CopyValueLabel
from fh6garage.v1_3_2_compact_card_layout_patch import (
    CONTENT_HORIZONTAL_MARGIN,
    GRID_HORIZONTAL_SPACING,
    GRID_SIDE_MARGIN,
    SIDEBAR_HORIZONTAL_MARGIN,
    SIDEBAR_WIDTH,
    _ElidedCopyValueController,
    _compact_window_chrome,
    _configure_card_metadata,
)


ROOT = Path(__file__).resolve().parents[1]


class V132CompactCardLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_compact_window_reclaims_horizontal_space(self) -> None:
        window = QMainWindow()
        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(170)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(15, 18, 15, 18)
        outer.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 18, 22, 18)
        outer.addWidget(content, 1)
        window.setCentralWidget(root)

        livery_host = QWidget()
        tuning_host = QWidget()
        window.livery_grid_layout = QGridLayout(livery_host)
        window.tuning_grid_layout = QGridLayout(tuning_host)
        for layout in (window.livery_grid_layout, window.tuning_grid_layout):
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setHorizontalSpacing(14)

        _compact_window_chrome(window)

        self.assertEqual(SIDEBAR_WIDTH, 150)
        self.assertEqual(sidebar.width(), 150)
        self.assertEqual(side_layout.contentsMargins().left(), SIDEBAR_HORIZONTAL_MARGIN)
        self.assertEqual(side_layout.contentsMargins().right(), SIDEBAR_HORIZONTAL_MARGIN)
        self.assertEqual(content_layout.contentsMargins().left(), CONTENT_HORIZONTAL_MARGIN)
        self.assertEqual(content_layout.contentsMargins().right(), CONTENT_HORIZONTAL_MARGIN)
        for layout in (window.livery_grid_layout, window.tuning_grid_layout):
            self.assertEqual(layout.contentsMargins().left(), GRID_SIDE_MARGIN)
            self.assertEqual(layout.contentsMargins().right(), GRID_SIDE_MARGIN)
            self.assertEqual(layout.horizontalSpacing(), GRID_HORIZONTAL_SPACING)

    def test_title_and_creator_use_equal_halves(self) -> None:
        card = QWidget()
        outer = QVBoxLayout(card)
        vehicle = CopyValueLabel("차량명", "1969 Nissan Fairlady 432 Z")
        title = CopyValueLabel("제목", "Shana | Guren S30 (V2)")
        creator = CopyValueLabel("제작자", "Apophis S")
        outer.addWidget(vehicle)
        row = QHBoxLayout()
        row.setSpacing(7)
        row.addWidget(title, 3)
        row.addWidget(creator, 2)
        outer.addLayout(row)

        # _configure_card_metadata uses the active translated prefixes. Make the
        # test labels match the requested Korean card wording directly.
        from fh6garage import i18n
        original = i18n._TRANSLATIONS["card.creator_label"]["ko"]
        i18n._TRANSLATIONS["card.creator_label"]["ko"] = "제작자"
        try:
            _configure_card_metadata(card)
        finally:
            i18n._TRANSLATIONS["card.creator_label"]["ko"] = original

        self.assertEqual(row.spacing(), 0)
        self.assertEqual(row.stretch(0), 1)
        self.assertEqual(row.stretch(1), 1)
        self.assertEqual(len(card._fh6_metadata_elide_controllers), 3)

    def test_elision_tooltip_only_when_text_is_truncated(self) -> None:
        label = CopyValueLabel("제작자", "VeryLongCreatorName123456789")
        label.setFixedWidth(90)
        controller = _ElidedCopyValueController(label)
        controller.apply()
        self.assertTrue(label.text().endswith("…"))
        self.assertEqual(label.toolTip(), "제작자: VeryLongCreatorName123456789")

        label.setFixedWidth(600)
        controller.apply()
        self.assertEqual(label.text(), "제작자: VeryLongCreatorName123456789")
        self.assertEqual(label.toolTip(), "")

    def test_patch_order_keeps_icon_fix_and_thread_finalizer(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        icon_fix = "apply_v1_3_2_icon_overlay_fix(MainWindow)"
        compact = "apply_v1_3_2_compact_card_layout_patch(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"
        self.assertIn(icon_fix, source)
        self.assertIn(compact, source)
        self.assertIn(thread_fix, source)
        self.assertLess(source.index(icon_fix), source.index(compact))
        self.assertLess(source.index(compact), source.index(thread_fix))


if __name__ == "__main__":
    unittest.main()
