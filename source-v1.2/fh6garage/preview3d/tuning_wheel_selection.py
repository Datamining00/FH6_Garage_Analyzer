from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
import struct
from typing import Any

from .wheel_placement import WheelPlacementSelection
from .wheel_spec import WheelSpecError, WheelUpgradeSelection


TUNING_DATA_SIZE = 598
TUNING_PART_COUNT = 104
TUNING_PART_BYTES = TUNING_PART_COUNT * 4
EMPTY_PART_VALUE = 0xFFFFFFFF

TARGET_SLOTS = frozenset(
    {
        "CarBody",
        "RimSizeFront",
        "RimSizeRear",
        "TireWidthFront",
        "TireWidthRear",
        "FrontAspectRatio",
        "RearAspectRatio",
        "TrackSpacingFront",
        "TrackSpacingRear",
        "TireCompound",
        "Brakes",
        "WheelStyle",
        "WheelStyleRear",
    }
)

CAR_BODY_SCOPED_SLOTS = frozenset(
    {
        "TireWidthFront",
        "TireWidthRear",
        "FrontAspectRatio",
        "RearAspectRatio",
        "TrackSpacingFront",
        "TrackSpacingRear",
    }
)


class TuningWheelSelectionError(WheelSpecError):
    """Raised when the FH6 598-byte tuning payload cannot be resolved safely."""


@dataclass(frozen=True)
class ResolvedTuningPart:
    slot_name: str
    table_name: str
    order_id: int
    payload_index: int
    raw_value: int
    decoded_id: int | None
    token: int
    resolved_row_id: int
    is_stock: bool | None
    lookup_mode: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "slot_name": self.slot_name,
            "table_name": self.table_name,
            "order_id": self.order_id,
            "payload_index": self.payload_index,
            "raw_value": self.raw_value,
            "raw_value_hex": f"0x{self.raw_value:08X}",
            "decoded_id": self.decoded_id,
            "token": self.token,
            "resolved_row_id": self.resolved_row_id,
            "is_stock": self.is_stock,
            "lookup_mode": self.lookup_mode,
        }


@dataclass(frozen=True)
class TuningWheelSelections:
    car_id: int
    wheel: WheelUpgradeSelection
    placement: WheelPlacementSelection
    resolved_parts: dict[str, ResolvedTuningPart] = field(default_factory=dict)
    unresolved_slots: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "car_id": self.car_id,
            "wheel_selection": self.wheel.applied_ids(),
            "placement_selection": self.placement.applied_ids(),
            "resolved_parts": {
                name: part.as_dict() for name, part in sorted(self.resolved_parts.items())
            },
            "unresolved_slots": list(self.unresolved_slots),
        }


def decode_part_id(raw_value: int) -> int:
    """Decode the FH6 tuning part ID word observed in the 598-byte payload."""

    value = int(raw_value) & 0xFFFFFFFF
    if value == EMPTY_PART_VALUE:
        return -1
    return ((value & 0xFFFF) << 16) | ((value >> 16) & 0xFFFF)


def tuning_part_words(data: bytes) -> tuple[int, ...]:
    if len(data) != TUNING_DATA_SIZE:
        raise TuningWheelSelectionError(
            f"FH6 tuning Data must be exactly {TUNING_DATA_SIZE} bytes; got {len(data)}"
        )
    return struct.unpack_from(f"<{TUNING_PART_COUNT}I", data, 0)


class FH6TuningWheelSelectionResolver:
    """Resolve wheel-related installed part IDs from an FH6 598-byte tuning Data file.

    The resolver never writes the tuning payload or the SQLite database. Slot order
    and backing table names are read from Data_UpgradePartOrder/Data_UpgradePart so
    the implementation does not hard-code numeric slot indexes.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        if not self.database_path.is_file():
            raise TuningWheelSelectionError(
                f"FH6 game database does not exist: {self.database_path}"
            )

    def resolve_file(self, car_id: int, tuning_data_path: str | Path) -> TuningWheelSelections:
        path = Path(tuning_data_path).expanduser().resolve()
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise TuningWheelSelectionError(f"could not read tuning Data: {exc}") from exc
        return self.resolve_bytes(car_id, data)

    def resolve_bytes(self, car_id: int, data: bytes) -> TuningWheelSelections:
        if int(car_id) <= 0:
            raise TuningWheelSelectionError(f"car_id must be positive: {car_id}")
        words = tuning_part_words(data)

        with closing(self._connect()) as connection:
            slots = self._target_slot_definitions(connection)
            if not slots:
                raise TuningWheelSelectionError(
                    "FH6 DB did not expose any wheel-related Data_UpgradePartOrder rows"
                )

            stock_wheel_id = self._stock_wheel_id(connection, int(car_id))
            stock_car_body_id = self._stock_car_body_id(connection, int(car_id))
            active_car_body_id = stock_car_body_id
            resolved: dict[str, ResolvedTuningPart] = {}
            rows: dict[str, sqlite3.Row] = {}
            unresolved: list[str] = []

            for order_id, slot_name, table_name in slots:
                payload_index = order_id + 3
                if payload_index < 0 or payload_index >= len(words):
                    unresolved.append(slot_name)
                    continue
                raw = int(words[payload_index])
                if raw == EMPTY_PART_VALUE:
                    continue
                token = (raw >> 16) & 0xFFFF

                if slot_name in {"WheelStyle", "WheelStyleRear"}:
                    row = self._query_unique(
                        connection,
                        "List_Wheels",
                        {"ID": token},
                        required=False,
                    )
                    lookup_mode = "wheel_id_high16"
                    decoded: int | None = None
                else:
                    decoded = decode_part_id(raw)
                    parent_value = (
                        active_car_body_id if slot_name in CAR_BODY_SCOPED_SLOTS else None
                    )
                    row, lookup_mode = self._resolve_part_row(
                        connection,
                        table_name,
                        decoded_id=decoded,
                        token=token,
                        car_id=int(car_id),
                        car_body_id=parent_value,
                        car_body_scoped=slot_name in CAR_BODY_SCOPED_SLOTS,
                    )

                if row is None:
                    unresolved.append(slot_name)
                    continue

                row_id = self._row_id(row)
                is_stock = self._row_stock_state(row)
                rows[slot_name] = row
                resolved[slot_name] = ResolvedTuningPart(
                    slot_name=slot_name,
                    table_name="List_Wheels" if slot_name in {"WheelStyle", "WheelStyleRear"} else table_name,
                    order_id=order_id,
                    payload_index=payload_index,
                    raw_value=raw,
                    decoded_id=decoded,
                    token=token,
                    resolved_row_id=row_id,
                    is_stock=is_stock,
                    lookup_mode=lookup_mode,
                )
                if slot_name == "CarBody":
                    active_car_body_id = self._optional_int(
                        self._row_value(row, "CarBodyID", "CarBodyId")
                    ) or active_car_body_id

            def selected_row_id(slot: str) -> int | None:
                part = resolved.get(slot)
                if part is None:
                    return None
                if part.is_stock is True:
                    return None
                return part.resolved_row_id

            def selected_wheel_id(slot: str) -> int | None:
                part = resolved.get(slot)
                if part is None:
                    return None
                return None if stock_wheel_id == part.resolved_row_id else part.resolved_row_id

            wheel = WheelUpgradeSelection(
                front_rim_size_id=selected_row_id("RimSizeFront"),
                rear_rim_size_id=selected_row_id("RimSizeRear"),
                front_tire_width_id=selected_row_id("TireWidthFront"),
                rear_tire_width_id=selected_row_id("TireWidthRear"),
                front_aspect_ratio_id=selected_row_id("FrontAspectRatio"),
                rear_aspect_ratio_id=selected_row_id("RearAspectRatio"),
                tire_compound_id=selected_row_id("TireCompound"),
                wheel_style_id=selected_wheel_id("WheelStyle"),
                rear_wheel_style_id=selected_wheel_id("WheelStyleRear"),
            )
            placement = WheelPlacementSelection(
                car_body_upgrade_id=selected_row_id("CarBody"),
                front_track_spacing_id=selected_row_id("TrackSpacingFront"),
                rear_track_spacing_id=selected_row_id("TrackSpacingRear"),
                tire_compound_id=selected_row_id("TireCompound"),
                brakes_id=selected_row_id("Brakes"),
            )

            return TuningWheelSelections(
                car_id=int(car_id),
                wheel=wheel,
                placement=placement,
                resolved_parts=resolved,
                unresolved_slots=tuple(sorted(set(unresolved))),
            )

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.database_path.as_uri() + "?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            return connection
        except sqlite3.Error as exc:
            raise TuningWheelSelectionError(
                f"could not open FH6 game database read-only: {exc}"
            ) from exc

    def _target_slot_definitions(
        self, connection: sqlite3.Connection
    ) -> list[tuple[int, str, str]]:
        try:
            rows = connection.execute(
                """
                SELECT ordering.Id, ordering.Name, definition.TableName
                FROM Data_UpgradePartOrder AS ordering
                LEFT JOIN Data_UpgradePart AS definition
                    ON definition.PartName = ordering.Name
                ORDER BY ordering.Id
                """
            )
        except sqlite3.Error as exc:
            raise TuningWheelSelectionError(
                f"could not read FH6 upgrade slot definitions: {exc}"
            ) from exc
        output: list[tuple[int, str, str]] = []
        for row in rows:
            name = str(row[1])
            if name not in TARGET_SLOTS:
                continue
            table = "" if row[2] is None else str(row[2]).strip()
            if not table and name not in {"WheelStyle", "WheelStyleRear"}:
                continue
            output.append((int(row[0]), name, table))
        return output

    def _resolve_part_row(
        self,
        connection: sqlite3.Connection,
        table: str,
        *,
        decoded_id: int,
        token: int,
        car_id: int,
        car_body_id: int | None,
        car_body_scoped: bool,
    ) -> tuple[sqlite3.Row | None, str]:
        columns = self._columns(connection, table)
        if not columns:
            return None, "missing_table"

        scope: dict[str, Any] = {}
        if car_body_scoped and car_body_id is not None and "carbodyid" in columns:
            scope[columns["carbodyid"]] = car_body_id
        elif "ordinal" in columns:
            scope[columns["ordinal"]] = car_id

        exact_filters = {"Id": decoded_id, **scope}
        row = self._query_unique(connection, table, exact_filters, required=False)
        if row is not None:
            return row, "decoded_id"

        if token == 0xFFFF:
            return None, "decoded_id"
        return self._query_by_low16_token(connection, table, token, scope), "low16_token"

    def _query_by_low16_token(
        self,
        connection: sqlite3.Connection,
        table: str,
        token: int,
        scope: dict[str, Any],
    ) -> sqlite3.Row | None:
        actual = self._table_name(connection, table)
        if actual is None:
            return None
        columns = self._columns(connection, actual)
        id_column = columns.get("id")
        if id_column is None:
            return None
        clauses = [f"({self._quote(id_column)} & 65535) = ?"]
        values: list[Any] = [int(token)]
        for requested, value in scope.items():
            column = columns.get(str(requested).casefold())
            if column is None:
                continue
            clauses.append(f"{self._quote(column)} = ?")
            values.append(value)
        rows = list(
            connection.execute(
                f"SELECT * FROM {self._quote(actual)} WHERE {' AND '.join(clauses)} LIMIT 2",
                values,
            )
        )
        return rows[0] if len(rows) == 1 else None

    def _stock_wheel_id(self, connection: sqlite3.Connection, car_id: int) -> int | None:
        table = self._table_name(connection, "Drivable_Data_Car") or self._table_name(
            connection, "Data_Car"
        )
        if table is None:
            return None
        row = self._query_unique(connection, table, {"Id": car_id}, required=False)
        return None if row is None else self._optional_int(self._row_value(row, "StockWheelID"))

    def _stock_car_body_id(self, connection: sqlite3.Connection, car_id: int) -> int | None:
        row = self._query_unique(
            connection,
            "List_UpgradeCarBody",
            {"Ordinal": car_id, "IsStock": 1},
            required=False,
        )
        return None if row is None else self._optional_int(
            self._row_value(row, "CarBodyID", "CarBodyId")
        )

    @staticmethod
    def _quote(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _table_name(self, connection: sqlite3.Connection, requested: str) -> str | None:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
        table_map = {str(row[0]).casefold(): str(row[0]) for row in rows}
        return table_map.get(requested.casefold())

    def _columns(self, connection: sqlite3.Connection, table: str) -> dict[str, str]:
        actual = self._table_name(connection, table)
        if actual is None:
            return {}
        return {
            str(row[1]).casefold(): str(row[1])
            for row in connection.execute(f"PRAGMA table_info({self._quote(actual)})")
        }

    def _query_unique(
        self,
        connection: sqlite3.Connection,
        table: str,
        filters: dict[str, Any],
        *,
        required: bool,
    ) -> sqlite3.Row | None:
        actual = self._table_name(connection, table)
        if actual is None:
            if required:
                raise TuningWheelSelectionError(f"FH6 DB is missing required table {table}")
            return None
        columns = self._columns(connection, actual)
        clauses: list[str] = []
        values: list[Any] = []
        for requested, value in filters.items():
            column = columns.get(requested.casefold())
            if column is None:
                if required:
                    raise TuningWheelSelectionError(
                        f"{actual} is missing required column {requested}"
                    )
                return None
            clauses.append(f"{self._quote(column)} = ?")
            values.append(value)
        rows = list(
            connection.execute(
                f"SELECT * FROM {self._quote(actual)} WHERE {' AND '.join(clauses)} LIMIT 2",
                values,
            )
        )
        if len(rows) == 1:
            return rows[0]
        if required and not rows:
            raise TuningWheelSelectionError(
                f"no row in {actual} matched {filters}"
            )
        if required and len(rows) > 1:
            raise TuningWheelSelectionError(
                f"ambiguous rows in {actual} matched {filters}"
            )
        return None

    @staticmethod
    def _row_value(row: sqlite3.Row, *candidates: str) -> Any:
        keys = {str(key).casefold(): str(key) for key in row.keys()}
        for candidate in candidates:
            key = keys.get(candidate.casefold())
            if key is not None:
                return row[key]
        return None

    def _row_id(self, row: sqlite3.Row) -> int:
        value = self._row_value(row, "Id", "ID")
        result = self._optional_int(value)
        if result is None:
            raise TuningWheelSelectionError(f"resolved DB row has no integer Id/ID: {dict(row)}")
        return result

    def _row_stock_state(self, row: sqlite3.Row) -> bool | None:
        value = self._row_value(row, "IsStock")
        if value is None:
            return None
        try:
            return bool(int(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
