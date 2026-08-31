from __future__ import annotations

from pathlib import Path
from typing import Any

from . import v1_4_vehicle_data_source_patch as _source
from .car_db import CarDatabase, CarDatabaseError


USER_DATA_GIST_ID = "30fe44689fad7ba5e99e2381927b7730"
USER_DATA_GIST_PAGE = f"https://gist.github.com/Datamining00/{USER_DATA_GIST_ID}"
USER_DATA_GIST_RAW_URL = (
    f"https://gist.githubusercontent.com/Datamining00/{USER_DATA_GIST_ID}/raw/"
)
USER_DATA_RUNTIME_TIMEOUT = 20


def _fetch_runtime_vehicle_update(
    car_cache_path: Path,
    acquisition_cache_path: Path,
    timeout: int = USER_DATA_RUNTIME_TIMEOUT,
):
    payload, last_modified = _source._download_json(USER_DATA_GIST_RAW_URL, timeout)
    if not isinstance(payload, dict):
        raise CarDatabaseError("FH6 Assistant Gist vehicle data root is invalid")

    id_to_name: dict[int, str] = {}
    acquisition_by_id: dict[int, str] = {}
    dlc_by_id: dict[int, str] = {}

    for raw_name, raw_info in payload.items():
        name = str(raw_name or "").strip()
        if not name or not isinstance(raw_info, dict):
            raise CarDatabaseError("invalid FH6 Assistant Gist vehicle entry")

        try:
            car_id = int(raw_info.get("id"))
        except (TypeError, ValueError) as exc:
            raise CarDatabaseError(f"invalid Car ID for {name}") from exc

        if car_id in id_to_name:
            raise CarDatabaseError(f"duplicate Car ID in Gist data: {car_id}")

        acquisition = str(raw_info.get("acquisition") or "-").strip() or "-"
        is_dlc = bool(raw_info.get("dlc", False))
        dlc_name = str(raw_info.get("dlc_name") or "").strip()
        if is_dlc and not dlc_name:
            raise CarDatabaseError(f"DLC name missing for Car ID {car_id}")
        if not is_dlc:
            dlc_name = ""

        id_to_name[car_id] = name
        acquisition_by_id[car_id] = acquisition
        if dlc_name:
            dlc_by_id[car_id] = dlc_name

    if len(id_to_name) < 500:
        raise CarDatabaseError(
            f"FH6 Assistant Gist vehicle count is too small: {len(id_to_name)}"
        )

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
        "source_url": USER_DATA_GIST_RAW_URL,
        "source_page": USER_DATA_GIST_PAGE,
        "downloaded_at": downloaded_at,
        "source_last_modified": last_modified,
        "count": len(id_to_name),
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
        count=len(id_to_name),
        downloaded_at=downloaded_at,
        source_last_modified=last_modified,
        cache_path=car_cache_path,
        acquisition_cache_path=acquisition_cache_path,
    )


def apply_v1_4_vehicle_runtime_update_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_vehicle_runtime_update_patched", False):
        return

    # Keep the data-source UI on the public Gist as well, so "open source"
    # points to the exact payload used by Vehicle Data 2.
    _source.USER_DATA_SOURCE_PAGE = USER_DATA_GIST_PAGE
    _source._fetch_user_vehicle_update = _fetch_runtime_vehicle_update
    MainWindow._fh6_v14_vehicle_runtime_update_patched = True
