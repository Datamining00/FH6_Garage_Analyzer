from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QThread, QTimer, Signal, Slot

from fh6garage import v1_3_2_responsiveness_sort_patch as responsive
from fh6garage import v1_3_4_backup_export_patch as backup_ui
from fh6garage import v1_3_4_backup_lazy_load_patch as lazy
from fh6garage import v1_3_4_backup_loading_resilience_patch as resilience


class _Emitter(QObject):
    finished = Signal(object)

    @Slot()
    def run(self) -> None:
        self.finished.emit(object())


class BackupLoadingResilienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_gui_receives_terminal_result_before_thread_finishes(self) -> None:
        window = QObject()
        token = lazy._CancelToken()
        window._fh6_backup_cancel_token = token
        thread = QThread()
        emitter = _Emitter()
        emitter.moveToThread(thread)
        bridge = resilience._StableBackupLoadGuiBridge(window, token, thread)
        sequence: list[str] = []
        loop = QEventLoop()
        timed_out = {"value": False}

        def handle(_owner: object, _result: object, _token: object) -> None:
            self.assertIs(QThread.currentThread(), window.thread())
            sequence.append("gui_handled")

        def thread_done() -> None:
            sequence.append("thread_finished")
            loop.quit()

        thread.started.connect(emitter.run)
        # Match production: the emitter-side Python callback may execute in the
        # worker thread; it is safe because it only stores the payload and uses
        # QMetaObject.invokeMethod for the actual GUI-thread delivery.
        emitter.finished.connect(bridge.enqueue_finished)
        thread.finished.connect(thread_done)

        def timeout() -> None:
            timed_out["value"] = True
            thread.quit()
            loop.quit()

        with patch.object(lazy, "_worker_finished", side_effect=handle):
            thread.start()
            QTimer.singleShot(2000, timeout)
            loop.exec()
            thread.quit()
            thread.wait(2000)

        self.assertFalse(timed_out["value"])
        self.assertIn("gui_handled", sequence)
        self.assertIn("thread_finished", sequence)
        self.assertLess(sequence.index("gui_handled"), sequence.index("thread_finished"))

    def test_running_previous_thread_defers_new_load(self) -> None:
        window = QObject()
        thread = QThread()
        window._fh6_backup_load_running = False
        window._fh6_backup_load_thread = thread
        window._fh6_backup_start_retry_pending = False
        thread.start()
        try:
            self.assertTrue(thread.isRunning())
            with patch.object(resilience.QTimer, "singleShot") as single_shot, patch.object(
                lazy._backup_ui, "_backup_root", side_effect=AssertionError("must not start a second load")
            ):
                resilience._stable_start_full_load(window)
                self.assertTrue(window._fh6_backup_start_retry_pending)
                single_shot.assert_called_once()
        finally:
            thread.quit()
            thread.wait(2000)

    def test_load_finish_waits_for_active_relayout(self) -> None:
        window = QObject()
        window._fh6_backup_relayout_active = True
        window._fh6_backup_finish_after_relayout = False
        with patch.object(resilience, "_ORIGINAL_LAZY_LOAD_FINISHED") as original:
            resilience._deferred_load_finished(window)
            original.assert_not_called()
            self.assertTrue(window._fh6_backup_finish_after_relayout)

    def test_resilience_patch_sets_chunking_busy_cadence_and_async_relayout(self) -> None:
        class MainWindow:
            pass

        old_chunk = lazy._CARD_BUILD_CHUNK
        old_interval = responsive._BUSY_YIELD_INTERVAL_SECONDS
        old_budget = responsive._BUSY_PROCESS_EVENTS_MS
        old_start = lazy._start_full_load
        old_relayout = backup_ui._relayout_backup
        old_widths = backup_ui._sync_backup_widths
        old_thumbnails = backup_ui._refresh_backup_thumbnails
        old_finished = lazy._load_finished
        try:
            resilience.apply_v1_3_4_backup_loading_resilience_patch(MainWindow)
            self.assertEqual(lazy._CARD_BUILD_CHUNK, 1)
            self.assertEqual(resilience._BACKUP_RELAYOUT_CHUNK, 8)
            self.assertAlmostEqual(responsive._BUSY_YIELD_INTERVAL_SECONDS, 0.033)
            self.assertEqual(responsive._BUSY_PROCESS_EVENTS_MS, 5)
            self.assertIs(lazy._start_full_load, resilience._stable_start_full_load)
            self.assertIs(backup_ui._relayout_backup, resilience._smooth_relayout_backup)
            self.assertIs(backup_ui._sync_backup_widths, resilience._stable_sync_backup_widths)
            self.assertIs(backup_ui._refresh_backup_thumbnails, resilience._stable_refresh_backup_thumbnails)
            self.assertIs(lazy._load_finished, resilience._deferred_load_finished)
        finally:
            lazy._CARD_BUILD_CHUNK = old_chunk
            responsive._BUSY_YIELD_INTERVAL_SECONDS = old_interval
            responsive._BUSY_PROCESS_EVENTS_MS = old_budget
            lazy._start_full_load = old_start
            backup_ui._relayout_backup = old_relayout
            backup_ui._sync_backup_widths = old_widths
            backup_ui._refresh_backup_thumbnails = old_thumbnails
            lazy._load_finished = old_finished

    def test_patch_order_keeps_resilience_before_profiler_and_final_thread_fix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        wording = (root / "fh6garage" / "v1_3_4_backup_action_wording_patch.py").read_text(encoding="utf-8")
        app = (root / "app.py").read_text(encoding="utf-8")
        source = (root / "fh6garage" / "v1_3_4_backup_loading_resilience_patch.py").read_text(encoding="utf-8")

        self.assertNotIn("worker.finished.connect(thread.quit)", source)
        self.assertNotIn("worker.cancelled.connect(thread.quit)", source)
        self.assertNotIn("worker.failed.connect(thread.quit)", source)
        self.assertIn("QMetaObject.invokeMethod", source)
        self.assertIn("Qt.ConnectionType.QueuedConnection", source)
        self.assertIn("worker.finished.connect(bridge.enqueue_finished)", source)
        self.assertIn("worker.cancelled.connect(bridge.enqueue_cancelled)", source)
        self.assertIn("worker.failed.connect(bridge.enqueue_failed)", source)
        self.assertIn("_lazy._CARD_BUILD_CHUNK = _BACKUP_CARD_BUILD_CHUNK", source)
        self.assertIn("_backup_ui._relayout_backup = _smooth_relayout_backup", source)
        self.assertIn("_lazy._load_finished = _deferred_load_finished", source)
        self.assertIn("backup.relayout.async_total", source)
        self.assertIn("backup.relayout.chunk", source)
        self.assertLess(
            wording.index("apply_v1_3_4_backup_lazy_thread_bridge_patch(MainWindow)"),
            wording.index("apply_v1_3_4_backup_loading_resilience_patch(MainWindow)"),
        )
        self.assertLess(
            wording.index("apply_v1_3_4_backup_loading_resilience_patch(MainWindow)"),
            wording.index("apply_v1_3_4_performance_probe_patch(MainWindow)"),
        )
        self.assertLess(
            app.index("apply_v1_3_4_backup_action_wording_patch(MainWindow)"),
            app.index("apply_v1_3_2_thread_affinity_fix(MainWindow)"),
        )


if __name__ == "__main__":
    unittest.main()
