from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .i18n import tr
from .models import LiveryRecord


def edit_content_note_dialog(
    owner: Any,
    current_note: str,
    content_type: str,
    key: str = "",
    *,
    app_style: str,
) -> Optional[str]:
    dialog = QDialog(owner)
    dialog.setWindowTitle(
        tr("memo.livery_title")
        if content_type == "livery"
        else tr("memo.tuning_title")
    )
    dialog.setModal(True)
    dialog.resize(
        620 if content_type == "livery" else 520,
        360 if content_type == "livery" else 260,
    )
    dialog.setStyleSheet(
        app_style
        + """
        QDialog { background:#f7f8fb; }
        QTextEdit {
            background:white;
            border:1px solid #dfe1e8;
            border-radius:10px;
            padding:10px;
            color:#171924;
        }
        """
    )

    root = QVBoxLayout(dialog)
    root.setContentsMargins(14, 14, 14, 14)
    root.setSpacing(10)

    livery_record = (
        owner._record_for_content_key("livery", key)
        if content_type == "livery" and key
        else None
    )
    creator = ""
    creator_count_label: Optional[QLabel] = None

    if isinstance(livery_record, LiveryRecord):
        creator = (livery_record.header.creator or "").strip()
        info_row = QHBoxLayout()
        vehicle_label = QLabel(owner._car_label(livery_record.header.car_id))
        vehicle_label.setStyleSheet(
            "font-size:11.5pt; font-weight:700; color:#303341;"
        )
        creator_label = QLabel(
            tr(
                "memo.creator_value",
                creator=creator or tr("creator.none"),
            )
        )
        creator_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        creator_label.setStyleSheet("font-weight:700; color:#5f39d8;")
        info_row.addWidget(vehicle_label, 1)
        info_row.addWidget(creator_label, 0)
        root.addLayout(info_row)

        creator_count_label = QLabel()
        creator_count_label.setObjectName("muted")
        root.addWidget(creator_count_label)
    else:
        label = QLabel(tr("memo.label"))
        label.setStyleSheet("font-weight:600; color:#4f5567;")
        root.addWidget(label)

    editor = QTextEdit()
    editor.setPlaceholderText(tr("memo.label"))
    editor.setPlainText(current_note or "")
    root.addWidget(editor, 1)

    def refresh_creator_count() -> None:
        if creator_count_label is None or not creator:
            if creator_count_label is not None:
                creator_count_label.setText(tr("memo.creator_note_count", count=0))
            return
        creator_count_label.setText(
            tr(
                "memo.creator_note_count",
                count=owner._creator_livery_note_count(creator),
            )
        )

    if isinstance(livery_record, LiveryRecord):
        refresh_creator_count()
        bulk_buttons = QHBoxLayout()

        append_btn = QPushButton(tr("memo.add_same_creator"))
        append_btn.setObjectName("secondary")
        append_btn.setStyleSheet(
            "QPushButton { background:#f1faf4; color:#287a45; border:1px solid #9ed5b0; "
            "border-radius:8px; padding:8px 10px; font-weight:650; }"
            "QPushButton:hover { background:#e8f7ed; border-color:#65b47e; }"
        )
        clear_btn = QPushButton(tr("memo.clear_same_creator"))
        clear_btn.setObjectName("secondary")
        clear_btn.setStyleSheet(
            "QPushButton { background:#fff4f8; color:#a23867; border:1px solid #e4a5c1; "
            "border-radius:8px; padding:8px 10px; font-weight:650; }"
            "QPushButton:hover { background:#ffeaf3; border-color:#cb6d98; }"
        )
        append_btn.setEnabled(bool(creator))
        clear_btn.setEnabled(bool(creator))

        def append_to_creator() -> None:
            owner._apply_note_to_same_creator(key, editor.toPlainText())
            refresh_creator_count()

        def clear_creator_notes() -> None:
            if owner._clear_notes_for_same_creator(key):
                editor.clear()
                refresh_creator_count()

        append_btn.clicked.connect(append_to_creator)
        clear_btn.clicked.connect(clear_creator_notes)
        bulk_buttons.addWidget(append_btn)
        bulk_buttons.addWidget(clear_btn)
        root.addLayout(bulk_buttons)

    buttons = QHBoxLayout()
    buttons.addStretch(1)

    cancel_btn = QPushButton(tr("common.cancel"))
    cancel_btn.setObjectName("secondary")
    save_btn = QPushButton(tr("common.save"))
    save_btn.setObjectName("primary")

    buttons.addWidget(cancel_btn)
    buttons.addWidget(save_btn)
    root.addLayout(buttons)

    cancel_btn.clicked.connect(dialog.reject)
    save_btn.clicked.connect(dialog.accept)

    owner._apply_pointing_cursors(dialog)
    editor.setFocus()

    if dialog.exec() == QDialog.DialogCode.Accepted:
        return editor.toPlainText().strip()
    return None
