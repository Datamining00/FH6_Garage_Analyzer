from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .performance_metrics import app_data_dir


DATA_DIR_NAME = "fh6_assistant_vehicle_data"
DATA_FILE_NAME = "fh6_cars.json"
LEGACY_DATA_FILE_NAME = "fh6_cars.json.gz"
SCHEMA_VERSION = 1
SUPPLEMENTAL_DISABLED_KEY = "disabled"


def load_vehicle_data_payload(path: Path) -> dict[str, Any]:
    """Load the committed directory format or a legacy single-file snapshot."""
    path = Path(path)
    if path.is_dir():
        metadata_path = path / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("vehicle metadata root is not an object")
        rows: list[Any] = []
        cars_dir = path / "cars"
        for chunk in sorted(cars_dir.glob("*.json")):
            payload = json.loads(chunk.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
                raise ValueError(f"invalid vehicle data chunk: {chunk.name}")
            rows.extend(payload["rows"])
        result = dict(metadata)
        result["c"] = rows
        return result

    if path.suffix.casefold() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
    else:
        with path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("vehicle data root is not an object")
    return payload


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
    """Offline Car ID -> acquisition/DLC index.

    The selected vehicle-name source is handled separately from this metadata
    index. Lookups never perform network access and are O(1) after one startup
    load. The v1.4 bundled format is an uncompressed directory committed to the
    main repository. Legacy LocalAppData JSON/gzip snapshots remain readable.
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
        candidates: list[Path] = [self.cache_path]
        legacy_cache = self.cache_path.with_name(LEGACY_DATA_FILE_NAME)
        if legacy_cache != self.cache_path:
            candidates.append(legacy_cache)
        if self.bundled_path is not None and self.bundled_path not in candidates:
            candidates.append(self.bundled_path)
        for path in candidates:
            if not path.exists():
                continue
            try:
                payload = load_vehicle_data_payload(path)
                if path == self.cache_path and bool(payload.get(SUPPLEMENTAL_DISABLED_KEY, False)):
                    if int(payload.get("v", 0) or 0) != SCHEMA_VERSION:
                        raise ValueError("unsupported supplemental schema")
                    self.loaded_path = path
                    return
                parsed = self._parse_payload(payload)
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
        return cls._parse_payload(load_vehicle_data_payload(path))

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
