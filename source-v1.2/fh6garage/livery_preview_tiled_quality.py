from __future__ import annotations

import hashlib
import io
import math
import threading
from functools import lru_cache
from pathlib import Path

from .exact_livery_preview import (
    ExactLiveryPreviewError,
    _projection_record,
    raster_resolver_for_game,
    require_fh6_game_folder,
)
from .livery_analysis import LiveryAnalysisError
from .livery_preview import (
    KFPS_VENDOR_COMMIT,
    LiveryPreviewError,
    RenderedLiverySection,
    _analysis_cached,
    _decode_cached,
    _file_signature,
    _load_backend,
)
from .livery_preview_mask_semantics import validate_exact_assets_and_filter_noops
from .livery_preview_native_resolution_test import _checkerboard_native_resolution
from .livery_preview_preview2 import _app_data_dir, _preflight_raster_layers, _read_disk_cache, _write_disk_cache
from .livery_preview_quality_pipeline import (
    RenderConfig,
    _aa_polygon_mask,
    _detail_sample_count,
    _premultiply_u8,
    _vertex_alpha_float_layer,
    render_livery_section_quality_pipeline,
)

CACHE_VERSION = "v14-tiled-quality-r2"
SUPPORTED_SCALES = (1, 2, 4, 8, 16)
RETAINED_SCALE_LIMIT = 4
TILE_SIZE = 4096
_CACHE_LOCK = threading.RLock()


def normalize_scale(value) -> int:
    try:
        scale = int(value)
    except (TypeError, ValueError):
        scale = 4
    return scale if scale in SUPPORTED_SCALES else 4


def _quality_for_scale(scale: int) -> str:
    return {1: "fast", 2: "balanced", 4: "high"}[int(scale)]


def _cache_path(path_text: str, file_size: int, mtime_ns: int, section: str, game_folder_text: str, scale: int) -> Path:
    payload = "|".join(
        (
            CACHE_VERSION,
            KFPS_VENDOR_COMMIT,
            str(Path(path_text).resolve()),
            str(int(file_size)),
            str(int(mtime_ns)),
            str(section),
            str(Path(game_folder_text).resolve()),
            f"scale{int(scale)}",
            "exact-no-sharpen",
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8", errors="surrogatepass")).hexdigest()
    return _app_data_dir() / "livery_preview_cache" / CACHE_VERSION / f"{digest}.png"


def _global_polygon_bounds(polygons, full_width: int, full_height: int):
    xs = [point[0] for polygon in polygons for point in polygon]
    ys = [point[1] for polygon in polygons for point in polygon]
    if not xs or not ys:
        return None
    left = max(0, math.floor(min(xs)) - 5)
    top = max(0, math.floor(min(ys)) - 5)
    right = min(full_width, math.ceil(max(xs)) + 6)
    bottom = min(full_height, math.ceil(max(ys)) + 6)
    return (left, top, right, bottom) if right > left and bottom > top else None


def _intersect(a, b):
    left = max(int(a[0]), int(b[0]))
    top = max(int(a[1]), int(b[1]))
    right = min(int(a[2]), int(b[2]))
    bottom = min(int(a[3]), int(b[3]))
    return (left, top, right, bottom) if right > left and bottom > top else None


def _render_raster_region(renderer, source, data, color, *, full_size, region):
    from PIL import Image, ImageChops

    source = source.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    color = color or (255, 255, 255, 255)
    if color != (255, 255, 255, 255):
        source = ImageChops.multiply(source, Image.new("RGBA", source.size, color))
    source_width, source_height = source.size
    full_width, full_height = full_size
    min_x, min_y, max_x, max_y = (-1024.0, -512.0, 1024.0, 512.0)

    def source_to_canvas(u: float, v: float):
        local_x = u - source_width / 2.0
        local_y = source_height / 2.0 - v
        world = renderer._transform_resource_polygon([(local_x, local_y)], data)[0]
        return (
            (world[0] - min_x) * full_width / (max_x - min_x),
            (max_y - world[1]) * full_height / (max_y - min_y),
        )

    origin = source_to_canvas(0.0, 0.0)
    x_axis = source_to_canvas(1.0, 0.0)
    y_axis = source_to_canvas(0.0, 1.0)
    a, d = x_axis[0] - origin[0], x_axis[1] - origin[1]
    b, e = y_axis[0] - origin[0], y_axis[1] - origin[1]
    c, f = origin
    determinant = a * e - b * d
    if abs(determinant) < 1.0e-12:
        return None
    inverse = (
        e / determinant,
        -b / determinant,
        (b * f - e * c) / determinant,
        -d / determinant,
        a / determinant,
        (d * c - a * f) / determinant,
    )
    rx0, ry0, rx1, ry1 = region
    adjusted = (
        inverse[0],
        inverse[1],
        inverse[0] * rx0 + inverse[1] * ry0 + inverse[2],
        inverse[3],
        inverse[4],
        inverse[3] * rx0 + inverse[4] * ry0 + inverse[5],
    )
    return source.transform(
        (rx1 - rx0, ry1 - ry0),
        Image.Transform.AFFINE,
        adjusted,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )


def _render_native_region(renderer, shapes, *, full_width: int, full_height: int, scale: int, region, raster_resolver=None):
    """Render one source-atlas tile while preserving global layer order and mask cutouts."""
    from PIL import Image, ImageChops

    rx0, ry0, rx1, ry1 = [int(value) for value in region]
    width, height = rx1 - rx0, ry1 - ry0
    if width <= 0 or height <= 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    world_bounds = (-1024.0, -512.0, 1024.0, 512.0)
    min_x, min_y, max_x, max_y = world_bounds
    config = RenderConfig(scale=scale, sharpen=False, base_samples=1, detail_samples=2).normalized()

    def to_global(point):
        return (
            (point[0] - min_x) * full_width / (max_x - min_x),
            (max_y - point[1]) * full_height / (max_y - min_y),
        )

    artwork = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    rendered_any = False
    region_box = (rx0, ry0, rx1, ry1)

    for shape_index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            continue
        data = list(shape.get("data") or [])
        if len(data) < 4:
            continue
        is_mask = bool(renderer._shape_mask_flag(shape, data))
        color = renderer._color_tuple(shape.get("color"))
        if not is_mask and (not color or color[3] <= 0):
            continue
        color = color or (255, 255, 255, 255)
        try:
            type_code = int(shape.get("type", 0))
        except (TypeError, ValueError):
            continue

        if shape.get("is_raster_logo"):
            if raster_resolver is None:
                raise LiveryPreviewError(f"layer {shape_index + 1}에 필요한 raster resolver가 없습니다.")
            raster_id = int(shape.get("raster_id") or 0)
            source = raster_resolver(raster_id) if raster_id > 0 else None
            if source is None:
                raise LiveryPreviewError(f"layer {shape_index + 1}의 raster decal {raster_id}를 찾지 못했습니다.")
            layer = _render_raster_region(
                renderer,
                source,
                data,
                color,
                full_size=(full_width, full_height),
                region=region_box,
            )
            if layer is None:
                continue
            alpha = layer.getchannel("A")
            if alpha.getbbox() is None:
                continue
            if is_mask:
                artwork.paste((0, 0, 0, 0), (0, 0, width, height), alpha)
            else:
                artwork.alpha_composite(layer)
            rendered_any = True
            continue

        resource = renderer._resolve_vinyl_resource(type_code, shape)
        alpha_triangles = renderer._resource_alpha_triangles(*resource) if resource else None
        if not alpha_triangles:
            identity = f"{resource[0]}/{resource[1]}" if resource else f"type {type_code}"
            raise LiveryPreviewError(f"layer {shape_index + 1}에 exact native resource가 없습니다: {identity}")

        transformed = [
            (renderer._transform_resource_polygon(points, data), values)
            for points, values in alpha_triangles
        ]
        global_polygons = [
            [to_global(point) for point in points]
            for points, _values in transformed
            if len(points) >= 3
        ]
        if not global_polygons:
            continue
        global_bounds = _global_polygon_bounds(global_polygons, full_width, full_height)
        clipped_global = _intersect(global_bounds, region_box) if global_bounds else None
        if clipped_global is None:
            continue

        local_polygons = [
            [(x - rx0, y - ry0) for x, y in polygon]
            for polygon in global_polygons
        ]
        canvas_alpha = [
            (local_polygons[index], transformed[index][1])
            for index in range(len(local_polygons))
        ]
        local_bounds = (
            clipped_global[0] - rx0,
            clipped_global[1] - ry0,
            clipped_global[2] - rx0,
            clipped_global[3] - ry0,
        )
        samples = _detail_sample_count(global_bounds, scale, config)
        has_vertex_alpha = any(any(int(v) != 255 for v in values) for _p, values in canvas_alpha)
        if has_vertex_alpha:
            layer = _vertex_alpha_float_layer(canvas_alpha, local_bounds, color, samples=samples)
            alpha = layer.getchannel("A")
        else:
            alpha = _aa_polygon_mask(local_polygons, local_bounds, samples=samples)
            if alpha is None:
                continue
            if not is_mask and color[3] != 255:
                alpha = ImageChops.multiply(alpha, Image.new("L", alpha.size, color[3]))
            layer = Image.new("RGBA", alpha.size, (color[0], color[1], color[2], 0))
            layer.putalpha(alpha)
        if alpha.getbbox() is None:
            continue
        dest = (local_bounds[0], local_bounds[1])
        if is_mask:
            artwork.paste((0, 0, 0, 0), local_bounds, alpha)
        else:
            artwork.alpha_composite(layer, dest=dest)
        rendered_any = True

    return artwork if rendered_any else Image.new("RGBA", (width, height), (0, 0, 0, 0))


def _map_corners(affine, box):
    a, b, c, d, e, f = affine
    x0, y0, x1, y1 = box
    points = []
    for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        points.append((a * x + b * y + c, d * x + e * y + f))
    return points


def _source_region_for_output(affine, output_box, full_size, margin: int = 8):
    points = _map_corners(affine, output_box)
    full_width, full_height = full_size
    left = max(0, int(math.floor(min(x for x, _ in points))) - margin)
    top = max(0, int(math.floor(min(y for _, y in points))) - margin)
    right = min(full_width, int(math.ceil(max(x for x, _ in points))) + margin)
    bottom = min(full_height, int(math.ceil(max(y for _, y in points))) + margin)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _project_tile(renderer, prepared_layers, *, slot, projection, base_mask, scale: int, output_box, raster_resolver=None):
    import numpy as np
    from PIL import Image

    full_size = (2048 * scale, 1024 * scale)
    affine = renderer._atlas_to_local_affine(
        slot,
        full_size[0],
        full_size[1],
        float(projection.get("xorigin", 0.0)) * scale,
        float(projection.get("yorigin", 0.0)) * scale,
    )
    source_region = _source_region_for_output(affine, output_box, full_size, margin=12)
    ox0, oy0, ox1, oy1 = [int(v) for v in output_box]
    out_size = (ox1 - ox0, oy1 - oy0)
    if source_region is None:
        return Image.new("RGBA", out_size, (0, 0, 0, 0)), Image.new("L", out_size, 0)

    source_tile = _render_native_region(
        renderer,
        prepared_layers,
        full_width=full_size[0],
        full_height=full_size[1],
        scale=scale,
        region=source_region,
        raster_resolver=raster_resolver,
    )
    sx0, sy0, _sx1, _sy1 = source_region
    a, b, c, d, e, f = affine
    local_affine = (
        a,
        b,
        a * ox0 + b * oy0 + c - sx0,
        d,
        e,
        d * ox0 + e * oy0 + f - sy0,
    )

    source_alpha = Image.fromarray(np.asarray(source_tile.getchannel("A"), dtype=np.float32) / 255.0, mode="F")
    premul = _premultiply_u8(source_tile)
    warped = premul.transform(out_size, Image.Transform.AFFINE, local_affine, resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
    alpha_f = source_alpha.transform(out_size, Image.Transform.AFFINE, local_affine, resample=Image.Resampling.BICUBIC, fillcolor=0.0)

    mask_affine = (1.0 / scale, 0.0, ox0 / scale, 0.0, 1.0 / scale, oy0 / scale)
    mask = base_mask.convert("L").transform(out_size, Image.Transform.AFFINE, mask_affine, resample=Image.Resampling.BICUBIC, fillcolor=0)
    mask_factor = np.asarray(mask, dtype=np.float32) / 255.0
    alpha = np.asarray(alpha_f, dtype=np.float32) * mask_factor
    premul_rgba = np.asarray(warped, dtype=np.float32) / 255.0
    out = np.zeros(premul_rgba.shape, dtype=np.uint8)
    visible = alpha > 1.0e-7
    for channel in range(3):
        premul_channel = premul_rgba[..., channel] * mask_factor
        restored = np.zeros_like(alpha, dtype=np.float32)
        restored[visible] = premul_channel[visible] / alpha[visible]
        out[..., channel] = np.clip(np.rint(restored * 255.0), 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(np.rint(alpha * 255.0), 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA"), mask


def _tiled_projection(prepared_layers, renderer, *, section: str, car_id: int, game_folder: Path, scale: int, raster_resolver=None) -> bytes:
    from PIL import Image

    render_contract, slot, base_mask, projection, _mask_hash = _projection_record(section, int(car_id), game_folder)
    base_bounds = render_contract._projection_pixel_bounds(projection)
    high_bounds = tuple(int(value * scale) for value in base_bounds)
    retained_scale = RETAINED_SCALE_LIMIT
    ratio = scale // retained_scale
    final_size = (
        (base_bounds[2] - base_bounds[0]) * retained_scale,
        (base_bounds[3] - base_bounds[1]) * retained_scale,
    )
    final = Image.new("RGBA", final_size, (0, 0, 0, 0))

    overlap = max(32, 16 * ratio)
    overlap -= overlap % ratio
    tile_size = TILE_SIZE - (TILE_SIZE % ratio)
    hx0, hy0, hx1, hy1 = high_bounds

    for core_y0 in range(hy0, hy1, tile_size):
        core_y1 = min(hy1, core_y0 + tile_size)
        for core_x0 in range(hx0, hx1, tile_size):
            core_x1 = min(hx1, core_x0 + tile_size)
            ex0 = max(hx0, core_x0 - overlap)
            ey0 = max(hy0, core_y0 - overlap)
            ex1 = min(hx1, core_x1 + overlap)
            ey1 = min(hy1, core_y1 + overlap)
            expanded = (ex0, ey0, ex1, ey1)
            art_hi, mask_hi = _project_tile(
                render_contract,
                prepared_layers,
                slot=slot,
                projection=projection,
                base_mask=base_mask,
                scale=scale,
                output_box=expanded,
                raster_resolver=raster_resolver,
            )
            down_size = ((ex1 - ex0) // ratio, (ey1 - ey0) // ratio)
            art = art_hi.resize(down_size, Image.Resampling.LANCZOS)
            mask = mask_hi.resize(down_size, Image.Resampling.LANCZOS)

            surface = Image.new("RGBA", down_size, (150, 154, 162, 0))
            surface.putalpha(mask.point(lambda value: (int(value) * 72) // 255))
            combined = Image.alpha_composite(surface, art)

            crop_left = (core_x0 - ex0) // ratio
            crop_top = (core_y0 - ey0) // ratio
            crop_right = crop_left + (core_x1 - core_x0) // ratio
            crop_bottom = crop_top + (core_y1 - core_y0) // ratio
            core = combined.crop((crop_left, crop_top, crop_right, crop_bottom))
            dest = ((core_x0 - hx0) // ratio, (core_y0 - hy0) // ratio)
            final.paste(core, dest)

    buffer = io.BytesIO()
    final.save(buffer, format="PNG", compress_level=3)
    return buffer.getvalue()


@lru_cache(maxsize=12)
def _render_tiled_cached(path_text: str, file_size: int, mtime_ns: int, section: str, game_folder_text: str, scale: int) -> RenderedLiverySection:
    scale = normalize_scale(scale)
    if scale <= 4:
        return render_livery_section_quality_pipeline(
            Path(path_text), section, _quality_for_scale(scale), sharpen=False
        )

    decoded = _decode_cached(path_text, file_size, mtime_ns)
    layers = list(decoded.sections.get(section) or ())
    if not layers:
        raise LiveryPreviewError("이 영역에는 표시할 리버리 배치가 없습니다.")
    try:
        analysis = _analysis_cached(path_text, file_size, mtime_ns)
    except LiveryAnalysisError as exc:
        raise LiveryPreviewError(f"리버리의 대상 차량을 확인하지 못했습니다: {exc}") from exc
    if analysis.car_id <= 0:
        raise LiveryPreviewError("C_livery에서 대상 Car ID를 확인할 수 없습니다.")

    cache_path = _cache_path(path_text, file_size, mtime_ns, section, game_folder_text, scale)
    cached = _read_disk_cache(cache_path)
    if cached is not None:
        return RenderedLiverySection(section, cached, len(layers), 0, decoded.warnings)

    game_folder = Path(game_folder_text)
    _decoder, renderer = _load_backend()
    raster_resolver = None
    if any(bool(layer.get("is_raster_logo")) for layer in layers):
        try:
            raster_resolver = raster_resolver_for_game(game_folder)
        except ExactLiveryPreviewError as exc:
            raise LiveryPreviewError(f"{section} 영역의 래스터 데칼을 불러오지 못했습니다: {exc}") from exc
        _preflight_raster_layers(layers, raster_resolver)

    prepared_layers, invisible_count = validate_exact_assets_and_filter_noops(renderer, layers, raster_resolver)
    if not prepared_layers:
        raise LiveryPreviewError("표시 가능한 native placement가 없습니다.")

    projected = _tiled_projection(
        prepared_layers,
        renderer,
        section=section,
        car_id=analysis.car_id,
        game_folder=game_folder,
        scale=scale,
        raster_resolver=raster_resolver,
    )
    preview = _checkerboard_native_resolution(projected, RETAINED_SCALE_LIMIT)
    _write_disk_cache(cache_path, preview)
    warnings = list(decoded.warnings)
    if invisible_count:
        warnings.append(f"{section}: {invisible_count}개의 실제 no-op placement를 제외했습니다.")
    warnings.append(f"{scale}× tiled supersampling → {RETAINED_SCALE_LIMIT}× retained preview")
    return RenderedLiverySection(section, preview, len(layers), 0, tuple(dict.fromkeys(warnings)))


def render_livery_section_scaled(path: Path | str, section: str, scale: int = 4) -> RenderedLiverySection:
    source = Path(path)
    if not source.is_file():
        raise LiveryPreviewError("C_livery 파일을 찾을 수 없습니다.")
    scale = normalize_scale(scale)
    if scale <= 4:
        return render_livery_section_quality_pipeline(source, section, _quality_for_scale(scale), sharpen=False)
    try:
        game_folder = require_fh6_game_folder()
    except ExactLiveryPreviewError as exc:
        raise LiveryPreviewError(str(exc)) from exc
    signature = _file_signature(source)
    with _CACHE_LOCK:
        return _render_tiled_cached(
            signature[0], signature[1], signature[2], str(section), str(game_folder.resolve()), scale
        )


def clear_tiled_quality_cache() -> None:
    with _CACHE_LOCK:
        _render_tiled_cached.cache_clear()
