from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from .i18n import tr


def build_saved_content_controls(
    owner: Any,
    content_type: str,
    *,
    filter_button_factory: Callable[..., Any],
    install_source_controls: Callable[[Any, QVBoxLayout], None],
) -> tuple[
    QVBoxLayout,
    QLineEdit,
    Any,
    QButtonGroup,
    dict[str, QPushButton],
]:
    """Create two toolbar rows: search/filter, then sort/view/actions."""
    controls = QVBoxLayout()
    controls.setSpacing(7)
    search_row = QHBoxLayout()
    action_row = QHBoxLayout()
    action_row.setSpacing(7)
    owner._saved_content_action_rows[content_type] = action_row

    search = QLineEdit()
    search.setPlaceholderText(tr("content.search_placeholder"))
    owner._connect_debounced_search(
        search,
        lambda text, kind=content_type: owner._request_saved_content_filter(kind, text),
    )
    search_row.addWidget(search, 1)

    status_filter = filter_button_factory(content_type == "livery", owner)
    status_filter.selectionChanged.connect(
        lambda kind=content_type, field=search: owner._request_saved_content_filter(
            kind, field.text()
        )
    )
    search_row.addWidget(status_filter)
    controls.addLayout(search_row)

    sort_label = QLabel(tr("content.sort_label"))
    sort_label.setObjectName("muted")
    action_row.addWidget(sort_label)

    sort_group = QButtonGroup(owner)
    sort_group.setExclusive(True)
    sort_buttons: dict[str, QPushButton] = {}

    for mode, label_text in (
        ("default", tr("content.sort_default")),
        ("brand", tr("content.sort_brand")),
        ("creator", tr("content.sort_creator")),
        ("download", tr("content.sort_download")),
    ):
        button = QPushButton(label_text)
        button.setObjectName("secondary")
        button.setCheckable(True)
        if mode == "default":
            button.setChecked(True)
        button.clicked.connect(
            lambda _checked=False, kind=content_type, selected_mode=mode: owner._set_saved_content_sort_mode(
                kind, selected_mode
            )
        )
        sort_group.addButton(button)
        sort_buttons[mode] = button
        action_row.addWidget(button)

    separator = QLabel("││")
    separator.setObjectName("sortGroupSeparator")
    separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
    separator.setStyleSheet("color:#b1a8c9; font-weight:700; padding:0 2px;")
    action_row.addWidget(separator)

    group_button = QPushButton(tr("content.group_vehicle"))
    group_button.setObjectName("secondary")
    group_button.setCheckable(True)
    group_button.setChecked(
        owner.local_preferences.get_bool(
            f"{content_type}_group_by_vehicle",
            False,
        )
    )
    group_button.setToolTip(tr("content.group_vehicle_tip"))
    group_button.toggled.connect(
        lambda checked, kind=content_type: owner._set_vehicle_grouping(kind, checked)
    )
    setattr(owner, f"{content_type}_group_button", group_button)
    action_row.addWidget(group_button)

    creator_group_button = QPushButton(tr("content.group_creator"))
    creator_group_button.setObjectName("secondary")
    creator_group_button.setCheckable(True)
    creator_group_button.setChecked(
        owner.local_preferences.get_bool(
            f"{content_type}_group_by_creator",
            False,
        )
    )
    if group_button.isChecked() and creator_group_button.isChecked():
        creator_group_button.setChecked(False)
        owner.local_preferences.set_bool(
            f"{content_type}_group_by_creator",
            False,
        )
    creator_group_button.setToolTip(tr("content.group_creator_tip"))
    creator_group_button.toggled.connect(
        lambda checked, kind=content_type: owner._set_creator_grouping(kind, checked)
    )
    setattr(owner, f"{content_type}_creator_group_button", creator_group_button)
    action_row.addWidget(creator_group_button)

    action_row.addStretch(1)
    controls.addLayout(action_row)

    if content_type == "livery":
        install_source_controls(owner, controls)

    return controls, search, status_filter, sort_group, sort_buttons
