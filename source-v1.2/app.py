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
from fh6garage.runtime_composition import apply_runtime_patches


def resource_root() -> Path:
    """Return the bundled-resource directory in source and PyInstaller builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _elapsed_ms(started_ns: int) -> float:
    return (time.perf_counter_ns() - started_ns) / 1_000_000.0


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
    apply_runtime_patches(MainWindow)
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
