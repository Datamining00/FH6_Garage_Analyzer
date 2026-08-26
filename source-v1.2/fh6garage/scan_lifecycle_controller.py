from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox

from .i18n import tr


def choose_save_folder(owner: Any, worker_type: type) -> None:
    start = owner.path_edit.text() or str(Path.home())
    path = QFileDialog.getExistingDirectory(
        owner,
        tr("save.folder_dialog"),
        start,
    )
    if path:
        owner.path_edit.setText(path)
        owner.settings.setValue("last_save_path", path)
        start_scan(owner, Path(path), worker_type)


def refresh_scan(owner: Any, worker_type: type) -> None:
    owner.car_db.reload()
    owner._refresh_db_status()
    if owner.path_edit.text():
        start_scan(
            owner,
            Path(owner.path_edit.text()),
            worker_type,
        )


def start_scan(owner: Any, path: Path, worker_type: type) -> None:
    if owner._scan_thread and owner._scan_thread.isRunning():
        # Do not discard a refresh or newly selected folder while the current
        # worker is winding down. Only the newest request needs to run.
        owner._pending_scan_request = (Path(path), worker_type)
        return
    owner._pending_scan_request = None
    owner._view_operations.cancel_pending()
    owner._begin_busy(tr("scan.loading"))
    owner._show_status(tr("scan.scanning"))
    thread = QThread(owner)
    worker = worker_type(path, owner.car_db)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(owner._scan_finished)
    worker.failed.connect(owner._scan_failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    owner._scan_thread = thread
    owner._scan_worker = worker
    thread.finished.connect(owner._scan_cleanup)
    thread.start()


def cleanup_scan(owner: Any) -> None:
    owner._scan_thread = None
    owner._scan_worker = None
    pending = getattr(owner, "_pending_scan_request", None)
    owner._pending_scan_request = None
    if pending is not None:
        path, worker_type = pending
        QTimer.singleShot(
            0,
            lambda: start_scan(owner, Path(path), worker_type),
        )


def finalize_scan_views(owner: Any, result: Any) -> None:
    """Commit the first visible layout after Qt has processed scan widgets."""
    if getattr(owner, "result", None) is not result:
        return
    owner._relayout_livery_grid(owner.livery_search.text())
    owner._relayout_tuning_grid(owner.tuning_search.text())
    for table_name in ("car_table", "creator_table"):
        table = getattr(owner, table_name, None)
        if table is not None:
            table.viewport().update()
    pages = getattr(owner, "pages", None)
    if pages is not None:
        pages.currentWidget().updateGeometry()
        pages.currentWidget().update()


def finish_scan(owner: Any, result: Any) -> None:
    try:
        owner.result = result
        owner._reset_game_navigation_sessions()
        owner._populate_all()
    finally:
        owner._end_busy()
    owner._show_status(
        tr(
            "scan.complete",
            liveries=sum(
                record.kind == "Livery" for record in result.liveries
            ),
            tunings=len(result.tunings),
        ),
        8000,
    )
    QTimer.singleShot(0, lambda: finalize_scan_views(owner, result))


def fail_scan(owner: Any, message: str) -> None:
    owner._end_busy()
    owner._show_status(tr("scan.failed"), 5000)
    QMessageBox.critical(owner, tr("scan.failed_title"), message)
