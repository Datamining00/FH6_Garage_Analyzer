from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
import zipfile

from .tire_morph_weights import (
    TireMorphWeightError,
    VehicleTireMorphWeights,
    stock_vehicle_tire_morph_weights,
)
from .wheel_spec import VehicleWheelSpec


TIRE_PRODUCTION_POLICY_REVISION = "fxx_1006_slick_stock_trial_v1"

# Evidence captured from the actual native tire diagnostic bundle produced from
# the user's FH6 installation on 2026-09-07.  Only Slick has both selector-role
# corroboration and an independent physical-dimension check against a real stock
# vehicle (Car ID 1006, FER_FXX_05).  Other families remain diagnostic-only.
_VALIDATED_SLICK_GEOMETRY_IDENTITY = (
    "c8a210f9cc9f09bd2cef658ebd5afb1630d7fe780c0e1b61d285591d31f9c9f1"
)
_VALIDATED_FXX_CAR_ID = 1006
_VALIDATED_FXX_FRONT = (245.0, 35.0, 19.0)
_VALIDATED_FXX_REAR = (345.0, 35.0, 19.0)

_TOPOLOGY_ONLY_IDENTITIES = {
    "a": "d8e6c0ca112e99775f731515637ab9f91fff705ee0b7bb786917dfd30d277435",
    "b": "627b8ee10019649dee3e353699ed660e3b6602abc9e414b7b696261790647b10",
    "b_dmack": "d9ff20f7be8fb9cb06729bf2966a594d3655f804b181f6bb79973ea105491fad",
    "b_horizonedition": "62764f28f167896a2e409b5678545b52089ec6925acc0aa48e9ae9e323f62221",
}
_STRUCTURAL_MISMATCH_IDENTITIES = {
    "b_horizon": "00e625ca8a299237f948e8794ec34e76b0e1b8852e1d7055feeba33a5f43a840",
}


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
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _geometry_identity(archive: Path) -> tuple[str, str]:
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


def _same_axle_spec(actual: tuple[float, float, float], expected: tuple[float, float, float]) -> bool:
    return all(abs(float(a) - float(b)) <= 1.0e-9 for a, b in zip(actual, expected))


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
    )


def evaluate_stock_tire_production_candidate(
    spec: VehicleWheelSpec,
    archive_path: str | Path,
) -> TireProductionEligibility:
    """Fail-closed gate for the first evidence-backed native tire production trial.

    This does *not* attach geometry to spindles.  It only proves that the input is
    the exact stock FXX/Slick combination whose selector 0/1 + X-width mapping was
    physically corroborated.  Selector 2..4 must remain literal zero.
    """
    archive = Path(archive_path).expanduser().resolve()
    if str(spec.mode).casefold() != "stock":
        return _blocked(
            "blocked_nonstock_spec",
            f"production tire trial requires stock wheel spec; got mode={spec.mode!r}",
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
            f"could not verify native tire archive read-only: {type(exc).__name__}: {exc}",
            spec,
            archive,
        )

    key = model_name.casefold()
    topology_identity = _TOPOLOGY_ONLY_IDENTITIES.get(key)
    if topology_identity is not None:
        if identity != topology_identity:
            return _blocked(
                "blocked_geometry_identity_mismatch",
                "known topology-only TireModelName has an unexpected modelbin identity",
                spec,
                archive,
                archive_sha,
                identity,
            )
        return _blocked(
            "blocked_dimension_formula_not_corroborated",
            "selector topology matches Slick, but physical tire dimensions have not been independently corroborated for this family",
            spec,
            archive,
            archive_sha,
            identity,
        )

    mismatch_identity = _STRUCTURAL_MISMATCH_IDENTITIES.get(key)
    if mismatch_identity is not None:
        return _blocked(
            "blocked_selector_signature_mismatch",
            "this tire family produced a different selector-role signature and is excluded from the production trial",
            spec,
            archive,
            archive_sha,
            identity,
        )

    if key != "slick":
        return _blocked(
            "blocked_family_not_evidence_approved",
            "this TireModelName has no physical-dimension production evidence",
            spec,
            archive,
            archive_sha,
            identity,
        )
    if identity != _VALIDATED_SLICK_GEOMETRY_IDENTITY:
        return _blocked(
            "blocked_geometry_identity_mismatch",
            "Slick modelbin identity differs from the physically validated native sample",
            spec,
            archive,
            archive_sha,
            identity,
        )
    if int(spec.car_id) != _VALIDATED_FXX_CAR_ID:
        return _blocked(
            "blocked_car_dimension_validation_missing",
            "Slick selector formula has not yet been physically dimension-validated for this Car ID",
            spec,
            archive,
            archive_sha,
            identity,
        )

    front = (
        float(spec.front.tire_width_mm),
        float(spec.front.tire_aspect_ratio),
        float(spec.front.rim_diameter_in),
    )
    rear = (
        float(spec.rear.tire_width_mm),
        float(spec.rear.tire_aspect_ratio),
        float(spec.rear.rim_diameter_in),
    )
    if not _same_axle_spec(front, _VALIDATED_FXX_FRONT) or not _same_axle_spec(
        rear, _VALIDATED_FXX_REAR
    ):
        return _blocked(
            "blocked_validated_dimension_mismatch",
            "FXX stock tire dimensions differ from the physically corroborated 245/35R19 front and 345/35R19 rear evidence",
            spec,
            archive,
            archive_sha,
            identity,
        )

    try:
        weights = stock_vehicle_tire_morph_weights(spec)
    except TireMorphWeightError as exc:
        return _blocked(
            "blocked_weight_mapping_invalid",
            str(exc),
            spec,
            archive,
            archive_sha,
            identity,
        )
    if weights.front.selector_weights[2:] != (0.0, 0.0, 0.0) or weights.rear.selector_weights[2:] != (
        0.0,
        0.0,
        0.0,
    ):
        return _blocked(
            "blocked_unresolved_selectors_nonzero",
            "selector 2..4 must remain zero until their game-facing semantics are verified",
            spec,
            archive,
            archive_sha,
            identity,
        )

    return TireProductionEligibility(
        status="production_trial_eligible",
        detail=(
            "exact stock FXX/Slick evidence matched; selector 0/1 and width X-scale may proceed to a derived-geometry trial, while selector 2..4 remain zero"
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
    )
