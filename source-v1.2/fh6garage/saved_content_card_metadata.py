from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from .i18n import tr
from .models import LiveryRecord, TuningRecord


CopyLabelFactory = Callable[[str, str], QLabel]


def append_card_metadata(
    owner: Any,
    outer: QVBoxLayout,
    record: LiveryRecord | TuningRecord,
    copy_label_factory: CopyLabelFactory,
) -> None:
    """Append the vehicle, title, and creator rows shared by saved-content cards."""
    content_name = record.header.name or "(unnamed)"
    creator_name = record.header.creator or "—"
    vehicle_name = owner._car_label(record.header.car_id)

    vehicle = copy_label_factory(tr("card.vehicle_label"), vehicle_name)
    vehicle.setStyleSheet(
        "QLabel { background:transparent; color:#171924; border:0; "
        "padding:4px 2px 1px 2px; font-size:11.5pt; font-weight:700; }"
    )
    vehicle.setFixedHeight(31)
    vehicle.setToolTip(
        tr(
            "common.copy_value_detail",
            label=tr("card.vehicle_label"),
            value=vehicle_name,
        )
    )
    vehicle.setMinimumWidth(0)
    vehicle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    outer.addWidget(vehicle)

    meta_row = QHBoxLayout()
    meta_row.setContentsMargins(0, 0, 0, 0)
    meta_row.setSpacing(7)

    title = copy_label_factory(tr("card.title_label"), content_name)
    title.setStyleSheet(
        "QLabel { background:transparent; color:#343744; border:0; padding:2px; "
        "font-size:10pt; font-weight:600; }"
    )
    title.setFixedHeight(28)
    title.setToolTip(
        tr(
            "common.copy_value_detail",
            label=tr("card.title_label"),
            value=content_name,
        )
    )
    title.setMinimumWidth(0)
    title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    meta_row.addWidget(title, 3)

    creator = copy_label_factory(tr("card.creator_label"), creator_name)
    creator.setStyleSheet(
        "QLabel { background:transparent; color:#6d7282; border:0; padding:2px; "
        "font-size:9.5pt; font-weight:500; }"
    )
    creator.setFixedHeight(28)
    creator.setToolTip(
        tr(
            "common.copy_value_detail",
            label=tr("card.creator_label"),
            value=creator_name,
        )
    )
    creator.setMinimumWidth(0)
    creator.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    meta_row.addWidget(creator, 2)
    outer.addLayout(meta_row)
