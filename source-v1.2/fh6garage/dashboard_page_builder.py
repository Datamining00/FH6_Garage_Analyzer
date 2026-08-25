from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr


WidgetFactory = Callable[..., QWidget]


def build_dashboard_page(
    owner: Any,
    summary_card_factory: WidgetFactory,
    sort_bar_factory: WidgetFactory,
) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addLayout(owner._page_header(tr("dashboard.title"), ""))

    cards = QGridLayout()
    cards.setSpacing(12)
    owner.card_cars = summary_card_factory(tr("dashboard.garage_cars"), "—")
    owner.card_livery = summary_card_factory(tr("content.source_my_designs"), "—")
    owner.card_auction = summary_card_factory(tr("content.source_auction"), "—")
    owner.card_tuning = summary_card_factory(tr("dashboard.saved_tuning"), "—")
    for index, card in enumerate(
        (owner.card_cars, owner.card_livery, owner.card_auction, owner.card_tuning)
    ):
        cards.addWidget(card, 0, index)
    layout.addLayout(cards)

    _append_database_panel(owner, layout)

    body = QHBoxLayout()
    body.addWidget(_build_content_panel(owner, sort_bar_factory), 5)
    body.addWidget(_build_selection_panel(owner), 4)
    layout.addLayout(body, 1)
    return page


def _append_database_panel(owner: Any, layout: QVBoxLayout) -> None:
    panel = QFrame()
    panel.setObjectName("panel")
    row = QHBoxLayout(panel)
    row.setContentsMargins(14, 11, 14, 11)

    title = QLabel(tr("db.title"))
    title.setStyleSheet("font-size:11pt;font-weight:700;")
    owner.db_last_update_label = QLabel(tr("db.last_update_unavailable"))
    owner.db_last_update_label.setObjectName("muted")
    owner.db_last_update_label.setStyleSheet(
        "color:#737787; font-size:9.5pt; background:transparent;"
    )

    owner.db_update_button = QPushButton(tr("db.check_update"))
    owner.db_update_button.setObjectName("secondary")
    owner.db_update_button.setToolTip(tr("db.check_update_tip"))
    owner.db_update_button.clicked.connect(owner.start_car_db_update)

    owner.db_source_button = QToolButton()
    owner.db_source_button.setText(tr("db.source"))
    owner.db_source_button.setIcon(owner._external_link_icon())
    owner.db_source_button.setIconSize(QSize(18, 18))
    owner.db_source_button.setToolButtonStyle(
        Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    )
    owner.db_source_button.setToolTip(tr("db.source_tip"))
    owner.db_source_button.setAccessibleName(tr("db.source_accessible"))
    owner.db_source_button.setMinimumHeight(38)
    owner.db_source_button.setStyleSheet(
        "QToolButton { background:white; color:#303341; "
        "border:1px solid #dfe1e8; border-radius:8px; padding:5px; }"
        "QToolButton:hover { border-color:#9c8cf5; background:#f7f5ff; }"
    )
    owner.db_source_button.clicked.connect(owner._open_car_db_source)

    owner.db_override_button = QPushButton(tr("db.override"))
    owner.db_override_button.setObjectName("secondary")
    owner.db_override_button.setToolTip(tr("db.override_tip"))
    owner.db_override_button.clicked.connect(owner.open_car_db_override)

    row.addWidget(title)
    row.addWidget(owner.db_last_update_label)
    row.addStretch(1)
    row.addWidget(owner.db_override_button)
    row.addWidget(owner.db_update_button)
    row.addWidget(owner.db_source_button)
    layout.addWidget(panel)


def _build_content_panel(owner: Any, sort_bar_factory: WidgetFactory) -> QFrame:
    panel = QFrame()
    panel.setObjectName("panel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 14, 14, 14)

    controls = QGridLayout()
    controls.setHorizontalSpacing(7)
    controls.setVerticalSpacing(7)
    owner.dashboard_mode_group = QButtonGroup(owner)
    owner.dashboard_mode_group.setExclusive(True)

    owner.dashboard_car_button = QPushButton(tr("dashboard.by_vehicle"))
    owner.dashboard_car_button.setObjectName("secondary")
    owner.dashboard_car_button.setCheckable(True)
    owner.dashboard_car_button.setChecked(True)
    owner.dashboard_car_button.clicked.connect(
        lambda _checked=False: owner._set_dashboard_content_mode(0)
    )
    owner.dashboard_creator_button = QPushButton(tr("dashboard.by_creator"))
    owner.dashboard_creator_button.setObjectName("secondary")
    owner.dashboard_creator_button.setCheckable(True)
    owner.dashboard_creator_button.clicked.connect(
        lambda _checked=False: owner._set_dashboard_content_mode(1)
    )
    owner.dashboard_mode_group.addButton(owner.dashboard_car_button)
    owner.dashboard_mode_group.addButton(owner.dashboard_creator_button)

    owner.car_search = QLineEdit()
    owner.car_search.setPlaceholderText(tr("dashboard.search_vehicle"))
    owner.car_search.setMinimumWidth(0)
    owner.car_search.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )
    owner._connect_debounced_search(owner.car_search, owner._filter_dashboard_table)

    controls.addWidget(owner.dashboard_car_button, 0, 0)
    controls.addWidget(owner.dashboard_creator_button, 0, 1)
    controls.setColumnStretch(2, 1)
    controls.addWidget(owner.car_search, 1, 0, 1, 3)
    layout.addLayout(controls)

    owner.dashboard_content_stack = QStackedWidget()
    _append_dashboard_table(
        owner,
        owner.dashboard_content_stack,
        "car",
        (tr("table.car_id"), tr("table.vehicle"), tr("table.livery"), tr("table.tuning")),
        sort_bar_factory,
    )
    _append_dashboard_table(
        owner,
        owner.dashboard_content_stack,
        "creator",
        (tr("table.total"), tr("table.creator"), tr("table.livery"), tr("table.tuning")),
        sort_bar_factory,
    )
    layout.addWidget(owner.dashboard_content_stack)
    return panel


def _append_dashboard_table(
    owner: Any,
    stack: QStackedWidget,
    kind: str,
    headers: tuple[str, ...],
    sort_bar_factory: WidgetFactory,
) -> None:
    table = owner._table(headers)
    update = owner._update_selected_car if kind == "car" else owner._update_selected_creator
    sort = owner._sort_car_dashboard if kind == "car" else owner._sort_creator_dashboard
    section = (
        owner._dashboard_car_sort_section
        if kind == "car"
        else owner._dashboard_creator_sort_section
    )
    order = (
        owner._dashboard_car_sort_order
        if kind == "car"
        else owner._dashboard_creator_sort_order
    )
    table.itemSelectionChanged.connect(update)
    owner._configure_dashboard_table(table)
    sort_bar = sort_bar_factory(table, headers)
    sort_bar.sortRequested.connect(sort)
    sort_bar.set_active_sort(section, order)
    setattr(owner, f"{kind}_table", table)
    setattr(owner, f"{kind}_sort_bar", sort_bar)

    pane = QWidget()
    pane_layout = QVBoxLayout(pane)
    pane_layout.setContentsMargins(0, 0, 0, 0)
    pane_layout.setSpacing(0)
    pane_layout.addWidget(sort_bar)
    pane_layout.addWidget(table, 1)
    stack.addWidget(pane)


def _build_selection_panel(owner: Any) -> QFrame:
    panel = QFrame()
    panel.setObjectName("panel")
    panel.setMinimumWidth(280)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 14, 14, 14)

    owner.selected_title = QLabel(tr("dashboard.select_vehicle"))
    owner.selected_title.setStyleSheet("font-size:13pt;font-weight:700;")
    owner.selected_hint = QLabel("")
    owner.selected_hint.setWordWrap(True)
    owner.selected_hint.setObjectName("muted")
    owner.selected_hint.hide()
    layout.addWidget(owner.selected_title)
    layout.addWidget(owner.selected_hint)

    owner.saved_livery_section = owner._dashboard_saved_section_header(
        tr("content.source_my_designs"), "livery"
    )
    layout.addWidget(owner.saved_livery_section)
    owner.selected_liveries = owner._table(
        ("", tr("table.livery_name"), tr("table.creator_short"))
    )
    layout.addWidget(owner.selected_liveries, 1)

    owner.saved_tuning_section = owner._dashboard_saved_section_header(
        tr("dashboard.saved_tuning"), "tuning"
    )
    layout.addWidget(owner.saved_tuning_section)
    owner.selected_tunings = owner._table(
        ("", tr("table.name"), tr("table.creator_short"), tr("table.size"))
    )
    layout.addWidget(owner.selected_tunings, 1)
    return panel
