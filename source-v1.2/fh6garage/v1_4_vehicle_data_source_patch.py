from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from .car_db import CarDatabase


HDR_SOURCE = "hdr"
USER_SOURCE = "user"
VEHICLE_DATA_SOURCE_KEY = "vehicle_data_source"
USER_DATA_FILE_NAME = "fh6_cars.json"


def normalize_vehicle_data_source(value: object) -> str:
    raw = str(value or "").strip().casefold()
    return raw if raw in {HDR_SOURCE, USER_SOURCE} else ""


class UserVehicleDatabase(CarDatabase):
    """Car ID/name provider backed by the bundled FH6 Assistant dataset.

    It deliberately reuses CarDatabase's user-override persistence API while
    skipping the HDR community-update cache. The effective resolution order is
    therefore: bundled FH6 Assistant name -> user override.
    """

    def reload(self) -> None:
        self._items.clear()
        self._load_warnings.clear()
        self._cached_count = 0
        self._cache_updated_at = ""
        self._cache_source_last_modified = ""

        built_in = self._load_user_dataset(self.bundled_path)
        self._items.update(built_in)
        self._built_in_count = len(built_in)
        self._base_items = dict(self._items)

        overrides = self._load_override(self.override_path)
        if overrides:
            self._items.update(overrides)
        self._override_count = len(overrides)

    def _load_user_dataset(self, path: Path) -> dict[int, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self._load_warnings.append(f"{path.name}: {exc}")
            return {}
        if not isinstance(payload, dict):
            self._load_warnings.append(f"{path.name}: vehicle dataset root is not an object")
            return {}
        rows = payload.get("c", [])
        if not isinstance(rows, list):
            self._load_warnings.append(f"{path.name}: vehicle dataset rows are invalid")
            return {}

        result = {}
        for row in rows:
            if not isinstance(row, list) or len(row) < 2:
                continue
            try:
                car_id = int(row[0])
            except (TypeError, ValueError):
                continue
            label = str(row[1] or "").strip()
            if car_id <= 0 or not label:
                continue
            result[car_id] = self._make_car_name(car_id, label, "FH6 Assistant data")
        return result


def _choose_vehicle_data_source(parent, user_data_available: bool) -> str:
    if not user_data_available:
        return HDR_SOURCE

    box = QMessageBox(parent)
    box.setWindowTitle("차량 데이터 선택")
    box.setText("기본 차량 데이터 소스를 선택하십시오.")
    box.setInformativeText("선택값은 저장되며 다음 실행부터 자동으로 사용됩니다.")
    hdr_button = box.addButton("HDR 데이터", QMessageBox.ButtonRole.AcceptRole)
    user_button = box.addButton("내 차량 데이터", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(hdr_button)
    box.exec()
    return USER_SOURCE if box.clickedButton() is user_button else HDR_SOURCE


def resolve_vehicle_data_source(settings, user_data_path: Path, parent=None) -> str:
    """Resolve the persisted source, prompting only when no choice exists.

    Smoke tests never show a modal dialog. If the user dataset is unavailable,
    HDR is used for the current run without destroying a previously saved user
    preference, so a transient packaging/file problem does not rewrite settings.
    """
    stored = normalize_vehicle_data_source(settings.value(VEHICLE_DATA_SOURCE_KEY, "", str))
    available = Path(user_data_path).is_file()
    if stored:
        if stored == USER_SOURCE and not available:
            return HDR_SOURCE
        return stored

    if os.environ.get("FH6_ASSISTANT_SMOKE_TEST_MS", "").strip():
        return HDR_SOURCE

    selected = _choose_vehicle_data_source(parent, available)
    settings.setValue(VEHICLE_DATA_SOURCE_KEY, selected)
    return selected


def apply_v1_4_vehicle_data_source_patch(window_cls) -> None:
    if getattr(window_cls, "_v1_4_vehicle_data_source_patch_applied", False):
        return

    previous_init = window_cls.__init__

    def patched_init(self, project_root: Path, *args, **kwargs):
        previous_init(self, project_root, *args, **kwargs)
        user_data_path = self.project_root / "data" / USER_DATA_FILE_NAME
        selected = resolve_vehicle_data_source(self.settings, user_data_path, self)
        self.vehicle_data_source = selected

        if selected == USER_SOURCE:
            existing_app_data_dir = getattr(self.car_db, "app_data_dir", None)
            candidate = UserVehicleDatabase(user_data_path, app_data_dir=existing_app_data_dir)
            # A malformed/empty user dataset must never break startup or replace
            # a working HDR provider with an empty database.
            if candidate.status.built_in_count > 0:
                self.car_db = candidate
            else:
                self.vehicle_data_source = HDR_SOURCE

        # v1.4 acquisition metadata uses the same committed plain JSON snapshot.
        try:
            from .acquisition_db import AcquisitionDatabase

            self.acquisition_db = AcquisitionDatabase(user_data_path)
        except Exception:
            # Supplemental metadata is optional; scans and HDR names must remain
            # usable even if this file is missing or malformed.
            pass

        refresh = getattr(self, "_refresh_db_status", None)
        if callable(refresh):
            refresh()

    window_cls.__init__ = patched_init
    window_cls._v1_4_vehicle_data_source_patch_applied = True
