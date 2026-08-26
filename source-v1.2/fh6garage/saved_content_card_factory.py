from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from .auction_ui_features import _add_auction_badge
from .card_action_alignment import configure_livery_card_actions
from .card_metadata_layout import _configure_card_metadata
from .card_visuals import _normalize_card_actions
from .creator_alias_views import decorate_creator_copy_label
from .models import LiveryRecord, TuningRecord
from .saved_content_card_actions import build_card_actions
from .saved_content_card_metadata import append_card_metadata
from .thumbnail_display import _configure_aspect_card
from .ui_cleanup import _install_card_hide_button


def make_saved_content_card(
    owner: Any,
    content_type: str,
    record: LiveryRecord | TuningRecord,
    key: str,
    *,
    image_min_height: int,
    copy_label_type: type,
    toggle_icon_factory: Callable[..., Any],
    pixmap_factory: Callable[..., Any],
) -> QFrame:
    card = QFrame()
    card.setObjectName("panel")
    card.setMinimumHeight(320)
    card.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(12, 12, 12, 12)
    outer.setSpacing(8)

    image_host = QWidget()
    image_stack = QStackedLayout(image_host)
    image_stack.setContentsMargins(0, 0, 0, 0)
    image_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

    image_label = QLabel()
    image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    image_label.setMinimumHeight(image_min_height)
    image_label.setStyleSheet("background:#f1f2f6;border-radius:9px;")
    image_label.setText("Thumbnail")
    image_label.setObjectName("muted")
    image_stack.addWidget(image_label)

    overlay = QWidget()
    overlay.setAttribute(
        Qt.WidgetAttribute.WA_TransparentForMouseEvents,
        False,
    )
    overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    overlay.setStyleSheet("background: transparent;")
    overlay_layout = QVBoxLayout(overlay)
    overlay_layout.setContentsMargins(8, 8, 8, 8)
    annotation = owner.annotations.get(key)
    actions = build_card_actions(
        owner,
        card,
        overlay_layout,
        content_type,
        record,
        key,
        annotation,
        toggle_icon_factory,
        pixmap_factory,
    )
    image_stack.addWidget(overlay)
    image_stack.setCurrentWidget(overlay)
    outer.addWidget(image_host)

    append_card_metadata(owner, outer, record, copy_label_type)

    card._fh6_image_label = image_label
    card._fh6_thumbnail_path = record.thumbnail_path
    card._fh6_thumbnail_loaded = False
    card._fh6_check_box = actions.check
    card._fh6_triangle_box = actions.triangle
    card._fh6_excluded_box = actions.excluded
    card._fh6_memo_button = actions.memo
    card._fh6_zoom_button = actions.zoom
    card._fh6_game_move_button = actions.game_move
    card._fh6_info_button = actions.info
    card._fh6_content_type = content_type
    owner._apply_pointing_cursors(card)
    _configure_card_metadata(card)
    _configure_aspect_card(card)
    if content_type == "livery":
        _install_card_hide_button(owner, card, key)
        configure_livery_card_actions(card, record)
        if record.kind == "SoulBoundLivery":
            card.setProperty("liverySource", "auction")
            _add_auction_badge(card)
        else:
            card.setProperty("liverySource", "my_designs")
    decorate_creator_copy_label(owner, card, record.header.creator or "")
    _normalize_card_actions(card)
    return card
