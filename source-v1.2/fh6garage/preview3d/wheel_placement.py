from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .wheel_spec import WheelSpecError


@dataclass(frozen=True)
class WheelPlacementSelection:
    """Already-resolved FH6 upgrade row IDs used by the W1.2 placement layer."""

    car_body_upgrade_id: int | None = None
    front_track_spacing_id: int | None = None
    rear_track_spacing_id: int | None = None
    tire_compound_id: int | None = None
    brakes_id: int | None = None

    def is_stock(self) -> bool:
        return not any(value is not None for value in self.__dict__.values())

    def applied_ids(self) -> dict[str, int]:
        return {
            name: int(value)
            for name, value in self.__dict__.items()
            if value is not None
        }


@dataclass(frozen=True)
class AxlePlacementSpec:
    axle: str
    model_track_outer_m: float
    track_spacing_m: float
    tire_compound_spacer_offset_m: float
    stock_ride_height_m: float

    @property
    def effective_track_outer_m(self) -> float:
        """Track used for geometry placement before tire-compound-specific offsets.

        FH6 public tooling independently confirms ModelTrackOuter + Spacing.
        TireCompound Front/RearTrackSpacerOffset is preserved separately until its
        exact geometry semantics are independently verified.
        """

        return self.model_track_outer_m + self.track_spacing_m

    @property
    def half_track_m(self) -> float:
        return self.effective_track_outer_m / 2.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "axle": self.axle,
            "model_track_outer_m": self.model_track_outer_m,
            "track_spacing_m": self.track_spacing_m,
            "tire_compound_spacer_offset_m": self.tire_compound_spacer_offset_m,
            "stock_ride_height_m": self.stock_ride_height_m,
            "effective_track_outer_m": self.effective_track_outer_m,
            "half_track_m": self.half_track_m,
        }


@dataclass(frozen=True)
class BrakeAxleSpec:
    axle: str
    size_mm: float | None
    rotor_thickness_mm: float | None
    drum_depth_mm: float | None
    non_spinning_mass: float | None
    brake_type_id: int | None
    caliper_pistons: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "axle": self.axle,
            "size_mm": self.size_mm,
            "rotor_thickness_mm": self.rotor_thickness_mm,
            "drum_depth_mm": self.drum_depth_mm,
            "non_spinning_mass": self.non_spinning_mass,
            "brake_type_id": self.brake_type_id,
            "caliper_pistons": self.caliper_pistons,
        }


@dataclass(frozen=True)
class VehicleWheelPlacementSpec:
    car_id: int
    mode: str
    car_body_id: int
    model_wheelbase_m: float
    bottom_center_wheelbase_pos_x_m: float
    bottom_center_wheelbase_pos_y_m: float
    bottom_center_wheelbase_pos_z_m: float
    front: AxlePlacementSpec
    rear: AxlePlacementSpec
    brakes_id: int | None
    front_brake: BrakeAxleSpec
    rear_brake: BrakeAxleSpec
    applied_upgrade_ids: dict[str, int] = field(default_factory=dict)

    @property
    def front_axle_z_m(self) -> float:
        return self.bottom_center_wheelbase_pos_z_m + self.model_wheelbase_m / 2.0

    @property
    def rear_axle_z_m(self) -> float:
        return self.bottom_center_wheelbase_pos_z_m - self.model_wheelbase_m / 2.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "car_id": self.car_id,
            "mode": self.mode,
            "car_body_id": self.car_body_id,
            "model_wheelbase_m": self.model_wheelbase_m,
            "bottom_center_wheelbase_pos_m": {
                "x": self.bottom_center_wheelbase_pos_x_m,
                "y": self.bottom_center_wheelbase_pos_y_m,
                "z": self.bottom_center_wheelbase_pos_z_m,
            },
            "front_axle_z_m": self.front_axle_z_m,
            "rear_axle_z_m": self.rear_axle_z_m,
            "front": self.front.as_dict(),
            "rear": self.rear.as_dict(),
            "brakes_id": self.brakes_id,
            "front_brake": self.front_brake.as_dict(),
            "rear_brake": self.rear_brake.as_dict(),
            "applied_upgrade_ids": dict(self.applied_upgrade_ids),
        }


class FH6WheelPlacementResolver:
    """Resolve FH6 wheel placement and brake dimensions from SQLite, read-only."""

    _BASE_TABLE_CANDIDATES = ("Drivable_Data_Car", "Data_Car")

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        if not self.database_path.is_file():
            raise WheelSpecError(f"FH6 game database does not exist: {self.database_path}")

    def resolve(
        self,
        car_id: int,
        selection: WheelPlacementSelection | None = None,
    ) -> VehicleWheelPlacementSpec:
        if int(car_id) <= 0:
            raise WheelSpecError(f"car_id must be positive: {car_id}")
        selection = selection or WheelPlacementSelection()

        with closing(self._connect()) as connection:
            source_table = self._first_existing_table(connection, self._BASE_TABLE_CANDIDATES)
            if source_table is None:
                raise WheelSpecError("FH6 DB is missing both Drivable_Data_Car and Data_Car")
            self._one(connection, source_table, {"Id": int(car_id)}, True, f"car {car_id}")

            body_upgrade = self._resolve_car_body_upgrade(
                connection,
                int(car_id),
                selection.car_body_upgrade_id,
            )
            car_body_id = self._required_int(
                self._value(body_upgrade, ("CarBodyID", "CarBodyId")),
                "CarBodyID",
            )
            body = self._one(
                connection,
                "Data_CarBody",
                {"Id": car_body_id},
                True,
                f"Data_CarBody {car_body_id}",
            )

            front_spacing = self._resolve_track_spacing(
                connection,
                "List_UpgradeCarBodyTrackSpacingFront",
                car_body_id,
                selection.front_track_spacing_id,
            )
            rear_spacing = self._resolve_track_spacing(
                connection,
                "List_UpgradeCarBodyTrackSpacingRear",
                car_body_id,
                selection.rear_track_spacing_id,
            )
            tire = self._resolve_ordinal_upgrade(
                connection,
                "List_UpgradeTireCompound",
                int(car_id),
                selection.tire_compound_id,
                required=False,
            )
            brakes = self._resolve_ordinal_upgrade(
                connection,
                "List_UpgradeBrakes",
                int(car_id),
                selection.brakes_id,
                required=False,
            )

            front_track = self._positive(
                self._value(body, ("ModelFrontTrackOuter",)),
                "ModelFrontTrackOuter",
            )
            rear_track = self._positive(
                self._value(body, ("ModelRearTrackOuter",)),
                "ModelRearTrackOuter",
            )
            model_wheelbase = self._positive(
                self._value(body, ("ModelWheelbase",)),
                "ModelWheelbase",
            )
            front_ride_height = self._nonnegative(
                self._value(body, ("ModelFrontStockRideHeight",)),
                "ModelFrontStockRideHeight",
            )
            rear_ride_height = self._nonnegative(
                self._value(body, ("ModelRearStockRideHeight",)),
                "ModelRearStockRideHeight",
            )

            front_spacing_value = self._number(
                self._value(front_spacing, ("Spacing",), required=False) or 0.0,
                "front track spacing",
            )
            rear_spacing_value = self._number(
                self._value(rear_spacing, ("Spacing",), required=False) or 0.0,
                "rear track spacing",
            )
            front_tire_offset = self._number(
                self._value(tire, ("FrontTrackSpacerOffset",), required=False) or 0.0,
                "FrontTrackSpacerOffset",
            )
            rear_tire_offset = self._number(
                self._value(tire, ("RearTrackSpacerOffset",), required=False) or 0.0,
                "RearTrackSpacerOffset",
            )

            brakes_id = self._optional_int(self._value(brakes, ("Id", "ID"), required=False))
            return VehicleWheelPlacementSpec(
                car_id=int(car_id),
                mode="stock" if selection.is_stock() else "effective",
                car_body_id=car_body_id,
                model_wheelbase_m=model_wheelbase,
                bottom_center_wheelbase_pos_x_m=self._number(
                    self._value(body, ("BottomCenterWheelbasePosX", "BottomCenterWheelbasePosx")),
                    "BottomCenterWheelbasePosX",
                ),
                bottom_center_wheelbase_pos_y_m=self._number(
                    self._value(body, ("BottomCenterWheelbasePosY", "BottomCenterWheelbasePosy")),
                    "BottomCenterWheelbasePosY",
                ),
                bottom_center_wheelbase_pos_z_m=self._number(
                    self._value(body, ("BottomCenterWheelbasePosZ",)),
                    "BottomCenterWheelbasePosZ",
                ),
                front=AxlePlacementSpec(
                    axle="front",
                    model_track_outer_m=front_track,
                    track_spacing_m=front_spacing_value,
                    tire_compound_spacer_offset_m=front_tire_offset,
                    stock_ride_height_m=front_ride_height,
                ),
                rear=AxlePlacementSpec(
                    axle="rear",
                    model_track_outer_m=rear_track,
                    track_spacing_m=rear_spacing_value,
                    tire_compound_spacer_offset_m=rear_tire_offset,
                    stock_ride_height_m=rear_ride_height,
                ),
                brakes_id=brakes_id,
                front_brake=self._brake_axle(brakes, "front"),
                rear_brake=self._brake_axle(brakes, "rear"),
                applied_upgrade_ids=selection.applied_ids(),
            )

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.database_path.as_uri() + "?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            return connection
        except sqlite3.Error as exc:
            raise WheelSpecError(f"could not open FH6 game database read-only: {exc}") from exc

    @staticmethod
    def _quote(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _table_map(connection: sqlite3.Connection) -> dict[str, str]:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        return {str(row[0]).casefold(): str(row[0]) for row in rows}

    def _first_existing_table(self, connection: sqlite3.Connection, candidates: Iterable[str]) -> str | None:
        tables = self._table_map(connection)
        for candidate in candidates:
            if candidate.casefold() in tables:
                return tables[candidate.casefold()]
        return None

    def _columns(self, connection: sqlite3.Connection, table: str) -> dict[str, str]:
        return {
            str(row[1]).casefold(): str(row[1])
            for row in connection.execute(f"PRAGMA table_info({self._quote(table)})")
        }

    def _one(
        self,
        connection: sqlite3.Connection,
        table: str,
        filters: dict[str, Any],
        required: bool,
        label: str,
    ) -> sqlite3.Row | None:
        actual = self._table_map(connection).get(table.casefold())
        if actual is None:
            if required:
                raise WheelSpecError(f"FH6 DB is missing required table {table}")
            return None
        columns = self._columns(connection, actual)
        clauses: list[str] = []
        values: list[Any] = []
        for requested, value in filters.items():
            column = columns.get(requested.casefold())
            if column is None:
                if required:
                    raise WheelSpecError(f"{actual} is missing required column {requested}")
                return None
            clauses.append(f"{self._quote(column)} = ?")
            values.append(value)
        rows = list(
            connection.execute(
                f"SELECT * FROM {self._quote(actual)} WHERE {' AND '.join(clauses)} LIMIT 2",
                values,
            )
        )
        if not rows:
            if required:
                raise WheelSpecError(f"could not resolve {label} in {actual}")
            return None
        if len(rows) > 1:
            raise WheelSpecError(f"{label} is ambiguous in {actual}")
        return rows[0]

    def _resolve_car_body_upgrade(
        self,
        connection: sqlite3.Connection,
        car_id: int,
        selected_id: int | None,
    ) -> sqlite3.Row:
        if selected_id is not None:
            row = self._one(
                connection,
                "List_UpgradeCarBody",
                {"Id": int(selected_id), "Ordinal": car_id},
                True,
                f"CarBody Id={selected_id} for car {car_id}",
            )
        else:
            row = self._one(
                connection,
                "List_UpgradeCarBody",
                {"Ordinal": car_id, "IsStock": 1},
                True,
                f"stock CarBody for car {car_id}",
            )
        assert row is not None
        return row

    def _resolve_track_spacing(
        self,
        connection: sqlite3.Connection,
        table: str,
        car_body_id: int,
        selected_id: int | None,
    ) -> sqlite3.Row | None:
        if selected_id is not None:
            return self._one(
                connection,
                table,
                {"Id": int(selected_id), "CarBodyId": car_body_id},
                True,
                f"{table} Id={selected_id} for CarBody {car_body_id}",
            )
        return self._one(
            connection,
            table,
            {"CarBodyId": car_body_id, "IsStock": 1},
            False,
            f"stock {table} for CarBody {car_body_id}",
        )

    def _resolve_ordinal_upgrade(
        self,
        connection: sqlite3.Connection,
        table: str,
        car_id: int,
        selected_id: int | None,
        *,
        required: bool,
    ) -> sqlite3.Row | None:
        if selected_id is not None:
            return self._one(
                connection,
                table,
                {"Id": int(selected_id), "Ordinal": car_id},
                True,
                f"{table} Id={selected_id} for car {car_id}",
            )
        return self._one(
            connection,
            table,
            {"Ordinal": car_id, "IsStock": 1},
            required,
            f"stock {table} for car {car_id}",
        )

    @staticmethod
    def _keys(row: sqlite3.Row) -> dict[str, str]:
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
        keys = self._keys(row)
        for candidate in candidates:
            key = keys.get(candidate.casefold())
            if key is not None:
                return row[key]
        if required:
            raise WheelSpecError("database row is missing required column: " + "/".join(candidates))
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

    def _nonnegative(self, value: Any, label: str) -> float:
        number = self._number(value, label)
        if number < 0:
            raise WheelSpecError(f"{label} must be non-negative: {number}")
        return number

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _required_int(self, value: Any, label: str) -> int:
        result = self._optional_int(value)
        if result is None:
            raise WheelSpecError(f"{label} is not an integer: {value!r}")
        return result

    def _optional_number(self, row: sqlite3.Row | None, candidates: Iterable[str]) -> float | None:
        value = self._value(row, candidates, required=False)
        return None if value is None else self._number(value, "/".join(candidates))

    def _brake_axle(self, row: sqlite3.Row | None, axle: str) -> BrakeAxleSpec:
        prefix = "Front" if axle == "front" else "Rear"
        return BrakeAxleSpec(
            axle=axle,
            size_mm=self._optional_number(row, (f"{prefix}BrakeSizeMM",)),
            rotor_thickness_mm=self._optional_number(row, (f"{prefix}BrakeRotorThicknessMM",)),
            drum_depth_mm=self._optional_number(row, (f"{prefix}BrakeDrumDepthMM",)),
            non_spinning_mass=self._optional_number(row, (f"{prefix}BrakeNonSpinningMass",)),
            brake_type_id=self._optional_int(self._value(row, (f"{prefix}BrakeTypeID",), required=False)),
            caliper_pistons=self._optional_int(self._value(row, (f"{prefix}CaliperPistons",), required=False)),
        )
