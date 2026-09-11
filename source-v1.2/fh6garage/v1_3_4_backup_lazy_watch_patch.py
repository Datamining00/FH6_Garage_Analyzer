from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QFileSystemWatcher, QTimer

from . import performance_metrics as _metrics
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_lazy_load_patch as _lazy
from .backup_export import INDEX_NAME


_EXTERNAL_CHANGE_DEBOUNCE_MS = 250


def _txt(ko: str, en: str) -> str:
    return _backup_ui._txt(ko, en)


def _watch_paths(window: Any) -> list[str]:
    root = _backup_ui._backup_root(window)
    if root is None:
        return []
    try:
        root = root.expanduser().resolve()
    except OSError:
        root = root.expanduser()
    paths = [str(root)] if root.is_dir() else []
    index = root / INDEX_NAME
    if index.is_file():
        paths.append(str(index))
    return paths


def _configure_watcher(window: Any) -> None:
    watcher = getattr(window, "_fh6_backup_fs_watcher", None)
    if not isinstance(watcher, QFileSystemWatcher):
        return
    current = list(watcher.files()) + list(watcher.directories())
    if current:
        watcher.removePaths(current)
    paths = _watch_paths(window)
    if paths:
        watcher.addPaths(paths)


def _schedule_external_refresh(window: Any) -> None:
    timer = getattr(window, "_fh6_backup_external_change_timer", None)
    if not isinstance(timer, QTimer):
        return
    timer.start(_EXTERNAL_CHANGE_DEBOUNCE_MS)


def _external_changed(window: Any, _path: str) -> None:
    # QFileSystemWatcher drops a file watch after atomic replacement on some
    # platforms. Re-add the current root/index on the next event-loop turn.
    QTimer.singleShot(0, lambda owner=window: _configure_watcher(owner))
    _lazy._mark_dirty(window, refresh_if_visible=False)
    _metrics.record("backup.lazy.external_dirty", 0.0, item_count=1)
    _schedule_external_refresh(window)


def _refresh_external_change(window: Any) -> None:
    if not getattr(window, "_fh6_backup_cache_dirty", False):
        return
    if not _lazy._backup_page_visible(window):
        return
    if getattr(window, "_fh6_backup_load_running", False):
        return
    if getattr(window, "_fh6_export_running", False) or getattr(window, "_fh6_import_running", False):
        return
    if not getattr(window, "_fh6_backup_lazy_loaded", False):
        return
    _lazy._start_full_load(
        window,
        force=True,
        message=_txt("외부 백업 변경을 반영하는 중...", "Applying external backup changes..."),
    )


def _capture_scroll(window: Any) -> None:
    scroll = getattr(window, "backup_grid_scroll", None)
    bar = scroll.verticalScrollBar() if scroll is not None else None
    window._fh6_backup_full_load_scroll = bar.value() if bar is not None else 0


def _restore_scroll(window: Any) -> None:
    scroll = getattr(window, "backup_grid_scroll", None)
    bar = scroll.verticalScrollBar() if scroll is not None else None
    value = int(getattr(window, "_fh6_backup_full_load_scroll", 0) or 0)
    if bar is not None:
        QTimer.singleShot(0, lambda target=bar, saved=value: target.setValue(min(saved, target.maximum())))


def apply_v1_3_4_backup_lazy_watch_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_lazy_watch_patched", False):
        return

    original_start_full_load = _lazy._start_full_load
    original_commit_cards = _lazy._commit_cards

    def start_full_load(window: Any, *args: Any, **kwargs: Any) -> None:
        _capture_scroll(window)
        _configure_watcher(window)
        original_start_full_load(window, *args, **kwargs)

    def commit_cards(window: Any, *args: Any, **kwargs: Any) -> None:
        original_commit_cards(window, *args, **kwargs)
        _configure_watcher(window)
        _restore_scroll(window)

    _lazy._start_full_load = start_full_load
    _lazy._commit_cards = commit_cards

    original_init = MainWindow.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        watcher = QFileSystemWatcher(self)
        watcher.fileChanged.connect(lambda path, owner=self: _external_changed(owner, path))
        watcher.directoryChanged.connect(lambda path, owner=self: _external_changed(owner, path))
        self._fh6_backup_fs_watcher = watcher

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda owner=self: _refresh_external_change(owner))
        self._fh6_backup_external_change_timer = timer

        path_edit = getattr(self, "backup_path_edit", None)
        if path_edit is not None:
            path_edit.textChanged.connect(lambda _text, owner=self: _configure_watcher(owner))
        _configure_watcher(self)

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v134_backup_lazy_watch_patched = True
