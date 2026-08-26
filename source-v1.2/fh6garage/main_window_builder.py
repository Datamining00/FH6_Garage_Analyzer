from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .i18n import SUPPORTED_LANGUAGES, get_language, tr
from .version import SIDEBAR_VERSION


def build_main_window(owner: Any) -> None:
    root = QWidget()
    owner.setCentralWidget(root)
    outer = QHBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    sidebar = QFrame()
    sidebar.setObjectName("sidebar")
    sidebar.setFixedWidth(170)
    side = QVBoxLayout(sidebar)
    side.setContentsMargins(15, 18, 15, 18)
    brand = QLabel("FH6\nASSISTANT")
    brand.setObjectName("brand")
    side.addWidget(brand)

    owner.nav_group = QButtonGroup(owner)
    owner.nav_group.setExclusive(True)
    owner.nav_buttons: list[QPushButton] = []
    for index, label in enumerate(
        (tr("nav.dashboard"), tr("nav.livery"), tr("nav.tuning"))
    ):
        button = QPushButton(label)
        button.setObjectName("nav")
        button.setCheckable(True)
        if index == 0:
            button.setChecked(True)
        button.clicked.connect(
            lambda checked=False, page_index=index: owner.pages.setCurrentIndex(
                page_index
            )
        )
        owner.nav_group.addButton(button)
        owner.nav_buttons.append(button)
        side.addWidget(button)
    side.addStretch(1)

    owner.language_label = QLabel(tr("language.label"))
    owner.language_label.setStyleSheet(
        "color:#8d91a0; padding:0 6px 2px 6px; font-size:9pt;"
    )
    side.addWidget(owner.language_label)

    owner.language_combo = QComboBox()
    owner.language_combo.setAccessibleName(tr("language.label"))
    for language_code, display_name in SUPPORTED_LANGUAGES.items():
        owner.language_combo.addItem(display_name, language_code)
    active_language_index = owner.language_combo.findData(get_language())
    if active_language_index >= 0:
        owner.language_combo.setCurrentIndex(active_language_index)
    owner.language_combo.setStyleSheet(
        "QComboBox { background:#242632; color:#f0f1f5; "
        "border:1px solid #343746; border-radius:7px; padding:6px 8px; }"
        "QComboBox:hover { border-color:#6e4bf2; }"
        "QComboBox::drop-down { border:0; width:22px; }"
        "QComboBox QAbstractItemView { background:#242632; color:#f0f1f5; "
        "selection-background-color:#6e4bf2; selection-color:white; }"
    )
    owner.language_combo.currentIndexChanged.connect(
        owner._on_language_preference_changed
    )
    side.addWidget(owner.language_combo)

    owner.always_on_top_box = QCheckBox(tr("sidebar.always_on_top"))
    owner.always_on_top_box.setStyleSheet(
        "QCheckBox { color:#c7c9d4; spacing:7px; padding:7px 6px; }"
        "QCheckBox:hover { color:white; }"
    )
    owner.always_on_top_box.setChecked(
        owner.settings.value("window_always_on_top", False, bool)
    )
    owner.always_on_top_box.setToolTip(tr("sidebar.always_on_top_tip"))
    owner.always_on_top_box.toggled.connect(owner._set_always_on_top)
    side.addWidget(owner.always_on_top_box)
    version = QLabel(SIDEBAR_VERSION)
    version.setStyleSheet("color:#777b8b; padding:8px;")
    side.addWidget(version)
    outer.addWidget(sidebar)

    content = QWidget()
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(22, 18, 22, 18)
    content_layout.setSpacing(14)

    top = QHBoxLayout()
    owner.path_edit = QLineEdit()
    owner.path_edit.setReadOnly(True)
    owner.path_edit.setPlaceholderText(tr("save.placeholder"))
    choose = QPushButton(tr("save.choose_folder"))
    choose.setObjectName("primary")
    choose.clicked.connect(owner.choose_save_folder)
    refresh = QPushButton(tr("save.refresh"))
    refresh.setObjectName("secondary")
    refresh.clicked.connect(owner.refresh_scan)
    top.addWidget(owner.path_edit, 1)
    top.addWidget(choose)
    top.addWidget(refresh)
    content_layout.addLayout(top)

    owner.pages = QStackedWidget()
    owner.pages.addWidget(owner._dashboard_page())
    owner.pages.addWidget(owner._livery_page())
    owner.pages.addWidget(owner._tuning_page())
    owner.pages.currentChanged.connect(owner._on_main_page_changed)
    content_layout.addWidget(owner.pages, 1)
    outer.addWidget(content, 1)
