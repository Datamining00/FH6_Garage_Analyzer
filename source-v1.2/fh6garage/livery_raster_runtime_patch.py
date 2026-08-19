from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .exact_livery_preview import raster_resolver_for_game, require_fh6_game_folder
from .livery_preview import _decode_cached, _file_signature, _load_backend
from .livery_preview_mask_semantics import validate_exact_assets_and_filter_noops
from .livery_preview_raster_policy import (
    filter_missing_visible_rasters,
    preflight_raster_layers_fail_soft,
)


_APPLIED = False


def _prepare_layers(renderer, layers, raster_resolver):
    if raster_resolver is not None:
        preflight_raster_layers_fail_soft(renderer, layers, raster_resolver)
        filtered, missing = filter_missing_visible_rasters(renderer, layers, raster_resolver)
    else:
        filtered, missing = list(layers), ()
    prepared, invisible = validate_exact_assets_and_filter_noops(
        renderer,
        filtered,
        raster_resolver,
    )
    return prepared, invisible, tuple(dict.fromkeys(int(value) for value in missing))


def _missing_visible_rasters_for(path: Path | str, section: str):
    source = Path(path)
    signature = _file_signature(source)
    decoded = _decode_cached(*signature)
    layers = list(decoded.sections.get(str(section), ()))
    if not any(bool(layer.get("is_raster_logo")) for layer in layers):
        return ()
    game_folder = require_fh6_game_folder()
    resolver = raster_resolver_for_game(game_folder)
    _decoder, renderer = _load_backend()
    preflight_raster_layers_fail_soft(renderer, layers, resolver)
    _kept, missing = filter_missing_visible_rasters(renderer, layers, resolver)
    return tuple(dict.fromkeys(int(value) for value in missing))


def _warning_for_missing(ids) -> str:
    shown = ", ".join(str(value) for value in ids[:8])
    if len(ids) > 8:
        shown += f" 외 {len(ids) - 8}개"
    return (
        f"FH6 설치의 Decals.zip에 없는 일반 raster decal {len(ids)}개를 건너뛰었습니다"
        + (f" (ID: {shown})" if shown else "")
        + ". raster mask 누락은 정확도 보호를 위해 계속 오류 처리합니다."
    )


def apply_livery_raster_runtime_patch() -> None:
    """Apply one raster fail-soft policy to the 1x-16x production preview paths."""
    global _APPLIED
    if _APPLIED:
        return

    from . import livery_preview_quality_pipeline as quality
    from . import livery_preview_tiled_quality as tiled

    def preflight_for_module(layers, resolver):
        _decoder, renderer = _load_backend()
        return preflight_raster_layers_fail_soft(renderer, layers, resolver)

    def validate_for_module(renderer, layers, resolver):
        prepared, invisible, _missing = _prepare_layers(renderer, layers, resolver)
        return prepared, invisible

    # These helpers are looked up as module globals when cached render functions
    # execute, so rebinding them updates both existing full-canvas and tiled code
    # without forking the render math.
    quality._preflight_raster_layers = preflight_for_module
    quality._validate_exact_assets_and_filter_noops = validate_for_module
    tiled._preflight_raster_layers = preflight_for_module
    tiled.validate_exact_assets_and_filter_noops = validate_for_module

    original_quality_public = quality.render_livery_section_quality_pipeline
    original_scaled_public = tiled.render_livery_section_scaled

    def quality_public(path, section: str, quality_name=quality.DEFAULT_QUALITY, *, sharpen: bool = False):
        missing = _missing_visible_rasters_for(path, section)
        result = original_quality_public(path, section, quality_name, sharpen=sharpen)
        if not missing:
            return result
        return replace(
            result,
            skipped_raster_logos=len(missing),
            warnings=tuple(dict.fromkeys((*result.warnings, _warning_for_missing(missing)))),
        )

    def scaled_public(path, section: str, scale: int = 4):
        missing = _missing_visible_rasters_for(path, section)
        result = original_scaled_public(path, section, scale)
        if not missing:
            return result
        return replace(
            result,
            skipped_raster_logos=len(missing),
            warnings=tuple(dict.fromkeys((*result.warnings, _warning_for_missing(missing)))),
        )

    quality.render_livery_section_quality_pipeline = quality_public
    # tiled imported the quality function directly; keep its <=4x delegation on
    # the wrapped public path so warnings are preserved there as well.
    tiled.render_livery_section_quality_pipeline = quality_public
    tiled.render_livery_section_scaled = scaled_public
    _APPLIED = True
