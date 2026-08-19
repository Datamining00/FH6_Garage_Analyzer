from __future__ import annotations

from typing import Any

from .livery_preview import LiveryPreviewError


def _color_alpha_is_zero(layer: dict[str, Any]) -> bool:
    color = layer.get("color")
    if not isinstance(color, (list, tuple)) or len(color) < 4:
        return False
    try:
        return float(color[3]) <= 0.0
    except (TypeError, ValueError):
        return False


def _is_mask(renderer, layer: dict[str, Any]) -> bool:
    data = list(layer.get("data") or [])
    flag = getattr(renderer, "_shape_mask_flag", None)
    if callable(flag):
        try:
            return bool(flag(layer, data))
        except Exception:
            pass
    return bool(layer.get("mask") or layer.get("is_mask") or layer.get("isMask"))


def validate_exact_assets_and_filter_noops(renderer, layers, raster_resolver):
    """Validate native assets while preserving FH6/KFPS cutout-mask semantics.

    A normal native mask is a geometry cutout. Its RGB/A color is not used by
    KFPS's non-gradient mask path, so a color alpha of zero does *not* make that
    mask a no-op. Removing those masks leaves large background shapes intact and
    can turn an otherwise correct section into an almost solid black silhouette.

    Gradient masks are different: their per-vertex opacity is rasterized through
    the layer color alpha, so a zero color alpha really is a no-op there.
    Raster-logo masks are also color-multiplied before their alpha is used.
    """
    visible: list[dict[str, Any]] = []
    invisible_count = 0

    resolve_resource = getattr(renderer, "_resolve_vinyl_resource", None)
    alpha_triangles_for = getattr(renderer, "_resource_alpha_triangles", None)
    shape_word_for = getattr(renderer, "_shape_word_from_shape", None)
    if not callable(resolve_resource) or not callable(alpha_triangles_for):
        raise LiveryPreviewError("native FH6 도형 검증 함수를 불러오지 못했습니다.")

    for layer_index, layer in enumerate(layers, 1):
        is_mask = _is_mask(renderer, layer)
        zero_color_alpha = _color_alpha_is_zero(layer)

        if bool(layer.get("is_raster_logo")):
            if raster_resolver is None:
                raise LiveryPreviewError(
                    f"layer {layer_index}의 FH6 내장 래스터 데칼 resolver가 없습니다."
                )
            try:
                raster_id = int(layer.get("raster_id"))
            except (TypeError, ValueError):
                raise LiveryPreviewError(
                    f"layer {layer_index}의 FH6 내장 래스터 데칼 ID가 올바르지 않습니다."
                )
            if raster_resolver(raster_id) is None:
                raise LiveryPreviewError(
                    f"layer {layer_index}의 FH6 내장 래스터 데칼 {raster_id}을 찾지 못했습니다."
                )
            # Raster decals are multiplied by the layer color before a mask uses
            # their alpha. Zero color alpha therefore genuinely contributes no cutout.
            if zero_color_alpha:
                invisible_count += 1
                continue
            visible.append(layer)
            continue

        try:
            type_code = int(layer.get("type", 0))
        except (TypeError, ValueError):
            type_code = 0
        resource = resolve_resource(type_code, layer)
        alpha_triangles = alpha_triangles_for(*resource) if resource else None
        if not alpha_triangles:
            if callable(shape_word_for):
                try:
                    word = int(shape_word_for(layer, type_code)) & 0xFFFF
                    identity = f"shape word 0x{word:04X}"
                except Exception:
                    identity = f"type {type_code}"
            else:
                identity = f"type {type_code}"
            if resource:
                identity = f"{resource[0]}/{resource[1]}"
            raise LiveryPreviewError(
                f"layer {layer_index}에 정확한 native FH6 도형 리소스가 없습니다: {identity}"
            )

        native_has_opacity = any(
            any(int(value) > 0 for value in alpha_values)
            for _triangle, alpha_values in alpha_triangles
        )
        if not native_has_opacity:
            invisible_count += 1
            continue

        has_vertex_alpha = any(
            any(int(value) != 255 for value in alpha_values)
            for _triangle, alpha_values in alpha_triangles
        )

        if not is_mask:
            if zero_color_alpha:
                invisible_count += 1
                continue
        else:
            # Opaque native cutout masks ignore layer color alpha. Gradient masks
            # use it, matching json_preview_renderer.render_typecode_layers_canvas.
            if has_vertex_alpha and zero_color_alpha:
                invisible_count += 1
                continue

        visible.append(layer)

    return visible, invisible_count
