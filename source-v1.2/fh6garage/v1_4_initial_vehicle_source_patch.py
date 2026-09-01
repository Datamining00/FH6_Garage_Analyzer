from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QMessageBox

from .acquisition_db import DATA_DIR_NAME
from . import v1_4_vehicle_data_source_patch as _source
from .v1_4_vehicle_source_database import SourceAwareCarDatabase


def _choose_initial_source(parent: Any) -> str:
    box = QMessageBox(parent)
    box.setWindowTitle("차량 데이터 소스")
    box.setText("처음 사용할 차량 데이터 소스를 선택하십시오.")
    box.setInformativeText(
        "선택은 저장되며 이후 차량 데이터 업데이트에서 다른 소스로 변경할 수 있습니다."
    )
    hdr_button = box.addButton("저장소1(HDR)", QMessageBox.ButtonRole.AcceptRole)
    user_button = box.addButton("저장소2(내 차량 데이터)", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(hdr_button)
    box.exec()
    return _source.USER_SOURCE if box.clickedButton() is user_button else _source.HDR_SOURCE


def _selected_database(window: Any, source: str, user_data_path: Path) -> SourceAwareCarDatabase:
    previous_db = getattr(window, "car_db", None)
    return SourceAwareCarDatabase(
        window.project_root / "data" / "car_names.json",
        source=source,
        user_data_path=user_data_path,
        app_data_dir=getattr(previous_db, "app_data_dir", None),
    )


def apply_v1_4_initial_vehicle_source_patch(MainWindow: Any) -> None:
    """Ask once for the v1.4 vehicle source and bind startup to that source."""
    if getattr(MainWindow, "_fh6_v14_initial_vehicle_source_patched", False):
        return

    previous_init = MainWindow.__init__

    def patched_init(self: Any, project_root: Path, *args, **kwargs) -> None:
        previous_init(self, project_root, *args, **kwargs)
        user_data_path = self.project_root / "data" / DATA_DIR_NAME
        stored = _source.normalize_vehicle_data_source(
            self.settings.value(_source.VEHICLE_DATA_SOURCE_KEY, "", str)
        )
        selected = stored
        if not selected:
            selected = _choose_initial_source(self)
            self.settings.setValue(_source.VEHICLE_DATA_SOURCE_KEY, selected)

        self.vehicle_data_source = selected
        self.car_db = _selected_database(self, selected, user_data_path)
        if (
            selected == _source.USER_SOURCE
            and self.car_db.status.built_in_count < 500
        ):
            selected = _source.HDR_SOURCE
            self.vehicle_data_source = selected
            self.settings.setValue(_source.VEHICLE_DATA_SOURCE_KEY, selected)
            self.car_db = _selected_database(self, selected, user_data_path)
            QMessageBox.warning(
                self,
                "차량 데이터 소스",
                "저장소2의 차량 데이터를 불러올 수 없어 저장소1(HDR)로 전환했습니다.",
            )

        refresh = getattr(self, "_refresh_db_status", None)
        if callable(refresh):
            refresh()

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v14_initial_vehicle_source_patched = True
