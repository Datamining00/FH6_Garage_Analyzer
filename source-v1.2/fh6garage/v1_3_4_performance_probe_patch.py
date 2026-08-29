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
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_export_performance_ui_patch as _perf
from . import v1_3_4_backup_import_refinement_patch as _import
from .i18n import get_language


_SETTING_KEY = "performance_profiling_enabled"


def _txt(ko: str, en: str) -> str:
    return ko if (get_language() or "ko").lower().startswith("ko") else en


def _count_items(counter: Callable[..., int | None] | None, args: tuple[Any, ...], kwargs: dict[str, Any]) -> int | None:
    if counter is None:
        return None
    try:
        return counter(*args, **kwargs)
    except Exception:
        return None


def _timed(
    name: str,
    fn: Callable[..., Any],
    *,
    item_count: Callable[..., int | None] | None = None,
    startup_name: str | None = None,
):
    """Measure a runtime path and optionally mirror it into always-on startup data."""
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any):
        runtime = _metrics.is_enabled()
        startup = bool(startup_name and _metrics.startup_active())
        if not runtime and not startup:
            return fn(*args, **kwargs)
        count = _count_items(item_count, args, kwargs)
        started = time.perf_counter_ns()
        try:
            return fn(*args, **kwargs)
        finally:
            elapsed = (time.perf_counter_ns() - started) / 1_000_000.0
            if startup and startup_name:
                _metrics.record_startup(startup_name, elapsed, item_count=count)
            if runtime:
                _metrics.record(name, elapsed, item_count=count)
    return wrapped


def _refresh_text(window: Any) -> None:
    edit = getattr(window, "performance_log_view", None)
    if not isinstance(edit, QPlainTextEdit):
        return
    edit.setPlainText(_metrics.format_recent(150) or _txt("측정 기록 없음", "No measurements yet"))
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
    QApplication.clipboard().setText(_metrics.format_recent(300))
    window._show_status(_txt("성능 측정 결과를 복사했습니다.", "Performance results copied."), 3000)


def _open_log_folder(window: Any) -> None:
    path = _metrics.log_dir()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _performance_page(window: Any) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    title = QLabel(_txt("성능 측정", "Performance profiling"))
    title.setObjectName("pageTitle")
    layout.addWidget(title)

    subtitle = QLabel(
        _txt(
            "초기 실행은 매번 자동 측정하며, ON/OFF는 실행 후 런타임 측정에만 적용됩니다.",
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

    info = QLabel(
        _txt(
            "항상 측정: 전체 시작, QApplication, 설정, 패치 설치, MainWindow, 스캔, 초기 populate, 최초 화면 준비. "
            "런타임 측정: 리버리 relayout 세부 구간, 썸네일, 백업 인덱스/목록, 내보내기/들여오기, SHA-256, fingerprint, index 저장.",
            "Always measured: total startup, QApplication, settings, patch install, MainWindow, scan, initial populate and first ready state. "
            "Runtime: livery relayout phases, thumbnails, backup index/list work, export/import, SHA-256, fingerprint and index writes.",
        )
    )
    info.setObjectName("muted")
    info.setWordWrap(True)
    layout.addWidget(info)

    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    view.setPlaceholderText(_txt("측정 기록 없음", "No measurements yet"))
    layout.addWidget(view, 1)

    window.performance_toggle_button = toggle
    window.performance_status_label = status
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

    # Two event-loop turns let the final thread-affinity layer queue SoulBound
    # append/layout work before the startup-ready timestamp is closed.
    QTimer.singleShot(0, lambda: QTimer.singleShot(0, second_turn))


def _install_probes(MainWindow: Any) -> None:
    # scan_save is called inside the existing @Slot worker; wrapping the function
    # preserves the Qt slot/thread-affinity contract while measuring the real scan.
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
        try:
            return timed_populate(self, *args, **kwargs)
        finally:
            _schedule_startup_ready(self)

    MainWindow._populate_all = populate_all

    # Populate-all children expose where the initial ~seconds are actually spent.
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

    MainWindow._relayout_livery_grid = _timed(
        "ui.livery_relayout.total",
        MainWindow._relayout_livery_grid,
        item_count=lambda self, *a, **k: len(getattr(self, "_livery_grid_cards", []) or []),
        startup_name="startup.livery_relayout.total",
    )
    if hasattr(MainWindow, "_clear_livery_grid_layout"):
        MainWindow._clear_livery_grid_layout = _timed(
            "ui.livery_relayout.clear_layout",
            MainWindow._clear_livery_grid_layout,
            startup_name="startup.livery_relayout.clear_layout",
        )
    if hasattr(MainWindow, "_layout_visible_grid_cards"):
        MainWindow._layout_visible_grid_cards = _timed(
            "ui.livery_relayout.add_widgets",
            MainWindow._layout_visible_grid_cards,
            item_count=lambda self, content_type, cards, *a, **k: len(cards) if content_type == "livery" else None,
            startup_name="startup.livery_relayout.add_widgets",
        )
    if hasattr(MainWindow, "_sync_livery_grid_card_widths"):
        MainWindow._sync_livery_grid_card_widths = _timed(
            "ui.livery_relayout.width_sync",
            MainWindow._sync_livery_grid_card_widths,
            item_count=lambda self, *a, **k: len(getattr(self, "_livery_grid_cards", []) or []),
            startup_name="startup.livery_relayout.width_sync",
        )
    if hasattr(MainWindow, "_refresh_visible_livery_thumbnails"):
        MainWindow._refresh_visible_livery_thumbnails = _timed(
            "ui.thumbnail_refresh",
            MainWindow._refresh_visible_livery_thumbnails,
            item_count=lambda self, *a, **k: len(getattr(self, "_livery_grid_cards", []) or []),
            startup_name="startup.thumbnail_refresh",
        )

    _perf._presence_snapshot = _timed("backup.presence_snapshot", _perf._presence_snapshot)
    _import._backup_items = _timed("backup.build_items", _import._backup_items)
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
        _install_navigation(self)

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v134_performance_probe_patched = True
