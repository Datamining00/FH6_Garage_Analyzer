from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from .wheel_spec import AxleWheelSpec, VehicleWheelSpec

RIM_MORPH_MAPPING_REVISION = "doliman_rim_weights_v1"


class WheelMorphWeightError(ValueError):
    """Raised when a wheel specification cannot be mapped without guessing."""


@dataclass(frozen=True)
class AxleRimMorphWeights:
    axle: str
    rim_diameter_in: float
    tire_width_mm: float
    diameter_weight: float
    width_weight: float
    scale_x: float = 1.0
    mapping_revision: str = RIM_MORPH_MAPPING_REVISION

    @property
    def weights(self) -> tuple[float, float]:
        return (self.diameter_weight, self.width_weight)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["weights"] = list(self.weights)
        return payload


@dataclass(frozen=True)
class VehicleRimMorphWeights:
    car_id: int
    wheel_spec_mode: str
    front: AxleRimMorphWeights
    rear: AxleRimMorphWeights
    mapping_revision: str = RIM_MORPH_MAPPING_REVISION

    def as_dict(self) -> dict[str, Any]:
        return {
            "car_id": self.car_id,
            "wheel_spec_mode": self.wheel_spec_mode,
            "mapping_revision": self.mapping_revision,
            "front": self.front.as_dict(),
            "rear": self.rear.as_dict(),
        }


def _finite_positive(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise WheelMorphWeightError(f"{label} must be a finite positive number: {value!r}")
    return number


def rim_morph_weights(rim_diameter_in: float, tire_width_mm: float) -> tuple[float, float]:
    """Return the two rim morph weights used by Doliman's ForzaTech importer.

    The mapping is intentionally not clamped.  Extrapolation, if present in real
    game data, must remain visible to diagnostics rather than being hidden by a
    heuristic correction.

    Source mapping:
      diameter = (wheel_diameter_in - 10) / 14
      width    = (1 - tire_width_mm / 1000) / 0.9
    """
    diameter = _finite_positive(rim_diameter_in, "rim_diameter_in")
    width_mm = _finite_positive(tire_width_mm, "tire_width_mm")
    return (
        (diameter - 10.0) / 14.0,
        (1.0 - width_mm / 1000.0) / 0.9,
    )


def axle_rim_morph_weights(spec: AxleWheelSpec) -> AxleRimMorphWeights:
    diameter_weight, width_weight = rim_morph_weights(
        spec.rim_diameter_in,
        spec.tire_width_mm,
    )
    return AxleRimMorphWeights(
        axle=str(spec.axle),
        rim_diameter_in=float(spec.rim_diameter_in),
        tire_width_mm=float(spec.tire_width_mm),
        diameter_weight=diameter_weight,
        width_weight=width_weight,
        scale_x=1.0,
    )


def vehicle_rim_morph_weights(spec: VehicleWheelSpec) -> VehicleRimMorphWeights:
    return VehicleRimMorphWeights(
        car_id=int(spec.car_id),
        wheel_spec_mode=str(spec.mode),
        front=axle_rim_morph_weights(spec.front),
        rear=axle_rim_morph_weights(spec.rear),
    )
