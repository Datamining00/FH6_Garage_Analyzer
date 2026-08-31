from __future__ import annotations

import re
from typing import Any

from PySide6.QtWidgets import QMessageBox, QPushButton

from . import v1_3_2_memory_state_patch as _memory_state
from .memory_applied_state import (
    MemoryScanResult,
    PersistedAppliedState,
    normalized_livery_name,
)
from .memory_snapshot_guard import (
    SnapshotDropDiagnostic,
    detect_suspicious_snapshot_drop,
)
from .models import LiveryRecord


FILTER_DEFAULT = "DEFAULT"
LEGACY_AUCTION_STATE_MODES = (12, 13)
_NORMALIZED_LIVERY_NAME_RE = re.compile(r"^Livery_\d+_\d{14}$")


def _classify_soulbound_from_memory(
    window: Any,
    result: MemoryScanResult,
) -> tuple[set[str], set[str], set[str]]:
    """Use the trusted exact memory identity as the primary SoulBound state.

    CacheThumbnails/manifest data is auxiliary evidence only. Missing, stale, or
    ambiguous cache metadata must not turn a conclusive HIGH/MEDIUM memory
    snapshot into REVIEW.
    """
    records = [
        record
        for record in getattr(getattr(window, "result", None), "liveries", [])
        if isinstance(record, LiveryRecord) and record.kind == "SoulBoundLivery"
    ]

    applied: set[str] = set()
    unapplied: set[str] = set()
    review: set[str] = set()

    for record in records:
        name = normalized_livery_name(record.container_name)
        if not name or _NORMALIZED_LIVERY_NAME_RE.fullmatch(name) is None:
            review.add(str(record.container_name or "<unknown>"))
            continue
        if name in result.active_livery_names:
            applied.add(name)
        else:
            unapplied.add(name)

    return applied, unapplied, review


def _snapshot_drop_diagnostic(
    window: Any,
    result: object,
) -> SnapshotDropDiagnostic | None:
    if not isinstance(result, MemoryScanResult) or not result.usable:
        return None
    previous = getattr(window, "_fh6_memory_state", None)
    if not isinstance(previous, PersistedAppliedState) or not previous.usable:
        return None
    return detect_suspicious_snapshot_drop(
        len(previous.active_livery_names),
        len(result.active_livery_names),
    )


def _confirm_suspicious_snapshot_drop(
    window: Any,
    diagnostic: SnapshotDropDiagnostic,
) -> bool:
    percent = diagnostic.drop_ratio * 100.0
    text = _memory_state._txt(
        f"이전 정상 스캔 {diagnostic.previous_count}개에서 현재 {diagnostic.current_count}개로 "
        f"{diagnostic.dropped_count}개({percent:.1f}%) 감소했습니다.\n\n"
        "게임 업데이트, 로딩 전환 또는 부분 스캔으로 인해 일부 리버리가 누락되었을 수 있습니다.\n"
        "이 결과를 계속 검토하시겠습니까?",
        f"Applied-livery count dropped from {diagnostic.previous_count} in the last valid scan "
        f"to {diagnostic.current_count}, a decrease of {diagnostic.dropped_count} ({percent:.1f}%).\n\n"
        "A game update, loading transition, or partial scan may have omitted some liveries.\n"
        "Continue reviewing this result?",
    )
    answer = QMessageBox.question(
        window,
        _memory_state._txt("메모리 스캔 안전 확인", "Memory scan safety check"),
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def _clear_legacy_auction_state_filter(window: Any) -> None:
    if getattr(window, "_fh6_memory_livery_filter_mode", FILTER_DEFAULT) == FILTER_DEFAULT:
        return
    filter_button = getattr(window, "livery_check_filter", None)
    actions = getattr(filter_button, "_actions", {}) if filter_button is not None else {}
    if not isinstance(actions, dict):
        return
    changed = False
    for mode in LEGACY_AUCTION_STATE_MODES:
        action = actions.get(mode)
        if action is not None and action.isChecked():
            action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(False)
            changed = True
    if changed:
        search = getattr(window, "livery_search", None)
        if search is not None:
            window._filter_saved_content_views("livery", search.text())


def _legacy_filter_changed(window: Any) -> None:
    filter_button = getattr(window, "livery_check_filter", None)
    if filter_button is None:
        return
    selected = filter_button.selected_modes()
    if not any(mode in selected for mode in LEGACY_AUCTION_STATE_MODES):
        return

    window._fh6_memory_livery_filter_mode = FILTER_DEFAULT
    for name in ("livery_applied_toggle", "livery_unapplied_toggle"):
        button = getattr(window, name, None)
        if isinstance(button, QPushButton) and button.isChecked():
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)


def apply_v1_3_2_memory_filter_coordination_patch(MainWindow: Any) -> None:
    """Keep legacy auction-state and new all-livery state selectors non-conflicting."""
    if getattr(MainWindow, "_fh6_v132_memory_filter_coordination_patched", False):
        return

    # v1.3.3 Beta: exact memory membership is authoritative for SoulBound
    # applied/unapplied state. Cache/manifest evidence remains auxiliary only.
    _memory_state._classify_soulbound = _classify_soulbound_from_memory

    original_memory_finished = _memory_state._on_memory_finished

    def guarded_memory_finished(window: Any, result: object) -> None:
        diagnostic = _snapshot_drop_diagnostic(window, result)
        if diagnostic is not None and not _confirm_suspicious_snapshot_drop(window, diagnostic):
            _memory_state._finish_scan_ui(window)
            window.memory_scan_detail.setText(
                _memory_state._txt(
                    "비정상적인 적용 리버리 수 감소가 감지되어 새 결과를 적용하지 않았습니다. "
                    "마지막 정상 적용 결과를 유지합니다.",
                    "An unusual applied-livery count drop was detected, so the new result was not applied. "
                    "The last valid applied result is retained.",
                )
            )
            return
        original_memory_finished(window, result)

    _memory_state._on_memory_finished = guarded_memory_finished

    original_init = MainWindow.__init__

    def patched_init(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        for name in ("livery_applied_toggle", "livery_unapplied_toggle"):
            button = getattr(self, name, None)
            if isinstance(button, QPushButton):
                button.clicked.connect(
                    lambda _checked=False, owner=self:
                    _clear_legacy_auction_state_filter(owner)
                )
        filter_button = getattr(self, "livery_check_filter", None)
        if filter_button is not None:
            filter_button.selectionChanged.connect(
                lambda owner=self: _legacy_filter_changed(owner)
            )

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v132_memory_filter_coordination_patched = True
