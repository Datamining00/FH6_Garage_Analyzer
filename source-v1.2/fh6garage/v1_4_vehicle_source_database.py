from __future__ import annotations

from pathlib import Path

from .acquisition_db import AcquisitionDatabase
from .car_db import CarDatabase


USER_SOURCE = "user"


class SourceAwareCarDatabase(CarDatabase):
    """Car database whose bundled/cache inputs are constrained to one v1.4 source."""

    def __init__(
        self,
        bundled_path: Path,
        *,
        source: str,
        user_data_path: Path,
        app_data_dir: Path | None = None,
    ) -> None:
        self.vehicle_source = str(source or "").strip().casefold()
        self.user_data_path = Path(user_data_path)
        super().__init__(Path(bundled_path), app_data_dir=app_data_dir)

    def _load_cache(self, path: Path):
        parsed, meta = super()._load_cache(path)
        source_kind = str(meta.get("source_kind", "")).strip().casefold()
        if self.vehicle_source == USER_SOURCE:
            if source_kind != USER_SOURCE:
                return {}, meta
        elif source_kind == USER_SOURCE:
            return {}, meta
        return parsed, meta

    def reload(self) -> None:
        if self.vehicle_source != USER_SOURCE:
            super().reload()
            return

        self._items.clear()
        self._load_warnings.clear()

        try:
            bundled = AcquisitionDatabase._load_file(self.user_data_path)
        except Exception as exc:
            bundled = {}
            self._load_warnings.append(f"{self.user_data_path.name}: {exc}")

        for car_id, info in bundled.items():
            label = str(info.dataset_name or "").strip()
            if label:
                self._items[car_id] = self._make_car_name(
                    car_id,
                    label,
                    "FH6 Assistant bundled",
                )
        self._built_in_count = len(self._items)

        cached, meta = self._load_cache(self.cache_path)
        if cached:
            self._items.update(cached)
            self._cached_count = len(cached)
        else:
            self._cached_count = 0
        self._cache_updated_at = str(meta.get("downloaded_at", ""))
        self._cache_source_last_modified = str(meta.get("source_last_modified", ""))

        self._base_items = dict(self._items)
        overrides = self._load_override(self.override_path)
        if overrides:
            self._items.update(overrides)
        self._override_count = len(overrides)
