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

        # QFileSystemWatcher can emit duplicate directory/file notifications for
        # one atomic index replacement, and re-adding a Windows file watch may
        # produce another notification. Once the repository signature already
        # matches the successfully committed cache there is nothing to reload.
        if _same_signature_as_cache(window, signature):
            _watch._configure_watcher(window)
            _metrics.record(
                "backup.lazy.external_duplicate_ignored",
                0.0,
                item_count=1,
                detail="signature_matches_cache=1",
            )
            return

        # Suppress an identical repeated notification while a refresh is already
        # pending/running. A genuinely new signature still passes through.
        timer = getattr(window, "_fh6_backup_external_change_timer", None)
        pending = bool(timer is not None and hasattr(timer, "isActive") and timer.isActive())
        running = bool(getattr(window, "_fh6_backup_load_running", False))
        if signature is not None and signature == previous_event_signature and (pending or running):
            _watch._configure_watcher(window)
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
        watcher = getattr(self, "_fh6_backup_fs_watcher", None)
        if isinstance(watcher, QFileSystemWatcher):
            _watch._configure_watcher(self)

    _watch._external_changed = stable_external_changed
    _lazy._commit_cards = commit_cards
    MainWindow.__init__ = patched_init
    MainWindow._fh6_v14_backup_watch_stability_patched = True
