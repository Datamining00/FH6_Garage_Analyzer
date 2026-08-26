from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QMessageBox

from .car_db import CarDatabase
from .i18n import tr


def refresh_db_status(
    owner: Any,
    unknown_ids: Optional[list[int]] = None,
) -> None:
    del unknown_ids
    if not hasattr(owner, "db_last_update_label"):
        return

    status = owner.car_db.status
    raw = (status.cache_updated_at or "").strip()
    if raw:
        date_text = raw[:10] if len(raw) >= 10 else raw
        owner.db_last_update_label.setText(
            tr("db.last_update", date=date_text)
        )
        tooltip = tr("db.local_download_time", value=raw)
        if status.cache_source_last_modified:
            tooltip += tr(
                "db.source_last_modified",
                value=status.cache_source_last_modified,
            )
        owner.db_last_update_label.setToolTip(tooltip)
        return

    owner.db_last_update_label.setText(tr("db.last_update_unavailable"))
    owner.db_last_update_label.setToolTip(tr("db.not_updated_tip"))


def start_car_db_update(owner: Any, worker_type: type) -> None:
    if owner._db_update_thread and owner._db_update_thread.isRunning():
        return
    answer = QMessageBox.question(
        owner,
        tr("db.update_title"),
        tr("db.update_prompt"),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return

    owner.db_update_button.setEnabled(False)
    owner.db_update_button.setText(tr("db.checking"))
    owner._begin_busy(tr("db.updating_busy"))
    owner._show_status(tr("db.downloading"))
    thread = QThread(owner)
    worker = worker_type(owner.car_db.cache_path)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(owner._car_db_update_finished)
    worker.failed.connect(owner._car_db_update_failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(owner._car_db_update_cleanup)
    owner._db_update_thread = thread
    owner._db_update_worker = worker
    thread.start()


def finish_car_db_update(owner: Any, update: Any) -> None:
    owner._end_busy()
    owner.car_db = CarDatabase(owner.project_root / "data" / "car_names.json")
    owner._refresh_db_status()
    owner._show_status(
        tr("db.update_complete_status", count=update.count),
        8000,
    )
    QMessageBox.information(
        owner,
        tr("db.update_complete_title"),
        tr(
            "db.update_complete_message",
            count=update.count,
            path=update.cache_path,
        ),
    )
    if owner.path_edit.text():
        owner.start_scan(Path(owner.path_edit.text()))


def fail_car_db_update(owner: Any, message: str) -> None:
    owner._end_busy()
    owner._show_status(tr("db.update_failed"), 6000)
    QMessageBox.critical(owner, tr("db.update_failed"), message)


def cleanup_car_db_update(owner: Any) -> None:
    owner._db_update_thread = None
    owner._db_update_worker = None
    if hasattr(owner, "db_update_button"):
        owner.db_update_button.setEnabled(True)
        owner.db_update_button.setText(tr("db.check_update"))
