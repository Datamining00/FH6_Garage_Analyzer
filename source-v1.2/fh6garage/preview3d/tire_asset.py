from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import zipfile

from .vehicle_index import VehicleIndexError, resolve_cars_dir


class TireAssetError(RuntimeError):
    """Raised when a native FH6 tire archive cannot be resolved safely."""


_TIRE_MODEL_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class TireArchiveReport:
    tire_model_name: str
    cars_dir: str
    tires_dir: str
    archive_path: str
    archive_name: str
    entry_count: int
    modelbin_entries: tuple[str, ...]
    preferred_modelbin_entries: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalize_tire_model_name(value: str) -> str:
    name = str(value).strip()
    if not name or name in {".", ".."} or not _TIRE_MODEL_RE.fullmatch(name):
        raise TireAssetError(f"unsafe or invalid TireModelName: {value!r}")
    return name


def tire_library_dir(game_or_cars_path: str | Path) -> Path:
    """Resolve Content/media/cars/_library/scene/tires without modifying it."""
    try:
        cars_dir = resolve_cars_dir(game_or_cars_path)
    except VehicleIndexError as exc:
        raise TireAssetError(str(exc)) from exc
    tires_dir = cars_dir / "_library" / "scene" / "tires"
    if not tires_dir.is_dir():
        raise TireAssetError(f"FH6 tire library directory does not exist: {tires_dir}")
    return tires_dir


def resolve_tire_archive(
    game_or_cars_path: str | Path,
    tire_model_name: str,
) -> Path:
    """Resolve tire_<TireModelName>.zip case-insensitively in the native tire library."""
    name = _normalize_tire_model_name(tire_model_name)
    tires_dir = tire_library_dir(game_or_cars_path)
    wanted = f"tire_{name}.zip".casefold()

    try:
        matches = [
            child
            for child in tires_dir.iterdir()
            if child.is_file() and child.name.casefold() == wanted
        ]
    except (OSError, PermissionError) as exc:
        raise TireAssetError(f"could not inspect FH6 tire library: {exc}") from exc

    if not matches:
        raise TireAssetError(
            f"native FH6 tire archive was not found for TireModelName={name!r}; "
            f"expected tire_{name}.zip below {tires_dir}"
        )
    if len(matches) > 1:
        raise TireAssetError(
            f"native FH6 tire archive is ambiguous for TireModelName={name!r}: "
            + ", ".join(str(path) for path in matches)
        )
    return matches[0]


def inspect_tire_archive(
    game_or_cars_path: str | Path,
    tire_model_name: str,
) -> TireArchiveReport:
    """Inspect a native tire ZIP read-only and identify modelbin candidates."""
    name = _normalize_tire_model_name(tire_model_name)
    archive = resolve_tire_archive(game_or_cars_path, name)
    tires_dir = archive.parent
    cars_dir = tires_dir.parents[2]

    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            entries = tuple(item.filename.replace("\\", "/") for item in bundle.infolist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise TireAssetError(f"could not read native tire archive {archive}: {exc}") from exc

    modelbins = tuple(
        entry for entry in entries if entry.casefold().endswith(".modelbin")
    )
    left_name = f"tireL_{name}.modelbin".casefold()
    right_name = f"tireR_{name}.modelbin".casefold()

    preferred = tuple(
        entry
        for entry in modelbins
        if Path(entry).name.casefold() in {left_name, right_name}
    )

    return TireArchiveReport(
        tire_model_name=name,
        cars_dir=str(cars_dir),
        tires_dir=str(tires_dir),
        archive_path=str(archive),
        archive_name=archive.name,
        entry_count=len(entries),
        modelbin_entries=modelbins,
        preferred_modelbin_entries=preferred,
    )


def report_json(report: TireArchiveReport) -> str:
    return json.dumps(report.as_dict(), indent=2, ensure_ascii=False)
