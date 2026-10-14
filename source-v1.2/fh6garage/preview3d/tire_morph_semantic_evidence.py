from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .tire_morph_boundary_roles import (
    TireMorphBoundaryRoleError,
    TireMorphBoundaryRoleReport,
    analyze_native_tire_selector_boundary_roles,
)

DOLIMAN_REFERENCE = (
    "Doliman100/ForzaTech-extraction-tools@"
    "d126767b4a63f4fdaa2143c4983f08a8c9974802:scripts/carbin_importer.py"
)
HYDRA_REFERENCE = (
    "Dr-hydra/FH6-Adjust-Tool@"
    "25cfd00195e74f8a85180b5f3193ee105259e2e2:src/QING.Core/Shared/FH6TuneDatabase.cs"
)


class TireMorphSemanticEvidenceError(RuntimeError):
    """Raised when selector semantic evidence cannot be assembled safely."""


@dataclass(frozen=True)
class SelectorInputSemanticEvidence:
    selector: int
    reference_stock_weight_kind: str
    reference_expression: str
    reference_inputs: tuple[str, ...]
    observed_geometric_roles: tuple[str, ...]
    semantic_status: str
    candidate_semantic: str
    excluded_candidate_semantics: tuple[str, ...]
    production_semantics_assigned: bool

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reference_inputs"] = list(self.reference_inputs)
        data["observed_geometric_roles"] = list(self.observed_geometric_roles)
        data["excluded_candidate_semantics"] = list(self.excluded_candidate_semantics)
        return data


@dataclass(frozen=True)
class TireMorphSemanticEvidenceReport:
    archive_path: str | None
    archive_sha256: str | None
    archive_read_only_unchanged: bool | None
    selectors: tuple[SelectorInputSemanticEvidence, ...]
    separate_controls: dict[str, dict[str, Any]]
    source_references: tuple[str, ...]
    production_mapping_enabled: bool
    complete_mapping_status: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "fh6_native_tire_selector_semantic_evidence_v1",
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "archive_read_only_unchanged": self.archive_read_only_unchanged,
            "selectors": [item.as_dict() for item in self.selectors],
            "separate_controls": self.separate_controls,
            "source_references": list(self.source_references),
            "production_mapping_enabled": self.production_mapping_enabled,
            "complete_mapping_status": self.complete_mapping_status,
            "limitations": list(self.limitations),
        }


_REFERENCE_EXPRESSIONS = {
    0: "(width_mm * original_aspect / 100 - 225 + original_rim_diameter_in * 12.7) / 275",
    1: "(rim_diameter_in - 10) / 14",
    2: "0",
    3: "0",
    4: "0",
}

_REFERENCE_INPUTS = {
    0: (
        "Data_Car.FrontTireWidthMM / RearTireWidthMM",
        "Data_Car.FrontTireAspect / RearTireAspect",
        "Data_Car.FrontWheelDiameterIN / RearWheelDiameterIN (original rim diameter)",
    ),
    1: ("effective front/rear wheel diameter in",),
    2: (),
    3: (),
    4: (),
}

_CANDIDATE_SEMANTICS = {
    0: "outer_radius_like_control",
    1: "rim_diameter_control",
    2: "unresolved_mixed_shape_control",
    3: "unresolved_positive_x_boundary_control",
    4: "unresolved_negative_x_boundary_control",
}

_EXPECTED_GEOMETRIC_ROLES = {
    0: {"radial_expansion_dominant"},
    1: {"radial_expansion_dominant"},
    2: {"mixed_x_expansion_radial_contraction"},
    3: {"positive_x_boundary_expansion"},
    4: {"negative_x_boundary_expansion"},
}


def _normalize_observed_roles(
    observed_roles: Mapping[int, Sequence[str]] | None,
) -> dict[int, tuple[str, ...]]:
    normalized: dict[int, tuple[str, ...]] = {selector: () for selector in range(5)}
    if observed_roles is None:
        return normalized
    for selector, roles in observed_roles.items():
        selector_id = int(selector)
        if selector_id not in normalized:
            raise TireMorphSemanticEvidenceError(
                f"selector index must be 0..4, got {selector_id}"
            )
        values = tuple(sorted({str(role) for role in roles if str(role)}))
        normalized[selector_id] = values
    return normalized


def _selector_status(selector: int, observed: tuple[str, ...]) -> str:
    if selector in (0, 1):
        if not observed:
            return "reference_mapped_geometry_not_supplied"
        if set(observed).issubset(_EXPECTED_GEOMETRIC_ROLES[selector]):
            return "reference_mapped_geometry_consistent"
        return "reference_mapped_geometry_conflict"

    if not observed:
        return "reference_stock_weight_zero_semantics_unresolved"
    if set(observed).issubset(_EXPECTED_GEOMETRIC_ROLES[selector]):
        return "reference_stock_weight_zero_geometry_role_observed_semantics_unresolved"
    return "reference_stock_weight_zero_geometry_role_mismatch_semantics_unresolved"


def build_tire_selector_semantic_evidence(
    observed_roles: Mapping[int, Sequence[str]] | None = None,
    *,
    archive_path: str | None = None,
    archive_sha256: str | None = None,
    archive_read_only_unchanged: bool | None = None,
) -> TireMorphSemanticEvidenceReport:
    """Combine public input mapping facts with observed selector geometry.

    This intentionally does not invent weights for selectors 2..4. Doliman's
    pinned reference stock tire call supplies literal zeros for those selectors,
    while tire width is applied separately as an X scale. Track spacing is also
    handled separately as a wheel transform in the reference importer and as a
    distinct upgrade slot in the FH6 tune database parser.
    """
    observed = _normalize_observed_roles(observed_roles)
    selectors: list[SelectorInputSemanticEvidence] = []
    for selector in range(5):
        excluded: tuple[str, ...]
        if selector in (2, 3, 4):
            base = ["primary_stock_tire_width_control"]
            if selector in (3, 4):
                base.append("track_spacing_control")
            excluded = tuple(base)
        else:
            excluded = ()
        selectors.append(
            SelectorInputSemanticEvidence(
                selector=selector,
                reference_stock_weight_kind=(
                    "computed" if selector in (0, 1) else "literal_zero"
                ),
                reference_expression=_REFERENCE_EXPRESSIONS[selector],
                reference_inputs=_REFERENCE_INPUTS[selector],
                observed_geometric_roles=observed[selector],
                semantic_status=_selector_status(selector, observed[selector]),
                candidate_semantic=_CANDIDATE_SEMANTICS[selector],
                excluded_candidate_semantics=excluded,
                production_semantics_assigned=False,
            )
        )

    unresolved = any(item.selector >= 2 for item in selectors if "unresolved" in item.semantic_status)
    conflict = any("conflict" in item.semantic_status or "mismatch" in item.semantic_status for item in selectors)
    if conflict:
        status = "diagnostic_selector_semantics_conflict_or_mismatch"
    elif unresolved:
        status = "diagnostic_selector_2_4_semantics_unresolved"
    else:
        status = "diagnostic_selector_semantics_incomplete"

    return TireMorphSemanticEvidenceReport(
        archive_path=archive_path,
        archive_sha256=archive_sha256,
        archive_read_only_unchanged=archive_read_only_unchanged,
        selectors=tuple(selectors),
        separate_controls={
            "tire_width": {
                "reference_behavior": "post-morph X scale",
                "expression": "scale_x = tire_width_mm / 1000",
                "implication": "selectors 2..4 are not the primary stock width driver in the pinned reference mapping",
            },
            "track_spacing": {
                "reference_behavior": "wheel-instance translation, not tire morph",
                "inputs": [
                    "Data_CarBody.ModelFrontTrackOuter",
                    "Data_CarBody.ModelRearTrackOuter",
                    "FH6 tune slots TrackSpacingFront / TrackSpacingRear",
                ],
                "expression": "translate_x = model_track_outer / 2 (sign mirrored by side)",
                "implication": "selector 3/4 boundary motion is not evidence that they implement track spacing",
            },
            "effective_tire_spec": {
                "reference_behavior": "separate width, aspect-ratio and rim-size upgrade inputs",
                "inputs": [
                    "TireWidthFront / TireWidthRear",
                    "FrontAspectRatio / RearAspectRatio",
                    "RimSizeFront / RimSizeRear",
                ],
                "implication": "no public reference input has been found that drives tire selectors 2..4",
            },
        },
        source_references=(DOLIMAN_REFERENCE, HYDRA_REFERENCE),
        production_mapping_enabled=False,
        complete_mapping_status=status,
        limitations=(
            "The pinned Doliman tire formula is explicitly labelled 'not verified' by its source.",
            "Selector 0/1 geometry consistency in one tire family does not establish a global production mapping.",
            "Literal zero weights in the public reference importer do not prove selectors 2..4 are unused by the game engine.",
            "Selectors 2..4 remain unresolved until an independent game-facing input or cross-family behavior identifies them.",
            "Production tire assembly remains disabled.",
        ),
    )


def analyze_native_tire_selector_semantics(
    archive_path: str | Path,
) -> TireMorphSemanticEvidenceReport:
    """Read a native tire archive and combine boundary roles with source evidence."""
    try:
        boundary: TireMorphBoundaryRoleReport = analyze_native_tire_selector_boundary_roles(
            archive_path
        )
    except TireMorphBoundaryRoleError as exc:
        raise TireMorphSemanticEvidenceError(str(exc)) from exc

    observed: dict[int, list[str]] = {selector: [] for selector in range(5)}
    for roles in boundary.modelbin_roles.values():
        for item in roles:
            observed[item.selector].append(item.geometric_role)

    return build_tire_selector_semantic_evidence(
        observed,
        archive_path=boundary.archive_path,
        archive_sha256=boundary.archive_sha256,
        archive_read_only_unchanged=boundary.archive_read_only_unchanged,
    )
