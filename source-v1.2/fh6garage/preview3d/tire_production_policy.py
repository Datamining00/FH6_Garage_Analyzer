from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
import zipfile

from .tire_morph_auto_inference import (
    GENERIC_TIRE_AUTO_INFERENCE_REVISION,
    TireMorphAutoInferenceError,
    infer_stock_native_tire_morph,
)
from .tire_morph_weights import VehicleTireMorphWeights
from .wheel_spec import VehicleWheelSpec


TIRE_PRODUCTION_POLICY_REVISION = "stock_native_tire_generic_auto_inference_v1"


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
    auto_inference_report: dict[str, Any] | None = None,
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
        auto_inference_report=auto_inference_report,
    )


def evaluate_stock_tire_production_candidate(
    spec: VehicleWheelSpec,
    archive_path: str | Path,
) -> TireProductionEligibility:
    """Gate native tire preview with generic file-driven morph auto-inference.

    Tire family names and pre-recorded selector-role signatures are not admission
    criteria.  The exact archive linked by TireModelName is inspected read-only and
    its own selector geometry is used to infer stock morph weights.  The inference
    must reproduce the database stock width and outer diameter within global
    fail-closed tolerances before the production-trial geometry path is admitted.
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

    try:
        inference = infer_stock_native_tire_morph(spec, archive)
    except TireMorphAutoInferenceError as exc:
        return _blocked(
            "blocked_generic_auto_inference_failed",
            str(exc),
            spec,
            archive,
            archive_sha,
            identity,
            auto_inference_report=exc.report,
        )

    if inference.archive_sha256.casefold() != archive_sha.casefold():
        return _blocked(
            "blocked_auto_inference_archive_identity_changed",
            "generic auto inference did not use the same archive identity validated by production policy",
            spec,
            archive,
            archive_sha,
            identity,
            auto_inference_report=inference.as_dict(),
        )
    if not inference.archive_read_only_unchanged:
        return _blocked(
            "blocked_auto_inference_not_read_only",
            "generic auto inference did not preserve the source tire archive",
            spec,
            archive,
            archive_sha,
            identity,
            auto_inference_report=inference.as_dict(),
        )

    weights = inference.weights
    if weights.front.selector_weights[2:] != (0.0, 0.0, 0.0) or weights.rear.selector_weights[2:] != (
        0.0,
        0.0,
        0.0,
    ):
        return _blocked(
            "blocked_unresolved_selectors_nonzero",
            "generic auto inference v1 must keep selectors 2..4 zero until their physical semantics are established",
            spec,
            archive,
            archive_sha,
            identity,
            auto_inference_report=inference.as_dict(),
        )

    report_path = inference.persistent_report_path or "<diagnostic write unavailable>"
    return TireProductionEligibility(
        status="production_trial_eligible",
        detail=(
            f"Car ID {int(spec.car_id)} admitted by {GENERIC_TIRE_AUTO_INFERENCE_REVISION} using the actual "
            f"{model_name} modelbin response; no tire-family whitelist or selector-role signature gate; "
            f"diagnostic={report_path}"
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
        auto_inference_report=inference.as_dict(),
    )
