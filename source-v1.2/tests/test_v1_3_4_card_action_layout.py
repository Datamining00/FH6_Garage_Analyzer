from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QToolButton, QWidget

from fh6garage.v1_3_4_card_action_layout_patch import (
    BUTTON_GAP,
    CARD_METADATA_HEIGHT,
    CARD_MIN_HEIGHT,
    EDGE_MARGIN,
    ICON_SIZE,
    ROW_HEIGHT,
    THUMBNAIL_MIN_HEIGHT,
    _SixRowActionAligner,
)


_APP = QApplication.instance() or QApplication([])


class V134CardActionLayoutTests(unittest.TestCase):
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
        self.assertIn('_legacy_runtime._force_card_action_geometry = lambda _card: None', source)

    def test_patch_runs_before_thread_affinity_finalizer(self) -> None:
        source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        layout = source.index("apply_v1_3_4_card_action_layout_patch(MainWindow)")
        finalizer = source.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(layout, finalizer)

    def test_both_columns_use_the_same_six_row_centers(self) -> None:
        overlay = QWidget()
        overlay.resize(560, THUMBNAIL_MIN_HEIGHT)
        left_sizes = (38, 34, 34, 38, 30, 34)
        right_sizes = (30, 34, 38, 34, 34, 34)
        left = [QToolButton(overlay) for _ in left_sizes]
        right = [QToolButton(overlay) for _ in right_sizes]
        for button, size in zip(left, left_sizes):
            button.setFixedSize(size, size)
        for button, size in zip(right, right_sizes):
            button.setFixedSize(size, size)

        aligner = _SixRowActionAligner(overlay, left, right)
        aligner.reposition()

        for row, (left_button, right_button) in enumerate(zip(left, right)):
            expected_center = EDGE_MARGIN + row * (ROW_HEIGHT + BUTTON_GAP) + ROW_HEIGHT / 2
            self.assertEqual(left_button.x(), EDGE_MARGIN)
            self.assertEqual(right_button.x(), overlay.width() - EDGE_MARGIN - right_button.width())
            self.assertEqual(left_button.y() + left_button.height() / 2, expected_center)
            self.assertEqual(right_button.y() + right_button.height() / 2, expected_center)


if __name__ == "__main__":
    unittest.main()
