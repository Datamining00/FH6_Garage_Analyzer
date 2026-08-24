from __future__ import annotations

import functools
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QToolBar

from .performance import RECORDER


def _timed_call(
    name: str,
    function: Callable[..., Any],
    *args: Any,
    details: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    started = time.perf_counter()
    try:
        return function(*args, **kwargs)
    finally:
        RECORDER.record(name, time.perf_counter() - started, details=details)


def _wrap_method(
    cls: type,
    method_name: str,
    event_name: str,
    details_factory: Callable[..., dict[str, Any]] | None = None,
) -> None:
    original = getattr(cls, method_name, None)
    if not callable(original):
        return

    @functools.wraps(original)
    def wrapped(self, *args, **kwargs):
        details: dict[str, Any] = {}
        if details_factory is not None:
            try:
                details = details_factory(self, *args, **kwargs)
            except Exception:
                details = {}
        return _timed_call(
            event_name,
            original,
            self,
            *args,
            details=details,
            **kwargs,
        )

    setattr(cls, method_name, wrapped)


def _install_core_instrumentation() -> None:
    """Instrument file parsing without changing scanner behavior."""
    from . import scanner as scanner_module
    from . import ui as ui_module

    if getattr(scanner_module, "_fh6_performance_instrumented", False):
        return

    original_hash = scanner_module._file_sha256

    @functools.wraps(original_hash)
    def timed_hash(path: Path) -> str:
        size = 0
        try:
            size = path.stat().st_size
        except OSError:
            pass
        return _timed_call(
            "scan.livery_sha256",
            original_hash,
            path,
            details={
                "container": path.parent.name,
                "file": path.name,
                "bytes": size,
            },
        )

    scanner_module._file_sha256 = timed_hash

    original_header = scanner_module.read_header_file

    @functools.wraps(original_header)
    def timed_header(path: Path, *args, **kwargs):
        kind = args[0] if args else kwargs.get("kind")
        return _timed_call(
            "scan.header_parse",
            original_header,
            path,
            *args,
            details={"container": path.parent.name, "kind": kind or ""},
            **kwargs,
        )

    scanner_module.read_header_file = timed_header

    original_metadata = scanner_module.parse_save_metadata

    @functools.wraps(original_metadata)
    def timed_metadata(*args, **kwargs):
        return _timed_call(
            "scan.save_metadata",
            original_metadata,
            *args,
            details={},
            **kwargs,
        )

    scanner_module.parse_save_metadata = timed_metadata

    original_resolve_layout = scanner_module.resolve_layout

    @functools.wraps(original_resolve_layout)
    def timed_resolve_layout(*args, **kwargs):
        return _timed_call(
            "scan.resolve_layout",
            original_resolve_layout,
            *args,
            details={},
            **kwargs,
        )

    scanner_module.resolve_layout = timed_resolve_layout

    original_scan_save = scanner_module.scan_save

    @functools.wraps(original_scan_save)
    def timed_scan_save(*args, **kwargs):
        started = time.perf_counter()
        result = None
        try:
            result = original_scan_save(*args, **kwargs)
            return result
        finally:
            details: dict[str, Any] = {}
            if result is not None:
                details = {
                    "liveries": len(result.liveries),
                    "tunings": len(result.tunings),
                    "cars": len(result.car_summaries),
                    "warnings": len(result.warnings),
                }
            RECORDER.record(
                "scan.save",
                time.perf_counter() - started,
                details=details,
            )

    scanner_module.scan_save = timed_scan_save
    # ui.py imported scan_save directly. Replace that bound module global as well
    # so ScanWorker continues to call the exact same scanner through this wrapper.
    ui_module.scan_save = timed_scan_save
    scanner_module._fh6_performance_instrumented = True


def _install_v132_instrumentation() -> None:
    """Measure auction-cache matching used by the final thread-affinity patch."""
    from . import v1_3_2_thread_affinity_patch as thread_patch

    if getattr(thread_patch, "_fh6_performance_instrumented", False):
        return
    original = thread_patch.assign_auction_thumbnails

    @functools.wraps(original)
    def timed_assign(records, cache_dir):
        record_list = list(records)
        return _timed_call(
            "v132.auction_thumbnail_assign",
            original,
            record_list,
            cache_dir,
            details={
                "records": len(record_list),
                "cache_enabled": cache_dir is not None,
            },
        )

    thread_patch.assign_auction_thumbnails = timed_assign
    thread_patch._fh6_performance_instrumented = True


def _install_mainwindow_instrumentation(MainWindow: type) -> None:
    if getattr(MainWindow, "_fh6_performance_patched", False):
        return

    original_init = MainWindow.__init__

    @functools.wraps(original_init)
    def timed_init(self, *args, **kwargs):
        started = time.perf_counter()
        original_init(self, *args, **kwargs)
        RECORDER.record(
            "startup.main_window_construct",
            time.perf_counter() - started,
            details={},
        )

        toolbar = QToolBar("Performance diagnostics", self)
        toolbar.setObjectName("performanceDiagnosticsToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        badge = QLabel("PERF")
        badge.setStyleSheet(
            "QLabel { background:#fff1c7; color:#6b4a00; border:1px solid #e7c75e; "
            "border-radius:5px; padding:4px 8px; font-weight:700; }"
        )
        toolbar.addWidget(badge)
        toolbar.addSeparator()

        reset_button = QPushButton("성능 기록 초기화")
        reset_button.setObjectName("secondary")
        report_button = QPushButton("성능 리포트 저장")
        report_button.setObjectName("secondary")
        toolbar.addWidget(reset_button)
        toolbar.addWidget(report_button)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        def reset_performance() -> None:
            RECORDER.reset()
            self._fh6_perf_scan_started_at = None
            self._show_status("성능 기록을 초기화했습니다.", 2500)

        def save_performance() -> None:
            try:
                txt_path, json_path = RECORDER.save_report()
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "성능 리포트 저장 실패",
                    f"{type(exc).__name__}: {exc}",
                )
                return
            QMessageBox.information(
                self,
                "성능 리포트 저장 완료",
                "성능 측정 결과를 저장했습니다.\n\n"
                f"TXT: {txt_path}\n"
                f"JSON: {json_path}",
            )

        reset_button.clicked.connect(reset_performance)
        report_button.clicked.connect(save_performance)
        self._fh6_performance_toolbar = toolbar
        self._fh6_perf_scan_started_at = None

    MainWindow.__init__ = timed_init

    original_start_scan = MainWindow.start_scan

    @functools.wraps(original_start_scan)
    def timed_start_scan(self, path: Path) -> None:
        running = bool(self._scan_thread and self._scan_thread.isRunning())
        if not running:
            self._fh6_perf_scan_started_at = time.perf_counter()
        original_start_scan(self, path)

    MainWindow.start_scan = timed_start_scan

    original_populate_all = MainWindow._populate_all

    @functools.wraps(original_populate_all)
    def timed_populate_all(self) -> None:
        started = time.perf_counter()
        try:
            original_populate_all(self)
        finally:
            RECORDER.record(
                "ui.populate_all_base",
                time.perf_counter() - started,
                details={
                    "liveries": len(self.result.liveries) if self.result else 0,
                    "tunings": len(self.result.tunings) if self.result else 0,
                },
            )
            action_started = getattr(self, "_fh6_perf_scan_started_at", None)
            if isinstance(action_started, (int, float)):
                RECORDER.record(
                    "action.scan_to_main_ui",
                    time.perf_counter() - action_started,
                    details={
                        "liveries": len(self.result.liveries) if self.result else 0,
                        "tunings": len(self.result.tunings) if self.result else 0,
                    },
                )
                self._fh6_perf_scan_started_at = None

    MainWindow._populate_all = timed_populate_all

    _wrap_method(MainWindow, "_populate_car_table", "ui.dashboard_vehicle_table")
    _wrap_method(MainWindow, "_populate_creator_table", "ui.dashboard_creator_table")
    _wrap_method(
        MainWindow,
        "_populate_saved_content_table",
        "ui.saved_content_table",
        lambda _self, content_type, *_a, **_k: {"type": content_type},
    )
    _wrap_method(MainWindow, "_populate_livery_table", "ui.livery_rebuild")
    _wrap_method(MainWindow, "_populate_tuning_table", "ui.tuning_rebuild")
    _wrap_method(MainWindow, "_populate_livery_grid", "ui.livery_grid_build")
    _wrap_method(MainWindow, "_populate_tuning_grid", "ui.tuning_grid_build")
    _wrap_method(
        MainWindow,
        "_make_livery_card",
        "ui.livery_card_create",
        lambda _self, record, *_a, **_k: {
            "kind": getattr(record, "kind", ""),
            "container": getattr(record, "container_name", ""),
        },
    )
    _wrap_method(
        MainWindow,
        "_make_tuning_card",
        "ui.tuning_card_create",
        lambda _self, record, *_a, **_k: {
            "container": getattr(record, "container_name", ""),
        },
    )
    _wrap_method(
        MainWindow,
        "_relayout_livery_grid",
        "ui.livery_grid_layout",
        lambda self, *_a, **_k: {"cards": len(self._livery_grid_cards)},
    )
    _wrap_method(
        MainWindow,
        "_relayout_tuning_grid",
        "ui.tuning_grid_layout",
        lambda self, *_a, **_k: {"cards": len(self._tuning_grid_cards)},
    )
    _wrap_method(
        MainWindow,
        "_filter_saved_content_views",
        "action.saved_content_filter",
        lambda _self, content_type, text="", *_a, **_k: {
            "type": content_type,
            "query_length": len(text or ""),
        },
    )
    _wrap_method(
        MainWindow,
        "_set_saved_content_sort_mode",
        "action.saved_content_sort",
        lambda _self, content_type, mode, *_a, **_k: {
            "type": content_type,
            "mode": mode,
        },
    )
    _wrap_method(
        MainWindow,
        "_set_vehicle_grouping",
        "action.group_by_vehicle",
        lambda _self, content_type, enabled, *_a, **_k: {
            "type": content_type,
            "enabled": bool(enabled),
        },
    )
    _wrap_method(
        MainWindow,
        "_set_creator_grouping",
        "action.group_by_creator",
        lambda _self, content_type, enabled, *_a, **_k: {
            "type": content_type,
            "enabled": bool(enabled),
        },
    )
    _wrap_method(MainWindow, "_sort_car_dashboard", "action.dashboard_vehicle_sort")
    _wrap_method(MainWindow, "_sort_creator_dashboard", "action.dashboard_creator_sort")
    _wrap_method(MainWindow, "_set_dashboard_content_mode", "action.dashboard_mode_switch")
    _wrap_method(MainWindow, "_update_selected_car", "action.dashboard_vehicle_select")
    _wrap_method(MainWindow, "_update_selected_creator", "action.dashboard_creator_select")
    _wrap_method(MainWindow, "_on_main_page_changed", "action.main_page_change")
    _wrap_method(MainWindow, "_prime_livery_grid_thumbnails", "ui.livery_thumbnail_prime")
    _wrap_method(MainWindow, "_prime_tuning_grid_thumbnails", "ui.tuning_thumbnail_prime")
    _wrap_method(
        MainWindow,
        "_refresh_visible_livery_thumbnails",
        "ui.livery_thumbnail_refresh",
        lambda self, *_a, **_k: {"cards": len(self._livery_grid_cards)},
    )
    _wrap_method(
        MainWindow,
        "_refresh_visible_tuning_thumbnails",
        "ui.tuning_thumbnail_refresh",
        lambda self, *_a, **_k: {"cards": len(self._tuning_grid_cards)},
    )

    original_load_thumbnail = MainWindow._load_livery_card_thumbnail

    @functools.wraps(original_load_thumbnail)
    def timed_load_thumbnail(self, card) -> None:
        if getattr(card, "_fh6_thumbnail_loaded", False):
            return original_load_thumbnail(self, card)
        path = getattr(card, "_fh6_thumbnail_path", None)
        started = time.perf_counter()
        try:
            return original_load_thumbnail(self, card)
        finally:
            RECORDER.record(
                "ui.thumbnail_decode",
                time.perf_counter() - started,
                details={"file": path.name if isinstance(path, Path) else ""},
            )

    MainWindow._load_livery_card_thumbnail = timed_load_thumbnail

    _wrap_method(
        MainWindow,
        "_handle_saved_content_check_clicked",
        "action.annotation_check",
        lambda _self, content_type, *_a, **_k: {"type": content_type},
    )
    _wrap_method(
        MainWindow,
        "_handle_saved_content_triangle_clicked",
        "action.annotation_triangle",
        lambda _self, content_type, *_a, **_k: {"type": content_type},
    )
    _wrap_method(
        MainWindow,
        "_handle_saved_content_excluded_clicked",
        "action.annotation_excluded",
        lambda _self, content_type, *_a, **_k: {"type": content_type},
    )

    MainWindow._fh6_performance_patched = True
    MainWindow._fh6_performance_recorder = RECORDER


def apply_v1_3_2_performance_patches(MainWindow: type) -> None:
    """Install diagnostic timing without replacing the Qt scan-completion slot.

    This patch must be applied after the normal v1.3.2 UI patches and before
    apply_v1_3_2_thread_affinity_fix(). The final thread-affinity patch remains
    responsible for restoring the original @Slot(object) _scan_finished method.
    """
    _install_core_instrumentation()
    _install_v132_instrumentation()
    _install_mainwindow_instrumentation(MainWindow)
