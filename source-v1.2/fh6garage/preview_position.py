"""Position magnifier dialogs on the owner's monitor, including its work area."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def center_in_area(dialog, area):
    frame = dialog.frameGeometry()
    extra_width = frame.width() - dialog.width()
    extra_height = frame.height() - dialog.height()
    if frame.width() > area.width() or frame.height() > area.height():
        dialog.resize(min(dialog.width(), max(1, area.width() - extra_width)),
                      min(dialog.height(), max(1, area.height() - extra_height)))
    offset = area.center() - dialog.frameGeometry().center()
    dialog.move(dialog.pos() + offset)


def queue_preview_center(dialog, owner):
    # Defer until exec() has made the native window and its frame available.
    # Run once, leaving subsequent user movement untouched.
    def position():
        screen = owner.screen() or QApplication.primaryScreen()
        if screen is not None:
            center_in_area(dialog, screen.availableGeometry())
            # A resize may change the native frame on the next event turn.
            QTimer.singleShot(0, dialog, lambda: center_in_area(dialog, screen.availableGeometry()))
    QTimer.singleShot(0, dialog, position)
