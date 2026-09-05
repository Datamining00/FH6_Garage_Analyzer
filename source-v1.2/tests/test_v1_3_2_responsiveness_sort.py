from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from fh6garage.v1_3_2_responsiveness_sort_patch import (
    _AUCTION_APPLIED_MODE,
    _HIDDEN_MODE,
    _BUSY_YIELD_INTERVAL_SECONDS,
    _install_download_sort_default,
    _livery_visibility_allowed,
    _yield_busy_events,
)


ROOT = Path(__file__).resolve().parents[1]


class _PropertyCard:
    def __init__(self, **properties):
        self._properties = properties

    def property(self, name: str):
        return self._properties.get(name)


class _Filter:
    def __init__(self, modes=()):
        self._modes = set(modes)

    def selected_modes(self):
        return set(self._modes)


class V132ResponsivenessSortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_busy_yield_services_timer_events(self) -> None:
        fired = []
        owner = SimpleNamespace(
            _busy_depth=1,
            _fh6_busy_last_yield=0.0,
            _fh6_busy_event_pump_active=False,
        )
        QTimer.singleShot(0, lambda: fired.append(True))
        _yield_busy_events(owner, force=True)
        self.assertEqual(fired, [True])
        self.assertEqual(_BUSY_YIELD_INTERVAL_SECONDS, 0.05)

    def test_busy_yield_does_nothing_when_no_busy_overlay_is_active(self) -> None:
        fired = []
        owner = SimpleNamespace(
            _busy_depth=0,
            _fh6_busy_last_yield=0.0,
            _fh6_busy_event_pump_active=False,
        )
        QTimer.singleShot(0, lambda: fired.append(True))
        _yield_busy_events(owner, force=True)
        self.assertEqual(fired, [])
        QApplication.processEvents()

    def test_first_download_sort_click_is_descending_then_toggles(self) -> None:
        class DummyWindow:
            def __init__(self):
                self._livery_sort_mode = "__initial__"
                self._livery_sort_descending = False
                self.calls = []

            def _set_saved_content_sort_mode(self, content_type: str, mode: str) -> None:
                if content_type == "livery":
                    self._livery_sort_descending = (
                        not self._livery_sort_descending
                        if self._livery_sort_mode == mode
                        else False
                    )
                    self._livery_sort_mode = mode
                self.calls.append((content_type, mode))

        _install_download_sort_default(DummyWindow)
        window = DummyWindow()
        window._set_saved_content_sort_mode("livery", "download")
        self.assertEqual(window._livery_sort_mode, "download")
        self.assertTrue(window._livery_sort_descending)

        window._set_saved_content_sort_mode("livery", "download")
        self.assertFalse(window._livery_sort_descending)

        window._set_saved_content_sort_mode("livery", "brand")
        window._set_saved_content_sort_mode("livery", "download")
        self.assertTrue(window._livery_sort_descending)

    def test_hidden_livery_visibility_contract_is_preserved(self) -> None:
        owner = SimpleNamespace(
            livery_check_filter=_Filter(),
            _fh6_v132_is_livery_hidden=lambda key: key == "hidden",
            _fh6_v132_is_auction_applied=lambda record: False,
            _record_for_content_key=lambda content_type, key: None,
        )
        self.assertFalse(
            _livery_visibility_allowed(owner, _PropertyCard(annotationKey="hidden"))
        )
        owner.livery_check_filter = _Filter({_HIDDEN_MODE})
        self.assertTrue(
            _livery_visibility_allowed(owner, _PropertyCard(annotationKey="hidden"))
        )
        self.assertFalse(
            _livery_visibility_allowed(owner, _PropertyCard(annotationKey="visible"))
        )

    def test_auction_filter_rejects_non_auction_records(self) -> None:
        owner = SimpleNamespace(
            livery_check_filter=_Filter({_AUCTION_APPLIED_MODE}),
            _fh6_v132_is_livery_hidden=lambda key: False,
            _fh6_v132_is_auction_applied=lambda record: True,
            _record_for_content_key=lambda content_type, key: None,
        )
        self.assertFalse(
            _livery_visibility_allowed(owner, _PropertyCard(annotationKey="normal"))
        )

    def test_patch_order_keeps_thread_affinity_fix_final(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        compact = "apply_v1_3_2_compact_card_layout_patch(MainWindow)"
        responsive = "apply_v1_3_2_responsiveness_sort_patch(MainWindow)"
        thread_fix = "apply_v1_3_2_thread_affinity_fix(MainWindow)"
        self.assertIn(compact, source)
        self.assertIn(responsive, source)
        self.assertIn(thread_fix, source)
        self.assertLess(source.index(compact), source.index(responsive))
        self.assertLess(source.index(responsive), source.index(thread_fix))


if __name__ == "__main__":
    unittest.main()
