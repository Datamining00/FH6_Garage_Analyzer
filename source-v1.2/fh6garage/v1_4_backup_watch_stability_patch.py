from __future__ import annotations

from typing import Any

from PySide6.QtCore import QFileSystemWatcher

from . import performance_metrics as _metrics
from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_lazy_load_patch as _lazy
from . import v1_3_4_backup_lazy_watch_patch as _watch


def _current_signature(window: Any):
    try:
        return _lazy._repository_signature(_backup_ui._backup_root(window))
    except (OSError, RuntimeError):
        return None


def _same_signature_as_cache(window: Any, signature: Any) -> bool:
    if signature is None:
        return False
    cached = getattr(window, "_fh6_backup_cache_signature", None)
    return cached is not None and signature == cached


def _watcher_matches_desired(window: Any) -> bool:
    watcher = getattr(window, "_fh6_backup_fs_watcher", None)
    if not isinstance(watcher, QFileSystemWatcher):
        return False
    try:
        current = set(watcher.files()) | set(watcher.directories())
        desired = set(_watch._watch_paths(window))
    except RuntimeError:
        return False
    return current == desired


def _ensure_watcher_current(window: Any) -> None:
    # Avoid remove/add churn on Windows. Reconfiguring an already-correct
    # QFileSystemWatcher from inside its own change signal can itself cause
    # additional directory/file notifications on some systems.
    if not _watcher_matches_desired(window):
        _watch._configure_watcher(window)


def apply_v1_4_backup_watch_stability_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_backup_watch_stability_patched", False):
        return

    original_init = MainWindow.__init__
    original_external_changed = _watch._external_changed
    original_commit_cards = _lazy._commit_cards

    def stable_external_changed(window: Any, path: str) -> None:
        signature = _current_signature(window)
        previous_event_signature = getattr(window, "_fh6_backup_last_watch_event_signature", None)
        window._fh6_backup_last_watch_event_signature = signature

        if _same_signature_as_cache(window, signature):
            _ensure_watcher_current(window)
            _metrics.record(
                "backup.lazy.external_duplicate_ignored",
                0.0,
                item_count=1,
                detail="signature_matches_cache=1",
            )
            return

        timer = getattr(window, "_fh6_backup_external_change_timer", None)
        pending = bool(timer is not None and hasattr(timer, "isActive") and timer.isActive())
        running = bool(getattr(window, "_fh6_backup_load_running", False))
        if signature is not None and signature == previous_event_signature and (pending or running):
            _ensure_watcher_current(window)
            _metrics.record(
                "backup.lazy.external_duplicate_ignored",
                0.0,
                item_count=1,
                detail=f"pending={int(pending)} running={int(running)}",
            )
            return

        original_external_changed(window, path)

    def commit_cards(window: Any, *args: Any, **kwargs: Any) -> None:
        original_commit_cards(window, *args, **kwargs)
        signature = getattr(window, "_fh6_backup_cache_signature", None)
        if signature is None:
            signature = _current_signature(window)
        window._fh6_backup_last_watch_event_signature = signature

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        self._fh6_backup_last_watch_event_signature = _current_signature(self)
        _ensure_watcher_current(self)

    _watch._external_changed = stable_external_changed
    _lazy._commit_cards = commit_cards
    MainWindow.__init__ = patched_init
    MainWindow._fh6_v14_backup_watch_stability_patched = True
