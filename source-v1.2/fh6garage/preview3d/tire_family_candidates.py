from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import sqlite3
from typing import Any, Sequence

from .tire_asset import TireAssetError, scan_tire_library
from .wheel_spec import FH6WheelSpecResolver, VehicleWheelSpec, WheelSpecError


class TireFamilyCandidateError(RuntimeError):
    """Raised when diagnostic tire-family candidates cannot be selected safely."""


@dataclass(frozen=True)
class TireFamilyCandidate:
    car_id: int
    tire_model_name: str
    archive_name: str
    archive_path: str
    spec: VehicleWheelSpec

    def as_dict(self) -> dict[str, Any]:
        return {
            "car_id": self.car_id,
            "tire_model_name": self.tire_model_name,
            "archive_name": self.archive_name,
            "archive_path": self.archive_path,
            "spec": self.spec.as_dict(),
        }


@dataclass(frozen=True)
class TireFamilyCandidateReport:
    database_path: str
    database_sha256: str
    database_read_only_unchanged: bool
    tires_dir: str
    source_table: str
    requested_limit: int
    excluded_model_names: tuple[str, ...]
    library_family_count: int
    stock_db_family_count: int
    matched_stock_family_count: int
    candidate_family_count: int
    candidates: tuple[TireFamilyCandidate, ...]
    rejected_unresolvable_car_ids: tuple[int, ...]
    production_mapping_enabled: bool
    complete_mapping_status: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "fh6_native_tire_family_candidates_v1",
            "database_path": self.database_path,
            "database_sha256": self.database_sha256,
            "database_read_only_unchanged": self.database_read_only_unchanged,
            "tires_dir": self.tires_dir,
            "source_table": self.source_table,
            "requested_limit": self.requested_limit,
            "excluded_model_names": list(self.excluded_model_names),
            "library_family_count": self.library_family_count,
            "stock_db_family_count": self.stock_db_family_count,
            "matched_stock_family_count": self.matched_stock_family_count,
            "candidate_family_count": self.candidate_family_count,
            "candidates": [item.as_dict() for item in self.candidates],
            "rejected_unresolvable_car_ids": list(self.rejected_unresolvable_car_ids),
            "production_mapping_enabled": self.production_mapping_enabled,
            "complete_mapping_status": self.complete_mapping_status,
            "limitations": list(self.limitations),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_map(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row[0]).casefold(): str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
    }


def _column_map(connection: sqlite3.Connection, table: str) -> dict[str, str]:
    return {
        str(row[1]).casefold(): str(row[1])
        for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
    }


def select_stock_tire_family_candidates(
    game_or_cars_path: str | Path,
    database_path: str | Path,
    *,
    exclude_model_names: Sequence[str] = (),
    limit: int = 5,
) -> TireFamilyCandidateReport:
    """Select representative stock cars for distinct native tire families read-only.

    The selector exact-matches stock ``List_UpgradeTireCompound.TireModelName``
    values against ``tire_<TireModelName>.zip`` in the installed native tire
    library. One resolvable stock car is retained per distinct model name. This
    only prepares inputs for cross-family diagnostics; it never enables tire
    production assembly.
    """
    requested_limit = int(limit)
    if requested_limit <= 0:
        raise TireFamilyCandidateError(f"limit must be positive: {limit}")

    database = Path(database_path).expanduser().resolve()
    if not database.is_file():
        raise TireFamilyCandidateError(f"FH6 game database does not exist: {database}")

    try:
        catalog = scan_tire_library(game_or_cars_path)
    except TireAssetError as exc:
        raise TireFamilyCandidateError(str(exc)) from exc
    if catalog.duplicate_model_names:
        raise TireFamilyCandidateError(
            "native tire library contains duplicate case-insensitive model names: "
            + ", ".join(catalog.duplicate_model_names)
        )

    excluded = {
        str(value).strip().casefold()
        for value in exclude_model_names
        if str(value).strip()
    }
    excluded_names = tuple(sorted(excluded))
    library_by_key = {
        item.tire_model_name.casefold(): item for item in catalog.entries
    }

    before = _sha256(database)
    try:
        uri = database.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            tables = _table_map(connection)
            table = tables.get("list_upgradetirecompound")
            if table is None:
                raise TireFamilyCandidateError(
                    "FH6 DB is missing List_UpgradeTireCompound"
                )
            columns = _column_map(connection, table)
            ordinal = columns.get("ordinal")
            model = columns.get("tiremodelname")
            stock = columns.get("isstock")
            if ordinal is None or model is None or stock is None:
                raise TireFamilyCandidateError(
                    f"{table} must contain Ordinal, TireModelName, and IsStock"
                )
            rows = list(
                connection.execute(
                    f"SELECT {_quote(ordinal)}, {_quote(model)} "
                    f"FROM {_quote(table)} "
                    f"WHERE {_quote(stock)} != 0 "
                    f"ORDER BY {_quote(ordinal)} ASC"
                )
            )
    except sqlite3.Error as exc:
        raise TireFamilyCandidateError(
            f"could not read FH6 game database read-only: {exc}"
        ) from exc

    after = _sha256(database)
    if before != after:
        raise TireFamilyCandidateError(
            "read-only tire family candidate query changed the source database"
        )

    stock_names: dict[str, str] = {}
    matched_keys: set[str] = set()
    rows_by_family: dict[str, list[int]] = {}
    display_by_family: dict[str, str] = {}
    for row in rows:
        raw_id, raw_model = row[0], row[1]
        if raw_id is None or raw_model is None:
            continue
        try:
            car_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        model_name = str(raw_model).strip()
        if car_id <= 0 or not model_name:
            continue
        key = model_name.casefold()
        stock_names.setdefault(key, model_name)
        if key in excluded or key not in library_by_key:
            continue
        matched_keys.add(key)
        display_by_family.setdefault(key, model_name)
        rows_by_family.setdefault(key, []).append(car_id)

    resolver = FH6WheelSpecResolver(database)
    candidates: list[TireFamilyCandidate] = []
    rejected_ids: list[int] = []
    for family_key in sorted(rows_by_family, key=lambda key: display_by_family[key].casefold()):
        selected: TireFamilyCandidate | None = None
        for car_id in rows_by_family[family_key]:
            try:
                spec = resolver.resolve(car_id)
            except WheelSpecError:
                rejected_ids.append(car_id)
                continue
            if str(spec.mode).casefold() != "stock":
                rejected_ids.append(car_id)
                continue
            if not spec.tire_model_name or spec.tire_model_name.casefold() != family_key:
                rejected_ids.append(car_id)
                continue
            asset = library_by_key[family_key]
            selected = TireFamilyCandidate(
                car_id=car_id,
                tire_model_name=asset.tire_model_name,
                archive_name=asset.archive_name,
                archive_path=asset.archive_path,
                spec=spec,
            )
            break
        if selected is not None:
            candidates.append(selected)
        if len(candidates) >= requested_limit:
            break

    status = (
        "diagnostic_family_candidates_ready"
        if len(candidates) >= 2
        else "diagnostic_family_candidates_insufficient"
    )
    return TireFamilyCandidateReport(
        database_path=str(database),
        database_sha256=before,
        database_read_only_unchanged=True,
        tires_dir=catalog.tires_dir,
        source_table=table,
        requested_limit=requested_limit,
        excluded_model_names=excluded_names,
        library_family_count=len(library_by_key),
        stock_db_family_count=len(stock_names),
        matched_stock_family_count=len(matched_keys),
        candidate_family_count=len(candidates),
        candidates=tuple(candidates),
        rejected_unresolvable_car_ids=tuple(sorted(set(rejected_ids))),
        production_mapping_enabled=False,
        complete_mapping_status=status,
        limitations=(
            "Candidates are exact stock TireModelName-to-archive matches only; no morph or physical-dimension corroboration is performed here.",
            "One representative resolvable car is selected per family; other cars in the same TireModelName family are intentionally omitted.",
            "Production tire assembly remains disabled regardless of candidate count.",
        ),
    )
