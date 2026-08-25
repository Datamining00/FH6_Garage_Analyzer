from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from .auction_ui_safety import is_auction_livery
from .card_state_sync import _refresh_dialog_memo_button
from .i18n import tr
from .models import LiveryRecord, TuningRecord


@dataclass(frozen=True)
class SavedContentCardActions:
    check: QToolButton
    triangle: QToolButton
    excluded: QToolButton
    zoom: QToolButton
    memo: QToolButton
    game_move: QToolButton | None
    info: QToolButton


def build_card_actions(
    owner: Any,
    card: QWidget,
    overlay_layout: QVBoxLayout,
    content_type: str,
    record: LiveryRecord | TuningRecord,
    key: str,
    annotation: Any,
    toggle_icon: Callable[[str], QIcon],
    action_pixmap: Callable[[str, bool, int], Any],
) -> SavedContentCardActions:
    noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")

    check = QToolButton()
    check.setCheckable(True)
    check.setIcon(toggle_icon("check"))
    check.setIconSize(QSize(22, 22))
    check.setChecked(annotation.checked)
    check.setToolTip(tr("status.toggle_check"))
    check.setAccessibleName(tr("status.accessible_check", noun=noun))
    check.setFixedSize(34, 34)
    check.setStyleSheet(
        "QToolButton { background:rgba(255,255,255,238); color:#9aa0aa; "
        "border:1px solid #dfe1e8; border-radius:17px; font-size:16px; font-weight:800; padding:0; }"
        "QToolButton:hover { border-color:#a9adb7; background:rgba(255,255,255,250); }"
        "QToolButton:checked { color:#2e9b50; border-color:#7ac58f; background:#eef9f1; }"
        "QToolButton:checked:hover { color:#238442; border-color:#58ad72; background:#e7f6eb; }"
    )
    check.toggled.connect(
        lambda checked: owner._set_grid_checked(content_type, key, card, checked)
    )

    triangle = QToolButton()
    triangle.setCheckable(True)
    triangle.setIcon(toggle_icon("triangle"))
    triangle.setIconSize(QSize(22, 22))
    triangle.setChecked(annotation.triangle)
    triangle.setToolTip(tr("status.toggle_triangle"))
    triangle.setAccessibleName(tr("status.accessible_triangle", noun=noun))
    triangle.setFixedSize(34, 34)
    triangle.setStyleSheet(
        "QToolButton { background:rgba(255,255,255,238); color:#9aa0aa; "
        "border:1px solid #dfe1e8; border-radius:8px; font-size:17px; font-weight:800; padding:0; }"
        "QToolButton:hover { border-color:#d4a14c; background:rgba(255,250,240,250); }"
        "QToolButton:checked { color:#d98216; border-color:#e2a64f; background:#fff5e6; }"
        "QToolButton:checked:hover { color:#c36f09; border-color:#d58d2c; background:#ffeed5; }"
    )
    triangle.toggled.connect(
        lambda enabled: owner._set_grid_triangle(content_type, key, card, enabled)
    )

    excluded = QToolButton()
    excluded.setCheckable(True)
    excluded.setIcon(toggle_icon("excluded"))
    excluded.setIconSize(QSize(22, 22))
    excluded.setChecked(annotation.excluded)
    excluded.setToolTip(tr("status.toggle_excluded"))
    excluded.setAccessibleName(tr("status.accessible_excluded", noun=noun))
    excluded.setFixedSize(34, 34)
    excluded.setStyleSheet(
        "QToolButton { background:rgba(255,255,255,238); color:#9aa0aa; "
        "border:1px solid #dfe1e8; border-radius:8px; font-size:18px; font-weight:800; padding:0; }"
        "QToolButton:hover { border-color:#df7d86; background:rgba(255,247,248,250); }"
        "QToolButton:checked { color:#c93c49; border-color:#df7d86; background:#fff0f2; }"
        "QToolButton:checked:hover { color:#ad2936; border-color:#cf5b66; background:#ffe7ea; }"
    )
    excluded.toggled.connect(
        lambda enabled: owner._set_grid_excluded(content_type, key, card, enabled)
    )

    zoom = QToolButton()
    zoom.setIcon(QIcon(action_pixmap("search", True, 24)))
    zoom.setIconSize(QSize(21, 21))
    zoom.setToolTip(tr("preview.enlarge"))
    zoom.setAccessibleName(tr("preview.enlarge"))
    zoom.setFixedSize(34, 34)
    zoom.setStyleSheet(
        "QToolButton { background:rgba(255,255,255,238); color:#555a68; "
        "border:1px solid #dfe1e8; border-radius:8px; padding:0; }"
        "QToolButton:hover { border-color:#8c74ee; background:rgba(247,245,255,250); }"
    )
    zoom.clicked.connect(lambda _checked=False: owner._show_livery_image(record))

    memo = QToolButton()
    memo.setIcon(owner._detail_memo_icon(bool(annotation.note.strip())))
    memo.setIconSize(QSize(18, 18))
    memo.setToolTip(
        annotation.note.strip() + tr("memo.edit_suffix")
        if annotation.note.strip()
        else tr("memo.none_add")
    )
    memo.setAccessibleName(tr("memo.accessible", noun=noun))
    memo.setFixedSize(34, 34)
    memo.setStyleSheet(
        "QToolButton { background:rgba(255,255,255,238); color:#555a68; "
        "border:1px solid #dfe1e8; border-radius:8px; padding:0; }"
        "QToolButton:hover { border-color:#8c74ee; background:rgba(247,245,255,250); }"
    )
    memo.clicked.connect(
        lambda _checked=False: owner._handle_saved_content_memo_clicked(content_type, key)
    )
    memo.clicked.connect(
        lambda _checked=False: QTimer.singleShot(
            0, lambda: _refresh_dialog_memo_button(owner, card, key)
        )
    )

    game_move = None
    if not (content_type == "livery" and is_auction_livery(record)):
        game_move = QToolButton()
        game_move.setIcon(QIcon(action_pixmap("move", True, 24)))
        game_move.setIconSize(QSize(23, 23))
        game_move.setToolTip(tr("content.game_move_tip"))
        game_move.setAccessibleName(tr("content.game_move_accessible", noun=noun))
        game_move.setFixedSize(38, 38)
        game_move.setStyleSheet(
            "QToolButton { background:rgba(255,255,255,242); color:#5f39d8; "
            "border:2px solid #8c74ee; border-radius:19px; padding:0; }"
            "QToolButton:hover { color:white; border-color:#6e4bf2; background:#6e4bf2; }"
        )
        game_move.clicked.connect(
            lambda _checked=False: owner._request_game_navigation(content_type, key)
        )

    if content_type == "livery":
        info_active = bool((record.header.description or "").strip())
        info_tooltip = tr("content.livery_info_tip")
        info_kind = "livery_info"
    else:
        info_active = bool(
            isinstance(record, TuningRecord)
            and record.data_path is not None
            and record.data_size == 598
        )
        info_tooltip = tr("content.tuning_info_tip")
        info_kind = "tuning_info"

    info = QToolButton()
    info.setIcon(QIcon(action_pixmap(info_kind, info_active, 24)))
    info.setIconSize(QSize(22, 22))
    info.setToolTip(info_tooltip)
    info.setAccessibleName(info_tooltip)
    info.setFixedSize(38, 38)
    info.setStyleSheet(
        "QToolButton { background:"
        + ("#f2edff" if info_active else "rgba(255,255,255,242)")
        + "; border:1px solid "
        + ("#9c86f2" if info_active else "#dfe1e8")
        + "; border-radius:9px; padding:0; }"
        "QToolButton:hover { border-color:#8c74ee; background:#f2edff; }"
    )
    if content_type == "livery":
        info.clicked.connect(lambda _checked=False: owner._show_livery_metadata(record))
    else:
        info.clicked.connect(lambda _checked=False: owner._show_tuning_details(record))

    right = QVBoxLayout()
    right.setContentsMargins(0, 0, 0, 0)
    right.setSpacing(6)
    for button in (check, triangle, excluded, zoom, memo):
        right.addWidget(button)
    right.addStretch(1)

    left = QVBoxLayout()
    left.setContentsMargins(0, 0, 0, 0)
    left.setSpacing(6)
    if content_type == "livery" and game_move is not None:
        left.addWidget(game_move, 0, Qt.AlignmentFlag.AlignTop)
    left.addStretch(1)
    left.addWidget(info, 0, Qt.AlignmentFlag.AlignBottom)

    columns = QHBoxLayout()
    columns.setContentsMargins(0, 0, 0, 0)
    columns.setSpacing(0)
    columns.addLayout(left)
    columns.addStretch(1)
    columns.addLayout(right)
    overlay_layout.addLayout(columns)

    return SavedContentCardActions(
        check=check,
        triangle=triangle,
        excluded=excluded,
        zoom=zoom,
        memo=memo,
        game_move=game_move,
        info=info,
    )
