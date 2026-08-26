from __future__ import annotations

from PySide6.QtWidgets import QLabel


VERSION_TEXT = "v1.3.3 Beta"
WINDOW_TITLE = "FH6 Assistant v1.3.3 Beta"


def apply_v1_3_3_beta_identity_patch(MainWindow) -> None:
    """Apply only the public v1.3.3 Beta identity on top of the verified v1.3.2 stack."""
    if getattr(MainWindow, "_fh6_v133_beta_identity_patched", False):
        return

    original_init = MainWindow.__init__

    def patched_init(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        self.setWindowTitle(WINDOW_TITLE)
        for label in self.findChildren(QLabel):
            text = label.text()
            if "LIVERY & TUNING" in text and text.startswith("v1."):
                label.setText(f"{VERSION_TEXT}\nLIVERY & TUNING")
                break

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v133_beta_identity_patched = True
