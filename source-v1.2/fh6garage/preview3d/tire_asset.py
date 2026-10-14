from __future__ import annotations

from .pipeline_diagnostics import timed

from contextlib import closing
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import zipfile

from .modelbin_morph import ModelbinMorphError, parse_modelbin_morph_inventory
from .modelbin_morph_profile import profile_weighted_morph_targets
from .vehicle_index import VehicleIndexError, resolve_cars_dir


class TireAssetError(RuntimeError):
    """Raised when a native FH6 tire archive cannot be resolved safely."""


_TIRE_MODEL_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_TIRE_ARCHIVE_RE = re.compile(r"^tire_(.+)\.zip$", re.IGNORECASE)


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


@dataclass(frozen=True)
class TireLibraryEntry:
    tire_model_name: str
    archive_name: str
    archive_path: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class TireLibraryCatalog:
    tires_dir: str
    entries: tuple[TireLibraryEntry, ...]
    duplicate_model_names: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "tires_dir": self.tires_dir,
            "entry_count": len(self.entries),
            "entries": [item.as_dict() for item in self.entries],
            "duplicate_model_names": list(self.duplicate_model_names),
        }


@dataclass(frozen=True)
class TireLibraryCoverage:
    tires_dir: str
    database_path: str
    source_table: str
    database_sha256: str
    database_read_only_unchanged: bool
    library_model_names: tuple[str, ...]
    database_model_names: tuple[str, ...]
    stock_database_model_names: tuple[str, ...]
    matched_model_names: tuple[str, ...]
    missing_database_model_names: tuple[str, ...]
    missing_stock_model_names: tuple[str, ...]
    unused_library_model_names: tuple[str, ...]
    duplicate_library_model_names: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        database_count = len(self.database_model_names)
        stock_count = len(self.stock_database_model_names)
        matched = len(self.matched_model_names)
        stock_missing = len(self.missing_stock_model_names)
        return {
            "format": "fh6_native_tire_library_coverage_v1",
            "tires_dir": self.tires_dir,
            "database_path": self.database_path,
            "source_table": self.source_table,
            "database_sha256": self.database_sha256,
            "database_read_only_unchanged": self.database_read_only_unchanged,
            "library_model_name_count": len(self.library_model_names),
            "database_model_name_count": database_count,
            "stock_database_model_name_count": stock_count,
            "matched_model_name_count": matched,
            "database_coverage_ratio": matched / database_count if database_count else None,
            "stock_coverage_ratio": (stock_count - stock_missing) / stock_count if stock_count else None,
            "library_model_names": list(self.library_model_names),
            "database_model_names": list(self.database_model_names),
            "stock_database_model_names": list(self.stock_database_model_names),
            "matched_model_names": list(self.matched_model_names),
            "missing_database_model_names": list(self.missing_database_model_names),
            "missing_stock_model_names": list(self.missing_stock_model_names),
            "unused_library_model_names": list(self.unused_library_model_names),
            "duplicate_library_model_names": list(self.duplicate_library_model_names),
        }


@dataclass(frozen=True)
class TireMorphArchiveProfile:
    archive_path: str
    archive_sha256: str
    archive_read_only_unchanged: bool
    modelbins: tuple[dict[str, object], ...]
    left_right_morph_buffers_identical: bool | None

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fh6_native_tire_morph_profile_v1",
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "archive_read_only_unchanged": self.archive_read_only_unchanged,
            "modelbin_count": len(self.modelbins),
            "modelbins": list(self.modelbins),
            "left_right_morph_buffers_identical": self.left_right_morph_buffers_identical,
        }


def _normalize_tire_model_name(value: str) -> str:
    name = str(value).strip()
    if not name or name in {".", ".."} or not _TIRE_MODEL_RE.fullmatch(name):
        raise TireAssetError(f"unsafe or invalid TireModelName: {value!r}")
    return name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def scan_tire_library(game_or_cars_path: str | Path) -> TireLibraryCatalog:
    """Enumerate native tire_*.zip assets without collapsing model-name suffixes."""
    tires_dir = tire_library_dir(game_or_cars_path)
    entries: list[TireLibraryEntry] = []
    seen: dict[str, list[str]] = {}
    try:
        children = tuple(tires_dir.iterdir())
    except (OSError, PermissionError) as exc:
        raise TireAssetError(f"could not inspect FH6 tire library: {exc}") from exc

    for child in children:
        if not child.is_file():
            continue
        match = _TIRE_ARCHIVE_RE.fullmatch(child.name)
        if match is None:
            continue
        model_name = _normalize_tire_model_name(match.group(1))
        entries.append(
            TireLibraryEntry(
                tire_model_name=model_name,
                archive_name=child.name,
                archive_path=str(child),
            )
        )
        seen.setdefault(model_name.casefold(), []).append(model_name)

    entries.sort(key=lambda item: (item.tire_model_name.casefold(), item.archive_name.casefold()))
    duplicates = tuple(
        sorted(
            (names[0] for names in seen.values() if len(names) > 1),
            key=str.casefold,
        )
    )
    return TireLibraryCatalog(
        tires_dir=str(tires_dir),
        entries=tuple(entries),
        duplicate_model_names=duplicates,
    )


def compare_tire_library_to_database(
    game_or_cars_path: str | Path,
    database_path: str | Path,
) -> TireLibraryCoverage:
    """Compare exact DB TireModelName values with native tire ZIP names read-only."""
    catalog = scan_tire_library(game_or_cars_path)
    if catalog.duplicate_model_names:
        raise TireAssetError(
            "native tire library contains duplicate case-insensitive model names: "
            + ", ".join(catalog.duplicate_model_names)
        )

    database = Path(database_path).expanduser().resolve()
    if not database.is_file():
        raise TireAssetError(f"FH6 game database does not exist: {database}")
    before = _sha256(database)
    try:
        uri = database.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            tables = {
                str(row[0]).casefold(): str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                )
            }
            table = tables.get("list_upgradetirecompound")
            if table is None:
                raise TireAssetError("FH6 DB is missing List_UpgradeTireCompound")
            quoted = '"' + table.replace('"', '""') + '"'
            columns = {
                str(row[1]).casefold(): str(row[1])
                for row in connection.execute(f"PRAGMA table_info({quoted})")
            }
            model_column = columns.get("tiremodelname")
            if model_column is None:
                raise TireAssetError(f"{table} is missing TireModelName")
            stock_column = columns.get("isstock")
            q_model = '"' + model_column.replace('"', '""') + '"'
            q_stock = (
                '"' + stock_column.replace('"', '""') + '"'
                if stock_column is not None
                else None
            )
            select = q_model + (f", {q_stock}" if q_stock else "")
            rows = list(connection.execute(f"SELECT {select} FROM {quoted}"))
    except sqlite3.Error as exc:
        raise TireAssetError(f"could not read FH6 game database read-only: {exc}") from exc

    after = _sha256(database)
    if before != after:
        raise TireAssetError("read-only tire coverage query changed the source database")

    database_names: dict[str, str] = {}
    stock_names: dict[str, str] = {}
    for row in rows:
        raw = row[0]
        if raw is None or not str(raw).strip():
            continue
        name = _normalize_tire_model_name(str(raw).strip())
        database_names.setdefault(name.casefold(), name)
        if q_stock and bool(row[1]):
            stock_names.setdefault(name.casefold(), name)

    library_names = {
        item.tire_model_name.casefold(): item.tire_model_name for item in catalog.entries
    }
    db_keys = set(database_names)
    library_keys = set(library_names)
    stock_keys = set(stock_names)

    def values(keys: set[str], source: dict[str, str]) -> tuple[str, ...]:
        return tuple(sorted((source[key] for key in keys), key=str.casefold))

    return TireLibraryCoverage(
        tires_dir=catalog.tires_dir,
        database_path=str(database),
        source_table=table,
        database_sha256=before,
        database_read_only_unchanged=True,
        library_model_names=values(library_keys, library_names),
        database_model_names=values(db_keys, database_names),
        stock_database_model_names=values(stock_keys, stock_names),
        matched_model_names=values(db_keys & library_keys, database_names),
        missing_database_model_names=values(db_keys - library_keys, database_names),
        missing_stock_model_names=values(stock_keys - library_keys, stock_names),
        unused_library_model_names=values(library_keys - db_keys, library_names),
        duplicate_library_model_names=catalog.duplicate_model_names,
    )


def profile_tire_morph_archive(archive_path: str | Path) -> TireMorphArchiveProfile:
    """Profile all weighted tire morph selectors without applying geometry changes."""
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file():
        raise TireAssetError(f"native tire archive does not exist: {archive}")
    before = _sha256(archive)
    model_reports: list[dict[str, object]] = []
    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            model_entries = [
                item for item in bundle.infolist()
                if not item.is_dir() and item.filename.casefold().endswith(".modelbin")
            ]
            for item in model_entries:
                data = bundle.read(item)
                try:
                    inventory = parse_modelbin_morph_inventory(data)
                    buffers = {buffer.blob_index: buffer for buffer in inventory.morph_buffers}
                    resolutions = {
                        resolution.mesh_blob_index: resolution
                        for resolution in inventory.resolutions
                    }
                    groups: dict[tuple[int, int], list[int]] = {}
                    unresolved: list[int] = []
                    weighted_mesh_count = 0
                    for mesh in inventory.mesh_bindings:
                        if mesh.is_morph_damage or mesh.morph_target_count <= 0:
                            continue
                        weighted_mesh_count += 1
                        resolution = resolutions.get(mesh.blob_index)
                        if resolution is None or resolution.morph_buffer_blob_index is None:
                            unresolved.append(mesh.blob_index)
                            continue
                        key = (resolution.morph_buffer_blob_index, mesh.morph_target_count)
                        groups.setdefault(key, []).append(mesh.blob_index)

                    profiles: list[dict[str, object]] = []
                    raw_hashes: list[str] = []
                    for (buffer_blob_index, target_count), mesh_blob_indices in sorted(groups.items()):
                        morph_buffer = buffers.get(buffer_blob_index)
                        if morph_buffer is None:
                            raise TireAssetError(
                                f"{item.filename}: resolved MBuf blob {buffer_blob_index} is missing"
                            )
                        profile = profile_weighted_morph_targets(morph_buffer, target_count)
                        raw_hash = hashlib.sha256(morph_buffer.raw_data).hexdigest()
                        raw_hashes.append(raw_hash)
                        profiles.append(
                            {
                                "mesh_blob_indices": mesh_blob_indices,
                                "morph_buffer_raw_sha256": raw_hash,
                                "profile": profile.as_dict(),
                            }
                        )
                except ModelbinMorphError as exc:
                    raise TireAssetError(
                        f"could not profile weighted morphs in {item.filename}: {exc}"
                    ) from exc

                model_reports.append(
                    {
                        "entry": item.filename.replace("\\", "/"),
                        "modelbin_sha256": hashlib.sha256(data).hexdigest(),
                        "mesh_binding_count": len(inventory.mesh_bindings),
                        "weighted_mesh_count": weighted_mesh_count,
                        "damage_mesh_count": sum(
                            1 for mesh in inventory.mesh_bindings if mesh.is_morph_damage
                        ),
                        "morph_buffer_count": len(inventory.morph_buffers),
                        "unresolved_weighted_mesh_blob_indices": unresolved,
                        "morph_buffer_raw_sha256s": raw_hashes,
                        "profiles": profiles,
                    }
                )
    except (OSError, zipfile.BadZipFile) as exc:
        raise TireAssetError(f"could not read native tire archive {archive}: {exc}") from exc

    after = _sha256(archive)
    if before != after:
        raise TireAssetError("read-only tire morph profiling changed the source archive")

    identical: bool | None = None
    if len(model_reports) == 2:
        identical = (
            model_reports[0]["morph_buffer_raw_sha256s"]
            == model_reports[1]["morph_buffer_raw_sha256s"]
        )
    return TireMorphArchiveProfile(
        archive_path=str(archive),
        archive_sha256=before,
        archive_read_only_unchanged=True,
        modelbins=tuple(model_reports),
        left_right_morph_buffers_identical=identical,
    )


@timed('tire_archive_resolve')
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


def report_json(
    report: TireArchiveReport | TireLibraryCatalog | TireLibraryCoverage | TireMorphArchiveProfile,
) -> str:
    return json.dumps(report.as_dict(), indent=2, ensure_ascii=False)
