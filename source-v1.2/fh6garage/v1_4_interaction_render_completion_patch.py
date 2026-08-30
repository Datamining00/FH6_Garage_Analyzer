from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QEvent, QEventLoop, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel

from . import performance_metrics as _metrics
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_lazy_load_patch as _lazy
from . import v1_3_4_backup_loading_resilience_patch as _resilience
from . import v1_3_4_card_features_patch as _features
from . import v1_4_acquisition_ui_patch as _acquisition
from .acquisition_db import AcquisitionDatabase


_METADATA_BACKGROUND_CHUNK = 32
_VISIBLE_MARGIN = 220
_BACKUP_PAINT_PROCESS_MS = 12
_BACKUP_COMPLETION_POLL_MS = 16
_BACKUP_COMPLETION_TIMEOUT_MS = 3000
_BACKUP_FULL_LOAD_FINISH_POLL_MS = 16
_BACKUP_FULL_LOAD_FINISH_TIMEOUT_MS = 3000


def _txt(ko: str, en: str) -> str:
    return _backup_ui._txt(ko, en)


class _AcquisitionCopyController(QObject):
    """Make the existing source QLabel copy its displayed raw value on click."""

    def __init__(self, window: Any, label: QLabel, value: str) -> None:
        super().__init__(label)
        self.window = window
        self.label = label
        self.copy_value = str(value or "-")
        label.installEventFilter(self)
        label.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_copy_value(self, value: str) -> None:
        self.copy_value = str(value or "-")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            button = getattr(event, "button", lambda: None)()
            if button == Qt.MouseButton.LeftButton:
                QApplication.clipboard().setText(self.copy_value)
                toast = getattr(self.window, "_show_copy_toast", None)
                if callable(toast):
                    toast()
                else:
                    status = getattr(self.window, "_show_status", None)
                    if callable(status):
                        status(_txt("복사했습니다.", "Copied."), 1000)
                event.accept()
                return True
        return False


def _install_acquisition_copy(window: Any, card: Any, record: Any) -> None:
    label = card.findChild(QLabel, "fh6AcquisitionPlaceholder")
    if not isinstance(label, QLabel):
        return
    header = getattr(record, "header", None)
    car_id = getattr(header, "car_id", None)
    database = getattr(window, "acquisition_db", None)
    info = database.get(car_id) if isinstance(database, AcquisitionDatabase) else None
    value = _acquisition._acquisition_text(info)

    controller = getattr(label, "_fh6_acquisition_copy_controller", None)
    if isinstance(controller, _AcquisitionCopyController):
        controller.set_copy_value(value)
    else:
        controller = _AcquisitionCopyController(window, label, value)
        label._fh6_acquisition_copy_controller = controller

    detail = _acquisition._acquisition_tooltip(info)
    copy_hint = _txt("클릭하여 출처 복사", "Click to copy source")
    label.setToolTip(f"{detail}\n\n{copy_hint}")


def _card_near_viewport(window: Any, card: Any) -> bool:
    for name in ("livery_grid_scroll", "tuning_grid_scroll", "backup_grid_scroll"):
        scroll = getattr(window, name, None)
        if scroll is None:
            continue
        viewport = scroll.viewport()
        if viewport is None or not viewport.isVisible():
            continue
        try:
            top_left = card.mapTo(viewport, QPoint(0, 0))
            rect = QRect(top_left, card.size())
            visible = viewport.rect().adjusted(0, -_VISIBLE_MARGIN, 0, _VISIBLE_MARGIN)
            if rect.intersects(visible):
                return True
        except RuntimeError:
            continue
    return False


def _set_metadata_collapsed_visible_first(window: Any, collapsed: bool) -> None:
    collapsed = bool(collapsed)
    preferences = getattr(window, "local_preferences", None)
    setter = getattr(preferences, "set_bool", None)
    if callable(setter):
        setter(_features._METADATA_COLLAPSED_PREF, collapsed)
    window._fh6_v134_metadata_collapsed = collapsed

    cards = _features._registered_metadata_cards(window)
    immediate: list[Any] = []
    deferred: list[Any] = []
    for card in cards:
        if _card_near_viewport(window, card):
            immediate.append(card)
        else:
            deferred.append(card)

    for card in immediate:
        _features._apply_metadata_state(card, collapsed)

    generation = int(getattr(window, "_fh6_metadata_update_generation", 0) or 0) + 1
    window._fh6_metadata_update_generation = generation

    def apply_chunk(start: int = 0) -> None:
        if generation != int(getattr(window, "_fh6_metadata_update_generation", 0) or 0):
            return
        end = min(len(deferred), start + _METADATA_BACKGROUND_CHUNK)
        for card in deferred[start:end]:
            try:
                _features._apply_metadata_state(card, collapsed)
            except RuntimeError:
                continue
        if end < len(deferred):
            QTimer.singleShot(0, lambda next_start=end: apply_chunk(next_start))

    if deferred:
        QTimer.singleShot(0, apply_chunk)


def _finish_cached_layout_busy(window: Any, generation: int) -> None:
    if generation != int(getattr(window, "_fh6_backup_cached_layout_generation", 0) or 0):
        return
    waiting = bool(getattr(window, "_fh6_backup_cached_layout_waiting", False))
    if not waiting:
        return
    window._fh6_backup_cached_layout_waiting = False

    try:
        _resilience._ORIGINAL_REFRESH_BACKUP_THUMBNAILS(window)
    except RuntimeError:
        pass
    viewport = getattr(getattr(window, "backup_grid_scroll", None), "viewport", lambda: None)()
    if viewport is not None:
        try:
            viewport.update()
        except RuntimeError:
            pass
    QApplication.processEvents(
        QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
        _BACKUP_PAINT_PROCESS_MS,
    )

    scroll = getattr(getattr(window, "backup_grid_scroll", None), "verticalScrollBar", lambda: None)()
    saved = getattr(window, "_fh6_backup_cached_layout_scroll", None)
    if scroll is not None and isinstance(saved, int):
        scroll.setValue(min(saved, scroll.maximum()))
    window._fh6_backup_cached_layout_scroll = None

    if bool(getattr(window, "_fh6_backup_cached_layout_busy_shown", False)):
        end = getattr(window, "_end_busy", None)
        if callable(end):
            end()
        _lazy._set_controls_enabled(window, True)
    window._fh6_backup_cached_layout_busy_shown = False


def _poll_cached_layout_completion(window: Any, generation: int, started_ns: int) -> None:
    if generation != int(getattr(window, "_fh6_backup_cached_layout_generation", 0) or 0):
        return
    if not bool(getattr(window, "_fh6_backup_cached_layout_waiting", False)):
        return

    active = bool(getattr(window, "_fh6_backup_relayout_active", False))
    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
    if active and elapsed_ms < _BACKUP_COMPLETION_TIMEOUT_MS:
        QTimer.singleShot(
            _BACKUP_COMPLETION_POLL_MS,
            lambda owner=window, gen=generation, started=started_ns: _poll_cached_layout_completion(owner, gen, started),
        )
        return

    if active:
        _metrics.record(
            "backup.cached_layout.completion_timeout",
            elapsed_ms,
            item_count=len(getattr(window, "_fh6_backup_cards", []) or []),
            detail="busy_released=1 relayout_still_active=1",
        )
    _finish_cached_layout_busy(window, generation)


def _run_cached_layout_until_visible_paint(window: Any, message: str, operation: Any) -> None:
    if getattr(window, "_fh6_backup_load_running", False):
        return

    scroll = getattr(getattr(window, "backup_grid_scroll", None), "verticalScrollBar", lambda: None)()
    scroll_value = scroll.value() if scroll is not None else 0
    card_count = len(getattr(window, "_fh6_backup_cards", []) or [])
    show_busy = card_count >= _lazy._BUSY_CARD_THRESHOLD

    generation = int(getattr(window, "_fh6_backup_cached_layout_generation", 0) or 0) + 1
    window._fh6_backup_cached_layout_generation = generation
    window._fh6_backup_cached_layout_waiting = True
    window._fh6_backup_cached_layout_busy_shown = show_busy
    window._fh6_backup_cached_layout_scroll = scroll_value

    if show_busy:
        _lazy._set_controls_enabled(window, False)
        begin = getattr(window, "_begin_busy", None)
        if callable(begin):
            begin(message)
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
            5,
        )

    started_ns = time.perf_counter_ns()
    try:
        operation()
    except Exception:
        _finish_cached_layout_busy(window, generation)
        raise

    QTimer.singleShot(
        0,
        lambda owner=window, gen=generation, started=started_ns: _poll_cached_layout_completion(owner, gen, started),
    )


def _poll_full_load_finish(window: Any, finish_generation: int, started_ns: int) -> None:
    if finish_generation != int(getattr(window, "_fh6_backup_full_load_finish_generation", 0) or 0):
        return
    if not bool(getattr(window, "_fh6_backup_load_running", False)):
        return

    active = bool(getattr(window, "_fh6_backup_relayout_active", False))
    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
    if active and elapsed_ms < _BACKUP_FULL_LOAD_FINISH_TIMEOUT_MS:
        QTimer.singleShot(
            _BACKUP_FULL_LOAD_FINISH_POLL_MS,
            lambda owner=window, gen=finish_generation, started=started_ns: _poll_full_load_finish(owner, gen, started),
        )
        return

    if active:
        _metrics.record(
            "backup.full_load.relayout_finish_timeout",
            elapsed_ms,
            item_count=len(getattr(window, "_fh6_backup_cards", []) or []),
            detail="load_ui_released=1 relayout_still_active=1",
        )

    # A superseded relayout generation must never strand the full-load state.
    # Clear the deferred flag before calling the original terminal UI cleanup so
    # a later relayout finish cannot invoke it a second time.
    window._fh6_backup_finish_after_relayout = False
    _resilience._ORIGINAL_LAZY_LOAD_FINISHED(window)


def _bounded_deferred_load_finished(window: Any) -> None:
    if not bool(getattr(window, "_fh6_backup_relayout_active", False)):
        _resilience._ORIGINAL_LAZY_LOAD_FINISHED(window)
        return

    window._fh6_backup_finish_after_relayout = True
    finish_generation = int(getattr(window, "_fh6_backup_full_load_finish_generation", 0) or 0) + 1
    window._fh6_backup_full_load_finish_generation = finish_generation
    started_ns = time.perf_counter_ns()
    QTimer.singleShot(
        0,
        lambda owner=window, gen=finish_generation, started=started_ns: _poll_full_load_finish(owner, gen, started),
    )


def apply_v1_4_interaction_render_completion_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_interaction_render_completion_patched", False):
        return

    original_decorate = _acquisition._decorate_acquisition_label

    def decorate(window: Any, card: Any, record: Any) -> None:
        original_decorate(window, card, record)
        _install_acquisition_copy(window, card, record)

    _acquisition._decorate_acquisition_label = decorate
    _features._set_metadata_collapsed = _set_metadata_collapsed_visible_first
    _lazy._run_cached_layout = _run_cached_layout_until_visible_paint
    _lazy._load_finished = _bounded_deferred_load_finished

    MainWindow._fh6_v14_interaction_render_completion_patched = True
