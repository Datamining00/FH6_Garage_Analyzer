from __future__ import annotations

import sys
from dataclasses import replace
from typing import Any

import numpy as np

from .livery_recovery_diagnostic import classify_strict_recovery_candidate


def apply_hybrid_recovery_to_scene(scene: Any) -> Any:
    """Recover only high-confidence Strict false negatives on authored exterior shell.

    Hybrid is intentionally a narrow superset of Strict.  The strict scene is
    calculated first, then only primitives classified as verified exterior shell
    with real UV/mask evidence are promoted.  Lights, handles, antennas, badges,
    wheels, brakes, interior geometry, and unclassified exterior remain excluded.
    """
    allowed = np.array(scene.allowed_sides, copy=True)
    projection = np.array(scene.projection_sides, copy=True)
    direct = np.array(scene.direct_uv, copy=True)
    diagnostics: list[dict[str, Any]] = []

    index_cursor = 0
    recovered = 0
    selected_counts = dict(getattr(scene, "selected_uv_channel_counts", {}) or {})
    selected_channel = int(getattr(scene, "livery_uv_channel", 3))

    for original_item in tuple(getattr(scene, "primitive_diagnostics", ()) or ()):
        item = dict(original_item)
        triangle_count = max(0, int(item.get("triangle_count") or 0))
        index_count = triangle_count * 3
        end = min(index_cursor + index_count, len(scene.indices))
        primitive_indices = np.asarray(scene.indices[index_cursor:end], dtype=np.int64)
        index_cursor = end

        decision = classify_strict_recovery_candidate(item)
        evidence_mask = int(decision.get("evidence_mask") or 0)
        selected_uv_available = bool(item.get("has_selected_uv", False))

        if (
            bool(decision.get("safe_candidate_for_review"))
            and evidence_mask
            and selected_uv_available
            and primitive_indices.size
        ):
            vertices = np.unique(primitive_indices)
            vertices = vertices[(vertices >= 0) & (vertices < len(allowed))]
            if vertices.size:
                allowed[vertices, 0] = float(evidence_mask)
                projection[vertices, 0] = 0.0
                direct[vertices, 0] = 1.0
                recovered += 1
                selected_counts[selected_channel] = selected_counts.get(selected_channel, 0) + 1
                item["final_allowed_sides"] = evidence_mask
                item["final_projection_sides"] = 0
                item["direct_uv"] = True
                item["selected_uv_channel"] = selected_channel
                item["inference_action"] = "hybrid_recovered_exterior_shell"
                item["livery_recovery_applied"] = True
            else:
                item["livery_recovery_applied"] = False
        else:
            item["livery_recovery_applied"] = False

        item["livery_recovery_class"] = decision.get("recovery_class")
        item["livery_recovery_review_reason"] = decision.get("review_reason")
        diagnostics.append(item)

    return replace(
        scene,
        allowed_sides=np.ascontiguousarray(allowed, dtype=np.float32),
        projection_sides=np.ascontiguousarray(projection, dtype=np.float32),
        direct_uv=np.ascontiguousarray(direct, dtype=np.float32),
        primitive_diagnostics=tuple(diagnostics),
        livery_eligibility_policy="hybrid",
        uv3_meshes=int(getattr(scene, "uv3_meshes", 0)) + recovered,
        promoted_livery_meshes=int(getattr(scene, "promoted_livery_meshes", 0)) + recovered,
        selected_uv_channel_counts=dict(sorted(selected_counts.items())),
    )


def install_hybrid_livery_recovery_patch() -> bool:
    """Expose Hybrid without changing the underlying Legacy/Strict parser contract."""
    from . import glb_parser

    if getattr(glb_parser, "_fh6_hybrid_livery_recovery_patched", False):
        return False

    original = glb_parser.load_kfps_glb

    def wrapped(path, *args, **kwargs):
        requested = str(kwargs.get("livery_eligibility") or "legacy").strip().casefold()
        if requested != "hybrid":
            return original(path, *args, **kwargs)

        strict_kwargs = dict(kwargs)
        strict_kwargs["livery_eligibility"] = "strict"
        strict_scene = original(path, *args, **strict_kwargs)
        return apply_hybrid_recovery_to_scene(strict_scene)

    glb_parser.load_kfps_glb = wrapped
    glb_parser._fh6_hybrid_livery_recovery_patched = True

    integration = sys.modules.get(f"{__package__}.integration")
    if integration is not None and getattr(integration, "load_kfps_glb", None) is original:
        integration.load_kfps_glb = wrapped
    return True
