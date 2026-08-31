from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThread, Slot
from PySide6.QtWidgets import QMessageBox

from . import v1_3_2_memory_state_patch as _memory_ui


class _MemoryGuiBridge(QObject):
    """Receive worker signals on the MainWindow/GUI thread."""

    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window = window

    @Slot(int, int, int, int, float)
    def on_progress(
        self,
        done: int,
        total: int,
        read_bytes: int,
        failures: int,
        elapsed: float,
    ) -> None:
        _memory_ui._on_memory_progress(
            self.window,
            done,
            total,
            read_bytes,
            failures,
            elapsed,
        )

    @Slot(object)
    def on_finished(self, result: object) -> None:
        guard = getattr(self.window, "_fh6_memory_result_guard", None)
        if callable(guard) and not guard(result):
            return
        _memory_ui._on_memory_finished(self.window, result)

    @Slot(str)
    def on_failed(self, message: str) -> None:
        _memory_ui._on_memory_failed(self.window, message)

    @Slot()
    def on_thread_finished(self) -> None:
        _memory_ui._clear_memory_thread(self.window)
        self.window._fh6_memory_bridge = None
        self.deleteLater()


def _safe_start_memory_scan(window: Any) -> None:
    window._fh6_memory_scan_running = True
    window.memory_refresh_button.setEnabled(False)
    window.memory_scan_progress.setRange(0, 100)
    window.memory_scan_progress.setValue(0)
    window.memory_scan_progress.show()
    window.memory_scan_detail.setText(
        _memory_ui._txt("스캔 준비 중…", "Preparing scan…")
    )

    thread = QThread(window)
    worker = _memory_ui._MemoryScanWorker()
    bridge = _MemoryGuiBridge(window)
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.progress.connect(bridge.on_progress)
    worker.finished.connect(bridge.on_finished)
    worker.failed.connect(bridge.on_failed)

    worker.finished.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(bridge.on_thread_finished)
    thread.finished.connect(thread.deleteLater)

    window._fh6_memory_thread = thread
    window._fh6_memory_worker = worker
    window._fh6_memory_bridge = bridge
    thread.start()


def apply_v1_3_2_memory_thread_safety_patch(MainWindow: Any) -> None:
    """Keep memory-scan UI callbacks on the GUI thread and prevent unsafe close."""
    if getattr(MainWindow, "_fh6_v132_memory_thread_safety_patched", False):
        return

    _memory_ui._start_memory_scan = _safe_start_memory_scan
    original_close_event = MainWindow.closeEvent

    def patched_close_event(self, event) -> None:
        if getattr(self, "_fh6_memory_scan_running", False):
            QMessageBox.information(
                self,
                _memory_ui._txt("메모리 스캔 진행 중", "Memory scan in progress"),
                _memory_ui._txt(
                    "메모리 스캔이 완료된 뒤 프로그램을 종료해 주세요.",
                    "Close the application after the memory scan finishes.",
                ),
            )
            event.ignore()
            return
        original_close_event(self, event)

    MainWindow.closeEvent = patched_close_event
    MainWindow._fh6_v132_memory_thread_safety_patched = True
