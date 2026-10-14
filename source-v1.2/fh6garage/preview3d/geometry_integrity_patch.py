from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
from typing import Any, Sequence


GEOMETRY_INTEGRITY_PATCH_REVISION = "geometry_integrity_global_v1"
_PATCH_MARKER = "_fh6_geometry_integrity_patch_installed"

# These are viewer-side heuristics from the earlier neutral-scene cleanup pass.
# They are not strong enough evidence that the underlying geometry is disposable:
# control arms, dampers, anti-roll bars, shafts, links, exhaust pipes and similar
# physical parts can legitimately satisfy them.  Preserve those meshes globally.
_UNSAFE_HIDE_REASONS = frozenset(
    {
        "wheel_dependent_support_part_type",
        "wheel_dependent_support_assembly",
        "extreme_thin_auxiliary_geometry",
    }
)


def _install_centered_native_tire_normalization() -> None:
    from . import tire_production_trial_geometry as module

    original = module._normalize_positions_to_stock_dimensions
    if bool(getattr(original, _PATCH_MARKER, False)):
        return

    def centered_normalize_positions_to_stock_dimensions(
        positions: Sequence[Sequence[float]],
        axle_spec: Any,
    ) -> tuple[
        tuple[tuple[float, float, float], ...],
        tuple[float, float, float],
        dict[str, object],
        dict[str, object],
    ]:
        """Normalize stock tire size around spindle-local origin.

        The previous implementation scaled around the source AABB center but kept
        that source center as a translation.  Native tire modelbins are not
        guaranteed to have their AABB centered at (0, 0, 0), so applying the
        WheelStyle spindle matrix afterwards could place an otherwise correctly
        sized tire beside the rim.  The source center is geometry-derived here and
        is subtracted before scaling; no vehicle-specific offset is introduced.
        """
        try:
            before = module._aabb(positions)
        except module.TireMorphGeometryError as exc:
            raise module.TireProductionTrialGeometryError(str(exc)) from exc

        target_width = float(axle_spec.tire_width_mm) / 1000.0
        target_outer = float(axle_spec.tire_outer_diameter_mm) / 1000.0
        spans = tuple(float(value) for value in before.span)
        if not all(math.isfinite(value) and value > 1.0e-9 for value in spans):
            raise module.TireProductionTrialGeometryError(
                f"{axle_spec.axle}: decoded tire geometry has invalid span {spans!r}"
            )
        if not all(
            math.isfinite(value) and value > 0.0
            for value in (target_width, target_outer)
        ):
            raise module.TireProductionTrialGeometryError(
                f"{axle_spec.axle}: stock tire target dimensions are invalid"
            )

        sx = target_width / spans[0]
        sy = target_outer / spans[1]
        sz = target_outer / spans[2]
        scales = (sx, sy, sz)
        if not all(math.isfinite(value) and value > 0.0 for value in scales):
            raise module.TireProductionTrialGeometryError(
                f"{axle_spec.axle}: automatic tire normalization produced invalid scale {scales!r}"
            )

        cx, cy, cz = (float(value) for value in before.center)
        normalized = tuple(
            (
                (float(point[0]) - cx) * sx,
                (float(point[1]) - cy) * sy,
                (float(point[2]) - cz) * sz,
            )
            for point in positions
        )
        try:
            after = module._aabb(normalized)
        except module.TireMorphGeometryError as exc:
            raise module.TireProductionTrialGeometryError(str(exc)) from exc

        center = tuple(float(value) for value in after.center)
        if any(abs(value) > 1.0e-6 for value in center):
            raise module.TireProductionTrialGeometryError(
                f"{axle_spec.axle}: spindle-local tire normalization did not center geometry: {center!r}"
            )
        return normalized, scales, before.as_dict(), after.as_dict()

    setattr(centered_normalize_positions_to_stock_dimensions, _PATCH_MARKER, True)
    module._normalize_positions_to_stock_dimensions = centered_normalize_positions_to_stock_dimensions


def _install_mechanical_geometry_preservation() -> None:
    from . import neutral_geometry as module

    original = module.annotate_neutral_geometry
    if bool(getattr(original, _PATCH_MARKER, False)):
        return

    def annotate_preserving_mechanical_geometry(
        glb_path: str | Path,
        converter_archive: str | Path,
        carbin_entry: str,
    ) -> Any:
        """Keep physical support/thin geometry visible after neutral annotation.

        Presentation-only draw groups and validated shadow-only passes remain
        eligible for A cleanup.  Only the unsafe B heuristics are reversed.
        Binary geometry and FH6 source archives remain untouched.
        """
        result = original(glb_path, converter_archive, carbin_entry)
        glb = Path(glb_path)
        document, chunks = module._read_glb(glb)
        meshes = document.get("meshes")
        if not isinstance(meshes, list):
            return result

        changed = False
        final_ab_hidden = 0
        for mesh in meshes:
            if not isinstance(mesh, dict):
                continue
            extras = mesh.get("extras")
            if not isinstance(extras, dict):
                continue
            raw_reasons = extras.get("kfps_neutral_ab_reasons")
            reasons = [str(item) for item in raw_reasons] if isinstance(raw_reasons, list) else []
            removed = [reason for reason in reasons if reason in _UNSAFE_HIDE_REASONS]
            if removed:
                kept = [reason for reason in reasons if reason not in _UNSAFE_HIDE_REASONS]
                extras["kfps_neutral_ab_reasons"] = kept
                extras["kfps_neutral_ab_hidden"] = bool(kept)
                extras["kfps_geometry_integrity_restored_reasons"] = sorted(set(removed))
                extras["kfps_geometry_integrity_patch_revision"] = GEOMETRY_INTEGRITY_PATCH_REVISION
                changed = True
            if bool(extras.get("kfps_neutral_ab_hidden", False)):
                final_ab_hidden += 1

        if changed:
            module._write_glb(glb, document, chunks)

        # Keep the result counters consistent with the actual post-patch GLB.
        # Pass B is deliberately disabled; Pass A presentation/shadow cleanup is retained.
        return replace(
            result,
            ab_hidden_meshes=final_ab_hidden,
            b_support_hidden_meshes=0,
            extreme_thin_hidden_meshes=0,
        )

    setattr(annotate_preserving_mechanical_geometry, _PATCH_MARKER, True)
    module.annotate_neutral_geometry = annotate_preserving_mechanical_geometry

    original_as_dict = module.NeutralGeometryResult.as_dict
    if not bool(getattr(original_as_dict, _PATCH_MARKER, False)):
        def preserved_as_dict(self: Any) -> dict:
            payload = original_as_dict(self)
            policy = dict(payload.get("policy") or {})
            policy["B"] = (
                "preserve suspension, axle/support and other mechanical geometry; "
                "do not hide by support part type or assembly"
            )
            policy["thin_geometry"] = (
                "preserve thin physical geometry; AABB thinness alone is not a visibility rule"
            )
            policy["geometry_integrity_patch_revision"] = GEOMETRY_INTEGRITY_PATCH_REVISION
            payload["policy"] = policy
            return payload

        setattr(preserved_as_dict, _PATCH_MARKER, True)
        module.NeutralGeometryResult.as_dict = preserved_as_dict


def install_geometry_integrity_patch() -> bool:
    """Install global FHA 3D geometry integrity rules once per process."""
    from . import neutral_geometry as neutral_module

    if bool(getattr(neutral_module, _PATCH_MARKER, False)):
        return False
    _install_centered_native_tire_normalization()
    _install_mechanical_geometry_preservation()
    setattr(neutral_module, _PATCH_MARKER, True)
    return True
