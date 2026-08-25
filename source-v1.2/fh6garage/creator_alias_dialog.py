from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from . import v1_3_2_change_view_alias_patch as _alias
from .i18n import tr


def open_creator_alias_dialog(window: Any) -> None:
    previous = getattr(window, "_fh6_alias_dialog", None)
    if isinstance(previous, QDialog) and previous.isVisible():
        previous.raise_()
        previous.activateWindow()
        return

    dialog = QDialog(window, Qt.WindowType.Window)
    dialog.setWindowTitle(_alias._txt("제작자 이름 관리", "Creator name manager"))
    dialog.setModal(False)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.resize(760, 560)
    window._fh6_alias_dialog = dialog
    dialog.destroyed.connect(lambda *_args: setattr(window, "_fh6_alias_dialog", None))

    root = QVBoxLayout(dialog)
    root.setContentsMargins(16, 16, 16, 16)
    root.setSpacing(10)

    explanation = QLabel(
        _alias._txt(
            "같은 제작자의 기존 이름을 신규 이름으로 연결합니다. 예: A→B, B→C이면 C (B, A). FH6 원본 파일은 수정하지 않습니다.",
            "Link an existing creator name to a new name. Example: A→B then B→C becomes C (B, A). FH6 files are not modified.",
        )
    )
    explanation.setWordWrap(True)
    explanation.setObjectName("muted")
    root.addWidget(explanation)

    form = QGridLayout()
    form.setHorizontalSpacing(8)
    form.setVerticalSpacing(8)

    form.addWidget(QLabel(_alias._txt("기존 이름", "Existing name")), 0, 0)
    source = QComboBox()
    source.setEditable(True)
    form.addWidget(source, 0, 1)

    form.addWidget(QLabel(_alias._txt("신규 이름", "New name")), 1, 0)
    target = QComboBox()
    target.setEditable(True)
    form.addWidget(target, 1, 1)

    link_button = QPushButton(_alias._txt("이름 연결", "Link names"))
    link_button.setObjectName("primary")
    unlink_button = QPushButton(_alias._txt("연결 해제", "Unlink"))
    unlink_button.setObjectName("secondary")
    form.addWidget(link_button, 0, 2)
    form.addWidget(unlink_button, 1, 2)
    form.setColumnStretch(1, 1)
    root.addLayout(form)

    table = QTableWidget(0, 3)
    table.setHorizontalHeaderLabels(
        (
            _alias._txt("현재 이름", "Current"),
            _alias._txt("이전 이름", "Previous"),
            _alias._txt("검색 이름 수", "Search names"),
        )
    )
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    root.addWidget(table, 1)

    bottom = QHBoxLayout()
    reset_button = QPushButton(_alias._txt("이름 매칭 초기화", "Reset name matching"))
    reset_button.setObjectName("secondary")
    close_button = QPushButton(tr("common.close"))
    close_button.setObjectName("primary")
    close_button.clicked.connect(dialog.close)
    bottom.addWidget(reset_button)
    bottom.addStretch(1)
    bottom.addWidget(close_button)
    root.addLayout(bottom)

    first_rebuild = True

    def rebuild(*, preserve_inputs: bool = True) -> None:
        nonlocal first_rebuild
        names = _alias._observed_creator_names(window)
        source_text = source.currentText().strip() if preserve_inputs and not first_rebuild else ""
        target_text = target.currentText().strip() if preserve_inputs and not first_rebuild else ""

        source.blockSignals(True)
        target.blockSignals(True)
        source.clear()
        target.clear()
        source.addItems(names)
        target.addItems(names)
        if source_text:
            source.setCurrentText(source_text)
        else:
            source.setCurrentIndex(-1)
            if source.lineEdit() is not None:
                source.lineEdit().clear()
        if target_text:
            target.setCurrentText(target_text)
        else:
            target.setCurrentIndex(-1)
            if target.lineEdit() is not None:
                target.lineEdit().clear()
        source.blockSignals(False)
        target.blockSignals(False)

        table.setRowCount(0)
        groups = [group for group in window.creator_aliases.groups if len(group.all_names()) > 1]
        groups.sort(key=lambda group: group.current.casefold())
        for group in groups:
            row = table.rowCount()
            table.insertRow(row)
            current_item = QTableWidgetItem(group.current)
            current_item.setData(Qt.ItemDataRole.UserRole, list(group.all_names()))
            table.setItem(row, 0, current_item)
            previous_item = QTableWidgetItem(", ".join(group.previous))
            previous_item.setData(Qt.ItemDataRole.UserRole, list(group.all_names()))
            table.setItem(row, 1, previous_item)
            count_item = QTableWidgetItem(str(len(group.all_names())))
            count_item.setData(Qt.ItemDataRole.UserRole, list(group.all_names()))
            table.setItem(row, 2, count_item)

        table.clearSelection()
        table.setCurrentItem(None)
        first_rebuild = False

    def link_names() -> None:
        old = source.currentText().strip()
        new = target.currentText().strip()
        if not old or not new:
            QMessageBox.information(
                dialog,
                _alias._txt("입력 필요", "Names required"),
                _alias._txt("두 이름을 모두 입력하세요.", "Enter both names."),
            )
            return
        if old.casefold() == new.casefold():
            return

        old_group = window.creator_aliases.find_group(old)
        new_group = window.creator_aliases.find_group(new)
        observed = {name.casefold() for name in _alias._observed_creator_names(window)}
        different_group = new_group is not None and old_group is not new_group
        if new.casefold() in observed or different_group:
            answer = QMessageBox.question(
                dialog,
                _alias._txt("제작자 연결 확인", "Confirm creator link"),
                _alias._txt(
                    f"'{new}' 이름이 이미 존재합니다. '{old}'가 속한 그룹 전체와 '{new}' 그룹을 동일 제작자로 연결하시겠습니까?",
                    f"'{new}' already exists. Link the entire group containing '{old}' with the '{new}' group?",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        window.creator_aliases.merge(old, new)
        _alias._refresh_alias_views(window)
        source.setCurrentIndex(-1)
        target.setCurrentIndex(-1)
        if source.lineEdit() is not None:
            source.lineEdit().clear()
        if target.lineEdit() is not None:
            target.lineEdit().clear()
        rebuild(preserve_inputs=False)

    def unlink_selected_group() -> None:
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(
                dialog,
                _alias._txt("선택 필요", "Selection required"),
                _alias._txt(
                    "아래 목록에서 연결을 해제할 항목을 선택하세요.",
                    "Select a linked-name entry in the list below.",
                ),
            )
            return

        item = table.item(row, 0)
        names = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(names, list) or len(names) <= 1:
            return

        # Dissolve only the selected linked group. The global reset button remains
        # the only action that clears every creator-name relationship.
        for name in list(names[1:]):
            window.creator_aliases.split(str(name))

        _alias._refresh_alias_views(window)
        rebuild(preserve_inputs=True)

    def reset_aliases() -> None:
        answer = QMessageBox.question(
            dialog,
            _alias._txt("이름 매칭 초기화", "Reset name matching"),
            _alias._txt(
                "모든 제작자 이름 연결을 초기화합니다. 초기화 직전에 현재 매칭 파일을 자동 백업합니다. 계속하시겠습니까?",
                "Reset all creator-name links. The current matching file will be backed up automatically immediately before reset. Continue?",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            backup = window.creator_aliases.reset_with_backup()
        except OSError as exc:
            QMessageBox.warning(dialog, _alias._txt("초기화 실패", "Reset failed"), str(exc))
            return

        _alias._refresh_alias_views(window)
        rebuild(preserve_inputs=False)
        message = _alias._txt("이름 매칭을 초기화했습니다.", "Creator name matching was reset.")
        if backup is not None:
            message += "\n\n" + _alias._txt("백업: ", "Backup: ") + str(backup)
        QMessageBox.information(dialog, _alias._txt("초기화 완료", "Reset complete"), message)

    link_button.clicked.connect(link_names)
    unlink_button.clicked.connect(unlink_selected_group)
    reset_button.clicked.connect(reset_aliases)

    dialog._fh6_alias_source = source
    dialog._fh6_alias_target = target
    dialog._fh6_alias_table = table
    dialog._fh6_alias_link_button = link_button
    dialog._fh6_alias_unlink_button = unlink_button

    rebuild(preserve_inputs=False)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
