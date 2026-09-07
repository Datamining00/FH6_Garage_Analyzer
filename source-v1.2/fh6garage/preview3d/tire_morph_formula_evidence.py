from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping, Sequence

from .tire_morph_weights import tire_morph_weights
from .wheel_spec import VehicleWheelSpec


class TireMorphFormulaEvidenceError(RuntimeError):
    """Raised when tire mapping evidence cannot be evaluated without guessing."""


_DOLIMAN_SOURCE_REVISION = "d126767b4a63f4fdaa2143c4983f08a8c9974802"
_EXPECTED_RADIAL_SCALE_M = {
    0: 0.275,              # (outer_radius_mm - 225) / 275
    1: 14.0 * 0.0254 / 2, # (rim_diameter_in - 10) / 14 -> radius change
}


@dataclass(frozen=True)
class SelectorFormulaEvidence:
    selector: int
    geometry_role_hint: str
    max_abs_delta: tuple[float, float, float]
    min_signed_delta: tuple[float, float, float]
    max_signed_delta: tuple[float, float, float]
    radial_yz_max_abs_m: float
    x_max_abs_m: float
    expected_physical_role: str | None
    expected_radial_scale_m_per_weight: float | None
    radial_scale_relative_error: float | None
    corroboration: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AxleFormulaEvidence:
    axle: str
    tire_width_mm: float
    tire_aspect_ratio: float
    rim_diameter_in: float
    sidewall_height_mm: float
    outer_radius_mm: float
    outer_diameter_mm: float
    selector0_outer_radius_weight: float
    selector1_rim_diameter_weight: float
    scale_x_width_m: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TireMorphFormulaEvidenceReport:
    car_id: int
    tire_model_name: str | None
    wheel_spec_mode: str
    historical_source_revision: str
    historical_source_warning: str
    production_mapping_enabled: bool
    left_right_morph_buffers_identical: bool | None
    selector_evidence: tuple[SelectorFormulaEvidence, ...]
    front: AxleFormulaEvidence
    rear: AxleFormulaEvidence
    baseline_x_spans: tuple[float, ...]
    width_scale_normalization_status: str
    complete_mapping_status: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fh6_native_tire_morph_formula_evidence_v1",
            "car_id": self.car_id,
            "tire_model_name": self.tire_model_name,
            "wheel_spec_mode": self.wheel_spec_mode,
            "historical_source_revision": self.historical_source_revision,
            "historical_source_warning": self.historical_source_warning,
            "production_mapping_enabled": self.production_mapping_enabled,
            "left_right_morph_buffers_identical": self.left_right_morph_buffers_identical,
            "selector_evidence": [item.as_dict() for item in self.selector_evidence],
            "front": self.front.as_dict(),
            "rear": self.rear.as_dict(),
            "baseline_x_spans": list(self.baseline_x_spans),
            "width_scale_normalization_status": self.width_scale_normalization_status,
            "complete_mapping_status": self.complete_mapping_status,
            "limitations": list(self.limitations),
        }


def _payload(value: Any, label: str) -> Mapping[str, Any]:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if not isinstance(value, Mapping):
        raise TireMorphFormulaEvidenceError(f"{label} must be a mapping or expose as_dict()")
    return value


def _vec3(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise TireMorphFormulaEvidenceError(f"{label} must contain exactly three values")
    result = tuple(float(component) for component in value)
    if not all(math.isfinite(component) for component in result):
        raise TireMorphFormulaEvidenceError(f"{label} contains a non-finite value")
    return result  # type: ignore[return-value]


def _selector_stats(morph_profile: Any) -> tuple[dict[int, dict[str, tuple[float, float, float]]], bool | None]:
    payload = _payload(morph_profile, "morph_profile")
    modelbins = payload.get("modelbins")
    if not isinstance(modelbins, Sequence) or isinstance(modelbins, (str, bytes)):
        raise TireMorphFormulaEvidenceError("morph_profile.modelbins is missing")

    aggregate: dict[int, dict[str, tuple[float, float, float]]] = {}
    for model_index, modelbin in enumerate(modelbins):
        if not isinstance(modelbin, Mapping):
            raise TireMorphFormulaEvidenceError(f"modelbins[{model_index}] is invalid")
        profiles = modelbin.get("profiles", ())
        if not isinstance(profiles, Sequence) or isinstance(profiles, (str, bytes)):
            raise TireMorphFormulaEvidenceError(f"modelbins[{model_index}].profiles is invalid")
        for profile_index, group in enumerate(profiles):
            if not isinstance(group, Mapping) or not isinstance(group.get("profile"), Mapping):
                raise TireMorphFormulaEvidenceError(
                    f"modelbins[{model_index}].profiles[{profile_index}] is invalid"
                )
            profile = group["profile"]
            if int(profile.get("morph_target_count", -1)) != 5:
                raise TireMorphFormulaEvidenceError(
                    "formula evidence is verified only for five-target native tire morph buffers"
                )
            selectors = profile.get("selectors", ())
            if not isinstance(selectors, Sequence) or isinstance(selectors, (str, bytes)):
                raise TireMorphFormulaEvidenceError("weighted selector statistics are missing")
            for item in selectors:
                if not isinstance(item, Mapping):
                    raise TireMorphFormulaEvidenceError("selector statistic is invalid")
                selector = int(item.get("selector", -1))
                if selector < 0 or selector >= 5:
                    raise TireMorphFormulaEvidenceError(f"unexpected selector {selector}")
                max_abs = _vec3(item.get("max_abs_delta"), f"selector {selector} max_abs_delta")
                min_signed = _vec3(
                    item.get("min_signed_delta"), f"selector {selector} min_signed_delta"
                )
                max_signed = _vec3(
                    item.get("max_signed_delta"), f"selector {selector} max_signed_delta"
                )
                current = aggregate.get(selector)
                if current is None:
                    aggregate[selector] = {
                        "max_abs": max_abs,
                        "min_signed": min_signed,
                        "max_signed": max_signed,
                    }
                else:
                    aggregate[selector] = {
                        "max_abs": tuple(
                            max(current["max_abs"][axis], max_abs[axis]) for axis in range(3)
                        ),
                        "min_signed": tuple(
                            min(current["min_signed"][axis], min_signed[axis]) for axis in range(3)
                        ),
                        "max_signed": tuple(
                            max(current["max_signed"][axis], max_signed[axis]) for axis in range(3)
                        ),
                    }

    if set(aggregate) != set(range(5)):
        raise TireMorphFormulaEvidenceError(
            f"expected selector statistics 0..4, got {sorted(aggregate)}"
        )
    identical = payload.get("left_right_morph_buffers_identical")
    if identical is not None:
        identical = bool(identical)
    return aggregate, identical


def _role_hint(
    max_abs: tuple[float, float, float],
    min_signed: tuple[float, float, float],
    max_signed: tuple[float, float, float],
) -> str:
    x = max_abs[0]
    radial = max(max_abs[1], max_abs[2])
    epsilon = 1e-9
    if radial > epsilon and radial >= 2.0 * max(x, epsilon):
        return "radial_dominant"
    if x > epsilon and x >= 2.0 * max(radial, epsilon):
        if min_signed[0] >= -epsilon and max_signed[0] > epsilon:
            return "positive_x_dominant"
        if max_signed[0] <= epsilon and min_signed[0] < -epsilon:
            return "negative_x_dominant"
        return "x_dominant"
    return "mixed"


def _selector_evidence(morph_profile: Any) -> tuple[tuple[SelectorFormulaEvidence, ...], bool | None]:
    aggregate, identical = _selector_stats(morph_profile)
    expected_roles = {0: "outer_radius_control", 1: "rim_diameter_control"}
    result: list[SelectorFormulaEvidence] = []
    for selector in range(5):
        stats = aggregate[selector]
        max_abs = stats["max_abs"]
        min_signed = stats["min_signed"]
        max_signed = stats["max_signed"]
        role = _role_hint(max_abs, min_signed, max_signed)
        radial = max(max_abs[1], max_abs[2])
        expected_scale = _EXPECTED_RADIAL_SCALE_M.get(selector)
        relative_error: float | None = None
        corroboration = "not_applicable"
        if expected_scale is not None:
            relative_error = abs(radial - expected_scale) / expected_scale
            corroboration = (
                "geometry_corroborated"
                if role == "radial_dominant" and relative_error <= 0.10
                else "not_corroborated"
            )
        result.append(
            SelectorFormulaEvidence(
                selector=selector,
                geometry_role_hint=role,
                max_abs_delta=max_abs,
                min_signed_delta=min_signed,
                max_signed_delta=max_signed,
                radial_yz_max_abs_m=radial,
                x_max_abs_m=max_abs[0],
                expected_physical_role=expected_roles.get(selector),
                expected_radial_scale_m_per_weight=expected_scale,
                radial_scale_relative_error=relative_error,
                corroboration=corroboration,
            )
        )
    return tuple(result), identical


def _axle_evidence(axle: Any) -> AxleFormulaEvidence:
    width = float(axle.tire_width_mm)
    aspect = float(axle.tire_aspect_ratio)
    rim = float(axle.rim_diameter_in)
    if not all(math.isfinite(value) and value > 0.0 for value in (width, aspect, rim)):
        raise TireMorphFormulaEvidenceError("wheel specification contains invalid tire dimensions")
    sidewall = width * aspect / 100.0
    outer_radius = rim * 12.7 + sidewall
    weights, scale_x = tire_morph_weights(width, aspect, rim, rim)
    selector0_expected = (outer_radius - 225.0) / 275.0
    selector1_expected = (rim - 10.0) / 14.0
    if not math.isclose(weights[0], selector0_expected, rel_tol=0.0, abs_tol=1e-12):
        raise TireMorphFormulaEvidenceError("selector 0 algebraic decomposition is inconsistent")
    if not math.isclose(weights[1], selector1_expected, rel_tol=0.0, abs_tol=1e-12):
        raise TireMorphFormulaEvidenceError("selector 1 algebraic decomposition is inconsistent")
    return AxleFormulaEvidence(
        axle=str(axle.axle),
        tire_width_mm=width,
        tire_aspect_ratio=aspect,
        rim_diameter_in=rim,
        sidewall_height_mm=sidewall,
        outer_radius_mm=outer_radius,
        outer_diameter_mm=outer_radius * 2.0,
        selector0_outer_radius_weight=weights[0],
        selector1_rim_diameter_weight=weights[1],
        scale_x_width_m=scale_x,
    )


def _baseline_x_spans(geometry_report: Any | None) -> tuple[float, ...]:
    if geometry_report is None:
        return ()
    payload = _payload(geometry_report, "geometry_report")
    modelbins = payload.get("modelbins")
    if not isinstance(modelbins, Sequence) or isinstance(modelbins, (str, bytes)):
        raise TireMorphFormulaEvidenceError("geometry_report.modelbins is missing")
    spans: list[float] = []
    for model_index, modelbin in enumerate(modelbins):
        if not isinstance(modelbin, Mapping):
            raise TireMorphFormulaEvidenceError(f"geometry modelbins[{model_index}] is invalid")
        states = modelbin.get("states")
        if not isinstance(states, Mapping) or not isinstance(states.get("baseline"), Mapping):
            raise TireMorphFormulaEvidenceError("geometry report has no baseline state")
        baseline = states["baseline"]
        aabb = baseline.get("aabb")
        if not isinstance(aabb, Mapping):
            raise TireMorphFormulaEvidenceError("geometry baseline has no AABB")
        span = _vec3(aabb.get("span"), "geometry baseline AABB span")
        spans.append(span[0])
    return tuple(spans)


def build_tire_morph_formula_evidence(
    spec: VehicleWheelSpec,
    morph_profile: Any,
    geometry_report: Any | None = None,
) -> TireMorphFormulaEvidenceReport:
    """Compare Doliman's historical tire mapping with native FH6 geometry evidence.

    This report is diagnostic-only. It may corroborate individual selector roles and
    normalization scales, but it never enables the complete tire mapping for production.
    """
    if str(spec.mode).casefold() != "stock":
        raise TireMorphFormulaEvidenceError(
            "formula evidence currently requires a stock VehicleWheelSpec; "
            "effective upgrades need both original and effective dimensions"
        )

    selectors, identical = _selector_evidence(morph_profile)
    front = _axle_evidence(spec.front)
    rear = _axle_evidence(spec.rear)
    spans = _baseline_x_spans(geometry_report)
    if not spans:
        width_status = "not_evaluated"
    elif all(math.isfinite(span) and abs(span - 1.0) <= 0.02 for span in spans):
        width_status = "base_x_normalization_consistent"
    else:
        width_status = "base_x_normalization_not_corroborated"

    selector_status = {item.selector: item.corroboration for item in selectors}
    complete_status = "diagnostic_only_partial_corroboration"
    if selector_status.get(0) != "geometry_corroborated" or selector_status.get(1) != "geometry_corroborated":
        complete_status = "diagnostic_only_not_corroborated"

    return TireMorphFormulaEvidenceReport(
        car_id=int(spec.car_id),
        tire_model_name=spec.tire_model_name,
        wheel_spec_mode=str(spec.mode),
        historical_source_revision=_DOLIMAN_SOURCE_REVISION,
        historical_source_warning="Doliman source labels the tire mapping '# tire, not verified'.",
        production_mapping_enabled=False,
        left_right_morph_buffers_identical=identical,
        selector_evidence=selectors,
        front=front,
        rear=rear,
        baseline_x_spans=spans,
        width_scale_normalization_status=width_status,
        complete_mapping_status=complete_status,
        limitations=(
            "Selector 0/1 corroboration compares native morph-axis scale with the algebraic physical mapping only.",
            "Selectors 2..4 remain unlabeled production-wise even when an axis-role hint is reported.",
            "scale_x=tire_width_mm/1000 is not treated as verified unless base X normalization is independently consistent.",
            "No wheel spindle assembly, vehicle-specific correction, or game/save write is performed.",
        ),
    )
