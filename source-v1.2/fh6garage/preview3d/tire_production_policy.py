from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
import zipfile

from .tire_morph_weights import AxleTireMorphWeights, VehicleTireMorphWeights
from .wheel_spec import AxleWheelSpec, VehicleWheelSpec


TIRE_PRODUCTION_POLICY_REVISION = "stock_native_tire_global_auto_recognition_v4"
_NORMALIZATION_MAPPING_REVISION = "native_tire_stock_dimension_normalization_v1"


@dataclass(frozen=True)
class TireProductionEligibility:
    status: str
    detail: str
    policy_revision: str
    car_id: int
    tire_model_name: str | None
    archive_path: str
    archive_sha256: str | None
    geometry_identity_sha256: str | None
    production_trial_eligible: bool
    production_renderer_enabled: bool
    weights: VehicleTireMorphWeights | None
    auto_inference_report: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "detail": self.detail,
            "policy_revision": self.policy_revision,
            "car_id": self.car_id,
            "tire_model_name": self.tire_model_name,
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "geometry_identity_sha256": self.geometry_identity_sha256,
            "production_trial_eligible": self.production_trial_eligible,
            "production_renderer_enabled": self.production_renderer_enabled,
            "weights": self.weights.as_dict() if self.weights is not None else None,
            "auto_inference_report": self.auto_inference_report,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _geometry_identity(archive: Path) -> tuple[str, str]:
    """Return archive and aggregate modelbin identities for diagnostics only."""
    before = _sha256(archive)
    with zipfile.ZipFile(archive, "r") as bundle:
        hashes = sorted(
            hashlib.sha256(bundle.read(item)).hexdigest()
            for item in bundle.infolist()
            if not item.is_dir() and item.filename.casefold().endswith(".modelbin")
        )
    if not hashes:
        raise ValueError("native tire archive contains no modelbin")
    after = _sha256(archive)
    if before != after:
        raise ValueError("read-only tire inspection changed the source archive")
    identity = hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()
    return before, identity


def _blocked(
    status: str,
    detail: str,
    spec: VehicleWheelSpec,
    archive: Path,
    archive_sha256: str | None = None,
    geometry_identity: str | None = None,
) -> TireProductionEligibility:
    return TireProductionEligibility(
        status=status,
        detail=detail,
        policy_revision=TIRE_PRODUCTION_POLICY_REVISION,
        car_id=int(spec.car_id),
        tire_model_name=spec.tire_model_name,
        archive_path=str(archive),
        archive_sha256=archive_sha256,
        geometry_identity_sha256=geometry_identity,
        production_trial_eligible=False,
        production_renderer_enabled=False,
        weights=None,
        auto_inference_report=None,
    )


def _axle_normalization_weights(spec: AxleWheelSpec) -> AxleTireMorphWeights:
    """Zero-selector carrier used by the global base-geometry normalization path."""
    return AxleTireMorphWeights(
        axle=str(spec.axle),
        tire_width_mm=float(spec.tire_width_mm),
        tire_aspect_ratio=float(spec.tire_aspect_ratio),
        original_rim_diameter_in=float(spec.rim_diameter_in),
        rim_diameter_in=float(spec.rim_diameter_in),
        selector_weights=(0.0, 0.0, 0.0, 0.0, 0.0),
        scale_x=1.0,
        mapping_revision=_NORMALIZATION_MAPPING_REVISION,
    )


def _normalization_weights(spec: VehicleWheelSpec) -> VehicleTireMorphWeights:
    return VehicleTireMorphWeights(
        car_id=int(spec.car_id),
        wheel_spec_mode=str(spec.mode),
        tire_model_name=spec.tire_model_name,
        front=_axle_normalization_weights(spec.front),
        rear=_axle_normalization_weights(spec.rear),
        mapping_revision=_NORMALIZATION_MAPPING_REVISION,
    )


def evaluate_stock_tire_production_candidate(
    spec: VehicleWheelSpec,
    archive_path: str | Path,
) -> TireProductionEligibility:
    """Admit every resolvable stock tire archive into the FHA global tire path.

    TireModelName is used only for automatic file resolution.  There is no family
    whitelist, selector-signature validation, geometry-family identity gate, or
    per-car morph calibration.  Once the matching native ZIP is found and contains
    at least one modelbin, the base tire geometry is decoded and later normalized to
    the stock width and outer diameter from the game database.
    """
    archive = Path(archive_path).expanduser().resolve()
    if str(spec.mode).casefold() != "stock":
        return _blocked(
            "blocked_nonstock_spec",
            f"global native tire preview requires stock wheel spec; got mode={spec.mode!r}",
            spec,
            archive,
        )

    model_name = str(spec.tire_model_name or "").strip()
    if not model_name:
        return _blocked(
            "blocked_missing_tire_model_name",
            "stock wheel spec has no TireModelName",
            spec,
            archive,
        )
    if not archive.is_file():
        return _blocked(
            "blocked_archive_missing",
            f"native tire archive does not exist: {archive}",
            spec,
            archive,
        )
    if archive.name.casefold() != f"tire_{model_name}.zip".casefold():
        return _blocked(
            "blocked_archive_model_mismatch",
            f"archive {archive.name!r} does not match TireModelName={model_name!r}",
            spec,
            archive,
        )

    try:
        archive_sha, identity = _geometry_identity(archive)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        return _blocked(
            "blocked_archive_invalid",
            f"could not inspect native tire archive read-only: {type(exc).__name__}: {exc}",
            spec,
            archive,
        )

    weights = _normalization_weights(spec)
    return TireProductionEligibility(
        status="production_trial_eligible",
        detail=(
            f"Car ID {int(spec.car_id)} / TireModelName={model_name} admitted by automatic file resolution; "
            "native base geometry will be normalized directly to stock DB dimensions; "
            "no tire-family or Car-ID-specific mapping"
        ),
        policy_revision=TIRE_PRODUCTION_POLICY_REVISION,
        car_id=int(spec.car_id),
        tire_model_name=spec.tire_model_name,
        archive_path=str(archive),
        archive_sha256=archive_sha,
        geometry_identity_sha256=identity,
        production_trial_eligible=True,
        production_renderer_enabled=False,
        weights=weights,
        auto_inference_report={
            "status": "not_required",
            "mode": _NORMALIZATION_MAPPING_REVISION,
        },
    )
