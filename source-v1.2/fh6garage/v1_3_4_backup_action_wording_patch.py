from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QMessageBox, QToolButton

from . import performance_metrics as _performance_metrics
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_export_performance_ui_patch as _perf
from .card_icons import icon as card_icon
from .models import LiveryRecord
from .performance_measurement_guard import install_performance_measurement_guard
from .v1_3_4_backup_import_refinement_patch import apply_v1_3_4_backup_import_refinement_patch
from .v1_3_4_backup_toolbar_followup_patch import apply_v1_3_4_backup_toolbar_followup_patch
from .v1_3_4_backup_lazy_load_patch import apply_v1_3_4_backup_lazy_load_patch
from .v1_3_4_backup_lazy_watch_patch import apply_v1_3_4_backup_lazy_watch_patch
from .v1_3_4_backup_lazy_thread_bridge_patch import apply_v1_3_4_backup_lazy_thread_bridge_patch
from .v1_3_4_backup_loading_resilience_patch import apply_v1_3_4_backup_loading_resilience_patch
from .v1_3_4_backup_visual_stability_patch import apply_v1_3_4_backup_visual_stability_patch
from .v1_3_4_card_polish_export_delete_patch import apply_v1_3_4_card_polish_export_delete_patch
from .v1_3_4_livery_backup_filter_patch import apply_v1_3_4_livery_backup_filter_patch
from .v1_3_4_status_backup_label_patch import apply_v1_3_4_status_backup_label_patch
from .v1_3_4_performance_probe_patch import apply_v1_3_4_performance_probe_patch

install_performance_measurement_guard(_performance_metrics)


def _backup_confirm(window: Any, count: int) -> bool:
    box = QMessageBox(window)
    box.setWindowTitle(_backup_ui._txt("백업하기", "Back up"))
    box.setText(_backup_ui._txt(
        f"{count}개 항목을 백업한 뒤 게임 쪽 원본을 삭제하시겠습니까?\n\n"
        "원본 삭제는 백업 데이터와 폴더 지문을 다시 검증한 항목에만 수행됩니다.",
        f"Delete the game-side source after backing up {count} item(s)?\n\n"
        "Source deletion is performed only after the backup data and folder fingerprint are verified again.",
    ))
    box.setIcon(QMessageBox.Icon.Question)
    keep = box.addButton(_backup_ui._txt("원본 유지", "Keep source"), QMessageBox.ButtonRole.AcceptRole)
    delete = box.addButton(_backup_ui._txt("원본 삭제", "Delete source"), QMessageBox.ButtonRole.DestructiveRole)
    delete.setToolTip(_backup_ui._txt(
        "백업 검증 성공 후 게임 쪽 원본 컨테이너를 삭제합니다.",
        "Delete the game-side source container only after backup verification succeeds.",
    ))
    cancel = box.addButton(_backup_ui._txt("취소", "Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(keep)
    box.exec()
    clicked = box.clickedButton()
    window._fh6_export_delete_source_requested = clicked is delete
    return clicked in {keep, delete} and clicked is not cancel


def apply_v1_3_4_backup_action_wording_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_action_wording_patched", False):
        return
    original_confirm = _backup_ui._confirm_keep_source
    original_configure = _perf._configure_backup_action_button

    def confirm(window: Any, count: int, *, operation: str) -> bool:
        if operation == "export":
            return _backup_confirm(window, count)
        return original_confirm(window, count, operation=operation)

    def request_backup(window: Any, record: LiveryRecord) -> None:
        window._fh6_backup_tab_backup_prompt = True
        try:
            _backup_ui._request_export(window, [record])
        finally:
            window._fh6_backup_tab_backup_prompt = False

    def configure(window: Any, card: Any, record: LiveryRecord, location: str) -> None:
        if location != "game":
            original_configure(window, card, record, location)
            return
        button = getattr(card, "_fh6_export_placeholder_button", None)
        if not isinstance(button, QToolButton):
            return
        button.setObjectName("fh6BackupButton")
        button.setEnabled(True)
        button.setIcon(card_icon("export", _backup_ui._INACTIVE_COLOR, 20))
        button.setIconSize(QSize(20, 20))
        button.setStyleSheet(_backup_ui._action_style(False))
        button.setToolTip(_backup_ui._txt("백업하기", "Back up"))
        button.setAccessibleName(_backup_ui._txt("백업하기", "Back up"))
        if not bool(button.property("fh6BackupActionInstalled")):
            button.setProperty("fh6BackupActionInstalled", True)
            button.clicked.connect(lambda _checked=False, owner=window, item=record: request_backup(owner, item))

    _backup_ui._confirm_keep_source = confirm
    _perf._configure_backup_action_button = configure
    MainWindow._fh6_v134_backup_action_wording_patched = True

    apply_v1_3_4_backup_import_refinement_patch(MainWindow)
    apply_v1_3_4_backup_toolbar_followup_patch(MainWindow)
    apply_v1_3_4_backup_lazy_load_patch(MainWindow)
    apply_v1_3_4_backup_lazy_watch_patch(MainWindow)
    apply_v1_3_4_backup_lazy_thread_bridge_patch(MainWindow)
    apply_v1_3_4_backup_loading_resilience_patch(MainWindow)
    apply_v1_3_4_backup_visual_stability_patch(MainWindow)
    apply_v1_3_4_card_polish_export_delete_patch(MainWindow)
    apply_v1_3_4_livery_backup_filter_patch(MainWindow)
    apply_v1_3_4_status_backup_label_patch(MainWindow)
    apply_v1_3_4_performance_probe_patch(MainWindow)
