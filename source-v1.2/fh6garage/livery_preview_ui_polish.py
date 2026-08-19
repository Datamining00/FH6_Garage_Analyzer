from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
)


_LIGHT_BUTTON_STYLE = """
QPushButton {
    min-height: 32px;
    padding: 0 12px;
    border-radius: 8px;
    border: 1px solid #dfe1e8;
    background: #ffffff;
    color: #303341;
    font-size: 9.5pt;
}
QPushButton:hover { background:#f8f7ff; border-color:#9c8cf5; }
QPushButton:checked {
    background:#6e4bf2;
    color:#ffffff;
    border-color:#6e4bf2;
    font-weight:600;
}
QPushButton:disabled { background:#f0f1f4; color:#9a9da7; border-color:#e2e4e9; }
"""

_SCROLL_STYLE = """
QScrollArea { background:transparent; border:0; }
QScrollArea > QWidget > QWidget { background:transparent; }
QScrollBar:horizontal {
    background:#eef0f5;
    height:8px;
    margin:1px 4px;
    border:0;
    border-radius:4px;
}
QScrollBar::handle:horizontal {
    background:#b8aecf;
    min-width:44px;
    border-radius:4px;
}
QScrollBar::handle:horizontal:hover { background:#8c74ee; }
QScrollBar::handle:horizontal:pressed { background:#6e4bf2; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width:0px;
    border:0;
    background:transparent;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:transparent; }
"""

_COMBO_STYLE = """
QComboBox {
    min-height:32px;
    min-width:92px;
    padding:0 30px 0 10px;
    background:#ffffff;
    color:#303341;
    border:1px solid #dfe1e8;
    border-radius:8px;
}
QComboBox:hover { border-color:#9c8cf5; }
QComboBox:focus { border-color:#8c74ee; }
QComboBox::drop-down {
    subcontrol-origin:padding;
    subcontrol-position:top right;
    width:26px;
    border:0;
    background:transparent;
}
QComboBox::down-arrow {
    width:8px;
    height:8px;
}
QComboBox QAbstractItemView {
    background:#ffffff;
    color:#20232d;
    border:1px solid #d9dce5;
    selection-background-color:#eee9ff;
    selection-color:#5335c7;
    outline:0;
    padding:4px;
}
"""

_MORE_STYLE = """
QToolButton {
    min-width:34px;
    min-height:32px;
    border:1px solid #dfe1e8;
    border-radius:8px;
    background:#ffffff;
    color:#303341;
    font-size:15pt;
    padding:0 4px 5px 4px;
}
QToolButton:hover { background:#f8f7ff; border-color:#9c8cf5; }
QToolButton::menu-indicator { image:none; width:0px; }
"""


def _is_folder_button(button: QPushButton) -> bool:
    text = str(button.text() or "").strip().casefold()
    return text in {"fh6 폴더", "fh6 folder"}


def _polish_preview_dialog(dialog: QDialog) -> bool:
    top_bar = dialog.findChild(QFrame, "liveryPreviewTopBar")
    if top_bar is None:
        return False
    if bool(top_bar.property("fh6_preview_polished")):
        return True
    top_bar.setProperty("fh6_preview_polished", True)

    top_bar.setStyleSheet(
        "QFrame#liveryPreviewTopBar{"
        "background:#ffffff;border:1px solid #e1e3ea;border-radius:12px;"
        "}"
    )

    for button in top_bar.findChildren(QPushButton):
        if _is_folder_button(button):
            continue
        button.setStyleSheet(_LIGHT_BUTTON_STYLE)

    for scroll in top_bar.findChildren(QScrollArea):
        scroll.setStyleSheet(_SCROLL_STYLE)
        # 34px section button + 8px modern scrollbar + small internal margin.
        scroll.setFixedHeight(48)

    for combo in top_bar.findChildren(QComboBox):
        combo.setObjectName("liveryPreviewScaleCombo")
        combo.setStyleSheet(_COMBO_STYLE)

    folder_button = next(
        (button for button in top_bar.findChildren(QPushButton) if _is_folder_button(button)),
        None,
    )
    if folder_button is not None:
        folder_button.hide()
        layout = top_bar.layout()
        if layout is not None and top_bar.findChild(QToolButton, "liveryPreviewMoreButton") is None:
            more = QToolButton(top_bar)
            more.setObjectName("liveryPreviewMoreButton")
            more.setText("⋯")
            more.setToolTip("추가 설정" if "폴더" in folder_button.text() else "More settings")
            more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            more.setStyleSheet(_MORE_STYLE)

            menu = QMenu(more)
            change_location = QAction(
                "FH6 설치 위치 변경" if "폴더" in folder_button.text() else "Change FH6 install location",
                menu,
            )
            change_location.triggered.connect(folder_button.click)
            menu.addAction(change_location)
            more.setMenu(menu)
            layout.addWidget(more)

    return True


class _PreviewDialogPolishFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show and isinstance(watched, QDialog):
            QTimer.singleShot(0, lambda dialog=watched: _polish_preview_dialog(dialog))
        return False


_FILTER = None


def apply_livery_preview_ui_polish() -> None:
    global _FILTER
    app = QApplication.instance()
    if app is None or _FILTER is not None:
        return
    _FILTER = _PreviewDialogPolishFilter(app)
    app.installEventFilter(_FILTER)
