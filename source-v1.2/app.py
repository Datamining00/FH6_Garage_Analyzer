from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Capture process-side application entry before importing Qt or the UI stack.
# This timestamp is used only for the always-on launch profiler.
_APP_ENTRY_NS = time.perf_counter_ns()

# Keep the application directory immutable during normal use. Python bytecode
# caches are disabled so opening a save cannot create __pycache__ beside the app.
sys.dont_write_bytecode = True

try:
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QIcon
except ModuleNotFoundError as exc:
    if exc.name == "PySide6":
        print(
            "PySide6 is not installed in the Python interpreter that launched this app.\n"
            "Run 'run.bat' instead of running app.py directly.\n"
            "The launcher creates/uses a virtual environment under LocalAppData and installs requirements automatically.",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    raise

from fh6garage import performance_metrics as _performance_metrics
from fh6garage.i18n import DEFAULT_LANGUAGE, set_language
from fh6garage.ui import MainWindow
from fh6garage.v1_3_ui_patch import apply_v1_3_ui_patches
from fh6garage.v1_3_1_patch import apply_v1_3_1_patches
from fh6garage.v1_3_2_patch import apply_v1_3_2_patches
from fh6garage.v1_3_2_safety_patch import apply_v1_3_2_safety_patches
from fh6garage.v1_3_2_startup_patch import apply_v1_3_2_startup_patches
from fh6garage.v1_3_2_list_fix import apply_v1_3_2_list_fixes
from fh6garage.v1_3_2_visibility_patch import apply_v1_3_2_visibility_patches
from fh6garage.v1_3_2_ui_cleanup_patch import apply_v1_3_2_ui_cleanup_patch
from fh6garage.v1_3_2_ui_followup_patch import apply_v1_3_2_ui_followup_patch
from fh6garage.v1_3_2_manifest_registry_patch import apply_v1_3_2_manifest_registry_patch
from fh6garage.v1_3_2_ui_performance_patch import apply_v1_3_2_ui_performance_patches
from fh6garage.v1_3_2_global_ui_patch import apply_v1_3_2_global_ui_patch
from fh6garage.v1_3_2_icon_overlay_fix import apply_v1_3_2_icon_overlay_fix
from fh6garage.v1_3_2_compact_card_layout_patch import apply_v1_3_2_compact_card_layout_patch
from fh6garage.v1_3_2_responsiveness_sort_patch import apply_v1_3_2_responsiveness_sort_patch
from fh6garage.v1_3_2_responsive_columns_fix import apply_v1_3_2_responsive_columns_fix
from fh6garage.v1_3_2_refresh_diff_patch import apply_v1_3_2_refresh_diff_patch
from fh6garage.v1_3_2_change_view_alias_patch import apply_v1_3_2_change_view_alias_patch
from fh6garage.v1_3_2_change_view_alias_sync_patch import apply_v1_3_2_change_view_alias_sync_patch
from fh6garage.v1_3_2_release_layout_patch import apply_v1_3_2_release_layout_patch
from fh6garage.v1_3_2_change_dialog_folder_patch import apply_v1_3_2_change_dialog_folder_patch
from fh6garage.v1_3_2_change_dialog_runtime_fix import apply_v1_3_2_change_dialog_runtime_fix
from fh6garage.v1_3_2_change_dialog_responsive_ui_fix import apply_v1_3_2_change_dialog_responsive_ui_fix
from fh6garage.v1_3_2_auction_unapplied_recent_frame_fix import apply_v1_3_2_auction_unapplied_recent_frame_fix
from fh6garage.v1_3_2_alias_manager_change_card_fix import apply_v1_3_2_alias_manager_change_card_fix
from fh6garage.v1_3_2_memory_state_patch import apply_v1_3_2_memory_state_patch
from fh6garage.v1_3_2_memory_filter_coordination_patch import apply_v1_3_2_memory_filter_coordination_patch
from fh6garage.v1_3_2_memory_thread_safety_patch import apply_v1_3_2_memory_thread_safety_patch
from fh6garage.v1_3_2_filter_alias_quality_patch import apply_v1_3_2_filter_alias_quality_patch
from fh6garage.v1_3_2_dashboard_change_group_patch import apply_v1_3_2_dashboard_change_group_patch
from fh6garage.v1_3_4_card_action_layout_patch import apply_v1_3_4_card_action_layout_patch
from fh6garage.v1_3_4_card_features_patch import apply_v1_3_4_card_features_patch
from fh6garage.v1_3_4_metadata_toggle_icon_patch import apply_v1_3_4_metadata_toggle_icon_patch
from fh6garage.v1_3_4_backup_export_patch import apply_v1_3_4_backup_export_patch
from fh6garage.v1_3_4_backup_export_thread_fix_patch import apply_v1_3_4_backup_export_thread_fix_patch
from fh6garage.v1_3_4_backup_export_performance_ui_patch import apply_v1_3_4_backup_export_performance_ui_patch
from fh6garage.v1_3_4_backup_action_wording_patch import (
    apply_v1_3_4_backup_action_wording_patch,
    apply_v1_3_4_v1_4_followup_patches,
)
from fh6garage.v1_4_finalverify1_preview_patch import apply_v1_4_finalverify1_preview_patch
from fh6garage.v1_3_2_thread_affinity_patch import (
    apply_v1_3_2_scan_postprocessing,
    apply_v1_3_2_performance_profiler,
    apply_v1_3_2_thread_affinity_fix,
)


def resource_root() -> Path:
    """Return the bundled-resource directory in source and PyInstaller builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _elapsed_ms(started_ns: int) -> float:
    return (time.perf_counter_ns() - started_ns) / 1_000_000.0


def _apply_foundation_patch_stack() -> None:
    """Install the base UI, card-lifetime and responsive-layout layers."""
    # Apply patches in release order so every maintenance release layers only its
    # own behavior on top of the already-verified previous version.
    apply_v1_3_ui_patches(MainWindow)
    apply_v1_3_1_patches(MainWindow)
    apply_v1_3_2_patches(MainWindow)
    apply_v1_3_2_safety_patches(MainWindow)
    apply_v1_3_2_startup_patches()
    apply_v1_3_2_list_fixes(MainWindow)
    apply_v1_3_2_visibility_patches(MainWindow)
    apply_v1_3_2_ui_cleanup_patch(MainWindow)
    apply_v1_3_2_ui_followup_patch(MainWindow)
    apply_v1_3_2_manifest_registry_patch(MainWindow)

    # Performance/card-lifetime optimization stays below all feature patches so
    # it reuses the final v1.3.2 card behavior.
    apply_v1_3_2_ui_performance_patches(MainWindow)

    # Geometry/aspect correction is deliberately layered after card reuse so
    # cached cards retain the same aspect controller through sort/filter/source
    # changes.
    apply_v1_3_2_global_ui_patch(MainWindow)

    # Normalize the final card action geometry only after all earlier card
    # patches have installed their controls. Also harden both thumbnail and busy
    # overlays against inherited black background/text palette combinations.
    apply_v1_3_2_icon_overlay_fix(MainWindow)

    # Reclaim horizontal space around the saved-content grid and make the title
    # and creator metadata use equal halves with pixel-based elision.
    apply_v1_3_2_compact_card_layout_patch(MainWindow)

    # Keep the indeterminate busy overlay repainting during synchronous card
    # rebuild/layout work and make first-click download/date sorting newest-first.
    apply_v1_3_2_responsiveness_sort_patch(MainWindow)

    # The responsiveness patch historically rebuilt cards in a hard-coded
    # two-column grid. Restore the v1.3 2/3/4-column calculation while retaining
    # its cooperative event-yield and newest-first date sorting behavior.
    apply_v1_3_2_responsive_columns_fix(MainWindow)


def _apply_state_patch_stack() -> None:
    """Install refresh, change-view, memory-state and dashboard layers."""
    # Snapshot visible livery instances and cache only thumbnail copies under
    # LocalAppData so the latest add/remove/change diff can retain deleted images.
    apply_v1_3_2_refresh_diff_patch(MainWindow)

    # Present latest refresh changes as cards and resolve user-managed creator
    # aliases across display/search/sort/group/statistics. This stays before the
    # final thread-affinity patch and never writes FH6 content.
    apply_v1_3_2_change_view_alias_patch(MainWindow)

    # Current cards opened from the change viewer are separate widgets from the
    # main-grid cache. Mirror their annotation/hide actions back to that cache so
    # both views remain visually consistent immediately.
    apply_v1_3_2_change_view_alias_sync_patch(MainWindow)

    # Put the compact refresh-change notice below Full Refresh and keep the legacy
    # hide/info left actions on the triangle/excluded rows.
    apply_v1_3_2_release_layout_patch(MainWindow)

    # Add the folder action and base standalone change-view card implementation.
    apply_v1_3_2_change_dialog_folder_patch(MainWindow)

    # Make the compact change button clickable after it is reparented into the
    # reserved toolbar slot.
    apply_v1_3_2_change_dialog_runtime_fix(MainWindow)

    # The standalone change window must calculate card geometry from its own
    # viewport, not from a hidden/main-grid width. Reuse the main 2/3/4-column
    # formula on every resize and force the same light application theme.
    apply_v1_3_2_change_dialog_responsive_ui_fix(MainWindow)

    # Preserve the default behavior of hiding only unapplied auction liveries.
    # Once a valid memory snapshot exists, the same rule uses the verified
    # memory/SoulBound state instead of relying on cache presence alone.
    apply_v1_3_2_auction_unapplied_recent_frame_fix(MainWindow)

    # Finalize deleted recent cards and creator-name manager interaction. Deleted
    # cards keep the normal card UI but no actions, and the alias manager remains
    # non-modal so the main window can still be used while it is open.
    apply_v1_3_2_alias_manager_change_card_fix(MainWindow)

    # Add the optional read-only memory scan page, persisted applied-state
    # snapshot, top applied/unapplied selector, and paint-bucket card indicator.
    apply_v1_3_2_memory_state_patch(MainWindow)

    # Keep the legacy auction-only filter and the new all-livery state selector
    # mutually exclusive so one state axis cannot contradict the other.
    apply_v1_3_2_memory_filter_coordination_patch(MainWindow)

    # Route worker progress/completion through an explicit QObject bridge so no
    # memory-scan callback can update Qt widgets from the worker thread.
    apply_v1_3_2_memory_thread_safety_patch(MainWindow)

    # Add live per-filter counts, stronger active-state styling, and collapse
    # creator-name unlink operations to a single persistence write.
    apply_v1_3_2_filter_alias_quality_patch(MainWindow)

    # Finalize dashboard applied/total ratios, remove legacy Saved page headings,
    # and present recent changes as grouped Add / Remove / Duplicate sections.
    apply_v1_3_2_dashboard_change_group_patch(MainWindow)


def _apply_release_patch_stack() -> None:
    """Install v1.3.4 features and the explicit v1.4 follow-up stack."""
    # Finalize the v1.3.4 six-row livery action layout after every feature has
    # installed its card buttons. New lock/export controls are placeholders.
    apply_v1_3_4_card_action_layout_patch(MainWindow)

    # Add the v1.3.4 card-wide metadata collapse, functional soft lock, and
    # duplicate-content grouping after the final card geometry is installed.
    apply_v1_3_4_card_features_patch(MainWindow)

    # Replace the metadata toggle glyph with packaged 20 px transparent PNG arrows.
    apply_v1_3_4_metadata_toggle_icon_patch(MainWindow)

    # Add the safe external backup repository, visible-item export action, and
    # backup/import status tab. Explicit import and verified backup-and-delete actions may modify the game save.
    apply_v1_3_4_backup_export_patch(MainWindow)

    # Export hashing/copying runs off the UI thread, while completion and all Qt
    # updates are explicitly marshalled back to the MainWindow thread.
    apply_v1_3_4_backup_export_thread_fix_patch(MainWindow)

    # Avoid repeated backup-index reads/hashes, build large backup card sets in
    # event-loop chunks, and mirror the livery search/filter/button styling.
    apply_v1_3_4_backup_export_performance_ui_patch(MainWindow)

    # Keep backup-tab terminology as Backup/Back up instead of Export while
    # preserving the same verified external-copy implementation underneath.
    apply_v1_3_4_backup_action_wording_patch(MainWindow)

    # Install the formerly hidden v1.3.4/v1.4 follow-up stack explicitly. The
    # order inside this compatibility bridge is unchanged from the verified
    # release chain; only the ownership boundary is now visible from app.py.
    apply_v1_3_4_v1_4_followup_patches(MainWindow)

    # FinalVerify1/ErrorFix1 3D livery renderer is scoped to the existing
    # livery-card magnifier. The final thread-affinity patch still runs last.
    apply_v1_4_finalverify1_preview_patch(MainWindow)


def _apply_runtime_patch_stack() -> None:
    """Install the verified runtime composition through explicit domain stages.

    The application still relies on ordered compatibility layers. These helpers
    expose stable ownership boundaries without changing patch order. The
    thread-affinity repair remains the final MainWindow mutation until scan
    completion is migrated to a class-defined Qt slot/controller architecture.
    """
    _apply_foundation_patch_stack()
    _apply_state_patch_stack()
    _apply_release_patch_stack()
    _apply_finalizer_patch_stack()


def _apply_finalizer_patch_stack() -> None:
    """Install final scan-result preparation, then restore the invariant Qt slot."""
    # Post-processing still has to capture the fully composed _populate_all(), so
    # it remains in this final stage even though it is not itself an affinity fix.
    apply_v1_3_2_scan_postprocessing(MainWindow)

    # Install performance reporting after functional post-processing so metrics
    # observe the final indexes/card counters without owning feature behavior.
    apply_v1_3_2_performance_profiler(MainWindow)

    # This must remain the final MainWindow mutation. Restoring the original
    # class-defined @Slot(object) keeps ScanWorker completion on the GUI thread.
    apply_v1_3_2_thread_affinity_fix(MainWindow)


def main() -> int:
    # Startup profiling is independent of the user-controlled runtime switch.
    _performance_metrics.begin_startup(_APP_ENTRY_NS)

    qapp_started = time.perf_counter_ns()
    app = QApplication(sys.argv)
    # Use a concrete positive base point size before applying application QSS.
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("FH6 Assistant")
    app.setApplicationVersion("1.4")
    app.setOrganizationName("LocalOnly")
    _performance_metrics.record_startup("startup.qapplication", _elapsed_ms(qapp_started))

    # Resolve the persisted UI language before constructing any translated widgets.
    settings_started = time.perf_counter_ns()
    settings = QSettings()
    set_language(settings.value("language", DEFAULT_LANGUAGE, str))
    _performance_metrics.record_startup("startup.settings", _elapsed_ms(settings_started))

    patch_started = time.perf_counter_ns()
    _apply_runtime_patch_stack()
    _performance_metrics.record_startup("startup.patch_install", _elapsed_ms(patch_started))

    root = resource_root()
    icon_path = root / "icons" / "FH6_Assistant.ico"
    if icon_path.is_file():
        app_icon = QIcon(str(icon_path))
        app.setWindowIcon(app_icon)
    else:
        app_icon = QIcon()

    mainwindow_started = time.perf_counter_ns()
    window = MainWindow(project_root=root)
    _performance_metrics.record_startup("startup.mainwindow_init", _elapsed_ms(mainwindow_started))
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)

    # MainWindow schedules an automatic scan with QTimer(0) when a persisted save
    # path exists. Mark that before entering the event loop so startup.total closes
    # only after the initial scan/populate path has completed.
    saved_path = ""
    path_edit = getattr(window, "path_edit", None)
    if path_edit is not None and hasattr(path_edit, "text"):
        saved_path = str(path_edit.text() or "").strip()
    wait_for_scan = bool(saved_path and Path(saved_path).is_dir())
    _performance_metrics.set_startup_waiting_for_scan(wait_for_scan)

    show_started = time.perf_counter_ns()
    window.show()
    _performance_metrics.record_startup("startup.window_show", _elapsed_ms(show_started))

    first_render_started = time.perf_counter_ns()

    def record_first_window_render() -> None:
        _performance_metrics.record_startup(
            "startup.first_window_render",
            _elapsed_ms(first_render_started),
        )
        if not _performance_metrics.startup_waiting_for_scan():
            _performance_metrics.finish_startup(detail="window ready; no saved path scan")

    QTimer.singleShot(0, record_first_window_render)

    # CI/distribution smoke tests use the real application entry point and then
    # request an ordinary window close. Avoiding force-termination also lets a
    # PyInstaller OneFile process remove its temporary extraction directory.
    smoke_delay = os.environ.get("FH6_ASSISTANT_SMOKE_TEST_MS", "").strip()
    if smoke_delay:
        try:
            delay_ms = max(250, min(60_000, int(smoke_delay)))
        except ValueError:
            delay_ms = 0
        if delay_ms:
            QTimer.singleShot(delay_ms, window.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
