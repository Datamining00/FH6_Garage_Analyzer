from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .performance_metrics import app_data_dir


DATA_FILE_NAME = "fh6_cars.json.gz"
SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class AcquisitionInfo:
    car_id: int
    dataset_name: str = ""
    acquisition: str = "-"
    dlc_name: str = ""

    @property
    def methods(self) -> tuple[str, ...]:
        value = (self.acquisition or "-").strip()
        if not value or value == "-":
            return ()
        return tuple(part.strip() for part in value.split(",") if part.strip())


class AcquisitionDatabase:
    """Offline supplemental Car ID -> acquisition/DLC index.

    HDR remains the authoritative vehicle-name database.  This loader reads only
    the compact supplemental dataset and never replaces CarDatabase resolution.
    A LocalAppData copy, when present, takes precedence over the bundled snapshot
    so a future updater can refresh the supplemental data without changing the
    user's vehicle-name overrides.
    """

    def __init__(self, bundled_path: Path | None = None, cache_path: Path | None = None) -> None:
        self.bundled_path = Path(bundled_path) if bundled_path is not None else None
        self.cache_path = Path(cache_path) if cache_path is not None else app_data_dir() / DATA_FILE_NAME
        self._items: dict[int, AcquisitionInfo] = {}
        self.loaded_path: Path | None = None
        self.load_warning = ""
        self.reload()

    def reload(self) -> None:
        self._items = {}
        self.loaded_path = None
        self.load_warning = ""
        candidates = [self.cache_path]
        if self.bundled_path is not None and self.bundled_path != self.cache_path:
            candidates.append(self.bundled_path)
        for path in candidates:
            if not path.is_file():
                continue
            try:
                parsed = self._load_file(path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                self.load_warning = f"{path.name}: {exc}"
                continue
            if parsed:
                self._items = parsed
                self.loaded_path = path
                return

    def get(self, car_id: int | None) -> AcquisitionInfo | None:
        if car_id is None:
            return None
        try:
            return self._items.get(int(car_id))
        except (TypeError, ValueError):
            return None

    def all_items(self) -> dict[int, AcquisitionInfo]:
        return dict(self._items)

    def __len__(self) -> int:
        return len(self._items)

    @classmethod
    def _load_file(cls, path: Path) -> dict[int, AcquisitionInfo]:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
        return cls._parse_payload(payload)

    @classmethod
    def _parse_payload(cls, payload: Any) -> dict[int, AcquisitionInfo]:
        if not isinstance(payload, dict):
            raise ValueError("supplemental root is not an object")
        if int(payload.get("v", 0) or 0) != SCHEMA_VERSION:
            raise ValueError("unsupported supplemental schema")

        acquisitions = payload.get("a", [])
        dlcs = payload.get("d", [])
        cars = payload.get("c", [])
        if not isinstance(acquisitions, list) or not isinstance(dlcs, list) or not isinstance(cars, list):
            raise ValueError("invalid supplemental tables")

        result: dict[int, AcquisitionInfo] = {}
        for row in cars:
            if not isinstance(row, list) or len(row) < 4:
                continue
            try:
                car_id = int(row[0])
                acquisition_index = int(row[2])
                dlc_code = int(row[3])
            except (TypeError, ValueError):
                continue
            if car_id <= 0 or not (0 <= acquisition_index < len(acquisitions)):
                continue
            dataset_name = str(row[1] or "").strip()
            acquisition = str(acquisitions[acquisition_index] or "-").strip() or "-"
            # The compact dataset uses 0 for no DLC and 1-based indices for d[].
            dlc_name = ""
            if dlc_code > 0 and dlc_code <= len(dlcs):
                dlc_name = str(dlcs[dlc_code - 1] or "").strip()
            result[car_id] = AcquisitionInfo(
                car_id=car_id,
                dataset_name=dataset_name,
                acquisition=acquisition,
                dlc_name=dlc_name,
            )

        declared = payload.get("n")
        if declared is not None:
            try:
                if int(declared) != len(result):
                    raise ValueError(f"declared count {declared} != parsed count {len(result)}")
            except (TypeError, ValueError) as exc:
                if isinstance(exc, ValueError) and str(exc).startswith("declared count"):
                    raise
                raise ValueError("invalid supplemental count") from exc
        return result
