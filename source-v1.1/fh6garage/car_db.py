from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import CarName


REMOTE_SOURCE_URL = "https://gist.githubusercontent.com/HDR/0659d1717bc61504bf83750628963f4f/raw/Forza%20Horizon%206%20Car%20Ordinals.json"
REMOTE_SOURCE_PAGE = "https://gist.github.com/HDR/0659d1717bc61504bf83750628963f4f"
UPSTREAM_REFERENCE = REMOTE_SOURCE_PAGE
CACHE_FILE_NAME = "fh6_car_ordinals.json"
OVERRIDE_FILE_NAME = "car_overrides.json"
MAX_DOWNLOAD_BYTES = 1024 * 1024


@dataclass(slots=True)
class CarDatabaseStatus:
    built_in_count: int
    cached_count: int
    override_count: int
    effective_count: int
    cache_updated_at: str = ""
    cache_source_last_modified: str = ""
    load_warning: str = ""


@dataclass(slots=True)
class CarDatabaseUpdateResult:
    count: int
    downloaded_at: str
    source_last_modified: str
    cache_path: Path


class CarDatabaseError(RuntimeError):
    pass


class CarDatabase:
    """Offline-first CarOrdinal -> display-name provider.

    Resolution order:
      1) bundled baseline database shipped with the application
      2) optional user-requested update cache in LocalAppData
      3) optional user overrides in LocalAppData

    No network request is made by construction or lookup. `fetch_remote_update()` is
    only called from the explicit UI update button.
    """

    def __init__(self, bundled_path: Path, app_data_dir: Path | None = None):
        self.bundled_path = bundled_path
        self.app_data_dir = app_data_dir or self.default_app_data_dir()
        self.cache_path = self.app_data_dir / CACHE_FILE_NAME
        self.override_path = self.app_data_dir / OVERRIDE_FILE_NAME
        self._items: dict[int, CarName] = {}
        self._base_items: dict[int, CarName] = {}
        self._built_in_count = 0
        self._cached_count = 0
        self._override_count = 0
        self._cache_updated_at = ""
        self._cache_source_last_modified = ""
        self._load_warnings: list[str] = []
        self.reload()

    @staticmethod
    def default_app_data_dir() -> Path:
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "FH6GarageAnalyzer"
        return Path.home() / ".fh6garage"

    def reload(self) -> None:
        self._items.clear()
        self._load_warnings.clear()

        built_in, bundled_meta = self._load_bundled(self.bundled_path)
        self._items.update(built_in)
        self._built_in_count = len(built_in)

        cached, meta = self._load_cache(self.cache_path)
        use_cache = bool(cached) and self._cache_is_newer_than_bundled(
            meta, bundled_meta
        )
        if use_cache:
            self._items.update(cached)
            self._cached_count = len(cached)
        else:
            self._cached_count = 0
            if cached:
                self._load_warnings.append(
                    "기존 업데이트 DB가 내장 DB보다 오래되어 사용하지 않음"
                )
        self._cache_updated_at = str(meta.get("downloaded_at", ""))
        self._cache_source_last_modified = str(meta.get("source_last_modified", ""))

        # Snapshot before user overrides are applied.
        self._base_items = dict(self._items)

        overrides = self._load_override(self.override_path)
        if overrides:
            self._items.update(overrides)
        self._override_count = len(overrides)

    @property
    def status(self) -> CarDatabaseStatus:
        return CarDatabaseStatus(
            built_in_count=self._built_in_count,
            cached_count=self._cached_count,
            override_count=self._override_count,
            effective_count=len(self._items),
            cache_updated_at=self._cache_updated_at,
            cache_source_last_modified=self._cache_source_last_modified,
            load_warning="; ".join(self._load_warnings),
        )

    def get(self, car_id: int) -> CarName:
        return self._items.get(car_id, CarName(car_id=car_id, label=f"Car ID {car_id}"))

    def is_known(self, car_id: int) -> bool:
        return car_id in self._items

    def all_items(self) -> dict[int, CarName]:
        """Return the effective Car ID mapping in numeric order."""
        return {car_id: self._items[car_id] for car_id in sorted(self._items)}

    def base_label(self, car_id: int) -> str:
        """Return the name before user override, or the default unknown label."""
        item = self._base_items.get(int(car_id))
        return item.label if item is not None else f"Car ID {int(car_id)}"

    def unknown_ids(self, car_ids: Iterable[int]) -> list[int]:
        return sorted({int(x) for x in car_ids if int(x) not in self._items})

    def user_overrides(self) -> dict[int, str]:
        """Return only user-authored Car ID -> display-name overrides."""
        parsed = self._load_override(self.override_path)
        return {car_id: item.label for car_id, item in sorted(parsed.items())}

    def replace_user_overrides(self, overrides: dict[int, str]) -> None:
        """Replace all user-authored overrides in one atomic write."""
        normalized: dict[int, str] = {}
        for raw_id, raw_label in overrides.items():
            car_id = int(raw_id)
            label = str(raw_label).strip()
            if car_id <= 0:
                raise ValueError("Car ID는 1 이상의 정수여야 합니다.")
            if not label:
                raise ValueError(f"Car ID {car_id}의 차량명은 비워둘 수 없습니다.")
            normalized[car_id] = label

        self._write_user_overrides(normalized)
        self.reload()

    def set_user_override(self, car_id: int, label: str) -> None:
        car_id = int(car_id)
        label = str(label).strip()
        if car_id <= 0:
            raise ValueError("Car ID는 1 이상의 정수여야 합니다.")
        if not label:
            raise ValueError("차량명은 비워둘 수 없습니다.")

        overrides = self.user_overrides()
        overrides[car_id] = label
        self._write_user_overrides(overrides)
        self.reload()

    def remove_user_override(self, car_id: int) -> bool:
        car_id = int(car_id)
        overrides = self.user_overrides()
        if car_id not in overrides:
            return False
        del overrides[car_id]
        self._write_user_overrides(overrides)
        self.reload()
        return True

    def _write_user_overrides(self, overrides: dict[int, str]) -> None:
        """Atomically persist only user-authored vehicle-name corrections."""
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": 1,
            "cars": {
                str(k): str(v).strip()
                for k, v in sorted(overrides.items())
                if str(v).strip()
            },
        }

        fd, tmp_name = tempfile.mkstemp(
            prefix="car_overrides_",
            suffix=".tmp",
            dir=str(self.app_data_dir),
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.override_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def ensure_override_template(self) -> Path:
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        if not self.override_path.exists():
            payload = {
                "schema": 1,
                "cars": {},
                "note": "Add entries like \"4223\": \"2000 Nissan Skyline GT-R V-Spec II\". Overrides win over all other sources.",
            }
            self.override_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.override_path

    @classmethod
    def fetch_remote_update(cls, cache_path: Path, timeout: int = 20) -> CarDatabaseUpdateResult:
        """Download the community mapping and atomically store a normalized cache.

        This function sends only a normal HTTP GET for the mapping URL. It receives
        no save path and no save data.
        """
        req = urllib.request.Request(
            REMOTE_SOURCE_URL,
            headers={
                "User-Agent": "FH6-Assistant/1.1",
                "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1",
                "Cache-Control": "no-cache",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read(MAX_DOWNLOAD_BYTES + 1)
                if len(raw) > MAX_DOWNLOAD_BYTES:
                    raise CarDatabaseError("차량 DB 응답이 예상 크기(1 MiB)를 초과했습니다.")
                last_modified = response.headers.get("Last-Modified", "")
        except Exception as exc:
            if isinstance(exc, CarDatabaseError):
                raise
            raise CarDatabaseError(f"차량 DB 다운로드 실패: {exc}") from exc

        try:
            source = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CarDatabaseError(f"차량 DB JSON 파싱 실패: {exc}") from exc

        normalized = cls._normalize_remote_mapping(source)
        if len(normalized) < 500:
            raise CarDatabaseError(
                f"차량 DB 항목이 {len(normalized)}개뿐입니다. 불완전한 응답으로 판단하여 적용하지 않았습니다."
            )

        downloaded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        payload = {
            "schema": 1,
            "source_url": REMOTE_SOURCE_URL,
            "source_page": REMOTE_SOURCE_PAGE,
            "upstream_reference": UPSTREAM_REFERENCE,
            "downloaded_at": downloaded_at,
            "source_last_modified": last_modified,
            "count": len(normalized),
            "cars": {str(k): v.label for k, v in sorted(normalized.items())},
        }

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="fh6_car_ordinals_", suffix=".tmp", dir=str(cache_path.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, cache_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        return CarDatabaseUpdateResult(
            count=len(normalized),
            downloaded_at=downloaded_at,
            source_last_modified=last_modified,
            cache_path=cache_path,
        )

    @classmethod
    def _normalize_remote_mapping(cls, source: object) -> dict[int, CarName]:
        if not isinstance(source, dict):
            raise CarDatabaseError("차량 DB 최상위 JSON이 object가 아닙니다.")

        result: dict[int, CarName] = {}
        # Upstream format is {"full display name": "CarOrdinal"}.
        for label_raw, car_id_raw in source.items():
            if not isinstance(label_raw, str) or not label_raw.strip():
                continue
            try:
                car_id = int(car_id_raw)
            except (TypeError, ValueError):
                continue
            if car_id <= 0:
                continue
            label = label_raw.strip()
            previous = result.get(car_id)
            if previous is not None and previous.label != label:
                raise CarDatabaseError(
                    f"동일 Car ID {car_id}에 서로 다른 이름이 존재합니다: '{previous.label}' / '{label}'"
                )
            result[car_id] = cls._make_car_name(car_id, label, "community update")
        return result

    @classmethod
    def _load_bundled(
        cls, path: Path
    ) -> tuple[dict[int, CarName], dict[str, object]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}, {}
        if not isinstance(data, dict):
            return {}, {}
        if "cars" in data:
            cars = data.get("cars", {})
            parsed = cls._parse_id_mapping(cars, "bundled")
            return parsed, data
        # Backward compatibility with the original flat ID -> label file.
        return cls._parse_id_mapping(data, "bundled"), {}

    @staticmethod
    def _cache_is_newer_than_bundled(
        cache_meta: dict[str, object],
        bundled_meta: dict[str, object],
    ) -> bool:
        """Use a local downloaded cache only when it post-dates the bundled snapshot."""
        bundled_raw = str(bundled_meta.get("source_updated_at", "")).strip()
        if not bundled_raw:
            return True
        cache_raw = str(cache_meta.get("downloaded_at", "")).strip()
        if not cache_raw:
            return False
        try:
            bundled_at = datetime.fromisoformat(bundled_raw.replace("Z", "+00:00"))
            cache_at = datetime.fromisoformat(cache_raw.replace("Z", "+00:00"))
        except ValueError:
            # Unknown cache freshness must not replace a known bundled snapshot.
            return False
        if bundled_at.tzinfo is None:
            bundled_at = bundled_at.replace(tzinfo=timezone.utc)
        if cache_at.tzinfo is None:
            cache_at = cache_at.replace(tzinfo=timezone.utc)
        return cache_at > bundled_at

    def _load_cache(self, path: Path) -> tuple[dict[int, CarName], dict[str, object]]:
        if not path.is_file():
            return {}, {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._load_warnings.append(f"업데이트 DB를 읽지 못함: {exc}")
            return {}, {}
        if not isinstance(data, dict):
            self._load_warnings.append("업데이트 DB 형식이 잘못됨")
            return {}, {}
        cars = data.get("cars", {})
        parsed = self._parse_id_mapping(cars, "community update")
        declared = data.get("count")
        if declared is not None:
            try:
                if int(declared) != len(parsed):
                    self._load_warnings.append("업데이트 DB count 메타데이터가 실제 항목 수와 다름")
            except (TypeError, ValueError):
                self._load_warnings.append("업데이트 DB count 메타데이터가 잘못됨")
        return parsed, data

    def _load_override(self, path: Path) -> dict[int, CarName]:
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._load_warnings.append(f"사용자 override를 읽지 못함: {exc}")
            return {}
        if isinstance(data, dict) and "cars" in data:
            data = data.get("cars", {})
        return self._parse_id_mapping(data, "user override")

    @classmethod
    def _parse_id_mapping(cls, data: object, source: str) -> dict[int, CarName]:
        result: dict[int, CarName] = {}
        if not isinstance(data, dict):
            return result
        for key, value in data.items():
            try:
                car_id = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(value, str):
                label = value.strip()
                if label:
                    result[car_id] = cls._make_car_name(car_id, label, source)
                continue
            if not isinstance(value, dict):
                continue
            label = str(value.get("label", "")).strip()
            if not label:
                continue
            result[car_id] = CarName(
                car_id=car_id,
                label=label,
                manufacturer=str(value.get("manufacturer", "")),
                model=str(value.get("model", "")),
                source=str(value.get("source", source)),
            )
        return result

    @staticmethod
    def _make_car_name(car_id: int, label: str, source: str) -> CarName:
        # Keep the original full display name as authoritative. Manufacturer/model
        # splitting is best-effort metadata only and is not used for rendering.
        parts = label.split(maxsplit=2)
        manufacturer = parts[1] if len(parts) >= 2 and parts[0].isdigit() else ""
        model = parts[2] if len(parts) >= 3 and parts[0].isdigit() else ""
        return CarName(
            car_id=car_id,
            label=label,
            manufacturer=manufacturer,
            model=model,
            source=source,
        )
