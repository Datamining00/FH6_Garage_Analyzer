from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QThread, QTimer, Signal, Slot

from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage import v1_3_4_backup_lazy_load_patch as lazy
from fh6garage.v1_3_4_backup_lazy_thread_bridge_patch import _BackupLoadGuiBridge


class _Emitter(QObject):
    finished = Signal(object)

    def __init__(self, result: object) -> None:
        super().__init__()
        self.result = result

    @Slot()
    def run(self) -> None:
        self.finished.emit(self.result)


class _FakeCard(QObject):
    def hide(self) -> None:
        pass


class BackupLazyThreadBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    @staticmethod
    def _record(index: int) -> LiveryRecord:
        name = f"backup-{index:03d}"
        return LiveryRecord(
            container_name=name,
            container_path=Path("C:/backup") / name,
            kind="Livery",
            header=HeaderInfo(name=name, creator="Creator", car_id=index),
            content_sha256=f"digest-{index:03d}",
        )

    @classmethod
    def _result(cls, count: int) -> lazy._LoadResult:
        items = []
        for index in range(count):
            record = cls._record(index)
            entry = {
                "kind": "Livery",
                "original_container_name": record.container_name,
                "relative_path": f"Livery/Creator/{record.container_name}",
                "content_sha256": record.content_sha256,
            }
            items.append((entry, record, "backup"))
        return lazy._LoadResult(
            items=items,
            total_backup=count,
            game_only=0,
            both=0,
            signature=("C:/backup", 1, 1, 1),
        )

    def test_worker_result_is_delivered_on_window_thread(self) -> None:
        window = QObject()
        token = lazy._CancelToken()
        window._fh6_backup_cancel_token = token
        bridge = _BackupLoadGuiBridge(window, token)
        result = self._result(1)
        emitter = _Emitter(result)
        thread = QThread()
        emitter.moveToThread(thread)
        loop = QEventLoop()
        observed = {"called": False, "gui_thread": False, "timed_out": False}

        def receive(owner: object, delivered: object, delivered_token: object) -> None:
            observed["called"] = True
            observed["gui_thread"] = QThread.currentThread() is window.thread()
            self.assertIs(owner, window)
            self.assertIs(delivered, result)
            self.assertIs(delivered_token, token)
            loop.quit()

        emitter.finished.connect(bridge.worker_finished)
        emitter.finished.connect(thread.quit)
        thread.started.connect(emitter.run)

        def timeout() -> None:
            observed["timed_out"] = True
            loop.quit()

        with patch.object(lazy, "_worker_finished", side_effect=receive):
            thread.start()
            QTimer.singleShot(2000, timeout)
            loop.exec()
            thread.quit()
            thread.wait(2000)

        self.assertFalse(observed["timed_out"])
        self.assertTrue(observed["called"])
        self.assertTrue(observed["gui_thread"])

    def test_twenty_five_cards_finish_across_multiple_timer_chunks(self) -> None:
        window = QObject()
        token = lazy._CancelToken()
        window._fh6_backup_cancel_token = token
        window._fh6_backup_cards = []
        created: list[_FakeCard] = []
        committed: list[object] = []
        finished = {"value": False, "timed_out": False}
        loop = QEventLoop()

        def factory(_content_type: str, _record: LiveryRecord, _key: str) -> _FakeCard:
            card = _FakeCard(window)
            created.append(card)
            return card

        def commit(_owner: object, _result: object, cards: list[object], _reused: set[int]) -> None:
            committed.extend(cards)

        def finish(_owner: object) -> None:
            finished["value"] = True
            loop.quit()

        window._fh6_backup_original_make_saved_content_card = factory
        result = self._result(25)

        with patch.object(lazy._backup_ui, "_backup_sort_key", side_effect=lambda _owner, item: (item[1].container_name,)), patch.object(
            lazy._ref, "_configure_backup_card", return_value=None
        ), patch.object(lazy, "_commit_cards", side_effect=commit), patch.object(
            lazy, "_load_finished", side_effect=finish
        ):
            lazy._build_cards_from_result(window, result, token)

            def timeout() -> None:
                finished["timed_out"] = True
                loop.quit()

            QTimer.singleShot(3000, timeout)
            loop.exec()

        self.assertFalse(finished["timed_out"])
        self.assertTrue(finished["value"])
        self.assertEqual(len(created), 25)
        self.assertEqual(len(committed), 25)
        self.assertIsNone(getattr(window, "_fh6_backup_card_chunk_timer", None))

    def test_chunk_cancellation_does_not_commit_partial_cards(self) -> None:
        window = QObject()
        token = lazy._CancelToken()
        window._fh6_backup_cancel_token = token
        window._fh6_backup_cards = []
        created: list[_FakeCard] = []
        cancelled = {"value": False, "timed_out": False}
        commit_calls = {"count": 0}
        loop = QEventLoop()

        def factory(_content_type: str, _record: LiveryRecord, _key: str) -> _FakeCard:
            card = _FakeCard(window)
            created.append(card)
            if len(created) == lazy._CARD_BUILD_CHUNK:
                token.cancel()
            return card

        def cancelled_handler(_owner: object) -> None:
            cancelled["value"] = True
            loop.quit()

        def commit(*_args: object, **_kwargs: object) -> None:
            commit_calls["count"] += 1

        window._fh6_backup_original_make_saved_content_card = factory
        result = self._result(25)

        with patch.object(lazy._backup_ui, "_backup_sort_key", side_effect=lambda _owner, item: (item[1].container_name,)), patch.object(
            lazy._ref, "_configure_backup_card", return_value=None
        ), patch.object(lazy, "_commit_cards", side_effect=commit), patch.object(
            lazy, "_load_cancelled", side_effect=cancelled_handler
        ):
            lazy._build_cards_from_result(window, result, token)

            def timeout() -> None:
                cancelled["timed_out"] = True
                loop.quit()

            QTimer.singleShot(3000, timeout)
            loop.exec()

        self.assertFalse(cancelled["timed_out"])
        self.assertTrue(cancelled["value"])
        self.assertEqual(len(created), lazy._CARD_BUILD_CHUNK)
        self.assertEqual(commit_calls["count"], 0)
        self.assertIsNone(getattr(window, "_fh6_backup_card_chunk_timer", None))

    def test_bridge_patch_is_between_lazy_watch_and_final_profiling(self) -> None:
        root = Path(__file__).resolve().parents[1]
        wording = (root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        bridge = (root / "fh6garage" / "v1_3_4_backup_lazy_thread_bridge_patch.py").read_text(encoding="utf-8")

        self.assertIn("worker.finished.connect(bridge.worker_finished)", bridge)
        self.assertIn("@Slot(object)", bridge)
        self.assertLess(
            wording.index("apply_v1_3_4_backup_lazy_watch_patch(MainWindow)"),
            wording.index("apply_v1_3_4_backup_lazy_thread_bridge_patch(MainWindow)"),
        )
        self.assertLess(
            wording.index("apply_v1_3_4_backup_lazy_thread_bridge_patch(MainWindow)"),
            wording.index("apply_v1_3_4_performance_probe_patch(MainWindow)"),
        )


if __name__ == "__main__":
    unittest.main()
