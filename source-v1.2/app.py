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
from fh6garage.v1_4_patch import apply_v1_4_patches
from fh6garage.v1_4_preview2_patch import apply_v1_4_preview2_patch
from fh6garage.v1_4_validation_patch import apply_v1_4_validation_patch
from fh6garage.v1_4_native_resolution_test_patch import apply_v1_4_native_resolution_test_patch
from fh6garage.v1_4_quality_pipeline_patch import apply_v1_4_quality_pipeline_patch
from fh6garage.v1_4_preview_final_ui_patch import apply_v1_4_preview_final_ui_patch
from fh6garage.livery_decoder_recovery_patch import apply_livery_decoder_recovery_patch
from fh6garage.livery_tiled_runtime_patch import apply_livery_tiled_runtime_patch
from fh6garage.livery_raster_runtime_patch import apply_livery_raster_runtime_patch
from fh6garage.livery_render_integrity_patch import apply_livery_render_integrity_patch
from fh6garage.livery_preview_ui_polish import apply_livery_preview_ui_polish


def resource_root() -> Path:
    """Return the bundled-resource directory in source and PyInstaller builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("FH6 Assistant")
    app.setApplicationVersion("1.4 Preview UX Test")
    app.setOrganizationName("LocalOnly")

    settings = QSettings()
    set_language(settings.value("language", DEFAULT_LANGUAGE, str))

    # Install structural decoding safeguards before any UI action can inspect a
    # livery. Flat sections are recovered only when their raw byte contract can
    # be proven, and stale pre-recovery render caches are invalidated.
    apply_livery_decoder_recovery_patch()

    apply_v1_3_ui_patches(MainWindow)
    apply_v1_3_1_patches(MainWindow)
    apply_v1_4_patches(MainWindow)
    apply_v1_4_preview2_patch(MainWindow)
    apply_v1_4_validation_patch()
    apply_v1_4_native_resolution_test_patch(MainWindow)
    apply_v1_4_quality_pipeline_patch(MainWindow)
    apply_v1_4_preview_final_ui_patch(MainWindow)

    # Keep the native shape renderer separate from the vehicle projection
    # contract in tiled 8x/16x execution, then apply the same raster policy to
    # every scale. Integrity/provenance verification wraps this final path.
    apply_livery_tiled_runtime_patch()
    apply_livery_raster_runtime_patch()
    apply_livery_render_integrity_patch()
    apply_livery_preview_ui_polish()

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
