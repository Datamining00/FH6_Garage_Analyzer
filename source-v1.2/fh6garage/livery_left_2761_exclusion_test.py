from __future__ import annotations

from typing import Any, Callable

from . import livery_preview as core
from . import livery_preview_mask_semantics as mask_semantics
from . import livery_preview_quality_pipeline as quality_pipeline
from . import livery_preview_tiled_quality as tiled_quality


_PATCHED = False
_ORIGINAL_VALIDATOR: Callable | None = None

# Diagnostic-only signature isolated by the layer probe.  This is intentionally
# not a production rule: the test answers only whether this exact decoded layer
# is responsible for the visible occlusion.
_TARGET_SECTION = "Left"
_TARGET_SOURCE_OFFSET = 185644
_TARGET_TYPE = 1048677


def is_probe_target(layer: dict[str, Any]) -> bool:
    try:
        source_offset = int(layer.get("source_offset"))
    except (TypeError, ValueError):
        return False
    try:
        type_code = int(layer.get("type", 0))
    except (TypeError, ValueError):
        return False
    return (
        str(layer.get("source_section") or "") == _TARGET_SECTION
        and source_offset == _TARGET_SOURCE_OFFSET
        and type_code == _TARGET_TYPE
        and not bool(layer.get("mask"))
    )


def filter_probe_target(layers) -> tuple[list[dict[str, Any]], int]:
    kept: list[dict[str, Any]] = []
    removed = 0
    for layer in list(layers):
        if isinstance(layer, dict) and is_probe_target(layer):
            removed += 1
            continue
        kept.append(layer)
    return kept, removed


def _validator_without_probe_target(renderer: Any, layers, raster_resolver):
    original = _ORIGINAL_VALIDATOR
    if original is None:
        raise RuntimeError("Left occluder exclusion test validator is not installed")
    filtered, _removed = filter_probe_target(layers)
    return original(renderer, filtered, raster_resolver)


def install_left_2761_exclusion_test() -> None:
    global _PATCHED, _ORIGINAL_VALIDATOR
    if _PATCHED:
        return

    _ORIGINAL_VALIDATOR = core._validate_exact_assets_and_filter_noops

    # Patch every validator binding used by the current v1.4 render paths.  The
    # layer is removed before native rendering, while parser output and all other
    # placements remain untouched.
    core._validate_exact_assets_and_filter_noops = _validator_without_probe_target
    quality_pipeline._validate_exact_assets_and_filter_noops = _validator_without_probe_target
    mask_semantics.validate_exact_assets_and_filter_noops = _validator_without_probe_target
    tiled_quality.validate_exact_assets_and_filter_noops = _validator_without_probe_target

    # Force this comparison build to render fresh PNGs rather than reuse output
    # generated before the diagnostic exclusion was installed.
    try:
        core.clear_livery_preview_cache()
    except Exception:
        pass
    try:
        quality_pipeline.CACHE_VERSION = "v14-quality-left2761-exclusion-test"
        quality_pipeline.clear_quality_pipeline_cache()
    except Exception:
        pass
    try:
        tiled_quality.CACHE_VERSION = "v14-tiled-left2761-exclusion-test"
        tiled_quality.clear_tiled_quality_cache()
    except Exception:
        pass

    _PATCHED = True
