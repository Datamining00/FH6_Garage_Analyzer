from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any

from .tire_morph_geometry import TireMorphGeometryError, bake_tire_morph_selectors


class TireMorphBoundaryRoleError(RuntimeError):
    """Raised when selector AABB evidence is insufficient for structural classification."""


@dataclass(frozen=True)
class AxisBoundaryDelta:
    minimum_delta: float
    maximum_delta: float
    span_delta: float
    center_delta: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class SelectorBoundaryRole:
    selector: int
    x: AxisBoundaryDelta
    y: AxisBoundaryDelta
    z: AxisBoundaryDelta
    radial_mean_span_delta: float
    radial_asymmetry: float
    x_boundary_bias: float
    geometric_role: str
    confidence: str
    production_semantics_assigned: bool

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["x"] = self.x.as_dict()
        data["y"] = self.y.as_dict()
        data["z"] = self.z.as_dict()
        return data


@dataclass(frozen=True)
class TireMorphBoundaryRoleReport:
    archive_path: str
    archive_sha256: str
    archive_read_only_unchanged: bool
    modelbin_roles: dict[str, tuple[SelectorBoundaryRole, ...]]
    left_right_role_match: bool | None
    production_mapping_enabled: bool
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "fh6_native_tire_selector_boundary_roles_v1",
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "archive_read_only_unchanged": self.archive_read_only_unchanged,
            "modelbin_roles": {
                key: [item.as_dict() for item in value]
                for key, value in self.modelbin_roles.items()
            },
            "left_right_role_match": self.left_right_role_match,
            "production_mapping_enabled": self.production_mapping_enabled,
            "limitations": list(self.limitations),
        }


def _finite_triplet(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise TireMorphBoundaryRoleError(f"{label} must contain exactly 3 values")
    result = tuple(float(v) for v in value)
    if not all(math.isfinite(v) for v in result):
        raise TireMorphBoundaryRoleError(f"{label} contains a non-finite value")
    return result


def _axis_delta(
    baseline_min: tuple[float, float, float],
    baseline_max: tuple[float, float, float],
    state_min: tuple[float, float, float],
    state_max: tuple[float, float, float],
    axis: int,
) -> AxisBoundaryDelta:
    min_delta = state_min[axis] - baseline_min[axis]
    max_delta = state_max[axis] - baseline_max[axis]
    span_delta = max_delta - min_delta
    center_delta = 0.5 * (max_delta + min_delta)
    return AxisBoundaryDelta(min_delta, max_delta, span_delta, center_delta)


def _classify(
    selector: int,
    x: AxisBoundaryDelta,
    y: AxisBoundaryDelta,
    z: AxisBoundaryDelta,
) -> tuple[str, str, float, float, float]:
    radial_mean = 0.5 * (y.span_delta + z.span_delta)
    radial_asymmetry = abs(y.span_delta - z.span_delta)
    x_boundary_bias = x.maximum_delta + x.minimum_delta

    eps = 1.0e-6
    x_abs = max(abs(x.minimum_delta), abs(x.maximum_delta), eps)
    radial_abs = max(abs(y.span_delta), abs(z.span_delta), eps)

    if (
        x.maximum_delta > 0.0
        and abs(x.minimum_delta) <= 0.15 * abs(x.maximum_delta)
        and radial_abs <= 0.10 * abs(x.maximum_delta)
    ):
        return "positive_x_boundary_expansion", "high", radial_mean, radial_asymmetry, x_boundary_bias
    if (
        x.minimum_delta < 0.0
        and abs(x.maximum_delta) <= 0.15 * abs(x.minimum_delta)
        and radial_abs <= 0.10 * abs(x.minimum_delta)
    ):
        return "negative_x_boundary_expansion", "high", radial_mean, radial_asymmetry, x_boundary_bias

    if radial_mean > 0.0 and abs(x.span_delta) <= 0.15 * abs(radial_mean):
        confidence = "high" if radial_asymmetry <= 0.05 * max(abs(radial_mean), eps) else "medium"
        return "radial_expansion_dominant", confidence, radial_mean, radial_asymmetry, x_boundary_bias

    if radial_mean < 0.0 and x.span_delta > 0.0:
        balance = min(abs(x.minimum_delta), abs(x.maximum_delta)) / x_abs
        confidence = "high" if balance >= 0.50 else "medium"
        return "mixed_x_expansion_radial_contraction", confidence, radial_mean, radial_asymmetry, x_boundary_bias

    return "mixed_or_unclassified", "low", radial_mean, radial_asymmetry, x_boundary_bias


def analyze_selector_state_boundaries(
    states: dict[str, dict[str, object]],
) -> tuple[SelectorBoundaryRole, ...]:
    baseline = states.get("baseline")
    if not isinstance(baseline, dict):
        raise TireMorphBoundaryRoleError("baseline state is missing")
    baseline_aabb = baseline.get("aabb")
    if not isinstance(baseline_aabb, dict):
        raise TireMorphBoundaryRoleError("baseline AABB is missing")
    baseline_min = _finite_triplet(baseline_aabb.get("minimum"), "baseline minimum")
    baseline_max = _finite_triplet(baseline_aabb.get("maximum"), "baseline maximum")

    result: list[SelectorBoundaryRole] = []
    for selector in range(5):
        state_name = f"selector{selector}"
        state = states.get(state_name)
        if not isinstance(state, dict):
            raise TireMorphBoundaryRoleError(f"{state_name} state is missing")
        aabb = state.get("aabb")
        if not isinstance(aabb, dict):
            raise TireMorphBoundaryRoleError(f"{state_name} AABB is missing")
        state_min = _finite_triplet(aabb.get("minimum"), f"{state_name} minimum")
        state_max = _finite_triplet(aabb.get("maximum"), f"{state_name} maximum")
        x = _axis_delta(baseline_min, baseline_max, state_min, state_max, 0)
        y = _axis_delta(baseline_min, baseline_max, state_min, state_max, 1)
        z = _axis_delta(baseline_min, baseline_max, state_min, state_max, 2)
        role, confidence, radial_mean, radial_asymmetry, x_bias = _classify(selector, x, y, z)
        result.append(
            SelectorBoundaryRole(
                selector=selector,
                x=x,
                y=y,
                z=z,
                radial_mean_span_delta=radial_mean,
                radial_asymmetry=radial_asymmetry,
                x_boundary_bias=x_bias,
                geometric_role=role,
                confidence=confidence,
                production_semantics_assigned=False,
            )
        )
    return tuple(result)


def analyze_native_tire_selector_boundary_roles(
    archive_path: str | Path,
) -> TireMorphBoundaryRoleReport:
    """Bake selector AABBs read-only, then classify only their geometric response."""
    archive = Path(archive_path).expanduser().resolve()
    try:
        bake = bake_tire_morph_selectors(archive, None, write_glb=False)
    except TireMorphGeometryError as exc:
        raise TireMorphBoundaryRoleError(str(exc)) from exc

    roles: dict[str, tuple[SelectorBoundaryRole, ...]] = {}
    for modelbin in bake.modelbins:
        roles[modelbin.entry] = analyze_selector_state_boundaries(modelbin.states)

    left_right_role_match: bool | None = None
    if len(roles) == 2:
        role_sets = list(roles.values())
        left_right_role_match = tuple(item.geometric_role for item in role_sets[0]) == tuple(
            item.geometric_role for item in role_sets[1]
        )

    return TireMorphBoundaryRoleReport(
        archive_path=str(archive),
        archive_sha256=bake.archive_sha256,
        archive_read_only_unchanged=bake.archive_read_only_unchanged,
        modelbin_roles=roles,
        left_right_role_match=left_right_role_match,
        production_mapping_enabled=False,
        limitations=(
            "Roles describe observed AABB boundary response only; they do not assign game-facing selector semantics.",
            "A single tire family is insufficient to promote selectors 2..4 into production mapping.",
            "Production tire assembly remains disabled.",
        ),
    )
