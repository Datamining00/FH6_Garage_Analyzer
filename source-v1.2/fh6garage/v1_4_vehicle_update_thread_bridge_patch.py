from __future__ import annotations

import weakref
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Slot

from . import v1_4_vehicle_data_source_patch as _source
from .acquisition_db import DATA_FILE_NAME
from .car_db import CarDatabase
from .v1_4_diagnostic_export_patch import apply_v1_4_diagnostic_export_patch
from .v1_4_initial_vehicle_source_patch import apply_v1_4_initial_vehicle_source_patch
from .v1_4_subsystem_logging_patch import apply_v1_4_subsystem_logging_patch


class _VehicleUpdateGuiBridge(QObject):
    """Deliver worker completion to MainWindow on the GUI thread.

    Runtime patch functions assigned to an already-created QObject subclass are
    not part of that class's original Qt meta-object. Connecting a worker signal
    directly to such a patched MainWindow method can therefore execute Python UI
    code in the worker thread. This bridge is a real QObject subclass whose slots
    exist when its meta-object is created, so QueuedConnection has an explicit GUI
    receiver context.
    """

    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self._window_ref = weakref.ref(window)

    def _window(self) -> Any | None:
        return self._window_ref()

    @Slot(object)
    def update_finished(self, update: Any) -> None:
        window = self._window()
        if window is None:
            return
        window._fh6_vehicle_update_callback_on_gui_thread = (
            QThread.currentThread() is window.thread()
        )
        handler = getattr(window, "_car_db_update_finished", None)
        if callable(handler):
            handler(update)

    @Slot(str)
    def update_failed(self, message: str) -> None:
        window = self._window()
        if window is None:
            return
        window._fh6_vehicle_update_callback_on_gui_thread = (
            QThread.currentThread() is window.thread()
        )
        handler = getattr(window, "_car_db_update_failed", None)
        if callable(handler):
            handler(message)

    @Slot()
    def thread_finished(self) -> None:
        window = self._window()
        if window is None:
            return
        handler = getattr(window, "_car_db_update_cleanup", None)
        if callable(handler):
            handler()


def apply_v1_4_vehicle_update_thread_bridge_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_vehicle_update_thread_bridge_patched", False):
        return

    @Slot()
    def start_car_db_update(self: Any) -> None:
        running = getattr(self, "_db_update_thread", None)
        if running is not None and running.isRunning():
            return

        selected = _source._choose_update_source(self)
        if not selected:
            return

        self._pending_vehicle_data_source = selected
        self.db_update_button.setEnabled(False)
        self.db_update_button.setText("업데이트 확인 중")
        self._begin_busy("차량 데이터를 업데이트하는 중입니다…")
        self._show_status("차량 데이터를 다운로드하는 중입니다…")

        thread = QThread(self)
        acquisition_cache_path = (
            getattr(getattr(self, "acquisition_db", None), "cache_path", None)
            or (CarDatabase.default_app_data_dir() / DATA_FILE_NAME)
        )
        worker = _source.VehicleDataUpdateWorker(
            selected,
            self.car_db.cache_path,
            Path(acquisition_cache_path),
        )
        worker.moveToThread(thread)

        # This bridge is constructed in the MainWindow/GUI thread and has a real
        # Qt meta-object. Never connect worker result signals directly to runtime-
        # patched MainWindow methods.
        bridge = _VehicleUpdateGuiBridge(self)

        thread.started.connect(worker.run)

        # Request worker-loop shutdown synchronously when run() emits either
        # terminal signal. The GUI callback is queued separately and cannot block
        # thread.quit() with a modal dialog or UI rebuild.
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.finished.connect(
            bridge.update_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.failed.connect(
            bridge.update_failed,
            Qt.ConnectionType.QueuedConnection,
        )

        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(
            bridge.thread_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        thread.finished.connect(thread.deleteLater)

        self._db_update_thread = thread
        self._db_update_worker = worker
        self._fh6_vehicle_update_bridge = bridge
        self._fh6_vehicle_update_callback_on_gui_thread = None
        thread.start()

    MainWindow.start_car_db_update = start_car_db_update
    MainWindow._fh6_v14_vehicle_update_thread_bridge_patched = True
    apply_v1_4_initial_vehicle_source_patch(MainWindow)
    apply_v1_4_subsystem_logging_patch(MainWindow)
    apply_v1_4_diagnostic_export_patch(MainWindow)
