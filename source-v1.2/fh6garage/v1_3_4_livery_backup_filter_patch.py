from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QPushButton, QWidgetAction

from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_export_performance_ui_patch as _perf
from .card_icons import icon as card_icon
from .models import LiveryRecord
from .v1_3_2_filter_alias_quality_patch import _ROW_STYLE


_NOT_BACKED_UP_MODE = 14


def _txt(ko: str, en: str) -> str:
    return _backup_ui._txt(ko, en)


def _install_filter_row(window: Any) -> None:
    button = getattr(window, "livery_check_filter", None)
    if button is None or _NOT_BACKED_UP_MODE in getattr(button, "_actions", {}):
        return
    menu = button.menu()
    if menu is None:
        return

    row = QPushButton(_txt("백업되지 않음", "Not backed up"))
    row.setCheckable(True)
    row.setIcon(card_icon("export", _backup_ui._INACTIVE_COLOR, 22))
    row.setIconSize(QSize(22, 22))
    row.setToolTip(_txt("외부 백업 저장소에 존재하지 않는 리버리만 표시", "Show only liveries that are not in the backup repository"))
    row.setFixedHeight(36)
    row.setCursor(Qt.CursorShape.PointingHandCursor)
    row.setStyleSheet(_ROW_STYLE)
    row.setProperty("fh6FilterBaseLabel", _txt("백업되지 않음", "Not backed up"))
    row.toggled.connect(
        lambda checked=False, owner=button: owner._row_toggled(_NOT_BACKED_UP_MODE, checked)
    )
    action = QWidgetAction(menu)
    action.setDefaultWidget(row)
    menu.addAction(action)
    button._actions[_NOT_BACKED_UP_MODE] = row


def _record_not_backed_up(window: Any, record: LiveryRecord | None) -> bool:
    if not isinstance(record, LiveryRecord):
        return False
    containers, identities = _perf._presence_snapshot(window)
    return not _perf._record_backed_up(record, containers, identities)


def _update_filter_count(window: Any) -> None:
    button = getattr(window, "livery_check_filter", None)
    row = getattr(button, "_actions", {}).get(_NOT_BACKED_UP_MODE) if button is not None else None
    if not isinstance(row, QPushButton):
        return

    resolver = getattr(window, "_record_for_content_key", None)
    if not callable(resolver):
        row.setText(f"{_txt('백업되지 않음', 'Not backed up')} (0)")
        return

    containers, identities = _perf._presence_snapshot(window)
    count = 0
    for card in getattr(window, "_livery_grid_cards", []) or []:
        key = str(card.property("annotationKey") or "")
        record = resolver("livery", key) if key else None
        if isinstance(record, LiveryRecord) and not _perf._record_backed_up(record, containers, identities):
            count += 1
    base = _txt("백업되지 않음", "Not backed up")
    row.setProperty("fh6FilterBaseLabel", base)
    row.setText(f"{base} ({count})")
    row.setStyleSheet(_ROW_STYLE)


def _apply_not_backed_up_layout(window: Any) -> None:
    button = getattr(window, "livery_check_filter", None)
    if button is None or _NOT_BACKED_UP_MODE not in button.selected_modes():
        _update_filter_count(window)
        return

    resolver = getattr(window, "_record_for_content_key", None)
    if not callable(resolver):
        return
    containers, identities = _perf._presence_snapshot(window)

    # The original relayout has already applied search, classification, hidden,
    # source, and memory-state rules. Filter only those currently visible cards,
    # then repack the grid so no holes remain.
    visible = []
    for card in getattr(window, "_livery_grid_cards", []) or []:
        if not card.isVisible():
            continue
        key = str(card.property("annotationKey") or "")
        record = resolver("livery", key) if key else None
        if not isinstance(record, LiveryRecord):
            continue
        if _perf._record_backed_up(record, containers, identities):
            window._unload_livery_card_thumbnail(card)
            continue
        visible.append(card)

    window.livery_grid_host.setUpdatesEnabled(False)
    window._clear_livery_grid_layout()
    window._layout_visible_grid_cards("livery", visible)
    window.livery_grid_layout.activate()
    window.livery_grid_host.setUpdatesEnabled(True)
    window.livery_grid_host.update()
    window._sync_livery_grid_card_widths()
    QTimer.singleShot(0, window._sync_livery_grid_card_widths)
    QTimer.singleShot(0, window._refresh_visible_livery_thumbnails)
    _update_filter_count(window)


def apply_v1_3_4_livery_backup_filter_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_livery_backup_filter_patched", False):
        return

    original_init = MainWindow.__init__
    original_relayout = MainWindow._relayout_livery_grid
    original_export_finished = _backup_ui._export_finished

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _install_filter_row(self)
        _update_filter_count(self)

    def relayout(self: Any, *args: Any, **kwargs: Any):
        result = original_relayout(self, *args, **kwargs)
        _apply_not_backed_up_layout(self)
        return result

    def export_finished(window: Any, result: object) -> None:
        original_export_finished(window, result)
        # The export completion refreshes the backup-presence cache first.
        # Re-apply the filter so newly backed-up cards disappear immediately.
        search = getattr(window, "livery_search", None)
        text = search.text() if search is not None else ""
        window._relayout_livery_grid(text)

    MainWindow.__init__ = patched_init
    MainWindow._relayout_livery_grid = relayout
    _backup_ui._export_finished = export_finished
    MainWindow._fh6_v134_livery_backup_filter_patched = True
