from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel


VERSION_TEXT = "v1.4 RC1"
APP_VERSION = "1.4-rc1"
WINDOW_TITLE = "FH6 Assistant v1.4 RC1"


def apply_v1_4_identity_patch(MainWindow) -> None:
    """Apply the v1.4 RC1 identity on top of the verified v1.4 stack."""
    if getattr(MainWindow, "_fh6_v14_identity_patched", False):
        return

    original_init = MainWindow.__init__

    def patched_init(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        app = QApplication.instance()
        if app is not None:
            app.setApplicationVersion(APP_VERSION)
        self.setWindowTitle(WINDOW_TITLE)
        for label in self.findChildren(QLabel):
            text = label.text()
            if "LIVERY & TUNING" in text and text.startswith("v1."):
                label.setText(f"{VERSION_TEXT}\nLIVERY & TUNING")
                break

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v14_identity_patched = True
