from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QTimer

from fh6garage import scan_lifecycle_controller as lifecycle


class _RunningThread:
    def isRunning(self) -> bool:
        return True


class _Text:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def text(self) -> str:
        return self._value


class _Viewport:
    def __init__(self) -> None:
        self.updated = 0

    def update(self) -> None:
        self.updated += 1


class _Table:
    def __init__(self) -> None:
        self._viewport = _Viewport()

    def viewport(self) -> _Viewport:
        return self._viewport


class ScanRefreshCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_refresh_during_scan_preserves_latest_request(self) -> None:
        owner = SimpleNamespace(
            _scan_thread=_RunningThread(),
            _pending_scan_request=None,
        )

        lifecycle.start_scan(owner, Path("new-save"), object)

        self.assertEqual(owner._pending_scan_request, (Path("new-save"), object))

    def test_cleanup_starts_preserved_refresh_on_next_event_turn(self) -> None:
        calls: list[tuple[Path, type]] = []
        owner = SimpleNamespace(
            _scan_thread=_RunningThread(),
            _scan_worker=object(),
            _pending_scan_request=(Path("new-save"), str),
        )
        original = lifecycle.start_scan
        lifecycle.start_scan = lambda _owner, path, worker: calls.append((path, worker))
        try:
            lifecycle.cleanup_scan(owner)
            self.app.processEvents()
        finally:
            lifecycle.start_scan = original

        self.assertEqual(calls, [(Path("new-save"), str)])
        self.assertIsNone(owner._pending_scan_request)

    def test_finalize_scan_views_relayouts_latest_result(self) -> None:
        result = object()
        calls: list[tuple[str, str]] = []
        car_table = _Table()
        creator_table = _Table()
        page = SimpleNamespace(updateGeometry=lambda: calls.append(("page", "geometry")), update=lambda: calls.append(("page", "update")))
        owner = SimpleNamespace(
            result=result,
            livery_search=_Text("livery query"),
            tuning_search=_Text("tuning query"),
            _relayout_livery_grid=lambda text: calls.append(("livery", text)),
            _relayout_tuning_grid=lambda text: calls.append(("tuning", text)),
            car_table=car_table,
            creator_table=creator_table,
            pages=SimpleNamespace(currentWidget=lambda: page),
        )

        lifecycle.finalize_scan_views(owner, result)

        self.assertIn(("livery", "livery query"), calls)
        self.assertIn(("tuning", "tuning query"), calls)
        self.assertEqual(car_table.viewport().updated, 1)
        self.assertEqual(creator_table.viewport().updated, 1)

    def test_stale_finalize_callback_is_ignored(self) -> None:
        calls: list[str] = []
        owner = SimpleNamespace(
            result=object(),
            _relayout_livery_grid=lambda _text: calls.append("livery"),
        )

        lifecycle.finalize_scan_views(owner, object())

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
