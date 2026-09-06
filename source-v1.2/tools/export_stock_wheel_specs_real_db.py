from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


REQUIRED_COLUMNS = (
    "Id",
    "MediaName",
    "FrontTireWidthMM",
    "FrontTireAspect",
    "FrontWheelDiameterIN",
    "RearTireWidthMM",
    "RearTireAspect",
    "RearWheelDiameterIN",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


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


def _columns(connection: sqlite3.Connection, table: str) -> dict[str, str]:
    quoted = '"' + table.replace('"', '""') + '"'
    return {
        str(row[1]).casefold(): str(row[1])
        for row in connection.execute(f"PRAGMA table_info({quoted})")
    }


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _source_table(connection: sqlite3.Connection) -> tuple[str, dict[str, str]]:
    tables = _table_map(connection)
    for requested in ("Data_Car", "Drivable_Data_Car"):
        actual = tables.get(requested.casefold())
        if not actual:
            continue
        columns = _columns(connection, actual)
        missing = [name for name in REQUIRED_COLUMNS if name.casefold() not in columns]
        if not missing:
            return actual, columns
    raise RuntimeError(
        "FH6 DB has no Data_Car/Drivable_Data_Car table containing all required stock wheel columns"
    )


def export_stock_wheel_specs(
    database: Path,
    *,
    source_repository: str,
    source_commit: str,
    source_blob_sha1: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before_sha256 = _sha256(database)
    actual_blob_sha1 = _git_blob_sha1(database)
    if source_blob_sha1 and actual_blob_sha1.casefold() != source_blob_sha1.casefold():
        raise RuntimeError(
            f"source Git blob mismatch: expected {source_blob_sha1}, got {actual_blob_sha1}"
        )

    with _connect_read_only(database) as connection:
        table, columns = _source_table(connection)
        select_columns = [columns[name.casefold()] for name in REQUIRED_COLUMNS]
        sql = (
            "SELECT "
            + ", ".join(_quote(name) for name in select_columns)
            + f" FROM {_quote(table)} ORDER BY {_quote(columns['id'])}"
        )
        rows = list(connection.execute(sql))

    after_sha256 = _sha256(database)
    if before_sha256 != after_sha256:
        raise RuntimeError("read-only export changed the source database")

    records: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    duplicate_ids: list[int] = []

    value_fields = (
        "front_tire_width_mm",
        "front_tire_aspect",
        "front_wheel_diameter_in",
        "rear_tire_width_mm",
        "rear_tire_aspect",
        "rear_wheel_diameter_in",
    )

    for row in rows:
        car_id = int(row[select_columns[0]])
        if car_id in seen_ids:
            duplicate_ids.append(car_id)
        seen_ids.add(car_id)
        record = {
            "car_id": car_id,
            "media_name": str(row[select_columns[1]] or "").strip(),
            "front_tire_width_mm": float(row[select_columns[2]] or 0),
            "front_tire_aspect": float(row[select_columns[3]] or 0),
            "front_wheel_diameter_in": float(row[select_columns[4]] or 0),
            "rear_tire_width_mm": float(row[select_columns[5]] or 0),
            "rear_tire_aspect": float(row[select_columns[6]] or 0),
            "rear_wheel_diameter_in": float(row[select_columns[7]] or 0),
        }
        missing = []
        if not record["media_name"]:
            missing.append("media_name")
        for key in value_fields:
            if float(record[key]) <= 0.0:
                missing.append(key)
        if missing:
            incomplete.append({"car_id": car_id, "media_name": record["media_name"], "missing": missing})
        else:
            records.append(record)

    ranges = {}
    for key in value_fields:
        values = [float(record[key]) for record in records]
        ranges[key] = {
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }

    provenance = {
        "source_repository": source_repository,
        "source_commit": source_commit,
        "source_git_blob_sha1": actual_blob_sha1,
        "source_database_sha256": before_sha256,
        "source_database_size": database.stat().st_size,
        "source_table": table,
        "source_columns": list(REQUIRED_COLUMNS),
        "database_read_only_unchanged": before_sha256 == after_sha256,
    }
    dataset = {
        "format": "fh6_stock_wheel_specs_v1",
        "provenance": provenance,
        "records": records,
    }
    report = {
        "format": "fh6_stock_wheel_specs_export_report_v1",
        "provenance": provenance,
        "source_row_count": len(rows),
        "complete_record_count": len(records),
        "incomplete_record_count": len(incomplete),
        "duplicate_car_ids": sorted(set(duplicate_ids)),
        "ranges": ranges,
        "incomplete_records": incomplete,
        "car_1006": next((record for record in records if record["car_id"] == 1006), None),
    }
    return dataset, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export minimal stock wheel/tire fields from a pinned FH6 SQLite DB read-only."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-blob-sha1", required=True)
    parser.add_argument("--min-complete", type=int, default=0)
    args = parser.parse_args()

    database = args.db.resolve()
    if not database.is_file():
        raise SystemExit(f"Database does not exist: {database}")

    dataset, report = export_stock_wheel_specs(
        database,
        source_repository=args.source_repository,
        source_commit=args.source_commit,
        source_blob_sha1=args.source_blob_sha1,
    )
    if report["duplicate_car_ids"]:
        raise SystemExit(f"Duplicate car IDs in source DB: {report['duplicate_car_ids'][:10]}")
    if report["complete_record_count"] < int(args.min_complete):
        raise SystemExit(
            f"Only {report['complete_record_count']} complete records; required {args.min_complete}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
