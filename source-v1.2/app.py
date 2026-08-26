from __future__ import annotations

import os
import sys
from pathlib import Path

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

from fh6garage.i18n import DEFAULT_LANGUAGE, set_language
from fh6garage.ui import MainWindow
from fh6garage.version import PRODUCT_NAME, VERSION


def resource_root() -> Path:
    """Return the bundled-resource directory in source and PyInstaller builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def main() -> int:
    app = QApplication(sys.argv)
    # Use a concrete positive base point size before applying application QSS.
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName(PRODUCT_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("LocalOnly")

    # Resolve the persisted UI language before constructing any translated widgets.
    settings = QSettings()
    set_language(settings.value("language", DEFAULT_LANGUAGE, str))

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

    # CI/distribution smoke tests use the real application entry point and then
    # request an ordinary window close.  Avoiding force-termination also lets a
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
