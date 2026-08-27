from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage.v1_3_4_card_action_layout_patch import (
    BUTTON_GAP,
    CARD_MIN_HEIGHT,
    EDGE_MARGIN,
    ICON_SIZE,
    THUMBNAIL_MIN_HEIGHT,
)


class V134CardActionLayoutTests(unittest.TestCase):
    def test_requested_geometry_constants(self) -> None:
        self.assertEqual(ICON_SIZE, 20)
        self.assertEqual(BUTTON_GAP, 5)
        self.assertEqual(EDGE_MARGIN, 5)
        self.assertGreaterEqual(THUMBNAIL_MIN_HEIGHT, 263)
        self.assertGreaterEqual(CARD_MIN_HEIGHT, 370)

    def test_layout_contains_requested_six_rows(self) -> None:
        source = (Path(__file__).parents[1] / "fh6garage" / "v1_3_4_card_action_layout_patch.py").read_text(encoding="utf-8")
        self.assertIn('(\"move\", \"zoom\", \"memo\", \"info\", \"folder\")', source)
        self.assertIn('(\"hide\", \"check\", \"triangle\", \"excluded\")', source)
        self.assertIn('lock.setCheckable(True)', source)
        self.assertIn('export.setEnabled(False)', source)

    def test_patch_runs_before_thread_affinity_finalizer(self) -> None:
        source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        layout = source.index("apply_v1_3_4_card_action_layout_patch(MainWindow)")
        finalizer = source.index("apply_v1_3_2_thread_affinity_fix(MainWindow)")
        self.assertLess(layout, finalizer)


if __name__ == "__main__":
    unittest.main()
