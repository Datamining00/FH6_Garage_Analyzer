from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from .i18n import get_language, tr
from .livery_visibility import eye_slash_pixmap, visibility_labels
from .models import LiveryRecord, TuningRecord
from .tune_data import TuneDataError, read_tune_data


def show_livery_metadata(owner: Any, record: LiveryRecord, *, app_style: str) -> None:
    key = owner._content_annotation_key("livery", record)
    labels = visibility_labels((get_language() or "ko").startswith("ko"))
    dialog = QDialog(owner)
    dialog.setWindowTitle(tr("detail.livery_info_title"))
    dialog.setModal(True)
    dialog.resize(560, 360)
    dialog.setStyleSheet(app_style)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)

    vehicle = QLabel(owner._car_label(record.header.car_id))
    vehicle.setStyleSheet("font-size:13pt;font-weight:700;")
    layout.addWidget(vehicle)
    title = QLabel(
        tr("detail.livery_prefix", name=record.header.name or tr("detail.no_title"))
    )
    title.setObjectName("muted")
    layout.addWidget(title)

    hide_row = QHBoxLayout()
    hide_row.addStretch(1)
    hide_button = QToolButton()
    hide_button.setCheckable(True)
    icon = QIcon()
    icon.addPixmap(eye_slash_pixmap(False), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(eye_slash_pixmap(True), QIcon.Mode.Normal, QIcon.State.On)
    hide_button.setIcon(icon)
    hide_button.setIconSize(QSize(22, 22))
    hide_button.setChecked(owner._fh6_v132_is_livery_hidden(key))
    hide_button.setToolTip(labels["hide_toggle"])
    hide_button.setAccessibleName(labels["hide_toggle"])
    hide_button.setFixedSize(38, 38)
    hide_button.setStyleSheet(
        "QToolButton { background:white; border:1px solid #dfe1e8; "
        "border-radius:9px; padding:0; }"
        "QToolButton:hover { border-color:#8c74ee; background:#f5f2ff; }"
        "QToolButton:checked { border-color:#8c74ee; background:#eee9ff; }"
    )
    hide_button.toggled.connect(
        lambda enabled, content_key=key: owner._fh6_v132_set_livery_hidden(
            content_key, enabled
        )
    )
    hide_row.addWidget(hide_button)
    layout.addLayout(hide_row)

    layout.addWidget(QLabel(tr("detail.description")))
    description = QPlainTextEdit()
    description.setReadOnly(True)
    description.setPlainText(
        (record.header.description or "").strip() or tr("detail.no_description")
    )
    layout.addWidget(description, 1)
    uploaded = record.header.created or tr("common.unavailable")
    layout.addWidget(QLabel(tr("detail.uploaded", date=uploaded)))
    close_button = QPushButton(tr("common.close"))
    close_button.setObjectName("primary")
    close_button.clicked.connect(dialog.accept)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(close_button)
    layout.addLayout(row)
    owner._apply_pointing_cursors(dialog)
    dialog.exec()


def show_tuning_details(owner: Any, record: TuningRecord, *, app_style: str) -> None:
    dialog = QDialog(owner)
    dialog.setWindowTitle(tr("detail.tuning_title"))
    dialog.setModal(True)
    dialog.resize(720, 720)
    dialog.setStyleSheet(app_style)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)

    heading = QLabel(owner._car_label(record.header.car_id))
    heading.setStyleSheet("font-size:13pt;font-weight:700;")
    layout.addWidget(heading)
    details = QPlainTextEdit()
    details.setReadOnly(True)
    details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    lines = [
        tr("detail.basic_info"),
        tr("detail.title_line", value=record.header.name or tr("detail.no_title")),
        tr("detail.creator_line", value=record.header.creator or "—"),
        tr(
            "detail.description_line",
            value=(record.header.description or "").strip()
            or tr("detail.no_description"),
        ),
        tr(
            "detail.uploaded",
            date=record.header.created or tr("common.unavailable"),
        ),
        "",
    ]
    if record.data_path is None:
        lines.extend((tr("detail.data_file"), tr("detail.data_missing")))
    else:
        try:
            parsed = read_tune_data(record.data_path)
        except TuneDataError as exc:
            lines.extend(
                (tr("detail.data_file"), tr("detail.read_failed", error=exc))
            )
        else:
            lines.extend(
                (
                    tr("detail.data_file"),
                    tr("detail.format_version", value=parsed.format_version),
                    tr(
                        "detail.lock_state",
                        value=tr("detail.locked")
                        if parsed.locked
                        else tr("detail.unlocked"),
                    ),
                    tr("detail.car_ordinal", value=parsed.car_ordinal_id),
                    "",
                    tr("detail.installed_parts"),
                )
            )
            lines.extend(
                f"0x{offset:04X}  {label}: 0x{value:08X}"
                for offset, label, value in parsed.parts
            )
            lines.extend(("", tr("detail.tuning_values")))
            lines.extend(
                f"0x{offset:04X}  {label}: {value:.6g}"
                for offset, label, value in parsed.values
            )
            if record.header.car_id is not None:
                lines.extend(
                    (
                        "",
                        tr("detail.validation"),
                        tr("detail.header_car_id", value=record.header.car_id),
                        tr("detail.data_ordinal", value=parsed.car_ordinal_id),
                    )
                )
    details.setPlainText("\n".join(lines))
    layout.addWidget(details, 1)
    close_button = QPushButton(tr("common.close"))
    close_button.setObjectName("primary")
    close_button.clicked.connect(dialog.accept)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(close_button)
    layout.addLayout(row)
    dialog.exec()
