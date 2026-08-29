from __future__ import annotations

import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from . import performance_metrics as _metrics
from . import ui as _ui
from . import v1_3_2_responsiveness_sort_patch as _responsive
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_export_performance_ui_patch as _perf
from . import v1_3_4_backup_import_refinement_patch as _import
from .i18n import get_language


_SETTING_KEY = "performance_profiling_enabled"
_SLOW_WIDTH_SYNC_MS = 10.0
_POPULATE_CHILD_PREFIX = "startup.populate."


def _txt(ko: str, en: str) -> str:
    return ko if (get_language() or "ko").lower().startswith("ko") else en


def _count_items(counter: Callable[..., int | None] | None, args: tuple[Any, ...], kwargs: dict[str, Any]) -> int | None:
    if counter is None:
        return None
    try:
        return counter(*args, **kwargs)
    except Exception:
        return None


def _phase_accumulate(owner: Any, name: str, elapsed_ms: float) -> None:
    if owner is None or int(getattr(owner, "_fh6_perf_livery_relayout_depth", 0) or 0) <= 0:
        return
    phases = getattr(owner, "_fh6_perf_livery_relayout_phases", None)
    if not isinstance(phases, dict):
        return
    phases[name] = float(phases.get(name, 0.0) or 0.0) + float(elapsed_ms)


def _populate_child_enter(owner: Any, startup_name: str, started_ns: int) -> None:
    state = getattr(owner, "_fh6_perf_populate_timeline", None)
    if not isinstance(state, dict):
        return
    depth = int(state.get("depth", 0) or 0)
    state["depth"] = depth + 1
    if depth:
        return
    previous = str(state.get("previous", "start") or "start")
    gap_ms = max(0.0, (started_ns - int(state["cursor_ns"])) / 1_000_000.0)
    state["gaps"].append((f"{previous}_to_{startup_name.removeprefix(_POPULATE_CHILD_PREFIX)}", gap_ms))


def _populate_child_exit(owner: Any, startup_name: str, started_ns: int, ended_ns: int) -> None:
    state = getattr(owner, "_fh6_perf_populate_timeline", None)
    if not isinstance(state, dict):
        return
    depth = max(0, int(state.get("depth", 1) or 1) - 1)
    state["depth"] = depth
    if depth:
        return
    state["child_nonoverlap_ms"] += max(0.0, (ended_ns - started_ns) / 1_000_000.0)
    state["cursor_ns"] = ended_ns
    state["previous"] = startup_name.removeprefix(_POPULATE_CHILD_PREFIX)


def _timed(
    name: str,
    fn: Callable[..., Any],
    *,
    item_count: Callable[..., int | None] | None = None,
    startup_name: str | None = None,
    aggregate_only: bool = False,
    slow_threshold_ms: float | None = None,
    phase_name: str | None = None,
):
    """Measure a runtime path and optionally mirror it into always-on startup data."""
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any):
        runtime = _metrics.is_enabled()
        startup = bool(startup_name and _metrics.startup_active())
        owner = args[0] if args else None
        relayout_phase = bool(phase_name and int(getattr(owner, "_fh6_perf_livery_relayout_depth", 0) or 0) > 0)
        if not runtime and not startup and not relayout_phase:
            return fn(*args, **kwargs)
        count = _count_items(item_count, args, kwargs)
        started = time.perf_counter_ns()
        populate_child = bool(startup and startup_name and startup_name.startswith(_POPULATE_CHILD_PREFIX))
        if populate_child:
            _populate_child_enter(owner, startup_name, started)
        try:
            return fn(*args, **kwargs)
        finally:
            ended = time.perf_counter_ns()
            elapsed = (ended - started) / 1_000_000.0
            if populate_child:
                _populate_child_exit(owner, startup_name, started, ended)
            if phase_name:
                _phase_accumulate(owner, phase_name, elapsed)
            if startup and startup_name:
                _metrics.record_startup(startup_name, elapsed, item_count=count)
            if runtime:
                if aggregate_only:
                    _metrics.add_sample(name, elapsed)
                    if slow_threshold_ms is not None and elapsed >= slow_threshold_ms:
                        _metrics.record(f"{name}.slow", elapsed, item_count=count)
                else:
                    _metrics.record(name, elapsed, item_count=count)
    return wrapped


def _format_copy_payload() -> str:
    startup = _metrics.format_startup() or _txt("측정 기록 없음", "No startup measurements")
    summary = _metrics.format_aggregate(300, max_rows=60) or _txt("집계 기록 없음", "No aggregate measurements")
    recent = _metrics.format_recent(300) or _txt("런타임 측정 기록 없음", "No runtime measurements")
    return (
        f"[{_txt('최근 시작 결과', 'Latest startup')}]\n{startup}\n\n"
        f"[{_txt('런타임 집계', 'Runtime summary')}]\n{summary}\n\n"
        f"[{_txt('최근 런타임 이벤트', 'Recent runtime events')}]\n{recent}"
    )


def _refresh_text(window: Any) -> None:
    startup_edit = getattr(window, "performance_startup_view", None)
    if isinstance(startup_edit, QPlainTextEdit):
        startup_edit.setPlainText(_metrics.format_startup() or _txt("측정 기록 없음", "No startup measurements"))
        startup_edit.moveCursor(startup_edit.textCursor().MoveOperation.End)

    summary_edit = getattr(window, "performance_summary_view", None)
    if isinstance(summary_edit, QPlainTextEdit):
        summary_edit.setPlainText(_metrics.format_aggregate(300, max_rows=40) or _txt("집계 기록 없음", "No aggregate measurements"))

    edit = getattr(window, "performance_log_view", None)
    if isinstance(edit, QPlainTextEdit):
        edit.setPlainText(_metrics.format_recent(150) or _txt("런타임 측정 기록 없음", "No runtime measurements"))
        cursor = edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        edit.setTextCursor(cursor)


def _set_enabled(window: Any, enabled: bool) -> None:
    enabled = bool(enabled)
    _metrics.set_enabled(enabled)
    window.settings.setValue(_SETTING_KEY, enabled)
    button = getattr(window, "performance_toggle_button", None)
    if isinstance(button, QPushButton):
        button.blockSignals(True)
        button.setChecked(enabled)
        button.setText(_txt("성능 측정 ON", "Profiling ON") if enabled else _txt("성능 측정 OFF", "Profiling OFF"))
        button.blockSignals(False)
    label = getattr(window, "performance_status_label", None)
    if isinstance(label, QLabel):
        label.setText(
            _txt(
                "런타임 측정 중 · 초기 실행 측정은 ON/OFF와 관계없이 항상 기록됩니다.",
                "Runtime profiling active · startup is always recorded regardless of this switch.",
            )
            if enabled
            else _txt(
                "런타임 측정 비활성 · 초기 실행 측정은 항상 기록됩니다.",
                "Runtime profiling disabled · startup is still always recorded.",
            )
        )
    _refresh_text(window)


def _clear(window: Any) -> None:
    _metrics.clear_recent(clear_file=True)
    _refresh_text(window)


def _copy(window: Any) -> None:
    QApplication.clipboard().setText(_format_copy_payload())
    window._show_status(_txt("성능 측정 결과를 복사했습니다.", "Performance results copied."), 3000)


def _open_log_folder(window: Any) -> None:
    path = _metrics.log_dir()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _readonly_view(*, maximum_height: int | None = None) -> QPlainTextEdit:
    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    if maximum_height is not None:
        view.setMaximumHeight(maximum_height)
    return view


def _performance_page(window: Any) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    title = QLabel(_txt("성능 측정", "Performance profiling"))
    title.setObjectName("pageTitle")
    layout.addWidget(title)

    subtitle = QLabel(
        _txt(
            "초기 실행은 매번 자동 측정합니다. ON/OFF는 실행 후 런타임 측정에만 적용됩니다.",
            "Startup is measured on every launch. The ON/OFF switch controls runtime measurements only.",
        )
    )
    subtitle.setObjectName("muted")
    subtitle.setWordWrap(True)
    layout.addWidget(subtitle)

    controls = QHBoxLayout()
    toggle = QPushButton()
    toggle.setObjectName("primary")
    toggle.setCheckable(True)
    toggle.clicked.connect(lambda checked=False, owner=window: _set_enabled(owner, checked))
    controls.addWidget(toggle)

    copy = QPushButton(_txt("결과 복사", "Copy results"))
    copy.setObjectName("secondary")
    copy.clicked.connect(lambda _checked=False, owner=window: _copy(owner))
    controls.addWidget(copy)

    folder = QPushButton(_txt("로그 폴더 열기", "Open log folder"))
    folder.setObjectName("secondary")
    folder.clicked.connect(lambda _checked=False, owner=window: _open_log_folder(owner))
    controls.addWidget(folder)

    clear = QPushButton(_txt("기록 초기화", "Clear history"))
    clear.setObjectName("secondary")
    clear.clicked.connect(lambda _checked=False, owner=window: _clear(owner))
    controls.addWidget(clear)
    controls.addStretch(1)
    layout.addLayout(controls)

    status = QLabel()
    status.setObjectName("muted")
    layout.addWidget(status)

    startup_label = QLabel(_txt("최근 시작 결과", "Latest startup"))
    startup_label.setObjectName("muted")
    layout.addWidget(startup_label)
    startup_view = _readonly_view(maximum_height=210)
    startup_view.setPlaceholderText(_txt("측정 기록 없음", "No startup measurements"))
    layout.addWidget(startup_view)

    summary_label = QLabel(_txt("런타임 집계 · 최근 세션", "Runtime summary · recent session"))
    summary_label.setObjectName("muted")
    layout.addWidget(summary_label)
    summary_view = _readonly_view(maximum_height=180)
    summary_view.setPlaceholderText(_txt("집계 기록 없음", "No aggregate measurements"))
    layout.addWidget(summary_view)

    recent_label = QLabel(_txt("최근 런타임 이벤트", "Recent runtime events"))
    recent_label.setObjectName("muted")
    layout.addWidget(recent_label)
    view = _readonly_view()
    view.setPlaceholderText(_txt("런타임 측정 기록 없음", "No runtime measurements"))
    layout.addWidget(view, 1)

    window.performance_toggle_button = toggle
    window.performance_status_label = status
    window.performance_startup_view = startup_view
    window.performance_summary_view = summary_view
    window.performance_log_view = view
    return page


def _install_navigation(window: Any) -> None:
    page = _performance_page(window)
    window.performance_page = page
    window.pages.addWidget(page)

    sidebar = window.findChild(QFrame, "sidebar")
    if sidebar is None or sidebar.layout() is None:
        return
    button = QPushButton(_txt("성능 측정", "Performance"), sidebar)
    button.setObjectName("nav")
    button.setCheckable(True)
    button.clicked.connect(lambda _checked=False, owner=window, target=page: owner.pages.setCurrentWidget(target))
    window.nav_group.addButton(button)
    window.nav_buttons.append(button)

    layout = sidebar.layout()
    memory = getattr(window, "memory_nav_button", None)
    index = layout.indexOf(memory) if memory is not None else -1
    layout.insertWidget(index + 1 if index >= 0 else max(1, layout.count() - 4), button)
    window.performance_nav_button = button

    enabled = bool(window.settings.value(_SETTING_KEY, False, bool))
    _set_enabled(window, enabled)
    timer = QTimer(page)
    timer.setInterval(750)
    timer.timeout.connect(lambda owner=window: _refresh_text(owner) if _metrics.is_enabled() else None)
    timer.start()
    window._fh6_performance_refresh_timer = timer


def _schedule_startup_ready(window: Any) -> None:
    if not _metrics.startup_active() or not _metrics.startup_waiting_for_scan():
        return
    if bool(getattr(window, "_fh6_startup_finish_scheduled", False)):
        return
    window._fh6_startup_finish_scheduled = True
    started = time.perf_counter_ns()

    def second_turn() -> None:
        _metrics.record_startup(
            "startup.ready_after_scan_render",
            (time.perf_counter_ns() - started) / 1_000_000.0,
        )
        _metrics.finish_startup(detail="saved path scan + initial UI ready")
        window._fh6_startup_finish_scheduled = False
        _refresh_text(window)

    QTimer.singleShot(0, lambda: QTimer.singleShot(0, second_turn))


def _wrap_relayout(MainWindow: Any) -> None:
    original = MainWindow._relayout_livery_grid

    @wraps(original)
    def wrapped(self: Any, *args: Any, **kwargs: Any):
        runtime = _metrics.is_enabled()
        startup = _metrics.startup_active()
        if not runtime and not startup:
            return original(self, *args, **kwargs)

        depth = int(getattr(self, "_fh6_perf_livery_relayout_depth", 0) or 0)
        outer = depth == 0
        if outer:
            self._fh6_perf_livery_relayout_phases = {}
        self._fh6_perf_livery_relayout_depth = depth + 1
        started = time.perf_counter_ns()
        try:
            return original(self, *args, **kwargs)
        finally:
            elapsed = (time.perf_counter_ns() - started) / 1_000_000.0
            self._fh6_perf_livery_relayout_depth = max(0, int(getattr(self, "_fh6_perf_livery_relayout_depth", 1)) - 1)
            count = len(getattr(self, "_livery_grid_cards", []) or [])
            if runtime:
                _metrics.record("ui.livery_relayout.total", elapsed, item_count=count)
            if startup:
                _metrics.record_startup("startup.livery_relayout.total", elapsed, item_count=count)
            if outer:
                phases = dict(getattr(self, "_fh6_perf_livery_relayout_phases", {}) or {})
                accounted = sum(float(value or 0.0) for value in phases.values())
                residual = max(0.0, elapsed - accounted)
                if runtime:
                    _metrics.record(
                        "ui.livery_relayout.unaccounted",
                        residual,
                        item_count=count,
                        detail="total minus measured sub-phases",
                    )
                if startup:
                    for phase_name, phase_ms in phases.items():
                        _metrics.record_startup(
                            f"startup.livery_relayout.{phase_name}",
                            float(phase_ms),
                            item_count=count,
                        )
                    _metrics.record_startup(
                        "startup.livery_relayout.unaccounted",
                        residual,
                        item_count=count,
                        detail="total minus measured sub-phases",
                    )
                self._fh6_perf_livery_relayout_phases = {}

    MainWindow._relayout_livery_grid = wrapped


def _install_relayout_internal_probes(MainWindow: Any) -> None:
    original_clear = _responsive._responsive_clear_grid_layout

    @wraps(original_clear)
    def timed_clear(self: Any, content_type: str, *args: Any, **kwargs: Any):
        active = content_type == "livery" and int(getattr(self, "_fh6_perf_livery_relayout_depth", 0) or 0) > 0
        if not active and not _metrics.is_enabled():
            return original_clear(self, content_type, *args, **kwargs)
        started = time.perf_counter_ns()
        try:
            return original_clear(self, content_type, *args, **kwargs)
        finally:
            elapsed = (time.perf_counter_ns() - started) / 1_000_000.0
            if active:
                _phase_accumulate(self, "clear_layout", elapsed)
            if _metrics.is_enabled() and content_type == "livery":
                _metrics.record("ui.livery_relayout.clear_layout", elapsed)

    _responsive._responsive_clear_grid_layout = timed_clear

    original_layout = _responsive._responsive_layout_visible_grid_cards

    @wraps(original_layout)
    def timed_layout(self: Any, content_type: str, cards: list[Any], *args: Any, **kwargs: Any):
        active = content_type == "livery" and int(getattr(self, "_fh6_perf_livery_relayout_depth", 0) or 0) > 0
        if not active and not _metrics.is_enabled():
            return original_layout(self, content_type, cards, *args, **kwargs)
        started = time.perf_counter_ns()
        try:
            return original_layout(self, content_type, cards, *args, **kwargs)
        finally:
            elapsed = (time.perf_counter_ns() - started) / 1_000_000.0
            if active:
                _phase_accumulate(self, "layout_visible", elapsed)
            if _metrics.is_enabled() and content_type == "livery":
                _metrics.record("ui.livery_relayout.layout_visible", elapsed, item_count=len(cards))

    _responsive._responsive_layout_visible_grid_cards = timed_layout
    _responsive._livery_visibility_allowed = _timed(
        "ui.livery_relayout.visibility",
        _responsive._livery_visibility_allowed,
        aggregate_only=True,
        phase_name="visibility",
    )

    original_yield = _responsive._yield_busy_events

    @wraps(original_yield)
    def timed_yield(self: Any, *args: Any, **kwargs: Any):
        active = int(getattr(self, "_fh6_perf_livery_relayout_depth", 0) or 0) > 0
        if not active and not _metrics.is_enabled():
            return original_yield(self, *args, **kwargs)
        started = time.perf_counter_ns()
        try:
            return original_yield(self, *args, **kwargs)
        finally:
            elapsed = (time.perf_counter_ns() - started) / 1_000_000.0
            if active:
                _phase_accumulate(self, "process_events", elapsed)
            if _metrics.is_enabled() and active:
                _metrics.add_sample("ui.livery_relayout.process_events", elapsed)

    _responsive._yield_busy_events = timed_yield

    if hasattr(MainWindow, "_livery_filter_matches"):
        MainWindow._livery_filter_matches = _timed(
            "ui.livery_relayout.filter_match",
            MainWindow._livery_filter_matches,
            aggregate_only=True,
            phase_name="filter_match",
        )

    if hasattr(MainWindow, "_sync_livery_grid_card_widths"):
        MainWindow._sync_livery_grid_card_widths = _timed(
            "ui.livery_relayout.width_sync",
            MainWindow._sync_livery_grid_card_widths,
            item_count=lambda self, *a, **k: len(getattr(self, "_livery_grid_cards", []) or []),
            aggregate_only=True,
            slow_threshold_ms=_SLOW_WIDTH_SYNC_MS,
            phase_name="width_sync",
        )


def _install_backup_probes(MainWindow: Any) -> None:
    _perf._presence_snapshot = _timed("backup.presence_snapshot", _perf._presence_snapshot)
    _perf._game_index = _timed("backup.match.game_index", _perf._game_index)
    _import.backup_records = _timed("backup.match.repository_records", _import.backup_records)
    _import._entry_is_in_game = _timed(
        "backup.match.entry_compare",
        _import._entry_is_in_game,
        aggregate_only=True,
    )
    _backup_ui._backup_sort_key = _timed(
        "backup.sort_key",
        _backup_ui._backup_sort_key,
        aggregate_only=True,
    )
    _import._backup_items = _timed("backup.build_items", _import._backup_items)
    _import._rebuild_backup_cards = _timed("backup.rebuild_request", _import._rebuild_backup_cards)
    _import._configure_backup_card = _timed(
        "backup.card_configure",
        _import._configure_backup_card,
        aggregate_only=True,
    )

    maker = getattr(MainWindow, "_make_saved_content_card", None)
    if callable(maker):
        @wraps(maker)
        def timed_maker(self: Any, *args: Any, **kwargs: Any):
            key = ""
            if len(args) >= 3:
                key = str(args[2] or "")
            elif "key" in kwargs:
                key = str(kwargs.get("key") or "")
            if not (_metrics.is_enabled() and key.startswith("backup::")):
                return maker(self, *args, **kwargs)
            started = time.perf_counter_ns()
            try:
                return maker(self, *args, **kwargs)
            finally:
                _metrics.add_sample("backup.card_factory", (time.perf_counter_ns() - started) / 1_000_000.0)
        MainWindow._make_saved_content_card = timed_maker


def _install_probes(MainWindow: Any) -> None:
    _ui.scan_save = _timed("scan.total", _ui.scan_save, startup_name="startup.scan")

    original_populate = MainWindow._populate_all
    timed_populate = _timed(
        "ui.populate_all",
        original_populate,
        item_count=lambda self: len(getattr(getattr(self, "result", None), "liveries", []) or [])
        + len(getattr(getattr(self, "result", None), "tunings", []) or []),
        startup_name="startup.initial_populate",
    )

    @wraps(original_populate)
    def populate_all(self: Any, *args: Any, **kwargs: Any):
        timeline_started = time.perf_counter_ns()
        tracking = _metrics.startup_active()
        if tracking:
            self._fh6_perf_populate_timeline = {
                "cursor_ns": timeline_started,
                "previous": "start",
                "depth": 0,
                "gaps": [],
                "child_nonoverlap_ms": 0.0,
            }
        try:
            return timed_populate(self, *args, **kwargs)
        finally:
            if tracking:
                ended = time.perf_counter_ns()
                state = getattr(self, "_fh6_perf_populate_timeline", {})
                tail_ms = max(0.0, (ended - int(state.get("cursor_ns", ended))) / 1_000_000.0)
                previous = str(state.get("previous", "start") or "start")
                state.get("gaps", []).append((f"{previous}_to_end", tail_ms))
                gap_total = 0.0
                for label, elapsed_ms in state.get("gaps", []):
                    gap_total += elapsed_ms
                    _metrics.record_startup(f"startup.populate.gap.{label}", elapsed_ms)
                _metrics.record_startup(
                    "startup.populate.child_nonoverlap_sum",
                    float(state.get("child_nonoverlap_ms", 0.0) or 0.0),
                )
                _metrics.record_startup("startup.populate.gap_total", gap_total)
                self._fh6_perf_populate_timeline = None
            _schedule_startup_ready(self)

    MainWindow._populate_all = populate_all

    for attr, runtime_name, startup_name in (
        ("_populate_car_table", "ui.populate.car_table", "startup.populate.car_table"),
        ("_populate_creator_table", "ui.populate.creator_table", "startup.populate.creator_table"),
        ("_populate_livery_table", "ui.populate.livery", "startup.populate.livery"),
        ("_populate_tuning_table", "ui.populate.tuning", "startup.populate.tuning"),
        ("_refresh_db_status", "ui.populate.db_status", "startup.populate.db_status"),
    ):
        fn = getattr(MainWindow, attr, None)
        if callable(fn):
            setattr(MainWindow, attr, _timed(runtime_name, fn, startup_name=startup_name))

    _install_relayout_internal_probes(MainWindow)
    _wrap_relayout(MainWindow)

    if hasattr(MainWindow, "_refresh_visible_livery_thumbnails"):
        MainWindow._refresh_visible_livery_thumbnails = _timed(
            "ui.thumbnail_refresh",
            MainWindow._refresh_visible_livery_thumbnails,
            item_count=lambda self, *a, **k: len(getattr(self, "_livery_grid_cards", []) or []),
            startup_name="startup.thumbnail_refresh",
        )

    _install_backup_probes(MainWindow)
    _backup_ui.export_records = _timed(
        "backup.export_total",
        _backup_ui.export_records,
        item_count=lambda root, records: len(records) if hasattr(records, "__len__") else None,
    )
    _import.import_backup_entry = _timed("backup.import_total", _import.import_backup_entry, item_count=lambda *a, **k: 1)
    _import.content_sha256 = _timed("backup.sha256", _import.content_sha256, item_count=lambda *a, **k: 1)
    _import.folder_fingerprint = _timed("backup.folder_fingerprint", _import.folder_fingerprint, item_count=lambda *a, **k: 1)
    _import.save_index = _timed("backup.index_write", _import.save_index)


def apply_v1_3_4_performance_probe_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_performance_probe_patched", False):
        return
    _install_probes(MainWindow)
    original_init = MainWindow.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        self._fh6_startup_finish_scheduled = False
        self._fh6_perf_livery_relayout_depth = 0
        self._fh6_perf_livery_relayout_phases = {}
        _install_navigation(self)

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v134_performance_probe_patched = True
