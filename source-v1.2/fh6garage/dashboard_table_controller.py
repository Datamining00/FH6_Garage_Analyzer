from __future__ import annotations

import re
from typing import Any, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from .creator_alias_view import aggregate_creator_alias_stats
from .i18n import tr


def order_key(value: object) -> object:
    return value.casefold() if isinstance(value, str) else value


def car_sort_key(owner: Any, summary: Any) -> tuple:
    section = owner._dashboard_car_sort_section
    if section == 0:
        return (summary.car_id,)
    if section == 1:
        info = owner.car_db.get(summary.car_id)
        label = (info.label or summary.label or "").strip()
        unknown = label.startswith("Car ID ")
        manufacturer = (info.manufacturer or "").strip()
        if not manufacturer:
            parts = label.split()
            if len(parts) >= 2 and parts[0].isdigit() and len(parts[0]) == 4:
                manufacturer = parts[1]
            elif parts:
                manufacturer = parts[0]
        return (
            1 if unknown else 0,
            manufacturer.casefold(),
            re.sub(r"^\d{4}\s+", "", label).casefold(),
            summary.car_id,
        )
    if section == 2:
        return (summary.livery_count, summary.car_id)
    if section == 3:
        return (summary.tuning_count, summary.car_id)
    return (summary.car_id,)


def creator_sort_key(owner: Any, row: tuple[str, int, int]) -> tuple:
    creator, livery_count, tuning_count = row
    total = livery_count + tuning_count
    section = owner._dashboard_creator_sort_section
    if section == 0:
        return (total, creator.casefold())
    if section == 1:
        return (creator == tr("creator.none"), creator.casefold())
    if section == 2:
        return (livery_count, creator.casefold())
    if section == 3:
        return (tuning_count, creator.casefold())
    return (creator.casefold(),)


def force_table_top(table: QTableWidget) -> None:
    def move_top() -> None:
        table.scrollToTop()
        table.verticalScrollBar().setValue(table.verticalScrollBar().minimum())

    move_top()
    QTimer.singleShot(0, move_top)
    QTimer.singleShot(40, move_top)


def sort_dashboard(owner: Any, kind: str, section: int, order: Qt.SortOrder) -> None:
    is_car = kind == "car"
    owner._begin_busy(
        tr("dashboard.sorting_vehicles")
        if is_car
        else tr("dashboard.sorting_creators")
    )
    try:
        setattr(owner, f"_dashboard_{kind}_sort_section", int(section))
        setattr(owner, f"_dashboard_{kind}_sort_order", order)
        sort_bar = getattr(owner, f"{kind}_sort_bar")
        sort_bar.set_active_sort(section, order)
        if is_car:
            populate_car_table(owner)
        else:
            populate_creator_table(owner)
        owner._filter_dashboard_table(owner.car_search.text())
        force_table_top(getattr(owner, f"{kind}_table"))
    finally:
        owner._end_busy()


def populate_car_table(owner: Any) -> None:
    table = owner.car_table
    selected_id: Optional[int] = None
    selected_rows = (
        table.selectionModel().selectedRows() if table.selectionModel() else []
    )
    if selected_rows:
        item = table.item(selected_rows[0].row(), 0)
        if item:
            try:
                selected_id = int(item.data(Qt.ItemDataRole.UserRole))
            except (TypeError, ValueError):
                selected_id = None

    table.setRowCount(0)
    if not owner.result:
        return
    rows = sorted(owner.result.car_summaries, key=lambda row: car_sort_key(owner, row))
    if owner._dashboard_car_sort_order == Qt.SortOrder.DescendingOrder:
        rows.reverse()

    selected_row = -1
    for summary in rows:
        row = table.rowCount()
        table.insertRow(row)
        values = (
            summary.car_id,
            summary.label,
            summary.livery_count,
            summary.tuning_count,
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setData(Qt.ItemDataRole.UserRole, summary.car_id)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, column, item)
        if selected_id == summary.car_id:
            selected_row = row

    if selected_row >= 0:
        table.selectRow(selected_row)
    elif table.rowCount():
        table.selectRow(0)
    if hasattr(owner, "car_sort_bar"):
        owner.car_sort_bar.set_active_sort(
            owner._dashboard_car_sort_section,
            owner._dashboard_car_sort_order,
        )


def creator_content_stats(owner: Any) -> list[tuple[str, int, int]]:
    return aggregate_creator_alias_stats(
        owner.result,
        owner.creator_aliases,
        tr("creator.none"),
    )


def populate_creator_table(owner: Any) -> None:
    table = owner.creator_table
    selected_creator = ""
    selected_rows = (
        table.selectionModel().selectedRows() if table.selectionModel() else []
    )
    if selected_rows:
        item = table.item(selected_rows[0].row(), 1)
        if item:
            selected_creator = str(
                item.data(Qt.ItemDataRole.UserRole) or item.text()
            )
    table.setRowCount(0)

    rows = sorted(
        creator_content_stats(owner),
        key=lambda row: creator_sort_key(owner, row),
    )
    if owner._dashboard_creator_sort_order == Qt.SortOrder.DescendingOrder:
        rows.reverse()

    selected_row = -1
    for creator, livery_count, tuning_count in rows:
        row = table.rowCount()
        table.insertRow(row)
        total = livery_count + tuning_count
        for column, value in enumerate(
            (total, creator, livery_count, tuning_count)
        ):
            item = QTableWidgetItem(str(value))
            item.setData(Qt.ItemDataRole.UserRole, creator)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, column, item)
        if selected_creator and creator.casefold() == selected_creator.casefold():
            selected_row = row

    for row in range(table.rowCount()):
        item = table.item(row, 1)
        if item is None:
            continue
        canonical = str(
            item.data(Qt.ItemDataRole.UserRole) or item.text() or ""
        ).strip()
        if not canonical or canonical == tr("creator.none"):
            continue
        item.setText(owner.creator_aliases.display_name(canonical))
        item.setToolTip(" / ".join(owner.creator_aliases.search_names(canonical)))

    if selected_row >= 0:
        table.selectRow(selected_row)
    elif table.rowCount():
        table.selectRow(0)
    if hasattr(owner, "creator_sort_bar"):
        owner.creator_sort_bar.set_active_sort(
            owner._dashboard_creator_sort_section,
            owner._dashboard_creator_sort_order,
        )
