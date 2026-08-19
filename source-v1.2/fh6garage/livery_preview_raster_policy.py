from __future__ import annotations

from typing import Any

from .livery_preview import LiveryPreviewError


def _is_mask(renderer, layer: dict[str, Any]) -> bool:
    data = list(layer.get("data") or [])
    flag = getattr(renderer, "_shape_mask_flag", None)
    if callable(flag):
        try:
            return bool(flag(layer, data))
        except Exception:
            pass
    return bool(layer.get("mask") or layer.get("is_mask") or layer.get("isMask"))


def preflight_raster_layers_fail_soft(renderer, layers, raster_resolver) -> None:
    """Require raster masks, but let missing visible raster decals be skipped later.

    A missing visible built-in decal affects only that decal. A missing raster mask
    changes cutout semantics for subsequent artwork, so exact reconstruction must
    still fail closed for masks.
    """
    for layer_index, layer in enumerate(layers, 1):
        if not bool(layer.get("is_raster_logo")):
            continue
        try:
            raster_id = int(layer.get("raster_id"))
        except (TypeError, ValueError):
            raise LiveryPreviewError(
                f"layer {layer_index}의 FH6 내장 래스터 데칼 ID가 올바르지 않습니다."
            )
        if raster_resolver(raster_id) is not None:
            continue
        if not _is_mask(renderer, layer):
            continue
        detail = ""
        describe = getattr(raster_resolver, "missing_description", None)
        if callable(describe):
            try:
                detail = str(describe(raster_id)).strip()
            except Exception:
                detail = ""
        suffix = f" {detail}" if detail else ""
        raise LiveryPreviewError(
            f"layer {layer_index}의 raster mask {raster_id}을 찾지 못해 정확한 cutout을 재구성할 수 없습니다.{suffix}"
        )


def filter_missing_visible_rasters(renderer, layers, raster_resolver):
    """Drop only unavailable non-mask raster decals and return their IDs."""
    kept = []
    missing: list[int] = []
    for layer in layers:
        if not bool(layer.get("is_raster_logo")):
            kept.append(layer)
            continue
        try:
            raster_id = int(layer.get("raster_id"))
        except (TypeError, ValueError):
            kept.append(layer)
            continue
        if raster_resolver is not None and raster_resolver(raster_id) is not None:
            kept.append(layer)
            continue
        if _is_mask(renderer, layer):
            kept.append(layer)
            continue
        missing.append(raster_id)
    return kept, tuple(missing)
