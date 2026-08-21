from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path

from .fh6_clivery.render_adapter import (
    IndependentRenderAdapterError,
    decode_clivery_renderer_scene,
)


_APPLIED = False
_PATCH_FLAG = "_fh6assistant_independent_render_bridge_v1"
_FALLBACK_PREFIX = "FH6 independent render bridge unavailable:"


def _decode_with_independent_bridge(
    path_text: str,
    file_size: int,
    mtime_ns: int,
    *,
    legacy_decode,
    preview_type,
):
    """Prefer exact independent vector semantics and fail safely to legacy decoding."""

    source = Path(path_text)
    try:
        independent = decode_clivery_renderer_scene(source)
    except IndependentRenderAdapterError as exc:
        legacy = legacy_decode(path_text, file_size, mtime_ns)
        warning = f"{_FALLBACK_PREFIX} {exc}; using pinned legacy preview decoder."
        return preview_type(
            sections=legacy.sections,
            warnings=tuple(dict.fromkeys([*legacy.warnings, warning])),
            total_layers=legacy.total_layers,
            raster_logo_count=legacy.raster_logo_count,
        )

    return preview_type(
        sections=independent.sections,
        warnings=(),
        total_layers=independent.total_layers,
        raster_logo_count=0,
    )


def _patch_decode_references(replacement, original) -> None:
    """Replace cached decoder references already imported by render pipeline modules."""

    module_names = (
        "fh6garage.livery_preview_preview2",
        "fh6garage.livery_preview_quality_pipeline",
        "fh6garage.livery_preview_tiled_quality",
    )
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        current = getattr(module, "_decode_cached", None)
        if current is original or current is not replacement:
            setattr(module, "_decode_cached", replacement)


def _bump_render_cache_revision() -> None:
    """Prevent old parser-generated PNGs from surviving the decoder handoff."""

    try:
        preview2 = importlib.import_module("fh6garage.livery_preview_preview2")
        preview2.PREVIEW2_CACHE_VERSION = "v14-render-rules-r3-independent-render-bridge"
        clear = getattr(preview2, "clear_preview2_cache", None)
        if callable(clear):
            clear()
    except Exception:
        pass

    try:
        quality = importlib.import_module("fh6garage.livery_preview_quality_pipeline")
        quality.CACHE_VERSION = "v14-quality-pipeline-r3-independent-render-bridge"
        clear = getattr(quality, "clear_quality_pipeline_cache", None)
        if callable(clear):
            clear()
    except Exception:
        pass

    try:
        tiled = importlib.import_module("fh6garage.livery_preview_tiled_quality")
        tiled.CACHE_VERSION = "v14-tiled-quality-r4-independent-render-bridge"
        clear = getattr(tiled, "clear_tiled_quality_cache", None)
        if callable(clear):
            clear()
    except Exception:
        pass


def apply_livery_independent_render_bridge_patch() -> None:
    """Connect the independent exact vector scene to the existing native renderer.

    The renderer, FH6 native shape resources, vehicle projection masks, and UI
    remain unchanged. Only the source of renderer placement dictionaries changes
    when the independent decoder can prove a complete vector-only scene. Raster
    or unresolved semantics explicitly fall back to the pinned legacy decoder.
    """

    global _APPLIED
    if _APPLIED:
        return

    from . import livery_preview as preview

    if bool(getattr(preview, _PATCH_FLAG, False)):
        _APPLIED = True
        return

    original = preview._decode_cached

    @lru_cache(maxsize=16)
    def decode_cached_independent(path_text: str, file_size: int, mtime_ns: int):
        return _decode_with_independent_bridge(
            path_text,
            file_size,
            mtime_ns,
            legacy_decode=original,
            preview_type=preview.DecodedLiveryPreview,
        )

    preview._decode_cached = decode_cached_independent
    _patch_decode_references(decode_cached_independent, original)
    setattr(preview, _PATCH_FLAG, True)
    _bump_render_cache_revision()

    try:
        preview.clear_livery_preview_cache()
    except Exception:
        decode_cached_independent.cache_clear()

    _APPLIED = True
