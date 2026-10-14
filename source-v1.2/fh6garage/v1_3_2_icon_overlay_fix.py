from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QStackedLayout, QToolButton, QWidget


CARD_ACTION_BUTTON_SIZE = 30
CARD_ACTION_ICON_SIZE = 20
CARD_ACTION_RADIUS = 8

_CARD_ACTION_STYLE = f"""
QToolButton {{
    background: rgba(255,255,255,242);
    color: #626979;
    border: 1px solid #dfe1e8;
    border-radius: {CARD_ACTION_RADIUS}px;
    padding: 0;
}}
QToolButton:hover {{
    border-color: #8c74ee;
    background: rgba(247,245,255,250);
}}
QToolButton:checked {{
    border-color: #8c74ee;
    background: #eee9ff;
}}
QToolButton:checked:hover {{
    border-color: #6e4bf2;
    background: #e8e1ff;
}}
QToolButton:disabled {{
    background: rgba(248,249,251,235);
    border-color: #e4e6ec;
}}
""".strip()

_BUSY_OVERLAY_STYLE = """
QWidget#fh6BusyOverlay {
    background: rgba(23,24,33,145);
}
QFrame#fh6BusyPanel {
    background: #ffffff;
    border: 1px solid #dddfea;
    border-radius: 14px;
}
QLabel#fh6BusyMessage {
    background: transparent;
    color: #20232d;
    border: 0;
    font-size: 11pt;
    font-weight: 650;
}
QProgressBar#fh6BusyProgress {
    background: #ececf3;
    border: 0;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
}
QProgressBar#fh6BusyProgress::chunk {
    background: #6e4bf2;
    border-radius: 4px;
}
""".strip()


def _card_action_buttons(card: Any) -> list[QToolButton]:
    names = (
        "_fh6_game_move_button",
        "_fh6_hide_button",
        "_fh6_info_button",
        "_fh6_check_box",
        "_fh6_triangle_box",
        "_fh6_excluded_box",
        "_fh6_zoom_button",
        "_fh6_memo_button",
    )
    result: list[QToolButton] = []
    seen: set[int] = set()
    for name in names:
        button = getattr(card, name, None)
        if not isinstance(button, QToolButton):
            continue
        identity = id(button)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(button)
    return result


def _fix_thumbnail_overlay(card: Any) -> None:
    """Keep only the action widgets above the thumbnail; never paint an opaque overlay."""
    image_label = getattr(card, "_fh6_image_label", None)
    if not isinstance(image_label, QLabel):
        return

    # Make the placeholder deterministic even if an inherited application style
    # or native palette would otherwise render it as black-on-black.
    image_label.setStyleSheet(
        "background:#f1f2f6; color:#737787; border-radius:9px;"
    )

    image_host = image_label.parentWidget()
    stack = image_host.layout() if isinstance(image_host, QWidget) else None
    if not isinstance(stack, QStackedLayout):
        return
    overlay = stack.currentWidget()
    if not isinstance(overlay, QWidget) or overlay is image_label:
        return

    overlay.setObjectName("fh6ThumbnailActionOverlay")
    overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    overlay.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    overlay.setStyleSheet(
        "QWidget#fh6ThumbnailActionOverlay { background: transparent; border: 0; }"
    )


def _normalize_card_actions(card: Any) -> None:
    for button in _card_action_buttons(card):
        button.setFixedSize(CARD_ACTION_BUTTON_SIZE, CARD_ACTION_BUTTON_SIZE)
        button.setIconSize(QSize(CARD_ACTION_ICON_SIZE, CARD_ACTION_ICON_SIZE))
        button.setStyleSheet(_CARD_ACTION_STYLE)

    _fix_thumbnail_overlay(card)

    # v1.3.2's alignment object positions the left hide/info controls against
    # the fourth/fifth right-side controls. Re-run it after the common 30 px
    # geometry has been applied so every centerline is calculated from final sizes.
    aligner = None if getattr(card, "_fh6_action_grid", None) is not None else getattr(card, "_fh6_card_action_aligner", None)
    if aligner is not None and hasattr(aligner, "reposition"):
        QTimer.singleShot(0, aligner.reposition)


def _fix_busy_overlay(window: Any) -> None:
    """Scope the loading overlay QSS so dark scrim styling cannot leak into children."""
    overlay = getattr(window, "_busy_overlay", None)
    if not isinstance(overlay, QWidget):
        return

    overlay.setObjectName("fh6BusyOverlay")
    overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    message = getattr(overlay, "message", None)
    if isinstance(message, QLabel):
        message.setObjectName("fh6BusyMessage")

    progress = getattr(overlay, "progress", None)
    if isinstance(progress, QProgressBar):
        progress.setObjectName("fh6BusyProgress")

    panel: QFrame | None = None
    for candidate in overlay.findChildren(QFrame):
        panel = candidate
        break
    if panel is not None:
        panel.setObjectName("fh6BusyPanel")

    # Use object-name selectors rather than a bare `background:` declaration on
    # the parent widget. The latter is inherited by descendants in Qt style
    # sheets and can produce a black panel with dark text on some Windows styles.
    overlay.setStyleSheet(_BUSY_OVERLAY_STYLE)


def apply_v1_3_2_icon_overlay_fix(MainWindow) -> None:
    """Normalize card action geometry and harden card/loading overlay colors."""
    if getattr(MainWindow, "_fh6_v132_icon_overlay_fix_patched", False):
        return

    original_make_card = MainWindow._make_saved_content_card
    original_init = MainWindow.__init__

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        _normalize_card_actions(card)
        return card

    def patched_init(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        _fix_busy_overlay(self)

    MainWindow._make_saved_content_card = patched_make_card
    MainWindow.__init__ = patched_init
    MainWindow._fh6_v132_icon_overlay_fix_patched = True
