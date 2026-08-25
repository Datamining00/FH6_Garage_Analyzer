from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox

from .annotations import append_note
from .i18n import tr


def apply_note_to_same_creator(
    owner: Any,
    source_key: str,
    source_note: str,
) -> None:
    source_record = owner._record_for_annotation_key(source_key)
    if source_record is None:
        return
    creator = (source_record.header.creator or "").strip()
    note = (source_note or "").strip()
    if not creator:
        QMessageBox.information(
            owner,
            tr("memo.creator_missing_title"),
            tr("memo.creator_missing_apply"),
        )
        return
    if not note:
        QMessageBox.information(
            owner,
            tr("memo.missing_title"),
            tr("memo.enter_first"),
        )
        return

    creator_key = creator.casefold()
    targets = [
        record
        for record in owner._custom_liveries()
        if (record.header.creator or "").strip().casefold() == creator_key
    ]
    answer = QMessageBox.question(
        owner,
        tr("memo.append_confirm_title"),
        tr(
            "memo.append_confirm_message",
            creator=creator,
            targets=len(targets),
            existing=owner._creator_livery_note_count(creator),
        ),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return

    owner.annotations.set(source_key, note=note, save=False)
    affected = 0
    for record in targets:
        key = owner._annotation_key(record)
        current = owner.annotations.get(key).note
        merged = append_note(current, note)
        if merged != current:
            affected += 1
        owner.annotations.set(key, note=merged, save=False)
    owner.annotations.save()
    owner._refresh_annotation_widgets()
    owner._show_status(tr("memo.apply_status", creator=creator), 3500)
    QMessageBox.information(
        owner,
        tr("memo.apply_title"),
        tr(
            "memo.apply_message",
            creator=creator,
            targets=len(targets),
            affected=affected,
        ),
    )


def clear_notes_for_same_creator(owner: Any, source_key: str) -> bool:
    source_record = owner._record_for_annotation_key(source_key)
    if source_record is None:
        return False
    creator = (source_record.header.creator or "").strip()
    if not creator:
        QMessageBox.information(
            owner,
            tr("memo.creator_missing_title"),
            tr("memo.creator_missing_remove"),
        )
        return False

    creator_key = creator.casefold()
    targets = [
        record
        for record in owner._custom_liveries()
        if (record.header.creator or "").strip().casefold() == creator_key
    ]
    with_notes = sum(
        1
        for record in targets
        if owner.annotations.get(owner._annotation_key(record)).note.strip()
    )
    if with_notes == 0:
        QMessageBox.information(
            owner,
            tr("memo.none_to_remove_title"),
            tr("memo.none_to_remove_message", creator=creator),
        )
        return False

    answer = QMessageBox.question(
        owner,
        tr("memo.clear_title"),
        tr("memo.clear_message", creator=creator, count=with_notes),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return False

    for record in targets:
        key = owner._annotation_key(record)
        owner.annotations.set(key, note="", save=False)
    owner.annotations.save()
    owner._refresh_annotation_widgets()
    owner._show_status(
        tr("memo.clear_status", creator=creator, count=with_notes),
        3500,
    )
    return True
