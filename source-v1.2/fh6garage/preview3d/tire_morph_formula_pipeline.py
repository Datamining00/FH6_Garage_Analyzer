from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import tempfile
from typing import Any

from .tire_asset import TireAssetError, profile_tire_morph_archive, resolve_tire_archive
from .tire_morph_formula_evidence import (
    TireMorphFormulaEvidenceError,
    TireMorphFormulaEvidenceReport,
    build_tire_morph_formula_evidence,
)
from .tire_morph_geometry import TireMorphGeometryError, bake_tire_morph_selectors
from .wheel_spec import FH6WheelSpecResolver, VehicleWheelSpec, WheelSpecError


class TireMorphFormulaValidationError(RuntimeError):
    """Raised when the one-click native tire formula diagnostic cannot run safely."""


@dataclass(frozen=True)
class TireMorphFormulaValidationReport:
    game_or_cars_path: str
    database_path: str
    database_sha256: str
    database_read_only_unchanged: bool
    archive_path: str
    archive_sha256: str
    archive_read_only_unchanged: bool
    car_spec: VehicleWheelSpec
    evidence: TireMorphFormulaEvidenceReport

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "fh6_native_tire_morph_formula_validation_v1",
            "game_or_cars_path": self.game_or_cars_path,
            "database_path": self.database_path,
            "database_sha256": self.database_sha256,
            "database_read_only_unchanged": self.database_read_only_unchanged,
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "archive_read_only_unchanged": self.archive_read_only_unchanged,
            "car_spec": self.car_spec.as_dict(),
            "evidence": self.evidence.as_dict(),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_stock_tire_morph_formula(
    game_or_cars_path: str | Path,
    database_path: str | Path,
    car_id: int,
) -> TireMorphFormulaValidationReport:
    """Run the complete stock native-tire formula diagnostic read-only.

    Pipeline:
      DB stock wheel/tire spec -> exact TireModelName ZIP -> weighted morph profile
      -> selector geometry bake without GLBs -> physical-formula evidence report.

    The source DB and tire ZIP are hashed before/after. The function never enables
    production tire assembly or modifies game/save data.
    """
    database = Path(database_path).expanduser().resolve()
    if not database.is_file():
        raise TireMorphFormulaValidationError(f"FH6 game database does not exist: {database}")
    if int(car_id) <= 0:
        raise TireMorphFormulaValidationError(f"car_id must be positive: {car_id}")

    database_before = _sha256(database)
    try:
        spec = FH6WheelSpecResolver(database).resolve(int(car_id))
        if str(spec.mode).casefold() != "stock":
            raise TireMorphFormulaValidationError(
                f"one-click formula validation requires stock wheel spec, got {spec.mode!r}"
            )
        if not spec.tire_model_name:
            raise TireMorphFormulaValidationError(
                f"car {car_id} has no resolvable stock TireModelName in the FH6 DB"
            )

        archive = resolve_tire_archive(game_or_cars_path, spec.tire_model_name)
        archive_before = _sha256(archive)
        morph_profile = profile_tire_morph_archive(archive)
        with tempfile.TemporaryDirectory(prefix="fh6_tire_formula_") as directory:
            geometry_report = bake_tire_morph_selectors(
                archive,
                Path(directory),
                write_glb=False,
            )
        evidence = build_tire_morph_formula_evidence(
            spec,
            morph_profile,
            geometry_report,
        )
        archive_after = _sha256(archive)
    except (
        TireAssetError,
        TireMorphFormulaEvidenceError,
        TireMorphGeometryError,
        WheelSpecError,
        OSError,
    ) as exc:
        raise TireMorphFormulaValidationError(str(exc)) from exc

    database_after = _sha256(database)
    if database_before != database_after:
        raise TireMorphFormulaValidationError(
            "read-only tire formula validation changed the source database"
        )
    if archive_before != archive_after:
        raise TireMorphFormulaValidationError(
            "read-only tire formula validation changed the native tire archive"
        )
    if not morph_profile.archive_read_only_unchanged:
        raise TireMorphFormulaValidationError("morph profiler did not preserve the tire archive")
    if not geometry_report.archive_read_only_unchanged:
        raise TireMorphFormulaValidationError("geometry bake did not preserve the tire archive")
    if morph_profile.archive_sha256 != geometry_report.archive_sha256:
        raise TireMorphFormulaValidationError(
            "morph profile and geometry bake were not produced from the same tire archive bytes"
        )

    return TireMorphFormulaValidationReport(
        game_or_cars_path=str(Path(game_or_cars_path).expanduser().resolve()),
        database_path=str(database),
        database_sha256=database_before,
        database_read_only_unchanged=True,
        archive_path=str(archive),
        archive_sha256=archive_before,
        archive_read_only_unchanged=True,
        car_spec=spec,
        evidence=evidence,
    )
