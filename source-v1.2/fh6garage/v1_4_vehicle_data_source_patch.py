from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from .acquisition_db import (
    DATA_DIR_NAME,
    DATA_FILE_NAME,
    AcquisitionDatabase,
)
from .car_db import (
    CarDatabase,
    CarDatabaseError,
    CarDatabaseUpdateResult,
    REMOTE_SOURCE_PAGE,
)


HDR_SOURCE = "hdr"
USER_SOURCE = "user"
VEHICLE_DATA_SOURCE_KEY = "vehicle_data_source"
USER_DATA_BASE_URL = (
    "https://raw.githubusercontent.com/Datamining00/"
    "FH6-Assistant-Data/main/vehicle_data"
)
USER_DATA_SOURCE_PAGE = "https://github.com/Datamining00/FH6-Assistant-Data"
USER_DATA_MANIFEST_URL = f"{USER_DATA_BASE_URL}/manifest.json"
USER_DATA_NAMES_URL = f"{USER_DATA_BASE_URL}/car_names.json"
USER_DATA_ACQUISITION_URL = f"{USER_DATA_BASE_URL}/acquisition.json"
USER_DATA_DLC_URL = f"{USER_DATA_BASE_URL}/dlc.json"
MAX_USER_DATA_BYTES = 2 * 1024 * 1024


def normalize_vehicle_data_source(value: object) -> str:
    raw = str(value or "").strip().casefold()
    return raw if raw in {HDR_SOURCE, USER_SOURCE} else ""


def resolve_vehicle_data_source(settings, user_data_path: Path, parent=None) -> str:
    """Resolve the previously updated source without prompting at startup.

    Source selection now belongs exclusively to the explicit database-update
    action. A fresh install therefore starts immediately with the bundled HDR
    baseline and never shows a vehicle-source modal during application launch.
    """
    del user_data_path, parent
    stored = normalize_vehicle_data_source(
        settings.value(VEHICLE_DATA_SOURCE_KEY, "", str)
    )
    return stored or HDR_SOURCE


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _download_json(url: str, timeout: int = 20) -> tuple[object, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FH6-Assistant/1.4",
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_USER_DATA_BYTES + 1)
            if len(raw) > MAX_USER_DATA_BYTES:
                raise CarDatabaseError("vehicle data response is too large")
            last_modified = response.headers.get("Last-Modified", "")
    except Exception as exc:
        if isinstance(exc, CarDatabaseError):
            raise
        raise CarDatabaseError(f"vehicle data download failed: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8-sig")), last_modified
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CarDatabaseError(f"vehicle data JSON decode failed: {exc}") from exc


def _atomic_write_json(path: Path, payload: object, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=prefix,
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


@dataclass(slots=True)
class VehicleDataUpdateResult:
    source: str
    count: int
    downloaded_at: str
    source_last_modified: str
    cache_path: Path
    acquisition_cache_path: Path | None = None


def _fetch_user_vehicle_update(
    car_cache_path: Path,
    acquisition_cache_path: Path,
    timeout: int = 20,
) -> VehicleDataUpdateResult:
    manifest, manifest_modified = _download_json(USER_DATA_MANIFEST_URL, timeout)
    names_raw, names_modified = _download_json(USER_DATA_NAMES_URL, timeout)
    acquisition_raw, _ = _download_json(USER_DATA_ACQUISITION_URL, timeout)
    dlc_raw, _ = _download_json(USER_DATA_DLC_URL, timeout)

    if not isinstance(manifest, dict):
        raise CarDatabaseError("FH6 Assistant manifest root is invalid")
    if manifest.get("format") != "fh6-assistant-readable-v1":
        raise CarDatabaseError("unsupported FH6 Assistant vehicle-data format")
    try:
        declared_count = int(manifest.get("vehicle_count", 0))
    except (TypeError, ValueError) as exc:
        raise CarDatabaseError("invalid FH6 Assistant vehicle count") from exc

    normalized = CarDatabase._normalize_remote_mapping(names_raw)
    if declared_count < 500 or len(normalized) != declared_count:
        raise CarDatabaseError(
            f"FH6 Assistant vehicle count mismatch: {len(normalized)} != {declared_count}"
        )
    if not isinstance(acquisition_raw, dict) or not isinstance(dlc_raw, dict):
        raise CarDatabaseError("FH6 Assistant supplemental data root is invalid")

    id_to_name = {car_id: item.label for car_id, item in normalized.items()}
    acquisition_by_id: dict[int, str] = {}
    for raw_id, raw_value in acquisition_raw.items():
        try:
            car_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        value = str(raw_value or "-").strip() or "-"
        acquisition_by_id[car_id] = value

    dlc_by_id: dict[int, str] = {}
    for raw_id, raw_value in dlc_raw.items():
        try:
            car_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        value = str(raw_value or "").strip()
        if value:
            dlc_by_id[car_id] = value

    if set(acquisition_by_id) != set(id_to_name):
        raise CarDatabaseError("FH6 Assistant acquisition coverage mismatch")
    if not set(dlc_by_id).issubset(id_to_name):
        raise CarDatabaseError("FH6 Assistant DLC contains unknown Car IDs")

    acquisition_values: list[str] = []
    acquisition_index: dict[str, int] = {}
    dlc_values: list[str] = []
    dlc_index: dict[str, int] = {}
    rows: list[list[object]] = []

    for car_id in sorted(id_to_name):
        acquisition = acquisition_by_id[car_id]
        if acquisition not in acquisition_index:
            acquisition_index[acquisition] = len(acquisition_values)
            acquisition_values.append(acquisition)

        dlc_name = dlc_by_id.get(car_id, "")
        if dlc_name and dlc_name not in dlc_index:
            dlc_index[dlc_name] = len(dlc_values) + 1
            dlc_values.append(dlc_name)

        rows.append(
            [
                car_id,
                id_to_name[car_id],
                acquisition_index[acquisition],
                dlc_index.get(dlc_name, 0),
            ]
        )

    downloaded_at = _utc_now()
    last_modified = names_modified or manifest_modified
    car_payload = {
        "schema": 1,
        "source_kind": USER_SOURCE,
        "source_url": USER_DATA_NAMES_URL,
        "source_page": USER_DATA_SOURCE_PAGE,
        "downloaded_at": downloaded_at,
        "source_last_modified": last_modified,
        "count": len(normalized),
        "cars": {
            str(car_id): id_to_name[car_id]
            for car_id in sorted(id_to_name)
        },
    }
    supplemental_payload = {
        "v": 1,
        "n": len(rows),
        "a": acquisition_values,
        "d": dlc_values,
        "c": rows,
    }

    # Write supplemental data first. If the second atomic replacement fails,
    # the previous car-name cache remains intact and the next explicit update can
    # safely retry; neither target is ever left partially written.
    _atomic_write_json(
        acquisition_cache_path,
        supplemental_payload,
        "fh6_vehicle_data_",
    )
    _atomic_write_json(car_cache_path, car_payload, "fh6_car_ordinals_")

    return VehicleDataUpdateResult(
        source=USER_SOURCE,
        count=len(normalized),
        downloaded_at=downloaded_at,
        source_last_modified=last_modified,
        cache_path=car_cache_path,
        acquisition_cache_path=acquisition_cache_path,
    )


class VehicleDataUpdateWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        source: str,
        car_cache_path: Path,
        acquisition_cache_path: Path,
    ) -> None:
        super().__init__()
        self.source = normalize_vehicle_data_source(source) or HDR_SOURCE
        self.car_cache_path = Path(car_cache_path)
        self.acquisition_cache_path = Path(acquisition_cache_path)

    @Slot()
    def run(self) -> None:
        try:
            if self.source == USER_SOURCE:
                result = _fetch_user_vehicle_update(
                    self.car_cache_path,
                    self.acquisition_cache_path,
                )
            else:
                hdr = CarDatabase.fetch_remote_update(self.car_cache_path)
                result = VehicleDataUpdateResult(
                    source=HDR_SOURCE,
                    count=hdr.count,
                    downloaded_at=hdr.downloaded_at,
                    source_last_modified=hdr.source_last_modified,
                    cache_path=hdr.cache_path,
                )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def _choose_update_source(parent) -> str:
    box = QMessageBox(parent)
    box.setWindowTitle("차량 데이터 업데이트")
    box.setText("업데이트할 차량 데이터 소스를 선택하십시오.")
    box.setInformativeText(
        "선택한 소스의 최신 데이터를 내려받아 로컬 캐시를 교체합니다. "
        "프로그램 시작 시에는 다시 묻지 않습니다."
    )
    hdr_button = box.addButton("HDR 데이터", QMessageBox.ButtonRole.AcceptRole)
    user_button = box.addButton("내 차량 데이터", QMessageBox.ButtonRole.AcceptRole)
    cancel_button = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(hdr_button)
    box.exec()
    clicked = box.clickedButton()
    if clicked is user_button:
        return USER_SOURCE
    if clicked is hdr_button:
        return HDR_SOURCE
    if clicked is cancel_button:
        return ""
    return ""


def apply_v1_4_vehicle_data_source_patch(window_cls) -> None:
    if getattr(window_cls, "_v1_4_vehicle_data_source_patch_applied", False):
        return

    previous_init = window_cls.__init__
    previous_finished = window_cls._car_db_update_finished
    previous_failed = window_cls._car_db_update_failed
    previous_cleanup = window_cls._car_db_update_cleanup

    def patched_init(self, project_root: Path, *args, **kwargs):
        previous_init(self, project_root, *args, **kwargs)
        user_data_path = self.project_root / "data" / DATA_DIR_NAME
        self.vehicle_data_source = resolve_vehicle_data_source(
            self.settings,
            user_data_path,
            self,
        )

        # Acquisition UI is installed immediately before this patch and normally
        # owns the already-loaded metadata index. Reuse it to avoid reading all
        # committed vehicle-data chunks twice during startup. Keep this fallback
        # so the source patch also remains safe when installed independently.
        if not isinstance(
            getattr(self, "acquisition_db", None), AcquisitionDatabase
        ):
            try:
                self.acquisition_db = AcquisitionDatabase(user_data_path)
            except Exception:
                pass

        refresh = getattr(self, "_refresh_db_status", None)
        if callable(refresh):
            refresh()

    @Slot()
    def start_car_db_update(self) -> None:
        if self._db_update_thread and self._db_update_thread.isRunning():
            return
        selected = _choose_update_source(self)
        if not selected:
            return

        self._pending_vehicle_data_source = selected
        self.db_update_button.setEnabled(False)
        self.db_update_button.setText("업데이트 확인 중")
        self._begin_busy("차량 데이터를 업데이트하는 중입니다…")
        self._show_status("차량 데이터를 다운로드하는 중입니다…")

        thread = QThread(self)
        acquisition_cache_path = (
            getattr(getattr(self, "acquisition_db", None), "cache_path", None)
            or (CarDatabase.default_app_data_dir() / DATA_FILE_NAME)
        )
        worker = VehicleDataUpdateWorker(
            selected,
            self.car_db.cache_path,
            acquisition_cache_path,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._car_db_update_finished)
        worker.failed.connect(self._car_db_update_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._car_db_update_cleanup)
        self._db_update_thread = thread
        self._db_update_worker = worker
        thread.start()

    @Slot(object)
    def car_db_update_finished(self, update) -> None:
        source = normalize_vehicle_data_source(getattr(update, "source", ""))
        if not source:
            previous_finished(self, update)
            return

        self._end_busy()
        self.vehicle_data_source = source
        self.settings.setValue(VEHICLE_DATA_SOURCE_KEY, source)

        # The common car cache now contains either HDR or FH6 Assistant names,
        # so the normal CarDatabase loader can handle both without startup-time
        # source switching or a second database implementation.
        self.car_db = CarDatabase(self.project_root / "data" / "car_names.json")

        user_data_path = self.project_root / "data" / DATA_DIR_NAME
        try:
            if isinstance(getattr(self, "acquisition_db", None), AcquisitionDatabase):
                self.acquisition_db.reload()
            else:
                self.acquisition_db = AcquisitionDatabase(user_data_path)
        except Exception:
            pass

        self._refresh_db_status()
        source_label = "내 차량 데이터" if source == USER_SOURCE else "HDR 데이터"
        self._show_status(
            f"{source_label} 업데이트 완료: {update.count}대",
            8000,
        )
        QMessageBox.information(
            self,
            "차량 데이터 업데이트 완료",
            f"{source_label}를 {update.count}대 기준으로 업데이트했습니다.\n\n"
            f"저장 위치: {update.cache_path}",
        )
        if self.path_edit.text() and Path(self.path_edit.text()).is_dir():
            self.start_scan(Path(self.path_edit.text()))

    @Slot(str)
    def car_db_update_failed(self, message: str) -> None:
        self._pending_vehicle_data_source = ""
        previous_failed(self, message)

    @Slot()
    def car_db_update_cleanup(self) -> None:
        self._pending_vehicle_data_source = ""
        previous_cleanup(self)

    @Slot()
    def open_car_db_source(self) -> None:
        source = normalize_vehicle_data_source(
            getattr(self, "vehicle_data_source", "")
        )
        page = USER_DATA_SOURCE_PAGE if source == USER_SOURCE else REMOTE_SOURCE_PAGE
        QDesktopServices.openUrl(QUrl(page))

    window_cls.__init__ = patched_init
    window_cls.start_car_db_update = start_car_db_update
    window_cls._car_db_update_finished = car_db_update_finished
    window_cls._car_db_update_failed = car_db_update_failed
    window_cls._car_db_update_cleanup = car_db_update_cleanup
    window_cls._open_car_db_source = open_car_db_source
    window_cls._v1_4_vehicle_data_source_patch_applied = True
