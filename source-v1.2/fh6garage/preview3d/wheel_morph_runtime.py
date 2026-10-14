from __future__ import annotations

import math
from typing import Any, Mapping

from .wheel_morph_weights import VehicleRimMorphWeights

WHEEL_MORPH_RUNTIME_REVISION = "verified_rim_combined_v1"


class WheelMorphRuntimeContractError(ValueError):
    """Raised when verified rim morph execution cannot be proven safely."""


def wheel_morph_environment(
    car_id: int,
    weights: VehicleRimMorphWeights | None,
) -> dict[str, str]:
    """Return KFPS environment values for a verified combined rim morph.

    No environment values are emitted when morphing is not requested, preserving
    the existing converter path exactly. The caller must use a morph-capable
    helper whenever a non-empty result is returned.
    """
    if weights is None:
        return {}
    if int(weights.car_id) != int(car_id):
        raise WheelMorphRuntimeContractError(
            f"rim morph Car ID {weights.car_id} does not match selected Car ID {car_id}"
        )

    values = {
        "KFPS_WHEEL_MORPH_FRONT_DIAMETER": weights.front.diameter_weight,
        "KFPS_WHEEL_MORPH_FRONT_WIDTH": weights.front.width_weight,
        "KFPS_WHEEL_MORPH_REAR_DIAMETER": weights.rear.diameter_weight,
        "KFPS_WHEEL_MORPH_REAR_WIDTH": weights.rear.width_weight,
    }
    for name, value in values.items():
        number = float(value)
        if not math.isfinite(number):
            raise WheelMorphRuntimeContractError(f"{name} must be finite: {value!r}")

    return {
        "KFPS_WHEEL_MORPH_MODE": "combined",
        **{name: format(float(value), ".17g") for name, value in values.items()},
    }


def validate_wheel_morph_diagnostics(
    car_id: int,
    weights: VehicleRimMorphWeights | None,
    diagnostics: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Fail closed unless the helper proves that requested rim morphs ran."""
    if weights is None:
        return None
    # Reuse the same Car ID/finite-weight validation used before process launch.
    wheel_morph_environment(car_id, weights)

    if not isinstance(diagnostics, Mapping):
        raise WheelMorphRuntimeContractError("converter returned no diagnostic object")
    mode = str(diagnostics.get("wheel_morph_mode") or "").casefold()
    if mode != "combined":
        raise WheelMorphRuntimeContractError(
            "converter did not prove combined rim morph support: "
            f"wheel_morph_mode={mode!r}"
        )

    applied_meshes = diagnostics.get("wheel_morph_applied_meshes")
    applied_vertices = diagnostics.get("wheel_morph_applied_vertices")
    if not isinstance(applied_meshes, int) or isinstance(applied_meshes, bool) or applied_meshes <= 0:
        raise WheelMorphRuntimeContractError(
            f"combined rim morph applied no verified meshes: {applied_meshes!r}"
        )
    if not isinstance(applied_vertices, int) or isinstance(applied_vertices, bool) or applied_vertices <= 0:
        raise WheelMorphRuntimeContractError(
            f"combined rim morph applied no verified vertices: {applied_vertices!r}"
        )

    split = diagnostics.get("wheel_morph_axle_split_z")
    if split is not None:
        try:
            split_value = float(split)
        except (TypeError, ValueError) as exc:
            raise WheelMorphRuntimeContractError(
                f"wheel morph axle split is not numeric: {split!r}"
            ) from exc
        if not math.isfinite(split_value):
            raise WheelMorphRuntimeContractError(
                f"wheel morph axle split is not finite: {split!r}"
            )
    else:
        split_value = None

    return {
        "status": "applied",
        "revision": WHEEL_MORPH_RUNTIME_REVISION,
        "mapping_revision": weights.mapping_revision,
        "weights": weights.as_dict(),
        "applied_meshes": applied_meshes,
        "applied_vertices": applied_vertices,
        "axle_split_z": split_value,
    }
