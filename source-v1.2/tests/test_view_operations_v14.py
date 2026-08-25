from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from fh6garage.ui import MainWindow
from fh6garage.view_operations import ViewOperationCoordinator


ROOT = Path(__file__).resolve().parents[1]


class _Owner:
    def __init__(self) -> None:
        self.begin_messages: list[str] = []
        self.end_count = 0

    def _begin_busy(self, message: str) -> None:
        self.begin_messages.append(message)

    def _end_busy(self) -> None:
        self.end_count += 1


class CoordinatorViewOperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_latest_request_replaces_older_queued_work(self) -> None:
        owner = _Owner()
        coordinator = ViewOperationCoordinator(owner)
        calls: list[str] = []

        coordinator.request("livery", "first", lambda: calls.append("first"))
        coordinator.request("livery", "second", lambda: calls.append("second"))

        self.assertEqual(calls, [])
        self.assertEqual(owner.begin_messages, ["first"])
        self.app.processEvents()

        self.assertEqual(calls, ["second"])
        self.assertEqual(owner.end_count, 1)
        self.assertEqual(coordinator.stats()["view_operations_coalesced"], 1)

    def test_invalid_content_type_is_rejected(self) -> None:
        coordinator = ViewOperationCoordinator(_Owner())
        with self.assertRaises(ValueError):
            coordinator.request("cars", "invalid", lambda: None)

    def test_order_cache_reuses_previous_sort_result(self) -> None:
        coordinator = ViewOperationCoordinator(_Owner())
        calls: list[bool] = []

        first = coordinator.cached_order(
            ("livery", 1, "creator"),
            lambda: calls.append(True) or [3, 1, 2],
        )
        second = coordinator.cached_order(
            ("livery", 1, "creator"),
            lambda: calls.append(True) or [],
        )

        self.assertEqual(first, [3, 1, 2])
        self.assertEqual(second, [3, 1, 2])
        self.assertEqual(calls, [True])
        self.assertEqual(coordinator.stats()["view_order_cache_hits"], 1)


class MainWindowViewOperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setOrganizationName("FH6AssistantTests")
        cls.app.setApplicationName("FH6AssistantV14ViewOperations")

    def setUp(self) -> None:
        self.window = MainWindow(project_root=ROOT)
        for button in (
            self.window.livery_group_button,
            self.window.livery_creator_group_button,
        ):
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)
        self.window.result = SimpleNamespace(liveries=[], tunings=[])

    def tearDown(self) -> None:
        self.window._view_operations.cancel_pending()
        focused = QApplication.focusWidget()
        if focused is not None:
            focused.clearFocus()
        for timer in list(
            getattr(self.window, "_fh6_view_restore_timers", ())
        ):
            timer.stop()
            timer.deleteLater()
        self.window._fh6_view_restore_timers = []
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_group_operation_shows_busy_before_deferred_layout(self) -> None:
        calls: list[tuple[str, str, bool]] = []
        self.window._filter_saved_content_views = (
            lambda content_type, text, preserve_scroll=False:
            calls.append((content_type, text, preserve_scroll))
        )

        self.window._set_vehicle_grouping("livery", True)

        self.assertFalse(self.window._busy_overlay.isHidden())
        self.assertEqual(calls, [])
        self.app.processEvents()

        self.assertEqual(calls, [("livery", "", True)])
        self.assertFalse(self.window._busy_overlay.isVisible())

    def test_rapid_group_changes_keep_only_latest_layout(self) -> None:
        calls: list[str] = []
        self.window._filter_saved_content_views = (
            lambda content_type, text, preserve_scroll=False:
            calls.append(content_type)
        )

        self.window.livery_group_button.setChecked(True)
        self.window.livery_creator_group_button.setChecked(True)
        self.app.processEvents()

        self.assertEqual(calls, ["livery"])
        self.assertTrue(self.window.livery_creator_group_button.isChecked())
        self.assertFalse(self.window.livery_group_button.isChecked())
        self.assertGreaterEqual(
            self.window._view_operations.stats()["view_operations_coalesced"],
            1,
        )

    def test_sort_state_updates_immediately_and_rebuild_is_deferred(self) -> None:
        calls: list[str] = []
        self.window._populate_livery_table = lambda: calls.append(
            self.window._livery_sort_mode
        )

        self.window._set_saved_content_sort_mode("livery", "brand")
        self.window._set_saved_content_sort_mode("livery", "creator")

        self.assertEqual(self.window._livery_sort_mode, "creator")
        self.assertEqual(calls, [])
        self.app.processEvents()
        self.assertEqual(calls, ["creator"])


if __name__ == "__main__":
    unittest.main()
