from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from . import v1_3_2_change_dialog_folder_patch as _change_dialog
from . import v1_3_2_dashboard_change_group_patch as _dashboard_changes
from .acquisition_db import DATA_DIR_NAME, AcquisitionDatabase, AcquisitionInfo
from .i18n import get_language
from .ui import APP_STYLE


def _txt(ko: str, en: str) -> str:
    return ko if (get_language() or "ko").lower().startswith("ko") else en


def _acquisition_text(info: AcquisitionInfo | None) -> str:
    if info is None:
        return "-"
    return (info.acquisition or "-").strip() or "-"


def _acquisition_tooltip(info: AcquisitionInfo | None) -> str:
    if info is None:
        return _txt("획득:\n-", "Acquisition:\n-")
    methods = list(info.methods) or ["-"]
    lines = [_txt("획득:", "Acquisition:"), *methods]
    if info.dlc_name:
        lines.extend(["", _txt("DLC:", "DLC:"), info.dlc_name])
    return "\n".join(lines)


class _ElideController(QObject):
    def __init__(self, label: QLabel, full_text: str) -> None:
        super().__init__(label)
        self.label = label
        self.full_text = full_text
        label.installEventFilter(self)
        self.apply()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in {QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.FontChange}:
            self.apply()
        return False

    def apply(self) -> None:
        try:
            width = max(1, self.label.contentsRect().width() - 4)
            text = self.label.fontMetrics().elidedText(
                self.full_text,
                Qt.TextElideMode.ElideRight,
                width,
            )
            self.label.setText(text)
        except RuntimeError:
            return


def _apply_acquisition_label(window: Any, label: QLabel, car_id: int | None) -> None:
    database = getattr(window, "acquisition_db", None)
    info = database.get(car_id) if isinstance(database, AcquisitionDatabase) else None
    full_text = f"{_txt('출처', 'Source')}: {_acquisition_text(info)}"
    label.setToolTip(_acquisition_tooltip(info))
    old_controller = getattr(label, "_fh6_acquisition_elider", None)
    if isinstance(old_controller, QObject):
        label.removeEventFilter(old_controller)
        old_controller.deleteLater()
    controller = _ElideController(label, full_text)
    label._fh6_acquisition_elider = controller
    label.setProperty("fh6AcquisitionCarId", int(car_id) if car_id is not None else -1)


def _decorate_acquisition_label(window: Any, card: Any, record: Any) -> None:
    label = card.findChild(QLabel, "fh6AcquisitionPlaceholder")
    if not isinstance(label, QLabel):
        return
    header = getattr(record, "header", None)
    car_id = getattr(header, "car_id", None)
    _apply_acquisition_label(window, label, car_id)


def _refresh_cached_acquisition_labels(window: Any) -> None:
    # Existing cards are intentionally reused for performance. Refresh only the
    # acquisition metadata so switching HDR/Datamining00 never leaves stale text.
    for label in window.findChildren(QLabel, "fh6AcquisitionPlaceholder"):
        try:
            car_id = int(label.property("fh6AcquisitionCarId"))
        except (TypeError, ValueError):
            car_id = -1
        _apply_acquisition_label(window, label, car_id if car_id > 0 else None)


def _readonly_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _open_override_dialog(window: Any) -> None:
    dialog = QDialog(window)
    dialog.setWindowTitle(_txt("차량명 사용자 오버라이드", "Vehicle name overrides"))
    dialog.resize(1180, 720)
    dialog.setStyleSheet(APP_STYLE)

    root = QVBoxLayout(dialog)
    root.setContentsMargins(16, 16, 16, 16)
    root.setSpacing(10)

    info_label = QLabel(
        _txt(
            "차량명은 현재 선택한 차량 데이터 소스를 기준으로 하며 사용자 오버라이드가 항상 우선합니다. 획득처/DLC는 Datamining00 데이터 선택 시에만 사용됩니다. 차량명 열만 편집됩니다.",
            "Vehicle names use the selected vehicle-data source and user overrides always win. Acquisition/DLC are used only with Datamining00 data. Only the vehicle-name column is editable.",
        )
    )
    info_label.setWordWrap(True)
    root.addWidget(info_label)

    table = QTableWidget(dialog)
    table.setColumnCount(5)
    table.setHorizontalHeaderLabels(["Car ID", _txt("차량명", "Vehicle name"), _txt("데이터셋 차량명", "Dataset name"), _txt("획득처", "Acquisition"), "DLC"])
    table.setColumnHidden(2, str(getattr(window, "vehicle_data_source", "hdr")) == "user")
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
    root.addWidget(table, 1)

    acquisition_db = getattr(window, "acquisition_db", None)
    supplemental = acquisition_db.all_items() if isinstance(acquisition_db, AcquisitionDatabase) else {}
    initial_overrides = window.car_db.user_overrides()
    effective = window.car_db.all_items()
    visible_ids = set(effective) | set(supplemental)
    result = getattr(window, "result", None)
    if result is not None:
        for record in [*(getattr(result, "liveries", []) or []), *(getattr(result, "tunings", []) or [])]:
            car_id = getattr(getattr(record, "header", None), "car_id", None)
            if car_id is not None:
                visible_ids.add(int(car_id))

    table.setRowCount(len(visible_ids))
    for row, car_id in enumerate(sorted(visible_ids)):
        id_item = _readonly_item(str(car_id)); id_item.setData(Qt.ItemDataRole.UserRole, car_id)
        name = window.car_db.get(car_id).label
        name_item = QTableWidgetItem(name); name_item.setData(Qt.ItemDataRole.UserRole, car_id)
        if car_id in initial_overrides:
            name_item.setBackground(QColor("#f3efff")); name_item.setToolTip(_txt("사용자 오버라이드 적용 중", "User override applied"))
        else:
            name_item.setToolTip(_txt("차량명을 편집하면 사용자 오버라이드로 저장됩니다.", "Edit to save a user override."))
        extra = supplemental.get(car_id)
        dataset_name = extra.dataset_name if extra is not None else "-"
        acquisition = _acquisition_text(extra)
        dlc_name = extra.dlc_name if extra is not None and extra.dlc_name else "-"
        acquisition_item = _readonly_item(acquisition); acquisition_item.setToolTip(_acquisition_tooltip(extra))
        table.setItem(row, 0, id_item); table.setItem(row, 1, name_item); table.setItem(row, 2, _readonly_item(dataset_name)); table.setItem(row, 3, acquisition_item); table.setItem(row, 4, _readonly_item(dlc_name))

    footer = QHBoxLayout(); footer.addStretch(1)
    close_button = QPushButton(_txt("닫기", "Close")); close_button.setObjectName("secondary")
    save_button = QPushButton(_txt("저장", "Save")); save_button.setObjectName("primary"); save_button.setEnabled(False)
    footer.addWidget(close_button); footer.addWidget(save_button); root.addLayout(footer)
    dirty = {"value": False}; saved_any = {"value": False}

    def mark_dirty(item: QTableWidgetItem) -> None:
        if item.column() == 1:
            dirty["value"] = True; save_button.setEnabled(True)

    def collect_overrides() -> Optional[dict[int, str]]:
        desired: dict[int, str] = {}
        for row in range(table.rowCount()):
            id_item = table.item(row, 0); name_item = table.item(row, 1)
            if id_item is None or name_item is None: continue
            car_id = int(id_item.data(Qt.ItemDataRole.UserRole)); value = name_item.text().strip()
            if not value:
                QMessageBox.warning(dialog, _txt("저장할 수 없음", "Cannot save"), _txt(f"Car ID {car_id}의 차량명이 비어 있습니다.", f"Vehicle name for Car ID {car_id} is empty.")); return None
            if value != window.car_db.base_label(car_id): desired[car_id] = value
        return desired

    def save() -> None:
        desired = collect_overrides()
        if desired is None: return
        try: window.car_db.replace_user_overrides(desired)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(dialog, _txt("저장 실패", "Save failed"), str(exc)); return
        dirty["value"] = False; saved_any["value"] = True; save_button.setEnabled(False)

    table.itemChanged.connect(mark_dirty); save_button.clicked.connect(save); close_button.clicked.connect(dialog.accept); dialog.exec()
    if saved_any["value"]:
        populate = getattr(window, "_populate_all", None)
        if callable(populate): populate()


def _install_change_dialog_first_layout_fix() -> None:
    original_open = _dashboard_changes._open_grouped_change_dialog
    if bool(getattr(original_open, "_fh6_v14_first_layout_fixed", False)): return
    def open_fixed(window: Any) -> None:
        original_open(window)
        dialog = getattr(window, "_fh6_change_dialog", None)
        if not isinstance(dialog, QDialog): return
        layout = dialog.layout()
        if layout is not None: layout.activate()
        scroll = getattr(dialog, "_fh6_change_scroll", None)
        if scroll is not None and scroll.viewport() is not None: scroll.viewport().updateGeometry()
        render = getattr(dialog, "_fh6_change_render", None)
        if callable(render): render(force=True)
    open_fixed._fh6_v14_first_layout_fixed = True
    _dashboard_changes._open_grouped_change_dialog = open_fixed; _change_dialog._open_change_dialog_same_as_main = open_fixed


def apply_v1_4_acquisition_ui_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_acquisition_ui_patched", False): return
    original_init = MainWindow.__init__; original_make_card = MainWindow._make_saved_content_card
    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs); self.acquisition_db = AcquisitionDatabase(self.project_root / "data" / DATA_DIR_NAME)
    def make_card(self: Any, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        if content_type == "livery": _decorate_acquisition_label(self, card, record)
        return card
    MainWindow.__init__ = patched_init; MainWindow._make_saved_content_card = make_card; MainWindow.open_car_db_override = lambda self: _open_override_dialog(self)
    MainWindow._refresh_cached_acquisition_labels = _refresh_cached_acquisition_labels
    _install_change_dialog_first_layout_fix(); MainWindow._fh6_v14_acquisition_ui_patched = True
