from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import tempfile
from typing import Any, Iterable

from .tire_morph_boundary_roles import (
    TireMorphBoundaryRoleError,
    analyze_selector_state_boundaries,
)
from .tire_morph_geometry import TireMorphGeometryError, bake_tire_morph_selectors


class TireMorphSignatureComparisonError(RuntimeError):
    """Raised when normalized selector signatures cannot be compared safely."""


@dataclass(frozen=True)
class NormalizedSelectorSignature:
    selector: int
    geometric_role: str
    role_confidence: str
    normalized_boundary_deltas: tuple[float, float, float, float, float, float]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["normalized_boundary_deltas"] = list(self.normalized_boundary_deltas)
        return data


@dataclass(frozen=True)
class ArchiveSelectorSignature:
    archive_path: str
    archive_sha256: str
    geometry_identity_sha256: str
    archive_read_only_unchanged: bool
    modelbin_sha256: tuple[str, ...]
    modelbin_count: int
    modelbin_role_consistent: bool
    selectors: tuple[NormalizedSelectorSignature, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "geometry_identity_sha256": self.geometry_identity_sha256,
            "archive_read_only_unchanged": self.archive_read_only_unchanged,
            "modelbin_sha256": list(self.modelbin_sha256),
            "modelbin_count": self.modelbin_count,
            "modelbin_role_consistent": self.modelbin_role_consistent,
            "selectors": [item.as_dict() for item in self.selectors],
        }


@dataclass(frozen=True)
class SelectorSignatureComparison:
    candidate_archive: str
    candidate_geometry_identity_sha256: str
    same_geometry_identity_as_reference: bool
    role_pattern_match: bool
    max_abs_feature_delta: float
    rms_feature_delta: float
    per_selector_max_abs_delta: dict[int, float]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["per_selector_max_abs_delta"] = {
            str(key): value for key, value in self.per_selector_max_abs_delta.items()
        }
        return data


@dataclass(frozen=True)
class CrossFamilySelectorSignatureReport:
    reference_archive: str
    quantitative_tolerance: float
    minimum_unique_geometry_families: int
    unique_geometry_family_count: int
    archives: tuple[ArchiveSelectorSignature, ...]
    comparisons: tuple[SelectorSignatureComparison, ...]
    status: str
    production_mapping_enabled: bool
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "fh6_native_tire_cross_family_selector_signature_v1",
            "reference_archive": self.reference_archive,
            "quantitative_tolerance": self.quantitative_tolerance,
            "minimum_unique_geometry_families": self.minimum_unique_geometry_families,
            "unique_geometry_family_count": self.unique_geometry_family_count,
            "archives": [item.as_dict() for item in self.archives],
            "comparisons": [item.as_dict() for item in self.comparisons],
            "status": self.status,
            "production_mapping_enabled": self.production_mapping_enabled,
            "limitations": list(self.limitations),
        }


def _triplet(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise TireMorphSignatureComparisonError(f"{label} must contain exactly 3 values")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise TireMorphSignatureComparisonError(f"{label} contains a non-finite value")
    return result


def _normalized_axis_boundaries(
    baseline_min: tuple[float, float, float],
    baseline_max: tuple[float, float, float],
    state_min: tuple[float, float, float],
    state_max: tuple[float, float, float],
    axis: int,
) -> tuple[float, float]:
    span = baseline_max[axis] - baseline_min[axis]
    if not math.isfinite(span) or span <= 1.0e-9:
        raise TireMorphSignatureComparisonError(
            f"baseline span for axis {axis} must be finite and positive"
        )
    return (
        (state_min[axis] - baseline_min[axis]) / span,
        (state_max[axis] - baseline_max[axis]) / span,
    )


def normalized_selector_signatures_from_states(
    states: dict[str, dict[str, object]],
) -> tuple[NormalizedSelectorSignature, ...]:
    """Normalize selector boundary motion by the baseline span of each axis."""
    baseline = states.get("baseline")
    if not isinstance(baseline, dict) or not isinstance(baseline.get("aabb"), dict):
        raise TireMorphSignatureComparisonError("baseline AABB is missing")
    baseline_aabb = baseline["aabb"]
    baseline_min = _triplet(baseline_aabb.get("minimum"), "baseline minimum")
    baseline_max = _triplet(baseline_aabb.get("maximum"), "baseline maximum")

    try:
        roles = analyze_selector_state_boundaries(states)
    except TireMorphBoundaryRoleError as exc:
        raise TireMorphSignatureComparisonError(str(exc)) from exc

    result: list[NormalizedSelectorSignature] = []
    for role in roles:
        state_name = f"selector{role.selector}"
        state = states.get(state_name)
        if not isinstance(state, dict) or not isinstance(state.get("aabb"), dict):
            raise TireMorphSignatureComparisonError(f"{state_name} AABB is missing")
        aabb = state["aabb"]
        state_min = _triplet(aabb.get("minimum"), f"{state_name} minimum")
        state_max = _triplet(aabb.get("maximum"), f"{state_name} maximum")
        features: list[float] = []
        for axis in range(3):
            features.extend(
                _normalized_axis_boundaries(
                    baseline_min,
                    baseline_max,
                    state_min,
                    state_max,
                    axis,
                )
            )
        result.append(
            NormalizedSelectorSignature(
                selector=role.selector,
                geometric_role=role.geometric_role,
                role_confidence=role.confidence,
                normalized_boundary_deltas=tuple(features),
            )
        )
    return tuple(result)


def compare_selector_signature_sets(
    reference: tuple[NormalizedSelectorSignature, ...],
    candidate: tuple[NormalizedSelectorSignature, ...],
) -> tuple[bool, float, float, dict[int, float]]:
    if len(reference) != 5 or len(candidate) != 5:
        raise TireMorphSignatureComparisonError("selector signatures must contain selectors 0..4")
    if [item.selector for item in reference] != list(range(5)) or [item.selector for item in candidate] != list(range(5)):
        raise TireMorphSignatureComparisonError("selector signatures must be ordered selectors 0..4")

    role_match = all(
        left.geometric_role == right.geometric_role
        for left, right in zip(reference, candidate)
    )
    differences: list[float] = []
    per_selector: dict[int, float] = {}
    for left, right in zip(reference, candidate):
        selector_diffs = [
            abs(a - b)
            for a, b in zip(left.normalized_boundary_deltas, right.normalized_boundary_deltas)
        ]
        differences.extend(selector_diffs)
        per_selector[left.selector] = max(selector_diffs, default=0.0)
    max_abs = max(differences, default=0.0)
    rms = math.sqrt(sum(value * value for value in differences) / len(differences)) if differences else 0.0
    return role_match, max_abs, rms, per_selector


def _geometry_identity(modelbin_hashes: Iterable[str]) -> str:
    canonical = "\n".join(sorted(str(value) for value in modelbin_hashes))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _archive_signature(archive_path: str | Path) -> ArchiveSelectorSignature:
    archive = Path(archive_path).expanduser().resolve()
    try:
        with tempfile.TemporaryDirectory(prefix="fh6-tire-signature-") as directory:
            bake = bake_tire_morph_selectors(archive, Path(directory), write_glb=False)
    except TireMorphGeometryError as exc:
        raise TireMorphSignatureComparisonError(str(exc)) from exc
    if not bake.archive_read_only_unchanged:
        raise TireMorphSignatureComparisonError(f"source archive changed during analysis: {archive}")
    if not bake.modelbins:
        raise TireMorphSignatureComparisonError(f"archive has no analyzable tire modelbins: {archive}")

    per_modelbin = [normalized_selector_signatures_from_states(item.states) for item in bake.modelbins]
    role_sequences = [tuple(entry.geometric_role for entry in signature) for signature in per_modelbin]
    role_consistent = all(sequence == role_sequences[0] for sequence in role_sequences[1:])

    averaged: list[NormalizedSelectorSignature] = []
    for selector in range(5):
        entries = [signature[selector] for signature in per_modelbin]
        feature_count = len(entries[0].normalized_boundary_deltas)
        means = tuple(
            sum(entry.normalized_boundary_deltas[index] for entry in entries) / len(entries)
            for index in range(feature_count)
        )
        role = entries[0].geometric_role if role_consistent else "inconsistent_within_archive"
        confidence = entries[0].role_confidence if role_consistent else "low"
        averaged.append(
            NormalizedSelectorSignature(
                selector=selector,
                geometric_role=role,
                role_confidence=confidence,
                normalized_boundary_deltas=means,
            )
        )

    modelbin_hashes = tuple(item.modelbin_sha256 for item in bake.modelbins)
    return ArchiveSelectorSignature(
        archive_path=str(archive),
        archive_sha256=bake.archive_sha256,
        geometry_identity_sha256=_geometry_identity(modelbin_hashes),
        archive_read_only_unchanged=bake.archive_read_only_unchanged,
        modelbin_sha256=modelbin_hashes,
        modelbin_count=len(bake.modelbins),
        modelbin_role_consistent=role_consistent,
        selectors=tuple(averaged),
    )


def compare_native_tire_selector_signatures(
    archive_paths: Iterable[str | Path],
    *,
    quantitative_tolerance: float = 0.25,
    minimum_unique_geometry_families: int = 2,
) -> CrossFamilySelectorSignatureReport:
    """Compare normalized selector geometry across native tire archives, diagnostic-only."""
    paths = tuple(archive_paths)
    if not paths:
        raise TireMorphSignatureComparisonError("at least one tire archive is required")
    tolerance = float(quantitative_tolerance)
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise TireMorphSignatureComparisonError("quantitative_tolerance must be finite and non-negative")
    minimum = int(minimum_unique_geometry_families)
    if minimum < 2:
        raise TireMorphSignatureComparisonError("minimum_unique_geometry_families must be at least 2")

    archives = tuple(_archive_signature(path) for path in paths)
    reference = archives[0]
    comparisons: list[SelectorSignatureComparison] = []
    for candidate in archives[1:]:
        role_match, max_abs, rms, per_selector = compare_selector_signature_sets(
            reference.selectors,
            candidate.selectors,
        )
        comparisons.append(
            SelectorSignatureComparison(
                candidate_archive=candidate.archive_path,
                candidate_geometry_identity_sha256=candidate.geometry_identity_sha256,
                same_geometry_identity_as_reference=(
                    candidate.geometry_identity_sha256 == reference.geometry_identity_sha256
                ),
                role_pattern_match=role_match,
                max_abs_feature_delta=max_abs,
                rms_feature_delta=rms,
                per_selector_max_abs_delta=per_selector,
            )
        )

    unique_identities = {item.geometry_identity_sha256 for item in archives}
    unique_comparisons = [item for item in comparisons if not item.same_geometry_identity_as_reference]

    if not all(item.modelbin_role_consistent for item in archives):
        status = "diagnostic_selector_signature_inconsistent_within_archive"
    elif len(unique_identities) < minimum:
        status = "diagnostic_selector_signature_insufficient_unique_families"
    elif unique_comparisons and all(
        item.role_pattern_match and item.max_abs_feature_delta <= tolerance
        for item in unique_comparisons
    ):
        status = "diagnostic_cross_family_selector_signature_consistent"
    else:
        status = "diagnostic_cross_family_selector_signature_differs"

    return CrossFamilySelectorSignatureReport(
        reference_archive=reference.archive_path,
        quantitative_tolerance=tolerance,
        minimum_unique_geometry_families=minimum,
        unique_geometry_family_count=len(unique_identities),
        archives=archives,
        comparisons=tuple(comparisons),
        status=status,
        production_mapping_enabled=False,
        limitations=(
            "Normalization removes absolute tire size but does not prove game-facing selector semantics.",
            "The quantitative tolerance is a diagnostic similarity heuristic, not a production acceptance threshold.",
            "Distinct ZIP containers with identical modelbin geometry count as one geometry family.",
            "Production tire assembly remains disabled regardless of comparison status.",
        ),
    )
