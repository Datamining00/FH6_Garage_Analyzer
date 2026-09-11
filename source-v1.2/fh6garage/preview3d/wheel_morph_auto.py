from __future__ import annotations

from .pipeline_diagnostics import timed

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Callable

from .wheel_morph_helper import WheelMorphHelperError, verified_bundled_wheel_morph_helper
from .wheel_morph_weights import (
    VehicleRimMorphWeights,
    WheelMorphWeightError,
    vehicle_rim_morph_weights,
)
from .wheel_spec import FH6WheelSpecResolver, WheelSpecError
from .wheel_spec_database import (
    PINNED_WHEEL_SPEC_DATABASE,
    WheelSpecDatabaseError,
    ensure_stock_wheel_database,
)


@dataclass(frozen=True)
class AutomaticRimMorphResolution:
    status: str
    weights: VehicleRimMorphWeights | None
    detail: str
    source_revision: str | None = None

    @property
    def applied(self) -> bool:
        return self.weights is not None and self.status == "applied"


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _database_media_name(database: Path, car_id: int) -> str | None:
    """Read only the Data_Car MediaName used to bind a Car ID to an archive code."""
    uri = database.resolve().as_uri() + "?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            tables = {
                str(row[0]).casefold(): str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                )
            }
            for requested in ("Drivable_Data_Car", "Data_Car"):
                table = tables.get(requested.casefold())
                if table is None:
                    continue
                columns = {
                    str(row[1]).casefold(): str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
                }
                id_column = columns.get("id")
                media_column = columns.get("medianame")
                if id_column is None or media_column is None:
                    continue
                row = connection.execute(
                    f"SELECT {_quote(media_column)} FROM {_quote(table)} "
                    f"WHERE {_quote(id_column)} = ? LIMIT 2",
                    (int(car_id),),
                ).fetchall()
                if len(row) > 1:
                    raise WheelSpecError(f"FH6 DB contains duplicate rows for Car ID {car_id}")
                if not row:
                    return None
                value = str(row[0][0] or "").strip()
                return value or None
    except sqlite3.Error as exc:
        raise WheelSpecError(f"could not validate FH6 Car ID/MediaName binding: {exc}") from exc
    return None


@timed('automatic_wheel_morph_resolve')
def resolve_automatic_stock_rim_morph(
    car_id: int,
    model_code: str,
    progress: Callable[[str], None] | None = None,
) -> AutomaticRimMorphResolution:
    """Resolve verified stock rim morph weights without making 3D preview dependent on them.

    Automatic production use is deliberately fail-open: if the verified patched helper,
    pinned stock-wheel DB, requested Car ID, or MediaName binding is unavailable, callers
    receive weights=None and may keep the pre-W3 geometry path. No wheel dimensions are
    guessed and no per-car fallback constants are used.
    """
    try:
        car_id = int(car_id)
    except (TypeError, ValueError):
        return AutomaticRimMorphResolution("invalid_request", None, f"invalid Car ID: {car_id!r}")
    model_code = str(model_code or "").strip()
    if car_id <= 0 or not model_code:
        return AutomaticRimMorphResolution(
            "invalid_request",
            None,
            f"invalid Car ID/model code: {car_id!r}/{model_code!r}",
        )

    try:
        helper = verified_bundled_wheel_morph_helper()
    except WheelMorphHelperError as exc:
        return AutomaticRimMorphResolution("helper_invalid", None, str(exc))
    if helper is None:
        return AutomaticRimMorphResolution(
            "helper_unavailable",
            None,
            "verified bundled wheel morph helper is unavailable",
        )

    try:
        database = ensure_stock_wheel_database(progress)
    except WheelSpecDatabaseError as exc:
        return AutomaticRimMorphResolution("database_unavailable", None, str(exc))

    source_revision = (
        f"{PINNED_WHEEL_SPEC_DATABASE.repository}@{PINNED_WHEEL_SPEC_DATABASE.commit}"
    )
    try:
        media_name = _database_media_name(database, car_id)
        if media_name is None:
            return AutomaticRimMorphResolution(
                "car_unavailable",
                None,
                f"Car ID {car_id} is absent from the verified stock-wheel DB",
                source_revision,
            )
        if media_name.casefold() != model_code.casefold():
            return AutomaticRimMorphResolution(
                "media_name_mismatch",
                None,
                f"Car ID {car_id} DB MediaName {media_name!r} does not match archive model code {model_code!r}",
                source_revision,
            )

        spec = FH6WheelSpecResolver(database).resolve(car_id)
        weights = vehicle_rim_morph_weights(spec)
    except (WheelSpecError, WheelMorphWeightError, OSError, ValueError) as exc:
        return AutomaticRimMorphResolution(
            "wheel_spec_unavailable",
            None,
            f"{type(exc).__name__}: {exc}",
            source_revision,
        )

    return AutomaticRimMorphResolution(
        "applied",
        weights,
        (
            f"stock rim morph resolved for {model_code}: "
            f"front {spec.front.tire_width_mm:g} mm / {spec.front.rim_diameter_in:g} in, "
            f"rear {spec.rear.tire_width_mm:g} mm / {spec.rear.rim_diameter_in:g} in"
        ),
        source_revision,
    )
