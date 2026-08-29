from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QEventLoop, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication, QProgressDialog, QPushButton, QToolButton

from . import performance_metrics as _metrics
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_export_performance_ui_patch as _perf
from . import v1_3_4_backup_import_refinement_patch as _ref
from . import v1_3_4_backup_toolbar_followup_patch as _toolbar
from .backup_export import BackupRepositoryError, INDEX_NAME, load_index
from .models import HeaderInfo, LiveryRecord


_BUSY_CARD_THRESHOLD = 180
_LOADING_DELAY_MS = 150
_CARD_BUILD_CHUNK = 12


def _txt(ko: str, en: str) -> str:
    return _backup_ui._txt(ko, en)


class BackupLoadCancelled(RuntimeError):
    pass


class _CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self.cancelled():
            raise BackupLoadCancelled("backup load cancelled")


@dataclass(slots=True)
class _LoadResult:
    items: list[tuple[dict[str, Any], LiveryRecord, str]]
    total_backup: int
    game_only: int
    both: int
    signature: tuple[str, int, int, int]


def _repository_signature(root: Path | None) -> tuple[str, int, int, int]:
    if root is None:
        return ("", 0, 0, 0)
    try:
        resolved = root.expanduser().resolve()
    except OSError:
        resolved = root.expanduser()
    index = resolved / INDEX_NAME
    try:
        stat = index.stat()
        index_mtime = int(stat.st_mtime_ns)
        index_size = int(stat.st_size)
    except OSError:
        index_mtime = 0
        index_size = 0
    try:
        root_mtime = int(resolved.stat().st_mtime_ns)
    except OSError:
        root_mtime = 0
    return (os.path.normcase(str(resolved)), index_mtime, index_size, root_mtime)


def _record_from_entry(root: Path, entry: dict[str, Any], token: _CancelToken) -> LiveryRecord | None:
    token.check()
    relative = str(entry.get("relative_path") or "").strip()
    if not relative:
        return None
    container_path = root / relative
    if not container_path.is_dir():
        return None

    token.check()
    preview_relative = str(entry.get("preview_relative") or "").strip()
    thumbnail_relative = str(entry.get("thumbnail_relative") or "").strip()
    thumbnail_path: Path | None
    if preview_relative:
        thumbnail_path = root / preview_relative
    elif thumbnail_relative:
        thumbnail_path = container_path / thumbnail_relative
    else:
        thumbnail_path = None
    if thumbnail_path is not None and not thumbnail_path.is_file():
        thumbnail_path = None

    livery_path = container_path / "C_livery"
    if not livery_path.is_file():
        livery_path = None

    car_id = entry.get("car_id")
    try:
        car_id = int(car_id) if car_id is not None else None
    except (TypeError, ValueError):
        car_id = None

    header = HeaderInfo(
        name=str(entry.get("name") or ""),
        description=str(entry.get("description") or ""),
        creator=str(entry.get("creator") or ""),
        created=str(entry.get("created") or ""),
        car_id=car_id,
        guid=str(entry.get("guid") or ""),
    )
    return LiveryRecord(
        container_name=str(entry.get("original_container_name") or container_path.name),
        container_path=container_path,
        kind=str(entry.get("kind") or "Livery"),
        header=header,
        thumbnail_path=thumbnail_path,
        livery_path=livery_path,
        downloaded_at=entry.get("downloaded_at") if isinstance(entry.get("downloaded_at"), (int, float)) else None,
        content_sha256=str(entry.get("content_sha256") or ""),
    )


def _game_maps(game: list[LiveryRecord]) -> tuple[
    dict[tuple[str, str], list[LiveryRecord]],
    dict[tuple[str, str], list[LiveryRecord]],
]:
    by_container: dict[tuple[str, str], list[LiveryRecord]] = {}
    by_digest: dict[tuple[str, str], list[LiveryRecord]] = {}
    for record in game:
        kind = str(record.kind or "").strip().casefold()
        container = str(record.container_name or "").strip().casefold()
        digest = str(record.content_sha256 or "").strip().casefold()
        if kind and container:
            by_container.setdefault((kind, container), []).append(record)
        if kind and digest:
            by_digest.setdefault((kind, digest), []).append(record)
    return by_container, by_digest


def _matched_game_records(
    entry: dict[str, Any],
    by_container: dict[tuple[str, str], list[LiveryRecord]],
    by_digest: dict[tuple[str, str], list[LiveryRecord]],
) -> list[LiveryRecord]:
    kind = str(entry.get("kind") or "").strip().casefold()
    container = str(entry.get("original_container_name") or "").strip().casefold()
    digest = str(entry.get("content_sha256") or "").strip().casefold()

    if digest:
        digest_matches = by_digest.get((kind, digest), [])
        if digest_matches:
            return list(digest_matches)

    candidates = by_container.get((kind, container), []) if kind and container else []
    if not candidates:
        return []
    if not digest:
        return list(candidates)

    known = [
        candidate
        for candidate in candidates
        if str(candidate.content_sha256 or "").strip()
    ]
    if not known:
        # SoulBound normally has no startup digest. Container identity is the
        # established low-I/O fallback used by the existing import refinement.
        return list(candidates)
    return [
        candidate
        for candidate in known
        if str(candidate.content_sha256 or "").strip().casefold() == digest
    ]


def _load_repository_items(
    root: Path | None,
    game: list[LiveryRecord],
    token: _CancelToken,
) -> _LoadResult:
    token.check()
    if root is None:
        return _LoadResult([], 0, len(game), 0, _repository_signature(None))

    resolved = root.expanduser().resolve()
    payload = load_index(resolved)
    by_container, by_digest = _game_maps(game)
    represented: set[int] = set()
    items: list[tuple[dict[str, Any], LiveryRecord, str]] = []
    both = 0

    for raw in payload.get("entries", []):
        token.check()
        if not isinstance(raw, dict):
            continue
        entry = dict(raw)
        record = _record_from_entry(resolved, entry, token)
        if record is None:
            continue
        matches = _matched_game_records(entry, by_container, by_digest)
        if matches:
            both += 1
            represented.update(id(record_) for record_ in matches)
            location = "both"
        else:
            location = "backup"
        items.append((entry, record, location))

    token.check()
    game_only = sum(1 for record in game if id(record) not in represented)
    return _LoadResult(
        items=items,
        total_backup=len(items),
        game_only=game_only,
        both=both,
        signature=_repository_signature(resolved),
    )


class _BackupLoadWorker(QObject):
    finished = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, root: Path | None, game: list[LiveryRecord], token: _CancelToken) -> None:
        super().__init__()
        self.root = root
        self.game = list(game)
        self.token = token

    @Slot()
    def run(self) -> None:
        started = time.perf_counter_ns()
        try:
            result = _load_repository_items(self.root, self.game, self.token)
        except BackupLoadCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:  # noqa: BLE001 - worker boundary
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        finally:
            _metrics.record(
                "backup.lazy.repository_load",
                (time.perf_counter_ns() - started) / 1_000_000.0,
            )
        self.finished.emit(result)


def _backup_controls(window: Any) -> list[Any]:
    controls: list[Any] = []
    controls.extend(getattr(window, "backup_sort_buttons", {}).values())
    controls.extend(
        getattr(window, name, None)
        for name in (
            "backup_filter_button",
            "backup_livery_toggle",
            "backup_auction_toggle",
            "backup_only_toggle",
            "backup_both_toggle",
            "backup_vehicle_group_button",
            "backup_creator_group_button",
            "backup_export_button",
            "backup_choose_button",
            "backup_refresh_button",
            "backup_search",
        )
    )
    return [control for control in controls if control is not None]


def _set_controls_enabled(window: Any, enabled: bool) -> None:
    for control in _backup_controls(window):
        try:
            control.setEnabled(enabled)
        except RuntimeError:
            pass


def _close_load_dialog(window: Any) -> None:
    timer = getattr(window, "_fh6_backup_loading_delay_timer", None)
    if timer is not None:
        timer.stop()
    window._fh6_backup_loading_delay_timer = None
    dialog = getattr(window, "_fh6_backup_loading_dialog", None)
    if isinstance(dialog, QProgressDialog):
        dialog.close()
        dialog.deleteLater()
    window._fh6_backup_loading_dialog = None


def _finish_load_ui(window: Any) -> None:
    _close_load_dialog(window)
    _set_controls_enabled(window, True)


def _show_delayed_loading_dialog(window: Any, token: _CancelToken, message: str) -> None:
    timer = QTimer(window)
    timer.setSingleShot(True)
    timer.setInterval(_LOADING_DELAY_MS)

    def show() -> None:
        if not getattr(window, "_fh6_backup_load_running", False) or token is not getattr(window, "_fh6_backup_cancel_token", None):
            return
        dialog = QProgressDialog(message, _txt("취소", "Cancel"), 0, 0, window)
        dialog.setWindowTitle(_txt("백업", "Backup"))
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setMinimumDuration(0)
        dialog.canceled.connect(token.cancel)
        dialog.show()
        window._fh6_backup_loading_dialog = dialog

    timer.timeout.connect(show)
    timer.start()
    window._fh6_backup_loading_delay_timer = timer


def _status_text(result: _LoadResult) -> str:
    return _txt(
        f"전체 백업 {result.total_backup} \\ 게임 {result.game_only} \\ 게임+백업 {result.both}",
        f"Total backup {result.total_backup} \\ Game {result.game_only} \\ Game+Backup {result.both}",
    )


def _card_identity(entry: dict[str, Any], record: LiveryRecord) -> tuple[str, str, str, str]:
    return (
        str(record.kind or "").strip().casefold(),
        str(entry.get("content_sha256") or record.content_sha256 or "").strip().casefold(),
        str(entry.get("original_container_name") or record.container_name or "").strip().casefold(),
        str(entry.get("relative_path") or "").strip().casefold(),
    )


def _existing_card_map(window: Any) -> dict[tuple[str, str, str, str], Any]:
    result: dict[tuple[str, str, str, str], Any] = {}
    for card in list(getattr(window, "_fh6_backup_cards", []) or []):
        entry = getattr(card, "_fh6_backup_entry", None)
        record = card.property("backupRecord")
        if isinstance(entry, dict) and isinstance(record, LiveryRecord):
            result[_card_identity(entry, record)] = card
    return result


def _dispose_pending_cards(cards: list[Any], reused_ids: set[int]) -> None:
    for card in cards:
        if id(card) not in reused_ids:
            try:
                card.deleteLater()
            except RuntimeError:
                pass


def _commit_cards(
    window: Any,
    result: _LoadResult,
    cards: list[Any],
    reused_ids: set[int],
) -> None:
    old_cards = list(getattr(window, "_fh6_backup_cards", []) or [])
    layout = getattr(window, "backup_grid_layout", None)
    if layout is not None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
    for header in getattr(window, "_fh6_backup_headers", {}).values():
        header.hide()

    window._fh6_backup_cards = cards
    for card in old_cards:
        if id(card) not in reused_ids:
            card.deleteLater()

    window._fh6_backup_items_cache = list(result.items)
    window._fh6_backup_cache_signature = result.signature
    window._fh6_backup_cache_dirty = False
    window._fh6_backup_lazy_loaded = True
    window._fh6_backup_cached_status = (
        result.total_backup,
        result.game_only,
        result.both,
    )
    window.backup_status_label.setText(_status_text(result))
    _backup_ui._relayout_backup(window)
    QTimer.singleShot(0, lambda owner=window: _backup_ui._sync_backup_widths(owner))
    QTimer.singleShot(0, lambda owner=window: _backup_ui._refresh_backup_thumbnails(owner))


def _build_cards_from_result(window: Any, result: _LoadResult, token: _CancelToken) -> None:
    items = list(result.items)
    items.sort(key=lambda item: _backup_ui._backup_sort_key(window, item))
    factory = getattr(window, "_fh6_backup_original_make_saved_content_card", None)
    if not callable(factory):
        _load_failed(window, _txt("백업 카드 생성기를 찾을 수 없습니다.", "Backup card factory is unavailable."))
        return

    existing = _existing_card_map(window)
    pending: list[Any] = []
    reused_ids: set[int] = set()
    started = time.perf_counter_ns()

    def build_chunk(start: int = 0) -> None:
        if token is not getattr(window, "_fh6_backup_cancel_token", None) or token.cancelled():
            _dispose_pending_cards(pending, reused_ids)
            _load_cancelled(window)
            return
        end = min(len(items), start + _CARD_BUILD_CHUNK)
        try:
            for index in range(start, end):
                token.check()
                entry, record, location = items[index]
                identity = _card_identity(entry, record)
                card = existing.get(identity)
                if card is None:
                    key = f"backup::{record.kind}::{record.content_sha256 or record.container_name}::{index}"
                    card = factory("livery", record, key)
                    card.hide()
                else:
                    reused_ids.add(id(card))
                _ref._configure_backup_card(window, card, record, entry, location)
                card.setProperty("backupRecord", record)
                pending.append(card)
        except BackupLoadCancelled:
            _dispose_pending_cards(pending, reused_ids)
            _load_cancelled(window)
            return
        except Exception as exc:  # noqa: BLE001 - UI build boundary
            _dispose_pending_cards(pending, reused_ids)
            _load_failed(window, f"{type(exc).__name__}: {exc}")
            return

        dialog = getattr(window, "_fh6_backup_loading_dialog", None)
        if isinstance(dialog, QProgressDialog):
            dialog.setLabelText(
                _txt(
                    f"백업 목록을 불러오는 중... {end}/{len(items)}",
                    f"Loading backup list... {end}/{len(items)}",
                )
            )

        if end < len(items):
            QTimer.singleShot(0, lambda next_start=end: build_chunk(next_start))
            return

        _metrics.record(
            "backup.lazy.card_build",
            (time.perf_counter_ns() - started) / 1_000_000.0,
            item_count=len(items),
            detail=f"reused={len(reused_ids)} new={len(items) - len(reused_ids)}",
        )
        _commit_cards(window, result, pending, reused_ids)
        _load_finished(window)

    if not items:
        _commit_cards(window, result, [], set())
        _load_finished(window)
        return
    QTimer.singleShot(0, build_chunk)


def _clear_load_thread(window: Any) -> None:
    window._fh6_backup_load_thread = None
    window._fh6_backup_load_worker = None


def _load_finished(window: Any) -> None:
    window._fh6_backup_load_running = False
    window._fh6_backup_cancel_token = None
    _finish_load_ui(window)


def _load_cancelled(window: Any) -> None:
    window._fh6_backup_load_running = False
    window._fh6_backup_cancel_token = None
    window._fh6_backup_cache_dirty = True
    _finish_load_ui(window)
    _metrics.record("backup.lazy.cancelled", 0.0, item_count=1)
    window._show_status(_txt("백업 목록 불러오기를 취소했습니다.", "Backup list loading was cancelled."), 4000)


def _load_failed(window: Any, message: str) -> None:
    window._fh6_backup_load_running = False
    window._fh6_backup_cancel_token = None
    window._fh6_backup_cache_dirty = True
    _finish_load_ui(window)
    window._show_status(_txt("백업 목록을 불러오지 못했습니다.", "Could not load the backup list."), 5000)
    _backup_ui.QMessageBox.warning(
        window,
        _txt("백업 목록 오류", "Backup list error"),
        message,
    )


def _worker_finished(window: Any, result: object, token: _CancelToken) -> None:
    if token is not getattr(window, "_fh6_backup_cancel_token", None):
        return
    if token.cancelled():
        _load_cancelled(window)
        return
    if not isinstance(result, _LoadResult):
        _load_failed(window, _txt("알 수 없는 백업 로딩 결과", "Unknown backup loading result"))
        return
    _build_cards_from_result(window, result, token)


def _worker_cancelled(window: Any, token: _CancelToken) -> None:
    if token is getattr(window, "_fh6_backup_cancel_token", None):
        _load_cancelled(window)


def _worker_failed(window: Any, message: str, token: _CancelToken) -> None:
    if token is getattr(window, "_fh6_backup_cancel_token", None):
        _load_failed(window, message)


def _start_full_load(window: Any, *, force: bool = False, message: str | None = None) -> None:
    if getattr(window, "_fh6_backup_load_running", False):
        return
    if not force and getattr(window, "_fh6_backup_lazy_loaded", False) and not getattr(window, "_fh6_backup_cache_dirty", True):
        _metrics.record("backup.lazy.cache_hit", 0.0, item_count=len(getattr(window, "_fh6_backup_cards", []) or []))
        _backup_ui._relayout_backup(window)
        return

    root = _backup_ui._backup_root(window)
    game = list(_backup_ui._game_records(window))
    token = _CancelToken()
    window._fh6_backup_load_running = True
    window._fh6_backup_cancel_token = token
    _set_controls_enabled(window, False)
    _show_delayed_loading_dialog(
        window,
        token,
        message or _txt("백업 목록을 불러오는 중...", "Loading backup list..."),
    )

    thread = QThread(window)
    worker = _BackupLoadWorker(root, game, token)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(lambda result, owner=window, t=token: _worker_finished(owner, result, t))
    worker.cancelled.connect(lambda owner=window, t=token: _worker_cancelled(owner, t))
    worker.failed.connect(lambda text, owner=window, t=token: _worker_failed(owner, text, t))
    worker.finished.connect(thread.quit)
    worker.cancelled.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(lambda owner=window: _clear_load_thread(owner))
    window._fh6_backup_load_thread = thread
    window._fh6_backup_load_worker = worker
    thread.start()


def _backup_page_visible(window: Any) -> bool:
    return getattr(window, "backup_page", None) is not None and window.pages.currentWidget() is window.backup_page


def _mark_dirty(window: Any, *, refresh_if_visible: bool = True) -> None:
    window._fh6_backup_cache_dirty = True
    if refresh_if_visible and _backup_page_visible(window) and getattr(window, "_fh6_backup_lazy_loaded", False):
        _start_full_load(
            window,
            force=True,
            message=_txt("백업 목록을 업데이트하는 중...", "Updating backup list..."),
        )


def _lazy_rebuild_request(window: Any) -> None:
    """Compatibility target for every older rebuild call site.

    Startup/import/export layers resolve this function through module globals at
    runtime. Before the backup page is opened it only marks the cache dirty.
    """
    _mark_dirty(window, refresh_if_visible=True)


def _open_backup_page(window: Any) -> None:
    window.pages.setCurrentWidget(window.backup_page)
    root = _backup_ui._backup_root(window)
    current_signature = _repository_signature(root)
    cached_signature = getattr(window, "_fh6_backup_cache_signature", None)
    if getattr(window, "_fh6_backup_lazy_loaded", False) and cached_signature != current_signature:
        window._fh6_backup_cache_dirty = True

    if not getattr(window, "_fh6_backup_lazy_loaded", False) or getattr(window, "_fh6_backup_cache_dirty", True):
        _start_full_load(window)
        return

    _metrics.record("backup.lazy.cache_hit", 0.0, item_count=len(getattr(window, "_fh6_backup_cards", []) or []))
    _backup_ui._relayout_backup(window)
    for delay in (0, 40, 120):
        QTimer.singleShot(delay, lambda owner=window: _backup_ui._refresh_backup_thumbnails(owner))


def _run_cached_layout(window: Any, message: str, operation: Any) -> None:
    if getattr(window, "_fh6_backup_load_running", False):
        return
    scroll = getattr(getattr(window, "backup_grid_scroll", None), "verticalScrollBar", lambda: None)()
    scroll_value = scroll.value() if scroll is not None else 0
    card_count = len(getattr(window, "_fh6_backup_cards", []) or [])
    show_busy = card_count >= _BUSY_CARD_THRESHOLD
    if show_busy:
        _set_controls_enabled(window, False)
        begin = getattr(window, "_begin_busy", None)
        if callable(begin):
            begin(message)
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
            5,
        )
    try:
        operation()
    finally:
        if scroll is not None:
            QTimer.singleShot(0, lambda bar=scroll, value=scroll_value: bar.setValue(min(value, bar.maximum())))
        if show_busy:
            end = getattr(window, "_end_busy", None)
            if callable(end):
                end()
            _set_controls_enabled(window, True)


def _set_sort_cached(window: Any, mode: str) -> None:
    def apply() -> None:
        window._fh6_backup_sort_mode = mode
        for key, button in getattr(window, "backup_sort_buttons", {}).items():
            button.setChecked(key == mode)
        cards = list(getattr(window, "_fh6_backup_cards", []) or [])

        def card_key(card: Any) -> tuple[Any, ...]:
            record = card.property("backupRecord")
            entry = getattr(card, "_fh6_backup_entry", None)
            location = str(card.property("backupLocation") or "")
            return _backup_ui._backup_sort_key(window, (entry, record, location))

        cards.sort(key=card_key)
        window._fh6_backup_cards = cards
        _backup_ui._relayout_backup(window)
        _metrics.record("backup.lazy.cached_sort", 0.0, item_count=len(cards), detail="repository_read=0 card_create=0")

    _run_cached_layout(
        window,
        _txt("백업 목록을 정렬하는 중...", "Sorting backup list..."),
        apply,
    )


def _set_group_cached(window: Any, mode: str, enabled: bool) -> None:
    def apply() -> None:
        if not enabled:
            if getattr(window, "_fh6_backup_group_mode", "none") == mode:
                window._fh6_backup_group_mode = "none"
        else:
            window._fh6_backup_group_mode = mode
            other = window.backup_creator_group_button if mode == "vehicle" else window.backup_vehicle_group_button
            other.blockSignals(True)
            other.setChecked(False)
            other.blockSignals(False)
        _backup_ui._relayout_backup(window)
        _metrics.record("backup.lazy.cached_group", 0.0, item_count=len(getattr(window, "_fh6_backup_cards", []) or []), detail="repository_read=0 card_create=0")

    _run_cached_layout(
        window,
        _txt("백업 목록을 분류하는 중...", "Grouping backup list..."),
        apply,
    )


def _set_location_cached(window: Any, mode: str) -> None:
    if mode not in {"all", "backup", "both"}:
        mode = "all"

    def apply() -> None:
        window._fh6_backup_location_filter = mode
        for key, action in getattr(window, "_fh6_backup_filter_actions", {}).items():
            action.setChecked(key == mode)
        _ref._set_location_button_checks(window, mode)
        _ref._repolish_filter(window)
        _backup_ui._relayout_backup(window)
        _metrics.record("backup.lazy.cached_filter", 0.0, item_count=len(getattr(window, "_fh6_backup_cards", []) or []), detail="repository_read=0 card_create=0")

    _run_cached_layout(
        window,
        _txt("백업 목록을 업데이트하는 중...", "Updating backup list..."),
        apply,
    )


def _location_toggle_cached(window: Any, changed: QPushButton) -> None:
    backup = window.backup_only_toggle
    both = window.backup_both_toggle
    if not backup.isChecked() and not both.isChecked():
        changed.blockSignals(True)
        changed.setChecked(True)
        changed.blockSignals(False)
    mode = "all" if backup.isChecked() and both.isChecked() else "backup" if backup.isChecked() else "both"
    _set_location_cached(window, mode)


def _source_toggle_cached(window: Any, changed: QPushButton) -> None:
    livery = window.backup_livery_toggle
    auction = window.backup_auction_toggle
    if not livery.isChecked() and not auction.isChecked():
        changed.blockSignals(True)
        changed.setChecked(True)
        changed.blockSignals(False)
    _run_cached_layout(
        window,
        _txt("백업 목록을 업데이트하는 중...", "Updating backup list..."),
        lambda: _backup_ui._relayout_backup(window),
    )


def _cached_perf_items(window: Any) -> list[tuple[dict[str, Any] | None, LiveryRecord, str]]:
    """Expose cached repository state to toolbar helpers without disk I/O."""
    if getattr(window, "_fh6_backup_lazy_loaded", False) and not getattr(window, "_fh6_backup_cache_dirty", True):
        repository_items = list(getattr(window, "_fh6_backup_items_cache", []) or [])
        represented: set[int] = set()
        game = list(_backup_ui._game_records(window))
        by_container, by_digest = _game_maps(game)
        result: list[tuple[dict[str, Any] | None, LiveryRecord, str]] = list(repository_items)
        for entry, _record, _location in repository_items:
            represented.update(id(record) for record in _matched_game_records(entry, by_container, by_digest))
        for record in game:
            if id(record) not in represented:
                result.append((None, record, "game"))
        return result
    # Do not silently trigger repository I/O before first tab entry.
    return [(None, record, "game") for record in _backup_ui._game_records(window)]


def _install_refresh_button(window: Any) -> None:
    if isinstance(getattr(window, "backup_refresh_button", None), QPushButton):
        return
    choose = getattr(window, "backup_choose_button", None)
    page = getattr(window, "backup_page", None)
    root_layout = page.layout() if page is not None else None
    if not isinstance(choose, QPushButton) or root_layout is None:
        return
    row = _ref._layout_with_widget(root_layout, choose)
    if row is None:
        return
    button = QPushButton(_txt("새로고침", "Refresh"))
    button.setObjectName("secondary")
    button.clicked.connect(
        lambda _checked=False, owner=window: (
            setattr(owner, "_fh6_backup_cache_dirty", True),
            _start_full_load(
                owner,
                force=True,
                message=_txt("백업 목록을 새로고치는 중...", "Refreshing backup list..."),
            ),
        )
    )
    index = row.indexOf(choose)
    row.insertWidget(index + 1 if index >= 0 else row.count(), button)
    window.backup_refresh_button = button


def _cancel_active_load(window: Any) -> None:
    token = getattr(window, "_fh6_backup_cancel_token", None)
    if isinstance(token, _CancelToken):
        token.cancel()


def apply_v1_3_4_backup_lazy_load_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_lazy_load_patched", False):
        return

    # Every older layer resolves these globals when the callback actually runs.
    # Replacing all aliases suppresses startup preload without rewriting the
    # already-validated backup/import/export implementation.
    _backup_ui._rebuild_backup_cards = _lazy_rebuild_request
    _ref._rebuild_backup_cards = _lazy_rebuild_request
    _toolbar._rebuild_backup_cards = _lazy_rebuild_request
    _backup_ui._open_backup_page = _open_backup_page
    _backup_ui._set_backup_sort = _set_sort_cached
    _ref._set_backup_sort_cached = _set_sort_cached
    _backup_ui._set_backup_group = _set_group_cached
    _backup_ui._set_backup_location_filter = _set_location_cached
    _ref._set_backup_location_filter = _set_location_cached
    _ref._location_toggle_changed = _location_toggle_cached
    _ref._source_toggle_changed = _source_toggle_cached
    _perf._backup_items = _cached_perf_items

    original_init = MainWindow.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        # These flags exist before any older __init__ wrapper runs, so its eager
        # rebuild callbacks are converted into dirty markers rather than I/O.
        self._fh6_backup_lazy_loaded = False
        self._fh6_backup_cache_dirty = True
        self._fh6_backup_items_cache = []
        self._fh6_backup_cache_signature = None
        self._fh6_backup_cached_status = (0, 0, 0)
        self._fh6_backup_load_running = False
        self._fh6_backup_cancel_token = None
        self._fh6_backup_load_thread = None
        self._fh6_backup_load_worker = None
        self._fh6_backup_loading_dialog = None
        self._fh6_backup_loading_delay_timer = None
        original_init(self, *args, **kwargs)
        _install_refresh_button(self)
        self.destroyed.connect(lambda *_args, owner=self: _cancel_active_load(owner))

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v134_backup_lazy_load_patched = True
