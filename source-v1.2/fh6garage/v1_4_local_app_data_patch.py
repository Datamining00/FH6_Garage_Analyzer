from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QLineEdit

from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_4_backup_repository_patch as _repository
from .performance_metrics import app_data_dir


def default_backup_root() -> Path:
    """Return the single application-owned default backup repository."""
    return app_data_dir() / "backup"


def _apply_default_path_to_window(window: Any) -> None:
    configured = str(window.settings.value(_backup_ui._BACKUP_PATH_KEY, "", str) or "").strip()
    if configured:
        return
    root = default_backup_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    edit = getattr(window, "backup_path_edit", None)
    if isinstance(edit, QLineEdit):
        edit.setText(str(root))


def apply_v1_4_local_app_data_patch(MainWindow: Any) -> None:
    """Keep the v1.4 backup repository in the established FH6GarageAnalyzer root."""
    if getattr(MainWindow, "_fh6_v14_local_app_data_patched", False):
        return

    # v1_4_backup_repository_patch resolves this module global at call time, so
    # replacing it also updates export/import/external-import destination lookup.
    _repository._default_backup_root = default_backup_root

    original_init = MainWindow.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _apply_default_path_to_window(self)

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v14_local_app_data_patched = True
