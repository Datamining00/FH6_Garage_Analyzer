from __future__ import annotations

from pathlib import Path
from typing import Any

from . import v1_4_vehicle_data_source_patch as _source
from .car_db import CarDatabase, CarDatabaseError


USER_DATA_RUNTIME_URL = f"{_source.USER_DATA_BASE_URL}/runtime.json"
USER_DATA_RUNTIME_FORMAT = "fh6-assistant-runtime-v1"
USER_DATA_RUNTIME_TIMEOUT = 20


def _fetch_runtime_vehicle_update(
    car_cache_path: Path,
    acquisition_cache_path: Path,
    timeout: int = USER_DATA_RUNTIME_TIMEOUT,
):
    payload, last_modified = _source._download_json(USER_DATA_RUNTIME_URL, timeout)
    if not isinstance(payload, dict):
        raise CarDatabaseError("FH6 Assistant runtime data root is invalid")
    if payload.get("format") != USER_DATA_RUNTIME_FORMAT:
        raise CarDatabaseError("unsupported FH6 Assistant runtime data format")

    try:
        declared_count = int(payload.get("vehicle_count", 0))
    except (TypeError, ValueError) as exc:
        raise CarDatabaseError("invalid FH6 Assistant runtime vehicle count") from exc

    names_raw = payload.get("car_names")
    acquisition_raw = payload.get("acquisition")
    dlc_raw = payload.get("dlc")
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
        acquisition_by_id[car_id] = str(raw_value or "-").strip() or "-"

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

        rows.append([
            car_id,
            id_to_name[car_id],
            acquisition_index[acquisition],
            dlc_index.get(dlc_name, 0),
        ])

    downloaded_at = _source._utc_now()
    car_payload = {
        "schema": 1,
        "source_kind": _source.USER_SOURCE,
        "source_url": USER_DATA_RUNTIME_URL,
        "source_page": _source.USER_DATA_SOURCE_PAGE,
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

    _source._atomic_write_json(
        acquisition_cache_path,
        supplemental_payload,
        "fh6_vehicle_data_",
    )
    _source._atomic_write_json(
        car_cache_path,
        car_payload,
        "fh6_car_ordinals_",
    )

    return _source.VehicleDataUpdateResult(
        source=_source.USER_SOURCE,
        count=len(normalized),
        downloaded_at=downloaded_at,
        source_last_modified=last_modified,
        cache_path=car_cache_path,
        acquisition_cache_path=acquisition_cache_path,
    )


def apply_v1_4_vehicle_runtime_update_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_vehicle_runtime_update_patched", False):
        return
    _source._fetch_user_vehicle_update = _fetch_runtime_vehicle_update
    MainWindow._fh6_v14_vehicle_runtime_update_patched = True
