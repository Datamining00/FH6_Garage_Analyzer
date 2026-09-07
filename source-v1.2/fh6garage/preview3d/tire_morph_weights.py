from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from .wheel_spec import AxleWheelSpec, VehicleWheelSpec

# Historical ForzaTech mapping from Doliman's importer. The source itself labels
# the tire mapping "not verified". Keep it diagnostic-only until selector roles
# and the physical-dimension formula are independently verified from geometry.
TIRE_MORPH_MAPPING_REVISION = "doliman_tire_weights_v1_unverified_diagnostic"


class TireMorphWeightError(ValueError):
    """Raised when tire morph weights cannot be derived without guessing."""


@dataclass(frozen=True)
class AxleTireMorphWeights:
    axle: str
    tire_width_mm: float
    tire_aspect_ratio: float
    original_rim_diameter_in: float
    rim_diameter_in: float
    selector_weights: tuple[float, float, float, float, float]
    scale_x: float
    mapping_revision: str = TIRE_MORPH_MAPPING_REVISION

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["selector_weights"] = list(self.selector_weights)
        return payload


@dataclass(frozen=True)
class VehicleTireMorphWeights:
    car_id: int
    wheel_spec_mode: str
    tire_model_name: str | None
    front: AxleTireMorphWeights
    rear: AxleTireMorphWeights
    mapping_revision: str = TIRE_MORPH_MAPPING_REVISION

    def as_dict(self) -> dict[str, Any]:
        return {
            "car_id": self.car_id,
            "wheel_spec_mode": self.wheel_spec_mode,
            "tire_model_name": self.tire_model_name,
            "mapping_revision": self.mapping_revision,
            "front": self.front.as_dict(),
            "rear": self.rear.as_dict(),
        }


def _finite_positive(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise TireMorphWeightError(f"{label} must be a finite positive number: {value!r}")
    return number


def tire_morph_weights(
    tire_width_mm: float,
    original_tire_aspect_ratio: float,
    original_rim_diameter_in: float,
    rim_diameter_in: float,
) -> tuple[tuple[float, float, float, float, float], float]:
    """Return Doliman's historical, explicitly unverified tire mapping.

    Source mapping (Doliman ForzaTech importer; source comment: "not verified"):
      selector 0 = (width_mm * original_aspect / 100 - 225
                    + original_rim_diameter_in * 12.7) / 275
      selector 1 = (rim_diameter_in - 10) / 14
      selectors 2..4 = 0
      scale_x = width_mm / 1000

    This function preserves the historical formula for diagnostic comparison only.
    Selector-controlled geometry characterization does not validate this physical
    formula, and this function does not enable production tire geometry by itself.
    """
    width = _finite_positive(tire_width_mm, "tire_width_mm")
    aspect = _finite_positive(original_tire_aspect_ratio, "original_tire_aspect_ratio")
    original_diameter = _finite_positive(
        original_rim_diameter_in, "original_rim_diameter_in"
    )
    diameter = _finite_positive(rim_diameter_in, "rim_diameter_in")
    selector_0 = (
        width * aspect / 100.0 - 225.0 + original_diameter * 12.7
    ) / 275.0
    selector_1 = (diameter - 10.0) / 14.0
    return ((selector_0, selector_1, 0.0, 0.0, 0.0), width / 1000.0)


def stock_axle_tire_morph_weights(spec: AxleWheelSpec) -> AxleTireMorphWeights:
    """Map a stock axle spec for diagnostic comparison only."""
    weights, scale_x = tire_morph_weights(
        spec.tire_width_mm,
        spec.tire_aspect_ratio,
        spec.rim_diameter_in,
        spec.rim_diameter_in,
    )
    return AxleTireMorphWeights(
        axle=str(spec.axle),
        tire_width_mm=float(spec.tire_width_mm),
        tire_aspect_ratio=float(spec.tire_aspect_ratio),
        original_rim_diameter_in=float(spec.rim_diameter_in),
        rim_diameter_in=float(spec.rim_diameter_in),
        selector_weights=weights,
        scale_x=scale_x,
    )


def stock_vehicle_tire_morph_weights(spec: VehicleWheelSpec) -> VehicleTireMorphWeights:
    """Build diagnostic stock tire weights only; upgraded/effective specs fail closed."""
    if str(spec.mode).casefold() != "stock":
        raise TireMorphWeightError(
            "stock tire morph mapping requires a stock VehicleWheelSpec; "
            f"got mode={spec.mode!r}"
        )
    return VehicleTireMorphWeights(
        car_id=int(spec.car_id),
        wheel_spec_mode=str(spec.mode),
        tire_model_name=spec.tire_model_name,
        front=stock_axle_tire_morph_weights(spec.front),
        rear=stock_axle_tire_morph_weights(spec.rear),
    )
