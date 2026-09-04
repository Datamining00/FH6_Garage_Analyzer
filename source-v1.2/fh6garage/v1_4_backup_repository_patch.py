from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QLineEdit, QMessageBox, QProgressDialog, QPushButton, QToolButton

from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_import_refinement_patch as _ref
from . import v1_3_4_backup_lazy_load_patch as _lazy
from .backup_export import BackupRepositoryError, ExportSummary
from .models import LiveryRecord
from .parsers import ParseError, read_header_file
from .performance_metrics import app_data_dir
from .scanner import _container_car_id


_EXTERNAL_CONTAINER_RE = re.compile(r"^(Livery|SoulBoundLivery)_", re.IGNORECASE)
_EXTERNAL_IMPORT_BATCH = 8


def _txt(ko: str, en: str) -> str:
    return _backup_ui._txt(ko, en)


def _default_backup_root() -> Path:
    return app_data_dir() / "backup"


def _ensure_default_backup_root(window: Any) -> Path:
    configured = str(window.settings.value(_backup_ui._BACKUP_PATH_KEY, "", str) or "").strip()
    edit = getattr(window, "backup_path_edit", None)
    if configured:
        path = Path(configured).expanduser()
        if isinstance(edit, QLineEdit) and not edit.text().strip():
            edit.setText(str(path))
        return path

    root = _default_backup_root()
    root.mkdir(parents=True, exist_ok=True)
    if isinstance(edit, QLineEdit):
        edit.setText(str(root))
    return root


def _backup_root_with_default(window: Any) -> Path | None:
    raw = ""
    edit = getattr(window, "backup_path_edit", None)
    if isinstance(edit, QLineEdit):
        raw = edit.text().strip()
    if not raw:
        raw = str(window.settings.value(_backup_ui._BACKUP_PATH_KEY, "", str) or "").strip()
    if not raw:
        try:
            raw = str(_ensure_default_backup_root(window))
        except OSError:
            return None
    path = Path(raw).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return path if path.is_dir() else None


def _record_identity(record: Any) -> tuple[str, str, str]:
    kind = str(getattr(record, "kind", "") or "").strip().casefold()
    digest = str(getattr(record, "content_sha256", "") or "").strip().casefold()
    container = str(getattr(record, "container_name", "") or "").strip().casefold()
    return kind, digest, container


def _backup_card_locked(window: Any, card: Any) -> bool:
    if bool(card.property("fh6MoveLocked")):
        return True
    record = card.property("backupRecord")
    if not isinstance(record, LiveryRecord):
        return False
    wanted_kind, wanted_digest, wanted_container = _record_identity(record)
    resolver = getattr(window, "_record_for_content_key", None)
    if not callable(resolver):
        return False
    for source_card in getattr(window, "_livery_grid_cards", []) or []:
        if not bool(source_card.property("fh6MoveLocked")):
            continue
        key = str(source_card.property("annotationKey") or "")
        source_record = resolver("livery", key) if key else None
        if not isinstance(source_record, LiveryRecord):
            continue
        kind, digest, container = _record_identity(source_record)
        if kind != wanted_kind:
            continue
        if wanted_digest and digest and wanted_digest == digest:
            return True
        if wanted_container and wanted_container == container:
            return True
    return False


def _install_locked_filter(window: Any) -> None:
    if isinstance(getattr(window, "backup_locked_filter_action", None), QAction):
        return
    button = getattr(window, "backup_filter_button", None)
    menu = button.menu() if isinstance(button, QToolButton) else None
    if menu is None:
        return
    action = QAction(_txt("잠금된 리버리", "Locked liveries"), menu)
    action.setCheckable(True)
    action.setChecked(False)
    menu.addSeparator()
    menu.addAction(action)
    window.backup_locked_filter_action = action

    def changed(_checked: bool = False, owner: Any = window) -> None:
        if getattr(owner, "_fh6_backup_load_running", False):
            return
        runner = getattr(_lazy, "_run_cached_layout", None)
        if callable(runner):
            runner(
                owner,
                _txt("백업 목록을 업데이트하는 중...", "Updating backup list..."),
                lambda: _backup_ui._relayout_backup(owner),
            )
        else:
            _backup_ui._relayout_backup(owner)

    action.toggled.connect(changed)


def _locked_filter_allows(original: Any, window: Any, card: Any) -> bool:
    if not original(window, card):
        return False
    action = getattr(window, "backup_locked_filter_action", None)
    if isinstance(action, QAction) and action.isChecked():
        return _backup_card_locked(window, card)
    return True


class ExternalImportCancelled(RuntimeError):
    pass


class _ExternalImportToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def check(self) -> None:
        if self._event.is_set():
            raise ExternalImportCancelled("external import cancelled")


@dataclass(slots=True)
class _ExternalImportSummary:
    discovered: int = 0
    unsupported: int = 0
    malformed: int = 0
    exported: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    cancelled: bool = False


def _thumbnail(container: Path) -> Path | None:
    for name in ("bigThumb.webp", "BigThumb.webp"):
        candidate = container / name
        if candidate.is_file():
            return candidate
    return None


def _external_record(container: Path) -> LiveryRecord:
    match = _EXTERNAL_CONTAINER_RE.match(container.name)
    if match is None:
        raise ValueError("unsupported container name")
    kind = "SoulBoundLivery" if match.group(1).casefold() == "soulboundlivery" else "Livery"
    header_path = container / "header"
    payload = container / "C_livery"
    if not header_path.is_file() or not payload.is_file():
        raise ValueError("header or C_livery is missing")
    header = read_header_file(header_path, kind)
    ordinal = _container_car_id(container.name, kind)
    if ordinal is not None:
        header.car_id = ordinal
    try:
        stat = payload.stat()
        downloaded_at = float(getattr(stat, "st_birthtime", stat.st_ctime))
    except OSError:
        downloaded_at = None
    return LiveryRecord(
        container_name=container.name,
        container_path=container,
        kind=kind,
        header=header,
        thumbnail_path=_thumbnail(container),
        livery_path=payload,
        downloaded_at=downloaded_at,
        content_sha256="",
    )


def _discover_external_records(source: Path, token: _ExternalImportToken) -> tuple[list[LiveryRecord], int, int]:
    records: list[LiveryRecord] = []
    unsupported = 0
    malformed = 0
    source = source.expanduser().resolve()
    for root_text, dirs, _files in os.walk(source):
        token.check()
        root = Path(root_text)
        name = root.name
        if name in {".staging", ".fh6_assistant_import_staging", ".fh6_assistant_delete_staging"}:
            dirs[:] = []
            continue
        match = _EXTERNAL_CONTAINER_RE.match(name)
        if match is not None:
            dirs[:] = []
            try:
                records.append(_external_record(root))
            except (OSError, ParseError, ValueError):
                malformed += 1
            continue
        lowered = name.casefold()
        if lowered.startswith(("baselivery_", "tuning_")):
            dirs[:] = []
            unsupported += 1
    return records, unsupported, malformed


class _ExternalImportWorker(QObject):
    def __init__(self, source: Path, destination: Path, token: _ExternalImportToken, bridge: Any) -> None:
        super().__init__()
        self.source = source
        self.destination = destination
        self.token = token
        self.bridge = bridge

    @Slot()
    def run(self) -> None:
        summary = _ExternalImportSummary()
        try:
            records, summary.unsupported, summary.malformed = _discover_external_records(self.source, self.token)
            summary.discovered = len(records)
            for start in range(0, len(records), _EXTERNAL_IMPORT_BATCH):
                self.token.check()
                batch = records[start:start + _EXTERNAL_IMPORT_BATCH]
                result: ExportSummary = _ref._safe_export_records(self.destination, batch)
                summary.exported.extend(result.exported)
                summary.skipped.extend(result.skipped)
                summary.failed.extend(result.failed)
        except ExternalImportCancelled:
            summary.cancelled = True
            self.bridge.enqueue_finished(summary)
            return
        except Exception as exc:  # noqa: BLE001 - worker boundary
            self.bridge.enqueue_failed(f"{type(exc).__name__}: {exc}")
            return
        self.bridge.enqueue_finished(summary)


class _ExternalImportBridge(QObject):
    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window = window
        self._lock = threading.Lock()
        self._result: _ExternalImportSummary | None = None
        self._error = ""

    def enqueue_finished(self, result: _ExternalImportSummary) -> None:
        with self._lock:
            self._result = result
        QMetaObject.invokeMethod(self, "deliver_finished", Qt.ConnectionType.QueuedConnection)

    def enqueue_failed(self, message: str) -> None:
        with self._lock:
            self._error = message
        QMetaObject.invokeMethod(self, "deliver_failed", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def deliver_finished(self) -> None:
        with self._lock:
            result = self._result
            self._result = None
        if result is not None:
            _external_import_finished(self.window, result)
        _request_external_thread_quit(self.window)

    @Slot()
    def deliver_failed(self) -> None:
        with self._lock:
            message = self._error
            self._error = ""
        _external_import_failed(self.window, message)
        _request_external_thread_quit(self.window)

    @Slot()
    def thread_finished(self) -> None:
        self.window._fh6_external_import_thread = None
        self.window._fh6_external_import_worker = None
        self.window._fh6_external_import_bridge = None


def _request_external_thread_quit(window: Any) -> None:
    thread = getattr(window, "_fh6_external_import_thread", None)
    if isinstance(thread, QThread) and thread.isRunning():
        thread.quit()


def _external_import_controls(window: Any, enabled: bool) -> None:
    for name in ("backup_external_import_button", "backup_choose_button", "backup_refresh_button"):
        control = getattr(window, name, None)
        if isinstance(control, QPushButton):
            control.setEnabled(enabled)


def _close_external_dialog(window: Any) -> None:
    dialog = getattr(window, "_fh6_external_import_dialog", None)
    if isinstance(dialog, QProgressDialog):
        dialog.close()
        dialog.deleteLater()
    window._fh6_external_import_dialog = None


def _external_import_finished(window: Any, summary: _ExternalImportSummary) -> None:
    _close_external_dialog(window)
    _external_import_controls(window, True)
    window._fh6_external_import_running = False
    window._fh6_backup_cache_dirty = True
    if summary.exported:
        _lazy._start_full_load(
            window,
            force=True,
            message=_txt("가져온 백업을 반영하는 중...", "Applying imported backups..."),
        )
    message = _txt(
        f"외부 가져오기 {'취소됨' if summary.cancelled else '완료'} · 신규 {len(summary.exported)} · "
        f"중복 {len(summary.skipped)} · 지원하지 않음 {summary.unsupported} · "
        f"해석 실패 {summary.malformed} · 저장 실패 {len(summary.failed)}",
        f"External import {'cancelled' if summary.cancelled else 'complete'} · new {len(summary.exported)} · "
        f"duplicates {len(summary.skipped)} · unsupported {summary.unsupported} · "
        f"parse failures {summary.malformed} · save failures {len(summary.failed)}",
    )
    window._show_status(message, 10000)
    if summary.failed:
        details = "\n".join(f"{name}: {error}" for name, error in summary.failed[:8])
        QMessageBox.warning(window, _txt("외부에서 가져오기", "Import external folder"), message + "\n\n" + details)
    else:
        QMessageBox.information(window, _txt("외부에서 가져오기", "Import external folder"), message)


def _external_import_failed(window: Any, message: str) -> None:
    _close_external_dialog(window)
    _external_import_controls(window, True)
    window._fh6_external_import_running = False
    QMessageBox.warning(window, _txt("외부 가져오기 실패", "External import failed"), message)


def _request_external_import(window: Any) -> None:
    if getattr(window, "_fh6_external_import_running", False):
        return
    destination = _backup_root_with_default(window)
    if destination is None:
        QMessageBox.warning(
            window,
            _txt("백업 경로 오류", "Backup path error"),
            _txt("백업 저장 경로를 준비할 수 없습니다.", "The backup repository cannot be prepared."),
        )
        return
    chosen = QFileDialog.getExistingDirectory(
        window,
        _txt("외부 FH6 폴더 선택", "Choose external FH6 folder"),
        str(Path.home()),
    )
    if not chosen:
        return
    source = Path(chosen).expanduser().resolve()
    if _backup_ui._paths_overlap(source, destination):
        QMessageBox.warning(
            window,
            _txt("외부 폴더 오류", "Invalid external folder"),
            _txt(
                "현재 백업 저장소 자체 또는 그 상·하위 폴더는 외부 가져오기 원본으로 사용할 수 없습니다.",
                "The current backup repository, its parent, or its child cannot be used as the external source.",
            ),
        )
        return

    token = _ExternalImportToken()
    dialog = QProgressDialog(
        _txt("외부 백업 폴더를 분석하고 정리하는 중...", "Analyzing and organizing external backup folder..."),
        _txt("취소", "Cancel"),
        0,
        0,
        window,
    )
    dialog.setWindowTitle(_txt("외부에서 가져오기", "Import external folder"))
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.canceled.connect(token.cancel)
    dialog.show()

    bridge = _ExternalImportBridge(window)
    thread = QThread(window)
    worker = _ExternalImportWorker(source, destination, token, bridge)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(bridge.thread_finished)
    thread.finished.connect(thread.deleteLater)

    window._fh6_external_import_running = True
    window._fh6_external_import_token = token
    window._fh6_external_import_dialog = dialog
    window._fh6_external_import_thread = thread
    window._fh6_external_import_worker = worker
    window._fh6_external_import_bridge = bridge
    _external_import_controls(window, False)
    thread.start()


def _install_external_import_button(window: Any) -> None:
    if isinstance(getattr(window, "backup_external_import_button", None), QPushButton):
        return
    choose = getattr(window, "backup_choose_button", None)
    refresh = getattr(window, "backup_refresh_button", None)
    page = getattr(window, "backup_page", None)
    root_layout = page.layout() if page is not None else None
    if not isinstance(choose, QPushButton) or root_layout is None:
        return
    row = _ref._layout_with_widget(root_layout, choose)
    if row is None:
        return
    button = QPushButton(_txt("외부에서 가져오기", "Import external folder"))
    button.setObjectName("secondary")
    button.setToolTip(
        _txt(
            "다른 위치에 보관한 Livery/SoulBoundLivery 폴더를 찾아 현재 백업 저장소 형식으로 정리합니다.",
            "Find stored Livery/SoulBoundLivery folders and organize them into the current backup repository format.",
        )
    )
    button.clicked.connect(lambda _checked=False, owner=window: _request_external_import(owner))
    if isinstance(refresh, QPushButton):
        index = row.indexOf(refresh)
        row.insertWidget(index if index >= 0 else row.count(), button)
    else:
        index = row.indexOf(choose)
        row.insertWidget(index + 1 if index >= 0 else row.count(), button)
    window.backup_external_import_button = button


def apply_v1_4_backup_repository_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_backup_repository_patched", False):
        return

    original_backup_root = _backup_ui._backup_root
    original_filter_allows = _backup_ui._backup_filter_allows
    original_ref_filter_allows = _ref._backup_filter_allows
    original_init = MainWindow.__init__

    def backup_root(window: Any) -> Path | None:
        root = _backup_root_with_default(window)
        return root if root is not None else original_backup_root(window)

    def filter_allows(window: Any, card: Any) -> bool:
        return _locked_filter_allows(original_filter_allows, window, card)

    def ref_filter_allows(window: Any, card: Any) -> bool:
        return _locked_filter_allows(original_ref_filter_allows, window, card)

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        self._fh6_external_import_running = False
        self._fh6_external_import_token = None
        self._fh6_external_import_dialog = None
        self._fh6_external_import_thread = None
        self._fh6_external_import_worker = None
        self._fh6_external_import_bridge = None
        original_init(self, *args, **kwargs)
        try:
            _ensure_default_backup_root(self)
        except OSError:
            pass
        _install_locked_filter(self)
        _install_external_import_button(self)

    _backup_ui._backup_root = backup_root
    _backup_ui._backup_filter_allows = filter_allows
    _ref._backup_filter_allows = ref_filter_allows
    MainWindow.__init__ = patched_init
    MainWindow._fh6_v14_backup_repository_patched = True
