from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fh6garage.preview3d.wheel_spec import FH6WheelSpecResolver  # noqa: E402

TARGET_TABLES = (
    "Drivable_Data_Car",
    "Data_Car",
    "Data_CarBody",
    "List_UpgradeCarBody",
    "List_UpgradeRimSizeFront",
    "List_UpgradeRimSizeRear",
    "List_UpgradeCarBodyTireWidthFront",
    "List_UpgradeCarBodyTireWidthRear",
    "List_UpgradeCarBodyTireAspectRatioFront",
    "List_UpgradeCarBodyTireAspectRatioRear",
    "List_UpgradeCarBodyTrackSpacingFront",
    "List_UpgradeCarBodyTrackSpacingRear",
    "List_UpgradeTireCompound",
    "List_Wheels",
    "List_UpgradeBrakes",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _table_map(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    )
    return {str(row[0]).casefold(): str(row[0]) for row in rows}


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    quoted = '"' + table.replace('"', '""') + '"'
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted})")]


def _car_identity(connection: sqlite3.Connection, car_id: int) -> dict[str, Any]:
    tables = _table_map(connection)
    table = tables.get("drivable_data_car") or tables.get("data_car")
    if not table:
        return {}
    columns = {name.casefold(): name for name in _columns(connection, table)}
    id_column = columns.get("id")
    if not id_column:
        return {}
    wanted = [
        name
        for key in ("id", "medianame", "makedisplayname", "modeldisplayname")
        if (name := columns.get(key)) is not None
    ]
    quoted_table = '"' + table.replace('"', '""') + '"'
    quoted_id = '"' + id_column.replace('"', '""') + '"'
    select = ", ".join('"' + name.replace('"', '""') + '"' for name in wanted)
    row = connection.execute(
        f"SELECT {select} FROM {quoted_table} WHERE {quoted_id}=? LIMIT 1",
        (int(car_id),),
    ).fetchone()
    return dict(row) if row is not None else {}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate FH6 WheelSpec resolver against a real read-only FH6 SQLite DB."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--car-id", type=int, action="append", dest="car_ids")
    args = parser.parse_args()

    database = args.db.resolve()
    if not database.is_file():
        raise SystemExit(f"Database does not exist: {database}")

    car_ids = args.car_ids or [1006, 1229, 1260]
    before_sha256 = _sha256(database)

    schema: dict[str, Any] = {}
    identities: dict[str, Any] = {}
    with _connect_read_only(database) as connection:
        tables = _table_map(connection)
        for requested in TARGET_TABLES:
            actual = tables.get(requested.casefold())
            schema[requested] = {
                "present": actual is not None,
                "actual_name": actual,
                "columns": _columns(connection, actual) if actual else [],
            }
        for car_id in car_ids:
            identities[str(car_id)] = _car_identity(connection, car_id)

    resolver = FH6WheelSpecResolver(database)
    resolved: dict[str, Any] = {}
    failures: dict[str, str] = {}
    for car_id in car_ids:
        try:
            resolved[str(car_id)] = resolver.resolve(car_id).as_dict()
        except Exception as exc:  # diagnostic boundary for real upstream data
            failures[str(car_id)] = f"{type(exc).__name__}: {exc}"

    after_sha256 = _sha256(database)
    report = {
        "format": "fh6_wheel_spec_real_db_validation_v1",
        "database": {
            "path_name": database.name,
            "size": database.stat().st_size,
            "sha256_before": before_sha256,
            "sha256_after": after_sha256,
            "read_only_unchanged": before_sha256 == after_sha256,
        },
        "schema": schema,
        "car_identity": identities,
        "resolved_stock_specs": resolved,
        "failures": failures,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    required = (
        "List_UpgradeCarBody",
        "List_UpgradeRimSizeFront",
        "List_UpgradeRimSizeRear",
        "List_UpgradeCarBodyTireWidthFront",
        "List_UpgradeCarBodyTireWidthRear",
        "List_UpgradeTireCompound",
    )
    missing_required = [name for name in required if not schema[name]["present"]]
    if missing_required:
        raise SystemExit("Required FH6 wheel tables are missing: " + ", ".join(missing_required))
    if before_sha256 != after_sha256:
        raise SystemExit("Read-only validation changed the database SHA-256")
    if "1006" in failures:
        raise SystemExit("Car ID 1006 failed real-DB wheel spec resolution: " + failures["1006"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
