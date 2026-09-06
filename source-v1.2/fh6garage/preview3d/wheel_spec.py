from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable


class WheelSpecError(RuntimeError):
    """Raised when FH6 wheel specification data cannot be resolved safely."""


@dataclass(frozen=True)
class WheelUpgradeSelection:
    """Already-resolved FH6 upgrade row IDs.

    Stage W1 intentionally does not decode the 598-byte Tuning payload. Stage W2
    will translate tuning slots into this neutral selection object.
    """

    front_rim_size_id: int | None = None
    rear_rim_size_id: int | None = None
    front_tire_width_id: int | None = None
    rear_tire_width_id: int | None = None
    front_aspect_ratio_id: int | None = None
    rear_aspect_ratio_id: int | None = None
    tire_compound_id: int | None = None
    wheel_style_id: int | None = None
    rear_wheel_style_id: int | None = None

    def is_stock(self) -> bool:
        return not any(value is not None for value in self.__dict__.values())

    def applied_ids(self) -> dict[str, int]:
        return {
            name: int(value)
            for name, value in self.__dict__.items()
            if value is not None
        }


@dataclass(frozen=True)
class AxleWheelSpec:
    axle: str
    tire_width_mm: float
    tire_aspect_ratio: float
    rim_diameter_in: float
    wheel_style_id: int | None = None
    wheel_style_name: str | None = None

    @property
    def rim_diameter_mm(self) -> float:
        return self.rim_diameter_in * 25.4

    @property
    def sidewall_height_mm(self) -> float:
        return self.tire_width_mm * self.tire_aspect_ratio / 100.0

    @property
    def tire_outer_diameter_mm(self) -> float:
        return self.rim_diameter_mm + 2.0 * self.sidewall_height_mm

    def as_dict(self) -> dict[str, Any]:
        return {
            "axle": self.axle,
            "tire_width_mm": self.tire_width_mm,
            "tire_aspect_ratio": self.tire_aspect_ratio,
            "rim_diameter_in": self.rim_diameter_in,
            "rim_diameter_mm": self.rim_diameter_mm,
            "sidewall_height_mm": self.sidewall_height_mm,
            "tire_outer_diameter_mm": self.tire_outer_diameter_mm,
            "wheel_style_id": self.wheel_style_id,
            "wheel_style_name": self.wheel_style_name,
        }


@dataclass(frozen=True)
class VehicleWheelSpec:
    car_id: int
    mode: str
    source_table: str
    car_body_id: int | None
    tire_compound_id: int | None
    tire_model_name: str | None
    front: AxleWheelSpec
    rear: AxleWheelSpec
    applied_upgrade_ids: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "car_id": self.car_id,
            "mode": self.mode,
            "source_table": self.source_table,
            "car_body_id": self.car_body_id,
            "tire_compound_id": self.tire_compound_id,
            "tire_model_name": self.tire_model_name,
            "front": self.front.as_dict(),
            "rear": self.rear.as_dict(),
            "applied_upgrade_ids": dict(self.applied_upgrade_ids),
        }


def find_game_database(explicit_path: str | Path | None = None) -> Path:
    """Resolve an FH6 SQLite DB without downloading or modifying anything."""

    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())

    env_path = os.environ.get("FH6_GAME_DB_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())

    source_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            source_root / "data" / "fh6_game_db.sqlite",
            source_root / "data" / "fh6_db.sqlite",
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate.absolute()
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return resolved

    attempted = ", ".join(str(item) for item in candidates) or "(none)"
    raise WheelSpecError(
        "FH6 game database was not found. Supply --db or set "
        f"FH6_GAME_DB_PATH. Checked: {attempted}"
    )


class FH6WheelSpecResolver:
    """Read-only FH6 SQLite wheel/tire specification resolver."""

    _BASE_TABLE_CANDIDATES = ("Drivable_Data_Car", "Data_Car")

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        if not self.database_path.is_file():
            raise WheelSpecError(f"FH6 game database does not exist: {self.database_path}")

    def resolve(
        self,
        car_id: int,
        selection: WheelUpgradeSelection | None = None,
    ) -> VehicleWheelSpec:
        if int(car_id) <= 0:
            raise WheelSpecError(f"car_id must be positive: {car_id}")
        selection = selection or WheelUpgradeSelection()

        with self._connect() as connection:
            source_table = self._first_existing_table(
                connection, self._BASE_TABLE_CANDIDATES
            )
            if source_table is None:
                raise WheelSpecError(
                    "FH6 DB is missing both Drivable_Data_Car and Data_Car"
                )

            car = self._one(
                connection,
                source_table,
                {"Id": int(car_id)},
                required=True,
                label=f"car {car_id}",
            )
            car_body_id = self._resolve_car_body_id(connection, int(car_id))

            front_width = self._positive(
                self._value(car, ("FrontTireWidthMM",)),
                "FrontTireWidthMM",
            )
            rear_width = self._positive(
                self._value(car, ("RearTireWidthMM",)),
                "RearTireWidthMM",
            )
            front_aspect = self._positive(
                self._value(car, ("FrontTireAspect",)),
                "FrontTireAspect",
            )
            rear_aspect = self._positive(
                self._value(car, ("RearTireAspect",)),
                "RearTireAspect",
            )
            front_rim = self._positive(
                self._value(car, ("FrontWheelDiameterIN",)),
                "FrontWheelDiameterIN",
            )
            rear_rim = self._positive(
                self._value(car, ("RearWheelDiameterIN",)),
                "RearWheelDiameterIN",
            )

            if selection.front_tire_width_id is not None:
                row = self._upgrade_row(
                    connection,
                    "List_UpgradeCarBodyTireWidthFront",
                    selection.front_tire_width_id,
                    car_id=int(car_id),
                    car_body_id=car_body_id,
                )
                front_width = self._positive(
                    self._value(row, ("FrontTireWidth",)),
                    "FrontTireWidth",
                )

            if selection.rear_tire_width_id is not None:
                row = self._upgrade_row(
                    connection,
                    "List_UpgradeCarBodyTireWidthRear",
                    selection.rear_tire_width_id,
                    car_id=int(car_id),
                    car_body_id=car_body_id,
                )
                rear_width = self._positive(
                    self._value(row, ("RearTireWidth",)),
                    "RearTireWidth",
                )

            if selection.front_aspect_ratio_id is not None:
                row = self._upgrade_row(
                    connection,
                    "List_UpgradeCarBodyTireAspectRatioFront",
                    selection.front_aspect_ratio_id,
                    car_id=int(car_id),
                    car_body_id=car_body_id,
                )
                front_aspect += self._number(
                    self._value(row, ("FrontTireAspectRatioOffset",)),
                    "FrontTireAspectRatioOffset",
                )

            if selection.rear_aspect_ratio_id is not None:
                row = self._upgrade_row(
                    connection,
                    "List_UpgradeCarBodyTireAspectRatioRear",
                    selection.rear_aspect_ratio_id,
                    car_id=int(car_id),
                    car_body_id=car_body_id,
                )
                rear_aspect += self._number(
                    self._value(row, ("RearTireAspectRatioOffset",)),
                    "RearTireAspectRatioOffset",
                )

            if selection.front_rim_size_id is not None:
                row = self._upgrade_row(
                    connection,
                    "List_UpgradeRimSizeFront",
                    selection.front_rim_size_id,
                    car_id=int(car_id),
                    car_body_id=car_body_id,
                )
                front_rim = self._positive(
                    self._value(row, ("FrontWheelDiameter",)),
                    "FrontWheelDiameter",
                )

            if selection.rear_rim_size_id is not None:
                row = self._upgrade_row(
                    connection,
                    "List_UpgradeRimSizeRear",
                    selection.rear_rim_size_id,
                    car_id=int(car_id),
                    car_body_id=car_body_id,
                )
                rear_rim = self._positive(
                    self._value(row, ("RearWheelDiameter",)),
                    "RearWheelDiameter",
                )

            front_aspect = self._positive(front_aspect, "effective front tire aspect")
            rear_aspect = self._positive(rear_aspect, "effective rear tire aspect")

            stock_wheel_id = self._optional_int(
                self._value(car, ("StockWheelID",), required=False)
            )
            front_style_id = (
                int(selection.wheel_style_id)
                if selection.wheel_style_id is not None
                else stock_wheel_id
            )
            rear_style_id = (
                int(selection.rear_wheel_style_id)
                if selection.rear_wheel_style_id is not None
                else front_style_id
            )
            front_style_name = self._resolve_wheel_name(connection, front_style_id)
            rear_style_name = self._resolve_wheel_name(connection, rear_style_id)

            tire_compound_id, tire_model_name = self._resolve_tire_compound(
                connection, int(car_id), selection.tire_compound_id
            )

            return VehicleWheelSpec(
                car_id=int(car_id),
                mode="stock" if selection.is_stock() else "effective",
                source_table=source_table,
                car_body_id=car_body_id,
                tire_compound_id=tire_compound_id,
                tire_model_name=tire_model_name,
                front=AxleWheelSpec(
                    axle="front",
                    tire_width_mm=front_width,
                    tire_aspect_ratio=front_aspect,
                    rim_diameter_in=front_rim,
                    wheel_style_id=front_style_id,
                    wheel_style_name=front_style_name,
                ),
                rear=AxleWheelSpec(
                    axle="rear",
                    tire_width_mm=rear_width,
                    tire_aspect_ratio=rear_aspect,
                    rim_diameter_in=rear_rim,
                    wheel_style_id=rear_style_id,
                    wheel_style_name=rear_style_name,
                ),
                applied_upgrade_ids=selection.applied_ids(),
            )

    def _connect(self) -> sqlite3.Connection:
        uri = self.database_path.as_uri() + "?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            return connection
        except sqlite3.Error as exc:
            raise WheelSpecError(
                f"could not open FH6 game database read-only: {exc}"
            ) from exc

    @staticmethod
    def _table_map(connection: sqlite3.Connection) -> dict[str, str]:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
        return {str(row[0]).casefold(): str(row[0]) for row in rows}

    def _existing_table(
        self, connection: sqlite3.Connection, requested: str
    ) -> str | None:
        return self._table_map(connection).get(requested.casefold())

    def _first_existing_table(
        self, connection: sqlite3.Connection, candidates: Iterable[str]
    ) -> str | None:
        tables = self._table_map(connection)
        for candidate in candidates:
            match = tables.get(candidate.casefold())
            if match:
                return match
        return None

    @staticmethod
    def _quote(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _columns(
        self, connection: sqlite3.Connection, table: str
    ) -> dict[str, str]:
        query = f"PRAGMA table_info({self._quote(table)})"
        return {
            str(row[1]).casefold(): str(row[1])
            for row in connection.execute(query)
        }

    def _matching_column(
        self,
        connection: sqlite3.Connection,
        table: str,
        requested: str,
    ) -> str | None:
        columns = self._columns(connection, table)
        aliases = [requested]
        if requested.casefold() == "carbodyid":
            aliases.extend(("CarBodyId",))
        elif requested.casefold() == "id":
            aliases.extend(("ID",))
        for candidate in aliases:
            match = columns.get(candidate.casefold())
            if match:
                return match
        return None

    def _one(
        self,
        connection: sqlite3.Connection,
        table: str,
        filters: dict[str, Any],
        *,
        required: bool,
        label: str,
    ) -> sqlite3.Row | None:
        actual_table = self._existing_table(connection, table)
        if actual_table is None:
            if required:
                raise WheelSpecError(f"FH6 DB is missing required table {table}")
            return None

        clauses: list[str] = []
        values: list[Any] = []
        for requested_column, value in filters.items():
            column = self._matching_column(connection, actual_table, requested_column)
            if column is None:
                raise WheelSpecError(
                    f"{actual_table} is missing required column {requested_column}"
                )
            clauses.append(f"{self._quote(column)} = ?")
            values.append(value)
        where = " AND ".join(clauses) if clauses else "1"
        sql = (
            f"SELECT * FROM {self._quote(actual_table)} "
            f"WHERE {where} LIMIT 2"
        )
        rows = list(connection.execute(sql, values))
        if not rows:
            if required:
                raise WheelSpecError(f"could not resolve {label} in {actual_table}")
            return None
        if len(rows) > 1:
            raise WheelSpecError(f"{label} is ambiguous in {actual_table}")
        return rows[0]

    @staticmethod
    def _row_keys(row: sqlite3.Row) -> dict[str, str]:
        return {str(key).casefold(): str(key) for key in row.keys()}

    def _value(
        self,
        row: sqlite3.Row | None,
        candidates: Iterable[str],
        *,
        required: bool = True,
    ) -> Any:
        if row is None:
            if required:
                raise WheelSpecError("required database row is missing")
            return None
        keys = self._row_keys(row)
        for candidate in candidates:
            key = keys.get(candidate.casefold())
            if key is not None:
                return row[key]
        if required:
            raise WheelSpecError(
                "database row is missing required column: "
                + "/".join(candidates)
            )
        return None

    @staticmethod
    def _number(value: Any, label: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise WheelSpecError(f"{label} is not numeric: {value!r}") from exc

    def _positive(self, value: Any, label: str) -> float:
        number = self._number(value, label)
        if number <= 0:
            raise WheelSpecError(f"{label} must be positive: {number}")
        return number

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _resolve_car_body_id(
        self, connection: sqlite3.Connection, car_id: int
    ) -> int | None:
        table = self._existing_table(connection, "List_UpgradeCarBody")
        if table is None:
            return None
        columns = self._columns(connection, table)
        if "ordinal" not in columns or "isstock" not in columns:
            return None
        row = self._one(
            connection,
            table,
            {"Ordinal": car_id, "IsStock": 1},
            required=False,
            label=f"stock CarBody for car {car_id}",
        )
        return self._optional_int(
            self._value(row, ("CarBodyID", "CarBodyId"), required=False)
        )

    def _upgrade_row(
        self,
        connection: sqlite3.Connection,
        table: str,
        row_id: int,
        *,
        car_id: int,
        car_body_id: int | None,
    ) -> sqlite3.Row:
        actual_table = self._existing_table(connection, table)
        if actual_table is None:
            raise WheelSpecError(f"FH6 DB is missing required table {table}")
        columns = self._columns(connection, actual_table)
        filters: dict[str, Any] = {"Id": int(row_id)}

        if "carbodyid" in columns:
            if car_body_id is None:
                raise WheelSpecError(
                    f"{actual_table} requires CarBodyID, but stock CarBody could not be resolved"
                )
            filters["CarBodyID"] = int(car_body_id)
        elif "ordinal" in columns:
            filters["Ordinal"] = int(car_id)

        return self._one(
            connection,
            actual_table,
            filters,
            required=True,
            label=f"{actual_table} Id={row_id} for car {car_id}",
        )

    def _resolve_wheel_name(
        self, connection: sqlite3.Connection, wheel_id: int | None
    ) -> str | None:
        if wheel_id is None:
            return None
        table = self._existing_table(connection, "List_Wheels")
        if table is None:
            return None
        row = self._one(
            connection,
            table,
            {"Id": int(wheel_id)},
            required=False,
            label=f"wheel style {wheel_id}",
        )
        if row is None:
            return None
        value = self._value(
            row,
            ("MediaName", "WheelName", "DisplayName", "ModelName", "Name"),
            required=False,
        )
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _resolve_tire_compound(
        self,
        connection: sqlite3.Connection,
        car_id: int,
        selected_id: int | None,
    ) -> tuple[int | None, str | None]:
        table = self._existing_table(connection, "List_UpgradeTireCompound")
        if table is None:
            return None, None

        if selected_id is not None:
            row = self._upgrade_row(
                connection,
                table,
                int(selected_id),
                car_id=car_id,
                car_body_id=None,
            )
        else:
            columns = self._columns(connection, table)
            if "ordinal" not in columns or "isstock" not in columns:
                return None, None
            row = self._one(
                connection,
                table,
                {"Ordinal": car_id, "IsStock": 1},
                required=False,
                label=f"stock tire compound for car {car_id}",
            )
        if row is None:
            return None, None

        compound_id = self._optional_int(
            self._value(row, ("TireCompoundID",), required=False)
        )
        model_name_raw = self._value(row, ("TireModelName",), required=False)
        model_name = (
            str(model_name_raw).strip()
            if model_name_raw is not None and str(model_name_raw).strip()
            else None
        )
        return compound_id, model_name
