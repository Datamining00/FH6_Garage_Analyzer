from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from . import v1_3_2_memory_filter_coordination_patch as _coord
from . import v1_3_2_memory_state_patch as _memory
from . import v1_3_4_backup_export_patch as _backup_ui


FILTER_NO_APPLIED_FOR_CAR = "NO_APPLIED_FOR_CAR"


def _txt(ko: str, en: str) -> str:
    return _backup_ui._txt(ko, en)


def _hide_layout_tree(layout: Any) -> None:
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        widget = item.widget()
        if isinstance(widget, QWidget):
            widget.hide()
        child = item.layout()
        if child is not None:
            _hide_layout_tree(child)


def _remove_backup_page_heading(window: Any) -> None:
    page = getattr(window, "backup_page", None)
    root = page.layout() if isinstance(page, QWidget) else None
    if root is None or bool(page.property("fh6BackupHeadingRemoved")):
        return
    first = root.itemAt(0)
    heading_layout = first.layout() if first is not None else None
    if heading_layout is None:
        return
    root.takeAt(0)
    _hide_layout_tree(heading_layout)
    page.setProperty("fh6BackupHeadingRemoved", True)


def _apply_backup_labels(window: Any) -> None:
    backup = getattr(window, "backup_only_toggle", None)
    both = getattr(window, "backup_both_toggle", None)
    if isinstance(backup, QPushButton):
        backup.setText(_txt("백업 폴더에만 존재", "Backup folder only"))
    if isinstance(both, QPushButton):
        both.setText(_txt("게임 및 백업에 존재", "In game and backup"))

    actions = getattr(window, "_fh6_backup_filter_actions", {})
    if isinstance(actions, dict):
        action = actions.get("backup")
        if action is not None:
            action.setText(_txt("백업 폴더에만 존재", "Backup folder only"))
        action = actions.get("both")
        if action is not None:
            action.setText(_txt("게임 및 백업에 존재", "In game and backup"))


def _install_no_applied_toggle(window: Any, controls: Any) -> None:
    if isinstance(getattr(window, "livery_no_applied_toggle", None), QPushButton):
        return
    unapplied = getattr(window, "livery_unapplied_toggle", None)
    if not isinstance(unapplied, QPushButton):
        return

    row_item = controls.itemAt(1)
    row = row_item.layout() if row_item is not None else None
    if row is None:
        return

    button = QPushButton(_txt("적용된 리버리 없음", "No applied livery"))
    button.setObjectName("secondary")
    button.setCheckable(True)
    button.setChecked(False)
    index = row.indexOf(unapplied)
    row.insertWidget(index + 1 if index >= 0 else max(0, row.count() - 1), button)
    window.livery_no_applied_toggle = button
    button.clicked.connect(
        lambda _checked=False, owner=window:
        _memory._set_status_filter_mode(owner, FILTER_NO_APPLIED_FOR_CAR)
    )


def apply_v1_3_4_status_backup_label_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_status_backup_label_patched", False):
        return

    original_state_icon = _memory._set_card_state_icon
    original_filter_allows = _memory._memory_filter_allows
    original_set_mode = _memory._set_status_filter_mode
    original_availability = _memory._update_status_filter_availability
    original_install_controls = _memory._install_source_and_state_controls
    original_legacy_changed = _coord._legacy_filter_changed
    original_init = MainWindow.__init__

    def state_icon(window: Any, card: Any, record: Any) -> None:
        original_state_icon(window, card, record)
        button = getattr(card, "_fh6_applied_state_button", None)
        if button is None:
            return
        if str(button.property("fh6AppliedState") or "") == "same_car_applied":
            button.setToolTip(
                _txt(
                    "현재 미적용 · 동일 차량에 다른 리버리가 적용 중",
                    "Currently unapplied · another livery for the same car is applied",
                )
            )
            button.setAccessibleName(
                _txt(
                    "현재 미적용 · 동일 차량에 다른 리버리가 적용 중",
                    "Currently unapplied · another livery for the same car is applied",
                )
            )

    def filter_allows(window: Any, record: Any) -> bool:
        mode = getattr(window, "_fh6_memory_livery_filter_mode", _memory.FILTER_DEFAULT)
        if mode != FILTER_NO_APPLIED_FOR_CAR:
            return original_filter_allows(window, record)
        if not _memory._memory_state_usable(window):
            return True
        return _memory._paint_state_for_record(window, record) == "unapplied"

    def set_mode(window: Any, mode: str) -> None:
        original_set_mode(window, mode)
        button = getattr(window, "livery_no_applied_toggle", None)
        if isinstance(button, QPushButton):
            button.blockSignals(True)
            button.setChecked(
                getattr(window, "_fh6_memory_livery_filter_mode", _memory.FILTER_DEFAULT)
                == FILTER_NO_APPLIED_FOR_CAR
            )
            button.blockSignals(False)
        _coord._clear_legacy_auction_state_filter(window)

    def availability(window: Any) -> None:
        original_availability(window)
        button = getattr(window, "livery_no_applied_toggle", None)
        if not isinstance(button, QPushButton):
            return
        enabled = _memory._memory_state_usable(window)
        button.setEnabled(enabled)
        button.setToolTip(
            "" if enabled else _txt(
                "메모리 스캔 후 사용할 수 있습니다.",
                "Available after a memory scan.",
            )
        )
        if not enabled:
            button.setChecked(False)

    def install_controls(window: Any, controls: Any, original: Any) -> None:
        original_install_controls(window, controls, original)
        _install_no_applied_toggle(window, controls)
        availability(window)

    def legacy_changed(window: Any) -> None:
        original_legacy_changed(window)
        filter_button = getattr(window, "livery_check_filter", None)
        selected = filter_button.selected_modes() if filter_button is not None else ()
        if any(mode in selected for mode in _coord.LEGACY_AUCTION_STATE_MODES):
            button = getattr(window, "livery_no_applied_toggle", None)
            if isinstance(button, QPushButton):
                button.blockSignals(True)
                button.setChecked(False)
                button.blockSignals(False)

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _apply_backup_labels(self)
        _remove_backup_page_heading(self)

    _memory._set_card_state_icon = state_icon
    _memory._memory_filter_allows = filter_allows
    _memory._set_status_filter_mode = set_mode
    _memory._update_status_filter_availability = availability
    _memory._install_source_and_state_controls = install_controls
    _coord._legacy_filter_changed = legacy_changed
    MainWindow.__init__ = patched_init
    MainWindow._fh6_v134_status_backup_label_patched = True
