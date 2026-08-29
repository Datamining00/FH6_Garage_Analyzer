from __future__ import annotations

from functools import wraps
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from . import performance_metrics as _metrics
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_export_performance_ui_patch as _perf
from . import v1_3_4_backup_import_refinement_patch as _import
from .i18n import get_language


_SETTING_KEY = "performance_profiling_enabled"


def _txt(ko: str, en: str) -> str:
    return ko if (get_language() or "ko").lower().startswith("ko") else en


def _timed(name: str, fn: Callable[..., Any], *, item_count: Callable[..., int | None] | None = None):
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any):
        if not _metrics.is_enabled():
            return fn(*args, **kwargs)
        count = None
        if item_count is not None:
            try:
                count = item_count(*args, **kwargs)
            except Exception:
                count = None
        with _metrics.measure(name, item_count=count):
            return fn(*args, **kwargs)
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
                "측정 중 · 최적화 진단용 로그를 기록합니다.",
                "Recording · diagnostic timing logs are being written.",
            )
            if enabled
            else _txt(
                "비활성 · 일반 사용 시 측정 오버헤드가 없습니다.",
                "Disabled · no measurement overhead during normal use.",
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
            "최적화를 위해 주요 작업의 실제 소요시간을 측정합니다. 기본값은 OFF입니다.",
            "Measures real elapsed time of major operations for optimization. Default is OFF.",
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
            "측정 항목: 화면 전체 갱신, 리버리 재배치, 썸네일 갱신, 백업 인덱스 판정, 백업 목록 생성, "
            "내보내기/들여오기, SHA-256, 폴더 fingerprint, backup_index 저장",
            "Measured: full population, livery relayout, thumbnail refresh, backup presence/index work, backup list build, "
            "export/import, SHA-256, folder fingerprint, and backup_index writes.",
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


def _install_probes(MainWindow: Any) -> None:
    MainWindow._populate_all = _timed(
        "ui.populate_all",
        MainWindow._populate_all,
        item_count=lambda self: len(getattr(getattr(self, "result", None), "liveries", []) or []),
    )
    MainWindow._relayout_livery_grid = _timed(
        "ui.livery_relayout",
        MainWindow._relayout_livery_grid,
        item_count=lambda self, *a, **k: len(getattr(self, "_livery_grid_cards", []) or []),
    )
    if hasattr(MainWindow, "_refresh_visible_livery_thumbnails"):
        MainWindow._refresh_visible_livery_thumbnails = _timed(
            "ui.thumbnail_refresh",
            MainWindow._refresh_visible_livery_thumbnails,
            item_count=lambda self, *a, **k: len(getattr(self, "_livery_grid_cards", []) or []),
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
        _install_navigation(self)

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v134_performance_probe_patched = True
