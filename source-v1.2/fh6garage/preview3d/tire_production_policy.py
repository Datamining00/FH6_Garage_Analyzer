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


TIRE_PRODUCTION_POLICY_REVISION = "stock_native_tire_global_preview_v1"

# Native tire-family geometry identities captured from the user's FH6 installation.
# Slick has the strongest evidence because selector 0/1 were also checked against
# real FER_FXX_05 stock dimensions.  The other approved families reproduced the
# same selector topology/sign pattern in the cross-family diagnostic.  Global
# preview is therefore permitted for stock specs only when the exact known native
# geometry identity is present.  b_Horizon remains excluded because its selector
# signature was structurally different.
_VALIDATED_SLICK_GEOMETRY_IDENTITY = (
    "c8a210f9cc9f09bd2cef658ebd5afb1630d7fe780c0e1b61d285591d31f9c9f1"
)
_TOPOLOGY_COMPATIBLE_IDENTITIES = {
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


def _expected_identity(model_name: str) -> str | None:
    key = model_name.casefold()
    if key == "slick":
        return _VALIDATED_SLICK_GEOMETRY_IDENTITY
    return _TOPOLOGY_COMPATIBLE_IDENTITIES.get(key)


def evaluate_stock_tire_production_candidate(
    spec: VehicleWheelSpec,
    archive_path: str | Path,
) -> TireProductionEligibility:
    """Gate the global stock native-tire preview using exact native-family evidence.

    Vehicle-specific FXX restrictions are intentionally removed after successful
    FXX wheel/rim/brake/tire visual validation.  The preview remains fail-closed at
    the tire-family level: only exact known geometry identities whose selector
    topology matches the validated Slick layout are admitted.  b_Horizon and
    unknown/changed families remain on FHA's existing vehicle-GLB path.

    Selector 2..4 remain literal zero for every admitted family.
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
            f"could not verify native tire archive read-only: {type(exc).__name__}: {exc}",
            spec,
            archive,
        )

    key = model_name.casefold()
    mismatch_identity = _STRUCTURAL_MISMATCH_IDENTITIES.get(key)
    if mismatch_identity is not None:
        if identity != mismatch_identity:
            return _blocked(
                "blocked_geometry_identity_mismatch",
                "known structurally different TireModelName has an unexpected modelbin identity",
                spec,
                archive,
                archive_sha,
                identity,
            )
        return _blocked(
            "blocked_selector_signature_mismatch",
            "this native tire family has a different selector-role signature and is excluded from global automatic preview",
            spec,
            archive,
            archive_sha,
            identity,
        )

    expected_identity = _expected_identity(model_name)
    if expected_identity is None:
        return _blocked(
            "blocked_family_not_evidence_approved",
            "this TireModelName has not been verified as selector-topology compatible with the global native tire preview",
            spec,
            archive,
            archive_sha,
            identity,
        )
    if identity != expected_identity:
        return _blocked(
            "blocked_geometry_identity_mismatch",
            "native tire modelbin identity differs from the verified family sample",
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

    evidence = (
        "physically dimension-corroborated Slick reference plus exact native geometry identity"
        if key == "slick"
        else "cross-family selector-topology match plus exact native geometry identity"
    )
    return TireProductionEligibility(
        status="production_trial_eligible",
        detail=(
            f"global stock native tire preview admitted Car ID {int(spec.car_id)} using {model_name}: {evidence}; "
            "selector 0/1 and width X-scale are applied, selector 2..4 remain zero"
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
