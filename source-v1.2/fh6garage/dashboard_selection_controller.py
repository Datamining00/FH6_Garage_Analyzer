from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QTableWidgetItem

from .creator_alias_views import creator_display
from .i18n import tr
from .models import LiveryRecord, TuningRecord


def selection_search_text(owner: Any) -> str:
    if owner.dashboard_content_stack.currentIndex() == 0:
        rows = owner.car_table.selectionModel().selectedRows()
        if not rows:
            return ""
        item = owner.car_table.item(rows[0].row(), 0)
        if item is None:
            return ""
        try:
            car_id = int(item.data(Qt.ItemDataRole.UserRole))
        except (TypeError, ValueError):
            return ""
        return owner._car_label(car_id).strip()

    rows = owner.creator_table.selectionModel().selectedRows()
    if not rows:
        return ""
    item = owner.creator_table.item(rows[0].row(), 1)
    if item is None:
        return ""
    creator = str(
        item.data(Qt.ItemDataRole.UserRole) or item.text() or ""
    ).strip()
    return "" if creator == tr("creator.none") else creator


def jump_to_selection(owner: Any, content_type: str) -> None:
    if content_type not in {"livery", "tuning"}:
        return
    query = selection_search_text(owner)
    if not query:
        QMessageBox.information(
            owner,
            tr("dashboard.instant_move_unavailable_title"),
            tr("dashboard.instant_move_unavailable_message"),
        )
        return

    page_index = 1 if content_type == "livery" else 2
    search = (
        owner.livery_search
        if content_type == "livery"
        else owner.tuning_search
    )
    owner.nav_buttons[page_index].setChecked(True)
    owner.pages.setCurrentIndex(page_index)
    search.blockSignals(True)
    search.setText(query)
    search.blockSignals(False)
    owner._filter_saved_content_views(content_type, query)
    search.setFocus(Qt.FocusReason.ShortcutFocusReason)
    search.selectAll()


def set_content_mode(owner: Any, index: int) -> None:
    if index not in (0, 1):
        return
    owner.dashboard_content_stack.setCurrentIndex(index)
    owner.car_search.blockSignals(True)
    owner.car_search.clear()
    owner.car_search.blockSignals(False)

    if index == 0:
        owner.car_search.setPlaceholderText(tr("dashboard.search_vehicle"))
        owner.selected_hint.clear()
        owner.selected_hint.hide()
        if (
            owner.car_table.rowCount()
            and not owner.car_table.selectionModel().selectedRows()
        ):
            owner.car_table.selectRow(0)
        update_selected_car(owner)
    else:
        owner.car_search.setPlaceholderText(tr("dashboard.search_creator"))
        owner.selected_hint.clear()
        owner.selected_hint.hide()
        if (
            owner.creator_table.rowCount()
            and not owner.creator_table.selectionModel().selectedRows()
        ):
            owner.creator_table.selectRow(0)
        update_selected_creator(owner)
    filter_dashboard_table(owner, "")


def update_selected_car(owner: Any) -> None:
    if not owner.result or owner.dashboard_content_stack.currentIndex() != 0:
        return
    rows = owner.car_table.selectionModel().selectedRows()
    if not rows:
        return
    item = owner.car_table.item(rows[0].row(), 0)
    if not item:
        return
    car_id = int(item.data(Qt.ItemDataRole.UserRole))
    summary = next(
        (row for row in owner.result.car_summaries if row.car_id == car_id),
        None,
    )
    owner.selected_title.setText(
        tr(
            "dashboard.selected_vehicle",
            value=summary.label if summary else owner._car_label(car_id),
        )
    )
    owner.selected_hint.clear()
    owner.selected_hint.hide()
    liveries = [
        record
        for record in owner.result.liveries
        if record.car_id == car_id and record.kind == "Livery"
    ]
    tunings = [
        record for record in owner.result.tunings if record.car_id == car_id
    ]
    fill_selected_liveries(owner, liveries)
    fill_selected_tunings(owner, tunings)


def update_selected_creator(owner: Any) -> None:
    if not owner.result or owner.dashboard_content_stack.currentIndex() != 1:
        return
    rows = owner.creator_table.selectionModel().selectedRows()
    if not rows:
        return
    item = owner.creator_table.item(rows[0].row(), 1)
    if not item:
        return
    creator = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
    creator_key = "" if creator == tr("creator.none") else creator.casefold()

    def same_creator(raw_name: str) -> bool:
        raw = (raw_name or "").strip()
        if not raw:
            return not creator_key
        return (
            owner.creator_aliases.canonical_name(raw).casefold()
            == creator_key
        )

    liveries = [
        record
        for record in owner.result.liveries
        if record.kind == "Livery"
        and same_creator(record.header.creator or "")
    ]
    tunings = [
        record
        for record in owner.result.tunings
        if same_creator(record.header.creator or "")
    ]
    display = (
        tr("creator.none")
        if not creator_key
        else owner.creator_aliases.display_name(creator)
    )
    owner.selected_title.setText(
        tr("dashboard.selected_creator", value=display)
    )
    owner.selected_hint.clear()
    owner.selected_hint.hide()
    fill_selected_liveries(owner, liveries)
    fill_selected_tunings(owner, tunings)


def fill_selected_liveries(owner: Any, records: list[LiveryRecord]) -> None:
    table = owner.selected_liveries
    table.setRowCount(0)
    for record in records:
        row = table.rowCount()
        table.insertRow(row)
        table.setRowHeight(row, 54)
        icon_item = QTableWidgetItem()
        icon_item.setIcon(owner._icon_for(record.thumbnail_path))
        table.setItem(row, 0, icon_item)
        values = (
            record.header.name or "(unnamed)",
            creator_display(owner, record.header.creator or ""),
        )
        for column, value in enumerate(values, 1):
            table.setItem(row, column, QTableWidgetItem(str(value)))


def fill_selected_tunings(owner: Any, records: list[TuningRecord]) -> None:
    table = owner.selected_tunings
    table.setRowCount(0)
    for record in records:
        row = table.rowCount()
        table.insertRow(row)
        table.setRowHeight(row, 54)
        icon_item = QTableWidgetItem()
        icon_item.setIcon(owner._icon_for(record.thumbnail_path))
        table.setItem(row, 0, icon_item)
        values = (
            record.header.name or "(unnamed)",
            creator_display(owner, record.header.creator or ""),
            owner._fmt_bytes(record.data_size),
        )
        for column, value in enumerate(values, 1):
            table.setItem(row, column, QTableWidgetItem(str(value)))


def filter_dashboard_table(owner: Any, text: str) -> None:
    if owner.dashboard_content_stack.currentIndex() == 0:
        owner._filter_table(owner.car_table, text, (0, 1))
        return
    needle = text.strip().casefold()
    for row in range(owner.creator_table.rowCount()):
        item = owner.creator_table.item(row, 1)
        if item is None:
            owner.creator_table.setRowHidden(row, bool(needle))
            continue
        canonical = str(
            item.data(Qt.ItemDataRole.UserRole) or item.text() or ""
        ).strip()
        if not canonical or canonical == tr("creator.none"):
            haystack = item.text().casefold()
        else:
            haystack = " ".join(
                [
                    owner.creator_aliases.display_name(canonical),
                    *owner.creator_aliases.search_names(canonical),
                ]
            ).casefold()
        owner.creator_table.setRowHidden(
            row,
            bool(needle) and needle not in haystack,
        )
