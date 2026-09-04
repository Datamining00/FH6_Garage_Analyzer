from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QLabel, QMessageBox, QSizePolicy

from . import v1_3_2_change_dialog_folder_patch as _change_dialog
from . import v1_4_vehicle_data_source_patch as _vehicle_source
from .acquisition_db import AcquisitionDatabase, DATA_DIR_NAME, SUPPLEMENTAL_DISABLED_KEY
from .v1_4_vehicle_source_database import SourceAwareCarDatabase
from .i18n import tr


def _choose_update_source(parent: Any) -> str:
    box = QMessageBox(parent)
    box.setWindowTitle("차량 데이터 업데이트")
    box.setText("업데이트할 차량 데이터 소스를 선택하십시오.")
    box.setInformativeText("선택한 소스의 최신 데이터를 내려받아 로컬 캐시를 교체합니다. 프로그램 시작 시에는 다시 묻지 않습니다.")
    hdr_button = box.addButton("저장소1(HDR)", QMessageBox.ButtonRole.AcceptRole)
    user_button = box.addButton("저장소2", QMessageBox.ButtonRole.AcceptRole)
    cancel_button = box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(hdr_button); box.exec(); clicked = box.clickedButton()
    if clicked is user_button: return _vehicle_source.USER_SOURCE
    if clicked is hdr_button: return _vehicle_source.HDR_SOURCE
    if clicked is cancel_button: return ""
    return ""


def _normalize_added_card_geometry(window: Any, entry: Any, card_width: int):
    card = _normalize_added_card_geometry._original(window, entry, card_width)
    card.setMinimumWidth(card_width); card.setMaximumWidth(card_width); card.setFixedWidth(card_width)
    card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    label = card.findChild(QLabel, "fh6AcquisitionPlaceholder")
    if isinstance(label, QLabel):
        label.setMinimumWidth(0); label.setFixedHeight(24)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    layout = card.layout()
    if layout is not None: layout.activate()
    card.updateGeometry(); return card


def _disable_supplemental_cache(acquisition_db: AcquisitionDatabase) -> None:
    payload = {"v": 1, "n": 0, "a": [], "d": [], "c": [], SUPPLEMENTAL_DISABLED_KEY: True, "source": _vehicle_source.HDR_SOURCE}
    _vehicle_source._atomic_write_json(acquisition_db.cache_path, payload, "fh6_vehicle_data_disabled_")


def apply_v1_4_vehicle_update_finish_ui_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_vehicle_update_finish_ui_patched", False): return
    _vehicle_source._choose_update_source = _choose_update_source
    previous_finished = MainWindow._car_db_update_finished

    @Slot(object)
    def update_finished(self: Any, update: Any) -> None:
        source = _vehicle_source.normalize_vehicle_data_source(getattr(update, "source", ""))
        if not source:
            previous_finished(self, update); return
        self._end_busy(); self.vehicle_data_source = source
        self.settings.setValue(_vehicle_source.VEHICLE_DATA_SOURCE_KEY, source)
        user_data_path = self.project_root / "data" / DATA_DIR_NAME
        self.car_db = SourceAwareCarDatabase(
            self.project_root / "data" / "car_names.json",
            source=source,
            user_data_path=user_data_path,
            app_data_dir=getattr(getattr(self, "car_db", None), "app_data_dir", None),
        )
        try:
            if not isinstance(getattr(self, "acquisition_db", None), AcquisitionDatabase):
                self.acquisition_db = AcquisitionDatabase(user_data_path)
            if source == _vehicle_source.HDR_SOURCE:
                _disable_supplemental_cache(self.acquisition_db)
            self.acquisition_db.reload()
        except Exception:
            pass

        refresh_acquisition = getattr(self, "_refresh_cached_acquisition_labels", None)
        if callable(refresh_acquisition): refresh_acquisition()

        if hasattr(self, "db_update_button"):
            self.db_update_button.setEnabled(True); self.db_update_button.setText(tr("db.check_update"))
        refresh = getattr(self, "_refresh_db_status", None)
        if callable(refresh): refresh()
        populate = getattr(self, "_populate_all", None)
        if getattr(self, "result", None) is not None and callable(populate): populate()

        source_label = "저장소2" if source == _vehicle_source.USER_SOURCE else "저장소1(HDR)"
        self._show_status(f"{source_label} 업데이트 완료: {update.count}대", 8000)
        QMessageBox.information(self, "차량 데이터 업데이트 완료", f"{source_label}를 {update.count}대 기준으로 업데이트했습니다.\n\n저장 위치: {update.cache_path}")

    MainWindow._car_db_update_finished = update_finished
    original_current_card = _change_dialog._current_card_same_size
    _normalize_added_card_geometry._original = original_current_card
    _change_dialog._current_card_same_size = _normalize_added_card_geometry
    MainWindow._fh6_v14_vehicle_update_finish_ui_patched = True
