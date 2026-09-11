from __future__ import annotations

from typing import Any

from . import v1_3_4_backup_lazy_load_patch as _lazy
from . import v1_3_4_backup_lazy_watch_patch as _watch
from . import v1_4_backup_repository_patch as _base


def apply_v1_4_backup_repository_followup_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_backup_repository_followup_patched", False):
        return

    original_controls = _lazy._backup_controls
    original_external_refresh = _watch._refresh_external_change
    original_import_controls = _base._external_import_controls
    original_request_external_import = _base._request_external_import

    def backup_controls(window: Any) -> list[Any]:
        controls = list(original_controls(window))
        external = getattr(window, "backup_external_import_button", None)
        if external is not None and external not in controls:
            controls.append(external)
        return controls

    def refresh_external_change(window: Any) -> None:
        if getattr(window, "_fh6_external_import_running", False):
            return
        original_external_refresh(window)

    def import_controls(window: Any, enabled: bool) -> None:
        _lazy._set_controls_enabled(window, enabled)
        original_import_controls(window, enabled)

    def request_external_import(window: Any) -> None:
        if getattr(window, "_fh6_backup_load_running", False):
            return
        if getattr(window, "_fh6_export_running", False):
            return
        if getattr(window, "_fh6_import_running", False):
            return
        original_request_external_import(window)

    _lazy._backup_controls = backup_controls
    _watch._refresh_external_change = refresh_external_change
    _base._external_import_controls = import_controls
    _base._request_external_import = request_external_import
    MainWindow._fh6_v14_backup_repository_followup_patched = True
