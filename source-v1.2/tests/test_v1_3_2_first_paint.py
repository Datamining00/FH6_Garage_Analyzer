from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QScrollArea, QWidget

from fh6garage.v1_3_2_card_parent_safety_patch import (
    apply_v1_3_2_card_parent_safety_patch,
)
from fh6garage.v1_3_2_first_paint_patch import (
    FIRST_PAINT_SETTLE_MS,
    _set_paint_barrier,
)


ROOT = Path(__file__).resolve().parents[1]


class _BarrierWindow:
    def __init__(self) -> None:
        for content_type in ("livery", "tuning"):
            scroll = QScrollArea()
            host = QWidget()
            host.setLayout(QGridLayout())
            scroll.setWidget(host)
            scroll.setWidgetResizable(True)
            setattr(self, f"{content_type}_grid_scroll", scroll)
            setattr(self, f"{content_type}_grid_host", host)
            setattr(self, f"{content_type}_grid_layout", host.layout())
            setattr(self, f"_{content_type}_grid_cards", [])


class _ParentWindow:
    def __init__(self) -> None:
        self.livery_grid_host = QWidget()
        self.tuning_grid_host = QWidget()
        self._fh6_v131_livery_card_width = 333
        self._fh6_v131_tuning_card_width = 287

    def _make_saved_content_card(self, content_type, record, key):
        return QFrame()


class V132FirstPaintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_paint_barrier_blocks_both_grid_viewports_and_hosts(self) -> None:
        window = _BarrierWindow()
        _set_paint_barrier(window, True)

        for content_type in ("livery", "tuning"):
            scroll = getattr(window, f"{content_type}_grid_scroll")
            host = getattr(window, f"{content_type}_grid_host")
            self.assertFalse(scroll.viewport().updatesEnabled())
            self.assertFalse(host.updatesEnabled())

        self.assertTrue(window._fh6_v132_first_paint_blocked)

        _set_paint_barrier(window, False)
        for content_type in ("livery", "tuning"):
            scroll = getattr(window, f"{content_type}_grid_scroll")
            host = getattr(window, f"{content_type}_grid_host")
            self.assertTrue(scroll.viewport().updatesEnabled())
            self.assertTrue(host.updatesEnabled())
        self.assertFalse(window._fh6_v132_first_paint_blocked)

    def test_deferred_card_inherits_last_settled_grid_width_before_rails(self) -> None:
        class MainWindow(_ParentWindow):
            pass

        apply_v1_3_2_card_parent_safety_patch(MainWindow)
        window = MainWindow()

        livery = window._make_saved_content_card("livery", object(), "l")
        tuning = window._make_saved_content_card("tuning", object(), "t")

        self.assertIs(livery.parentWidget(), window.livery_grid_host)
        self.assertIs(tuning.parentWidget(), window.tuning_grid_host)
        self.assertEqual(livery.width(), 333)
        self.assertEqual(tuning.width(), 287)
        self.assertEqual(livery.property("fh6InheritedSettledCardWidth"), 333)
        self.assertEqual(tuning.property("fh6InheritedSettledCardWidth"), 287)
        self.assertTrue(livery.isHidden())
        self.assertTrue(tuning.isHidden())

    def test_first_paint_wait_covers_existing_resize_debounce(self) -> None:
        # v1.3.1 uses a 110 ms resize debounce. The paint barrier must remain
        # active beyond it so the minimum-two-column intermediate frame cannot
        # become visible before the final 3/4-column layout settles.
        self.assertGreater(FIRST_PAINT_SETTLE_MS, 110)

    def test_patch_order_keeps_first_paint_after_rails_and_thread_fix_last(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        parent = "apply_v1_3_2_card_parent_safety_patch(MainWindow)"
        rails = "apply_v1_3_2_card_rail_patch(MainWindow)"
        first_paint = "apply_v1_3_2_first_paint_patch(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"

        for marker in (parent, rails, first_paint, thread_fix):
            self.assertIn(marker, source)
        self.assertLess(source.index(parent), source.index(rails))
        self.assertLess(source.index(rails), source.index(first_paint))
        self.assertLess(source.index(first_paint), source.index(thread_fix))


if __name__ == "__main__":
    unittest.main()
