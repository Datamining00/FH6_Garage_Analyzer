from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
)

from .i18n import tr


def open_car_db_override_dialog(owner: Any, app_style: str) -> None:
    dialog = QDialog(owner)
    dialog.setWindowTitle(tr("db.override_title"))
    dialog.resize(820, 680)
    dialog.setStyleSheet(
        app_style
        + """
        QDialog { background:#f7f8fb; }
        QTableWidget {
            background:white;
            border:1px solid #dfe1e8;
            border-radius:10px;
            gridline-color:#e8eaf0;
            selection-background-color:#eee9ff;
            selection-color:#171924;
        }
        QTableWidget::item { padding:6px 8px; }
        QHeaderView::section {
            background:#fafbfc;
            color:#5f6474;
            border:0;
            border-bottom:1px solid #dfe1e8;
            padding:8px;
            font-weight:600;
        }
        """
    )

    root = QVBoxLayout(dialog)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(10)
    table = owner._table((tr("table.car_id"), tr("table.vehicle_name")))
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(
        QAbstractItemView.EditTrigger.DoubleClicked
        | QAbstractItemView.EditTrigger.EditKeyPressed
        | QAbstractItemView.EditTrigger.SelectedClicked
    )
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.setColumnWidth(0, 120)
    table.verticalHeader().setVisible(True)
    table.verticalHeader().setDefaultSectionSize(31)
    root.addWidget(table, 1)

    footer = QHBoxLayout()
    footer.setContentsMargins(0, 0, 0, 0)
    footer.addStretch(1)
    save_button = QPushButton(tr("common.save"))
    save_button.setObjectName("primary")
    save_button.setEnabled(False)
    save_button.setMinimumWidth(92)
    footer.addWidget(save_button)
    root.addLayout(footer)

    initial_overrides = owner.car_db.user_overrides()
    visible_ids = set(owner.car_db.all_items())
    if owner.result is not None:
        visible_ids.update(summary.car_id for summary in owner.result.car_summaries)
    ids = sorted(visible_ids)
    table.setRowCount(len(ids))

    for row, car_id in enumerate(ids):
        id_item = QTableWidgetItem(str(car_id))
        id_item.setData(Qt.ItemDataRole.UserRole, car_id)
        id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        id_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        name_item = QTableWidgetItem(owner.car_db.get(car_id).label)
        name_item.setData(Qt.ItemDataRole.UserRole, car_id)
        name_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        if car_id in initial_overrides:
            name_item.setBackground(QColor("#f3efff"))
            name_item.setToolTip(tr("db.override_applied_tip"))
        else:
            name_item.setToolTip(tr("db.override_edit_tip"))
        table.setItem(row, 0, id_item)
        table.setItem(row, 1, name_item)

    saved_any = {"value": False}

    def mark_dirty(item: QTableWidgetItem) -> None:
        if item.column() == 1:
            save_button.setEnabled(True)

    def collect_overrides() -> Optional[dict[int, str]]:
        desired: dict[int, str] = {}
        for row in range(table.rowCount()):
            id_item = table.item(row, 0)
            name_item = table.item(row, 1)
            if id_item is None or name_item is None:
                continue
            car_id = int(id_item.data(Qt.ItemDataRole.UserRole))
            value = name_item.text().strip()
            if not value:
                QMessageBox.warning(
                    dialog,
                    tr("db.name_check_title"),
                    tr("db.name_empty_message", car_id=car_id),
                )
                table.setCurrentCell(row, 1)
                table.editItem(name_item)
                return None
            if value != owner.car_db.base_label(car_id):
                desired[car_id] = value
        return desired

    def refresh_override_marks(overrides: dict[int, str]) -> None:
        for row in range(table.rowCount()):
            id_item = table.item(row, 0)
            name_item = table.item(row, 1)
            if id_item is None or name_item is None:
                continue
            car_id = int(id_item.data(Qt.ItemDataRole.UserRole))
            if car_id in overrides:
                name_item.setBackground(QColor("#f3efff"))
                name_item.setToolTip(tr("db.override_applied_tip"))
            else:
                name_item.setBackground(QColor(Qt.GlobalColor.transparent))
                name_item.setToolTip(tr("db.override_edit_tip"))

    def save_overrides() -> None:
        desired = collect_overrides()
        if desired is None:
            return
        try:
            owner.car_db.replace_user_overrides(desired)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(dialog, tr("db.override_save_failed"), str(exc))
            return
        refresh_override_marks(desired)
        saved_any["value"] = True
        save_button.setEnabled(False)
        owner._show_status(tr("db.override_saved", count=len(desired)), 2000)

    table.itemChanged.connect(mark_dirty)
    save_button.clicked.connect(save_overrides)
    owner._apply_pointing_cursors(dialog)
    dialog.exec()

    if saved_any["value"]:
        owner.car_db.reload()
        owner._refresh_db_status()
        source = Path(owner.path_edit.text())
        if owner.path_edit.text() and source.is_dir():
            owner.start_scan(source)
