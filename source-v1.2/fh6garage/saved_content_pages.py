from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QScrollArea, QVBoxLayout, QWidget

from .i18n import tr


def _build_saved_content_page(
    owner: Any,
    content_type: str,
    title: str,
) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addLayout(owner._page_header(title, ""))

    controls_result = owner._build_saved_content_controls(content_type)
    controls, search, status_filter, sort_group, sort_buttons = controls_result
    setattr(owner, f"{content_type}_search", search)
    setattr(owner, f"{content_type}_check_filter", status_filter)
    setattr(owner, f"{content_type}_sort_group", sort_group)
    setattr(owner, f"{content_type}_sort_buttons", sort_buttons)
    layout.addLayout(controls)

    scroll = QScrollArea()
    scroll.setObjectName(f"{content_type}GridScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    scroll.setStyleSheet(
        f"QScrollArea#{content_type}GridScroll "
        "{ background:#f7f8fb; border:0; }"
    )
    setattr(owner, f"{content_type}_grid_scroll", scroll)

    viewport = scroll.viewport()
    viewport.setObjectName(f"{content_type}GridViewport")
    viewport.setStyleSheet(
        f"QWidget#{content_type}GridViewport "
        "{ background:#f7f8fb; }"
    )

    host = QWidget()
    host.setObjectName(f"{content_type}GridHost")
    host.setMinimumWidth(0)
    host.setStyleSheet(
        f"QWidget#{content_type}GridHost "
        "{ background:#f7f8fb; }"
    )
    setattr(owner, f"{content_type}_grid_host", host)

    grid_layout = QGridLayout(host)
    grid_layout.setContentsMargins(2, 2, 2, 2)
    grid_layout.setHorizontalSpacing(14)
    grid_layout.setVerticalSpacing(14)
    grid_layout.setColumnStretch(0, 1)
    grid_layout.setColumnStretch(1, 1)
    grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    setattr(owner, f"{content_type}_grid_layout", grid_layout)
    scroll.setWidget(host)

    thumbnail_callback = getattr(
        owner,
        f"_schedule_visible_{content_type}_thumbnails",
    )
    width_callback = getattr(owner, f"_sync_{content_type}_grid_card_widths")
    scroll.verticalScrollBar().valueChanged.connect(thumbnail_callback)
    scroll.verticalScrollBar().rangeChanged.connect(
        lambda *_args: width_callback()
    )
    viewport.installEventFilter(owner)

    layout.addWidget(scroll, 1)
    return page


def build_livery_page(owner: Any) -> QWidget:
    return _build_saved_content_page(owner, "livery", tr("content.livery_page"))


def build_tuning_page(owner: Any) -> QWidget:
    return _build_saved_content_page(owner, "tuning", tr("dashboard.saved_tuning"))
