from __future__ import annotations

import sys
from pathlib import Path

# Keep the application directory immutable during normal use. Python bytecode
# caches are disabled so opening a save cannot create __pycache__ beside the app.
sys.dont_write_bytecode = True

try:
    from PySide6.QtCore import QSettings
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
from fh6garage.v1_3_2_card_alignment_patch import apply_v1_3_2_card_alignment_patch
from fh6garage.v1_3_2_ui_performance_patch import apply_v1_3_2_ui_performance_patches
from fh6garage.v1_3_2_global_ui_patch import apply_v1_3_2_global_ui_patch
from fh6garage.v1_3_2_icon_overlay_fix import apply_v1_3_2_icon_overlay_fix
from fh6garage.v1_3_2_compact_card_layout_patch import apply_v1_3_2_compact_card_layout_patch
from fh6garage.v1_3_2_responsiveness_sort_patch import apply_v1_3_2_responsiveness_sort_patch
from fh6garage.v1_3_2_refresh_diff_patch import apply_v1_3_2_refresh_diff_patch
from fh6garage.v1_3_2_change_view_alias_patch import apply_v1_3_2_change_view_alias_patch
from fh6garage.v1_3_2_thread_affinity_patch import apply_v1_3_2_thread_affinity_fix


def resource_root() -> Path:
    """Return the bundled-resource directory in source and PyInstaller builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def main() -> int:
    app = QApplication(sys.argv)
    # Use a concrete positive base point size before applying application QSS.
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("FH6 Assistant")
    app.setApplicationVersion("1.3.2")
    app.setOrganizationName("LocalOnly")

    # Resolve the persisted UI language before constructing any translated widgets.
    settings = QSettings()
    set_language(settings.value("language", DEFAULT_LANGUAGE, str))

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
    apply_v1_3_2_card_alignment_patch(MainWindow)

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

    # Snapshot visible livery instances and cache only thumbnail copies under
    # LocalAppData so the latest add/remove/change diff can retain deleted images.
    apply_v1_3_2_refresh_diff_patch(MainWindow)

    # Present latest refresh changes as cards and resolve user-managed creator
    # aliases across display/search/sort/group/statistics. This stays before the
    # final thread-affinity patch and never writes FH6 content.
    apply_v1_3_2_change_view_alias_patch(MainWindow)

    # This must be the final MainWindow patch. It restores the original
    # class-defined @Slot(object) scan callback so all UI rebuilding runs on the
    # GUI thread, then moves v1.3.2 post-processing into _populate_all().
    apply_v1_3_2_thread_affinity_fix(MainWindow)

    root = resource_root()
    icon_path = root / "icons" / "FH6_Assistant.ico"
    if icon_path.is_file():
        app_icon = QIcon(str(icon_path))
        app.setWindowIcon(app_icon)
    else:
        app_icon = QIcon()

    window = MainWindow(project_root=root)
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
