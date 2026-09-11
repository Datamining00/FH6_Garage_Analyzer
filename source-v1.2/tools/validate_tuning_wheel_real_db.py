from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import struct
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fh6garage.preview3d.tuning_wheel_selection import (  # noqa: E402
    CAR_BODY_SCOPED_SLOTS,
    EMPTY_PART_VALUE,
    FH6TuningWheelSelectionResolver,
    TARGET_SLOTS,
    TUNING_DATA_SIZE,
    TUNING_PART_COUNT,
)
from fh6garage.preview3d.wheel_placement import FH6WheelPlacementResolver  # noqa: E402
from fh6garage.preview3d.wheel_spec import FH6WheelSpecResolver  # noqa: E402


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _columns(connection: sqlite3.Connection, table: str) -> dict[str, str]:
    return {
        str(row[1]).casefold(): str(row[1])
        for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
    }


def _rows(
    connection: sqlite3.Connection,
    table: str,
    filters: dict[str, Any],
) -> list[sqlite3.Row]:
    columns = _columns(connection, table)
    clauses = []
    values = []
    for requested, value in filters.items():
        column = columns.get(requested.casefold())
        if column is None:
            return []
        clauses.append(f"{_quote(column)} = ?")
        values.append(value)
    where = " AND ".join(clauses) if clauses else "1"
    order = ""
    if "level" in columns:
        order = f" ORDER BY {_quote(columns['level'])} ASC"
    elif "id" in columns:
        order = f" ORDER BY {_quote(columns['id'])} ASC"
    return list(
        connection.execute(
            f"SELECT * FROM {_quote(table)} WHERE {where}{order}",
            values,
        )
    )


def _row_value(row: sqlite3.Row, *names: str) -> Any:
    keys = {str(key).casefold(): str(key) for key in row.keys()}
    for name in names:
        key = keys.get(name.casefold())
        if key is not None:
            return row[key]
    return None


def _row_id(row: sqlite3.Row) -> int:
    value = _row_value(row, "Id", "ID")
    if value is None:
        raise RuntimeError("row has no Id/ID")
    return int(value)


def _encode_part_id(part_id: int) -> int:
    value = int(part_id) & 0xFFFFFFFF
    return ((value & 0xFFFF) << 16) | ((value >> 16) & 0xFFFF)


def _payload(raw_by_order: dict[int, int]) -> bytes:
    words = [EMPTY_PART_VALUE] * TUNING_PART_COUNT
    for order, raw in raw_by_order.items():
        index = int(order) + 3
        if not 0 <= index < TUNING_PART_COUNT:
            raise RuntimeError(f"upgrade slot order {order} is outside the 104-word payload")
        words[index] = int(raw) & 0xFFFFFFFF
    prefix = struct.pack(f"<{TUNING_PART_COUNT}I", *words)
    return prefix + bytes(TUNING_DATA_SIZE - len(prefix))


def _slot_definitions(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT ordering.Id, ordering.Name, definition.TableName
        FROM Data_UpgradePartOrder AS ordering
        LEFT JOIN Data_UpgradePart AS definition
            ON definition.PartName = ordering.Name
        ORDER BY ordering.Id
        """
    )
    result = []
    for row in rows:
        name = str(row[1])
        if name not in TARGET_SLOTS:
            continue
        table = "" if row[2] is None else str(row[2])
        result.append(
            {
                "order_id": int(row[0]),
                "payload_index": int(row[0]) + 3,
                "slot_name": name,
                "table_name": table,
                "columns": _columns(connection, table) if table else {},
            }
        )
    return result


def _stock_car_body(connection: sqlite3.Connection, car_id: int) -> sqlite3.Row:
    rows = _rows(connection, "List_UpgradeCarBody", {"Ordinal": car_id, "IsStock": 1})
    if len(rows) != 1:
        raise RuntimeError(f"expected one stock CarBody for car {car_id}, got {len(rows)}")
    return rows[0]


def _stock_wheel_id(connection: sqlite3.Connection, car_id: int) -> int:
    table = "Drivable_Data_Car"
    try:
        rows = _rows(connection, table, {"Id": car_id})
    except sqlite3.Error:
        rows = []
    if not rows:
        table = "Data_Car"
        rows = _rows(connection, table, {"Id": car_id})
    if len(rows) != 1:
        raise RuntimeError(f"car {car_id} not found")
    value = _row_value(rows[0], "StockWheelID")
    if value is None:
        raise RuntimeError(f"car {car_id} has no StockWheelID")
    return int(value)


def _part_row(
    connection: sqlite3.Connection,
    slot: str,
    table: str,
    car_id: int,
    car_body_id: int,
    *,
    want_stock: bool,
) -> sqlite3.Row | None:
    if slot in {"WheelStyle", "WheelStyleRear"}:
        return None
    filters: dict[str, Any]
    if slot in CAR_BODY_SCOPED_SLOTS:
        filters = {"CarBodyId": car_body_id}
    else:
        filters = {"Ordinal": car_id}
    columns = _columns(connection, table)
    if "isstock" in columns:
        filters["IsStock"] = 1 if want_stock else 0
    rows = _rows(connection, table, filters)
    return rows[0] if rows else None


def _build_payload_from_real_rows(
    connection: sqlite3.Connection,
    car_id: int,
    slots: list[dict[str, Any]],
    *,
    effective: bool,
) -> tuple[bytes, dict[str, Any]]:
    stock_body = _stock_car_body(connection, car_id)
    car_body_id = int(_row_value(stock_body, "CarBodyID", "CarBodyId"))
    stock_wheel = _stock_wheel_id(connection, car_id)
    raw_by_order: dict[int, int] = {}
    source_rows: dict[str, Any] = {}

    for slot in slots:
        name = slot["slot_name"]
        table = slot["table_name"]
        order = int(slot["order_id"])
        if name in {"WheelStyle", "WheelStyleRear"}:
            wheel_id = stock_wheel
            if effective:
                wheel_rows = _rows(connection, "List_Wheels", {})
                alternative = next(
                    (
                        row
                        for row in wheel_rows
                        if _row_id(row) != stock_wheel and 0 <= _row_id(row) <= 0xFFFF
                    ),
                    None,
                )
                if alternative is not None:
                    wheel_id = _row_id(alternative)
            raw_by_order[order] = int(wheel_id) << 16
            source_rows[name] = {"ID": int(wheel_id)}
            continue

        if name == "CarBody":
            row = stock_body
        else:
            row = _part_row(
                connection,
                name,
                table,
                car_id,
                car_body_id,
                want_stock=not effective,
            )
            if row is None and effective:
                row = _part_row(
                    connection,
                    name,
                    table,
                    car_id,
                    car_body_id,
                    want_stock=True,
                )
        if row is None:
            continue
        part_id = _row_id(row)
        raw_by_order[order] = _encode_part_id(part_id)
        source_rows[name] = dict(row)

    return _payload(raw_by_order), source_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--car-id", type=int, default=1006)
    args = parser.parse_args()

    database = args.db.resolve()
    car_id = int(args.car_id)
    with _connect(database) as connection:
        slots = _slot_definitions(connection)
        stock_payload, stock_rows = _build_payload_from_real_rows(
            connection, car_id, slots, effective=False
        )
        effective_payload, effective_rows = _build_payload_from_real_rows(
            connection, car_id, slots, effective=True
        )

    tuning_resolver = FH6TuningWheelSelectionResolver(database)
    wheel_resolver = FH6WheelSpecResolver(database)
    placement_resolver = FH6WheelPlacementResolver(database)

    stock = tuning_resolver.resolve_bytes(car_id, stock_payload)
    effective = tuning_resolver.resolve_bytes(car_id, effective_payload)
    stock_wheel = wheel_resolver.resolve(car_id, stock.wheel)
    stock_placement = placement_resolver.resolve(car_id, stock.placement)
    effective_wheel = wheel_resolver.resolve(car_id, effective.wheel)
    effective_placement = placement_resolver.resolve(car_id, effective.placement)

    report = {
        "format": "fh6_tuning_wheel_real_db_validation_v1",
        "car_id": car_id,
        "slot_definitions": slots,
        "stock_source_rows": stock_rows,
        "stock_tuning_resolution": stock.as_dict(),
        "stock_wheel_spec": stock_wheel.as_dict(),
        "stock_placement": stock_placement.as_dict(),
        "effective_source_rows": effective_rows,
        "effective_tuning_resolution": effective.as_dict(),
        "effective_wheel_spec": effective_wheel.as_dict(),
        "effective_placement": effective_placement.as_dict(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not stock.wheel.is_stock() or not stock.placement.is_stock():
        raise SystemExit("real-DB stock payload did not normalize to stock selections")
    if stock.unresolved_slots:
        raise SystemExit(
            "real-DB stock payload has unresolved wheel slots: "
            + ", ".join(stock.unresolved_slots)
        )
    if not effective.wheel.applied_ids() and not effective.placement.applied_ids():
        raise SystemExit(
            "real-DB effective payload did not resolve any non-stock wheel selections"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
