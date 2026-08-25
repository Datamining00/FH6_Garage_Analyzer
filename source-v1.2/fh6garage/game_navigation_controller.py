from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .auction_ui_safety import is_auction_livery
from .game_navigation import GameNavigationError, send_arrow_keys_to_fh6
from .i18n import get_language, tr
from .livery_visibility import visibility_labels


def request_game_navigation(owner: Any, content_type: str, key: str) -> None:
    record = owner._record_for_content_key(content_type, key)
    if content_type == "livery" and is_auction_livery(record):
        return
    if content_type == "livery" and owner._fh6_v132_is_livery_hidden(key):
        labels = visibility_labels((get_language() or "ko").startswith("ko"))
        owner._show_status(labels["hidden_move"], 3500)
        return
    if owner._game_navigation_pending:
        QMessageBox.information(
            owner, tr("navigation.pending_title"), tr("navigation.pending_message")
        )
        return
    session = owner._game_navigation_sessions.get(content_type)
    if session is None or record is None or not session.contains(key):
        QMessageBox.warning(
            owner,
            tr("navigation.unavailable_title"),
            tr("navigation.unavailable_message"),
        )
        return

    dialog = QDialog(owner)
    dialog.setWindowTitle(tr("navigation.dialog_title"))
    dialog.setModal(True)
    dialog.setMinimumWidth(520)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)

    target_panel = QFrame()
    target_panel.setObjectName("panel")
    target_layout = QVBoxLayout(target_panel)
    target_layout.setContentsMargins(12, 9, 12, 9)
    target_layout.setSpacing(2)
    vehicle_label = QLabel(owner._car_label(record.car_id))
    vehicle_label.setStyleSheet("font-weight: 700; font-size: 11pt;")
    title_label = QLabel(record.header.name or tr("detail.no_title"))
    title_label.setObjectName("muted")
    target_layout.addWidget(vehicle_label)
    target_layout.addWidget(title_label)
    layout.addWidget(target_panel)

    description = QLabel(tr("navigation.description"))
    description.setWordWrap(True)
    layout.addWidget(description)
    delete_notice = QLabel(tr("navigation.delete_notice"))
    delete_notice.setWordWrap(True)
    delete_notice.setStyleSheet(
        "background: #fff7e8; color: #7a4b00; border: 1px solid #f0d6a6; "
        "border-radius: 8px; padding: 8px 10px;"
    )
    layout.addWidget(delete_notice)

    settings_panel = QFrame()
    settings_panel.setObjectName("panel")
    settings_layout = QGridLayout(settings_panel)
    settings_layout.setContentsMargins(12, 9, 12, 9)
    settings_layout.setHorizontalSpacing(12)
    settings_layout.setVerticalSpacing(7)
    settings_title = QLabel(tr("navigation.settings_title"))
    settings_title.setStyleSheet("font-weight: 700;")
    settings_layout.addWidget(settings_title, 0, 0, 1, 2)

    settings_layout.addWidget(QLabel(tr("navigation.delay")), 1, 0)
    delay_spin = QDoubleSpinBox()
    delay_spin.setRange(0.1, 30.0)
    delay_spin.setDecimals(1)
    delay_spin.setSingleStep(0.1)
    delay_spin.setSuffix(tr("common.seconds_suffix"))
    delay_spin.setValue(owner.settings.value("game_navigation_delay", 1.0, float))
    settings_layout.addWidget(delay_spin, 1, 1)

    settings_layout.addWidget(QLabel(tr("navigation.arrow_interval")), 2, 0)
    arrow_interval_spin = QSpinBox()
    arrow_interval_spin.setRange(20, 500)
    arrow_interval_spin.setSuffix(tr("common.milliseconds_suffix"))
    arrow_interval_spin.setValue(
        owner.settings.value("game_navigation_arrow_interval_ms", 70, int)
    )
    settings_layout.addWidget(arrow_interval_spin, 2, 1)

    auto_activate_box = QCheckBox(tr("navigation.auto_activate"))
    auto_activate_box.setChecked(
        owner.settings.value("game_navigation_auto_activate", True, bool)
    )
    auto_activate_box.setToolTip(tr("navigation.auto_activate_tip"))
    settings_layout.addWidget(auto_activate_box, 3, 0, 1, 2)
    settings_layout.setColumnStretch(1, 1)
    layout.addWidget(settings_panel)

    choice = {"mode": ""}
    button_row = QHBoxLayout()
    delete_button = QPushButton(tr("navigation.move_delete"))
    delete_button.setObjectName("secondary")
    apply_button = QPushButton(tr("navigation.move_apply"))
    apply_button.setObjectName("primary")
    cancel_button = QPushButton(tr("common.cancel"))
    cancel_button.setObjectName("secondary")
    delete_button.clicked.connect(
        lambda: (choice.__setitem__("mode", "delete"), dialog.accept())
    )
    apply_button.clicked.connect(
        lambda: (choice.__setitem__("mode", "apply"), dialog.accept())
    )
    cancel_button.clicked.connect(dialog.reject)
    button_row.addWidget(delete_button)
    button_row.addWidget(apply_button)
    button_row.addStretch(1)
    button_row.addWidget(cancel_button)
    layout.addLayout(button_row)

    if dialog.exec() != QDialog.DialogCode.Accepted or not choice["mode"]:
        return
    delay = delay_spin.value()
    auto_activate = auto_activate_box.isChecked()
    arrow_interval_ms = arrow_interval_spin.value()
    try:
        planned_keys = session.plan_from_first(key)
    except GameNavigationError as exc:
        QMessageBox.warning(owner, tr("navigation.unavailable_title"), str(exc))
        return

    owner.settings.setValue("game_navigation_delay", delay)
    owner.settings.setValue("game_navigation_auto_activate", auto_activate)
    owner.settings.setValue("game_navigation_arrow_interval_ms", arrow_interval_ms)
    owner._game_navigation_pending = True
    generation = owner._game_navigation_generation
    mode = choice["mode"]
    delay_text = tr("navigation.delay_text", value=f"{delay:g}")
    wait_message = (
        tr("navigation.wait_auto", delay=delay_text)
        if auto_activate
        else tr("navigation.wait_manual", delay=delay_text)
    )
    owner._show_status(wait_message, int((delay + 8) * 1000))
    QTimer.singleShot(
        int(round(delay * 1000)),
        lambda: owner._execute_game_navigation(
            content_type,
            key,
            planned_keys,
            mode,
            generation,
            auto_activate,
            arrow_interval_ms,
        ),
    )


def execute_game_navigation(
    owner: Any,
    content_type: str,
    key: str,
    planned_keys: list[str],
    mode: str,
    generation: int,
    auto_activate: bool,
    arrow_interval_ms: int,
) -> None:
    owner._game_navigation_pending = False
    if generation != owner._game_navigation_generation:
        owner._show_status(tr("navigation.cancelled_refresh"), 5000)
        return
    session = owner._game_navigation_sessions.get(content_type)
    if session is None or not session.contains(key):
        owner._show_status(tr("navigation.cancelled_changed"), 5000)
        return
    try:
        window_title = send_arrow_keys_to_fh6(
            planned_keys,
            interval=arrow_interval_ms / 1000.0,
            auto_activate=auto_activate,
        )
    except GameNavigationError as exc:
        QMessageBox.warning(owner, tr("navigation.cancel_title"), str(exc))
        owner._show_status(tr("navigation.focus_failed"), 5000)
        return

    deleted = mode == "delete"
    session.complete_move(key, deleted=deleted)
    count = len(planned_keys)
    message = (
        tr("navigation.complete_deleted", count=count, window=window_title)
        if deleted
        else tr("navigation.complete_applied", count=count, window=window_title)
    )
    owner._show_status(message, 8000)
