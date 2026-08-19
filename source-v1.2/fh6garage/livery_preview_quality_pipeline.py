from __future__ import annotations

import hashlib
import io
import math
import threading
from dataclasses import dataclass
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
    _validate_exact_assets_and_filter_noops,
)
from .livery_preview_native_resolution_test import (
    _checkerboard_native_resolution,
    normalize_quality,
    quality_scale,
)
from .livery_preview_preview2 import (
    _app_data_dir,
    _preflight_raster_layers,
    _read_disk_cache,
    _write_disk_cache,
)

CACHE_VERSION = "v14-quality-pipeline-r1"
DEFAULT_QUALITY = "high"
FULL_CANVAS_MAX_AXIS = 8192
FUTURE_MAX_SCALE = 16
DEFAULT_TILE_SIZE = 4096
DEFAULT_TILE_OVERLAP = 24
_CACHE_LOCK = threading.RLock()


@dataclass(frozen=True)
class RenderConfig:
    scale: int = 4
    sharpen: bool = False
    base_samples: int = 2
    detail_samples: int = 4
    tile_size: int = DEFAULT_TILE_SIZE
    tile_overlap: int = DEFAULT_TILE_OVERLAP

    def normalized(self) -> "RenderConfig":
        scale = max(1, min(FUTURE_MAX_SCALE, int(self.scale)))
        base = max(1, min(4, int(self.base_samples)))
        detail = max(base, min(8, int(self.detail_samples)))
        tile_size = max(1024, min(8192, int(self.tile_size)))
        overlap = max(8, min(128, int(self.tile_overlap)))
        return RenderConfig(scale, bool(self.sharpen), base, detail, tile_size, overlap)


@dataclass(frozen=True)
class TileRect:
    x0: int
    y0: int
    x1: int
    y1: int
    render_x0: int
    render_y0: int
    render_x1: int
    render_y1: int


@dataclass(frozen=True)
class RenderPlan:
    width: int
    height: int
    scale: int
    strategy: str
    tiles: tuple[TileRect, ...]


def build_render_plan(scale: int, *, tile_size: int = DEFAULT_TILE_SIZE, overlap: int = DEFAULT_TILE_OVERLAP) -> RenderPlan:
    """Return a render plan that is already structurally ready for 8x/16x tiled output."""
    scale = max(1, min(FUTURE_MAX_SCALE, int(scale)))
    width = 2048 * scale
    height = 1024 * scale
    if width <= FULL_CANVAS_MAX_AXIS and height <= FULL_CANVAS_MAX_AXIS:
        return RenderPlan(width, height, scale, "full", ())

    tile_size = max(1024, min(FULL_CANVAS_MAX_AXIS, int(tile_size)))
    overlap = max(8, min(128, int(overlap)))
    tiles: list[TileRect] = []
    for y0 in range(0, height, tile_size):
        y1 = min(height, y0 + tile_size)
        for x0 in range(0, width, tile_size):
            x1 = min(width, x0 + tile_size)
            tiles.append(
                TileRect(
                    x0,
                    y0,
                    x1,
                    y1,
                    max(0, x0 - overlap),
                    max(0, y0 - overlap),
                    min(width, x1 + overlap),
                    min(height, y1 + overlap),
                )
            )
    return RenderPlan(width, height, scale, "tiled", tuple(tiles))


def _disk_cache_dir() -> Path:
    return _app_data_dir() / "livery_preview_cache" / CACHE_VERSION


def _cache_path(path_text: str, file_size: int, mtime_ns: int, section: str, game_folder_text: str, quality: str, sharpen: bool) -> Path:
    payload = "|".join(
        (
            CACHE_VERSION,
            KFPS_VENDOR_COMMIT,
            str(Path(path_text).resolve()),
            str(int(file_size)),
            str(int(mtime_ns)),
            str(section),
            str(Path(game_folder_text).resolve()),
            normalize_quality(quality),
            "sharp1" if sharpen else "sharp0",
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8", errors="surrogatepass")).hexdigest()
    return _disk_cache_dir() / f"{digest}.png"


def _scaled_bounds(base_bounds: tuple[int, int, int, int], scale: int) -> tuple[int, int, int, int]:
    return tuple(int(round(value * scale)) for value in base_bounds)


def _detail_sample_count(bounds: tuple[int, int, int, int], scale: int, config: RenderConfig) -> int:
    """Spend more local samples only on glyph-like or thin geometry."""
    left, top, right, bottom = bounds
    native_w = max(1.0, (right - left) / max(1, scale))
    native_h = max(1.0, (bottom - top) / max(1, scale))
    short = min(native_w, native_h)
    long = max(native_w, native_h)
    if short <= 8.0 or long <= 72.0:
        return config.detail_samples
    if short <= 14.0 or long <= 128.0:
        return max(config.base_samples, 3)
    return config.base_samples


def _aa_polygon_mask(polygons, bounds, *, samples: int):
    from PIL import Image, ImageDraw

    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None
    samples = max(1, int(samples))
    high = Image.new("L", (width * samples, height * samples), 0)
    draw = ImageDraw.Draw(high)
    for polygon in polygons:
        points = [((float(x) - left) * samples, (float(y) - top) * samples) for x, y in polygon]
        if len(points) >= 3:
            draw.polygon(points, fill=255)
    if high.getbbox() is None:
        return None
    return high if samples == 1 else high.resize((width, height), Image.Resampling.LANCZOS)


def _vertex_alpha_float_layer(canvas_alpha, bounds, color, *, samples: int):
    """Keep barycentric opacity in float32 until the final local coverage image is quantized."""
    import numpy as np
    from PIL import Image

    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    samples = max(1, int(samples))
    high_w = width * samples
    high_h = height * samples
    coverage = np.zeros((high_h, high_w), dtype=np.float32)

    for points, values in canvas_alpha:
        if len(points) != 3:
            continue
        local = [((float(x) - left) * samples, (float(y) - top) * samples) for x, y in points]
        x0, y0 = local[0]
        x1, y1 = local[1]
        x2, y2 = local[2]
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1.0e-10:
            continue
        min_x = max(0, int(math.floor(min(x0, x1, x2))))
        max_x = min(high_w, int(math.ceil(max(x0, x1, x2))) + 1)
        min_y = max(0, int(math.floor(min(y0, y1, y2))))
        max_y = min(high_h, int(math.ceil(max(y0, y1, y2))) + 1)
        if min_x >= max_x or min_y >= max_y:
            continue
        xs = np.arange(min_x, max_x, dtype=np.float32) + 0.5
        ys = np.arange(min_y, max_y, dtype=np.float32)[:, None] + 0.5
        w0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / denom
        w1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / denom
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-5) & (w1 >= -1e-5) & (w2 >= -1e-5)
        interp = (
            w0 * (float(values[0]) / 255.0)
            + w1 * (float(values[1]) / 255.0)
            + w2 * (float(values[2]) / 255.0)
        )
        region = coverage[min_y:max_y, min_x:max_x]
        np.maximum(region, np.where(inside, interp, 0.0), out=region)

    if samples > 1:
        float_img = Image.fromarray(coverage, mode="F").resize((width, height), Image.Resampling.LANCZOS)
        coverage = np.asarray(float_img, dtype=np.float32)
    alpha = np.clip(coverage * (float(color[3]) / 255.0), 0.0, 1.0)
    rgba = np.empty((height, width, 4), dtype=np.uint8)
    rgba[..., 0] = color[0]
    rgba[..., 1] = color[1]
    rgba[..., 2] = color[2]
    rgba[..., 3] = np.clip(np.rint(alpha * 255.0), 0, 255).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def _render_native_high_precision(renderer, shapes, *, width: int, height: int, scale: int, config: RenderConfig, raster_resolver=None, cancel_event=None):
    """D-derived renderer with adaptive subpixel coverage and float32 local alpha."""
    import concurrent.futures
    from PIL import Image, ImageChops

    if width > FULL_CANVAS_MAX_AXIS or height > FULL_CANVAS_MAX_AXIS:
        raise LiveryPreviewError("현재 실행기는 full-canvas 4×까지 지원합니다. 8×/16×용 tile plan은 준비되어 있습니다.")

    world_bounds = (-1024.0, -512.0, 1024.0, 512.0)
    min_x, min_y, max_x, max_y = world_bounds

    def to_canvas(point):
        return ((point[0] - min_x) * width / (max_x - min_x), (max_y - point[1]) * height / (max_y - min_y))

    def layer_bounds(polygons):
        xs = [p[0] for poly in polygons for p in poly]
        ys = [p[1] for poly in polygons for p in poly]
        if not xs or not ys:
            return None
        left = max(0, math.floor(min(xs)) - 4)
        top = max(0, math.floor(min(ys)) - 4)
        right = min(width, math.ceil(max(xs)) + 5)
        bottom = min(height, math.ceil(max(ys)) + 5)
        return (left, top, right, bottom) if right > left and bottom > top else None

    artwork = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    rendered_any = False
    for shape_index, shape in enumerate(shapes):
        if shape_index % 32 == 0 and cancel_event is not None and cancel_event.is_set():
            raise concurrent.futures.CancelledError()
        if not isinstance(shape, dict):
            continue
        data = list(shape.get("data") or [])
        if len(data) < 4:
            continue
        is_mask = renderer._shape_mask_flag(shape, data)
        color = renderer._color_tuple(shape.get("color"))
        if not is_mask and (not color or color[3] <= 0):
            continue
        try:
            [float(item) for item in data[:4]]
            type_code = int(shape.get("type", 0))
        except (TypeError, ValueError):
            continue

        if shape.get("is_raster_logo"):
            if raster_resolver is None:
                raise LiveryPreviewError(f"layer {shape_index + 1}에 필요한 raster resolver가 없습니다.")
            raster_id = int(shape.get("raster_id") or 0)
            source = raster_resolver(raster_id) if raster_id > 0 else None
            if source is None:
                raise LiveryPreviewError(f"layer {shape_index + 1}의 FH6 내장 raster decal {raster_id}를 찾지 못했습니다.")
            layer = renderer._render_raster_layer_canvas(source, data, color, (width, height), world_bounds)
            if layer is None:
                raise LiveryPreviewError(f"layer {shape_index + 1}의 raster decal을 변환하지 못했습니다.")
            if is_mask:
                alpha = layer.getchannel("A")
                if alpha.getbbox():
                    artwork.paste((0, 0, 0, 0), (0, 0, width, height), alpha)
                    rendered_any = True
            else:
                artwork.alpha_composite(layer)
                rendered_any = True
            continue

        resource = renderer._resolve_vinyl_resource(type_code, shape)
        alpha_triangles = renderer._resource_alpha_triangles(*resource) if resource else None
        if not alpha_triangles:
            identity = f"{resource[0]}/{resource[1]}" if resource else f"shape word 0x{renderer._shape_word_from_shape(shape, type_code):04X}"
            raise LiveryPreviewError(f"layer {shape_index + 1}에 exact native resource가 없습니다: {identity}")

        transformed = [(renderer._transform_resource_polygon(points, data), values) for points, values in alpha_triangles]
        polygons = [[to_canvas(point) for point in points] for points, _ in transformed if len(points) >= 3]
        if not polygons:
            continue
        canvas_alpha = [(polygon, transformed[index][1]) for index, polygon in enumerate(polygons)]
        bounds = layer_bounds(polygons)
        if bounds is None:
            continue
        samples = _detail_sample_count(bounds, scale, config)
        has_vertex_alpha = any(any(v != 255 for v in values) for _, values in canvas_alpha)

        if has_vertex_alpha:
            layer = _vertex_alpha_float_layer(canvas_alpha, bounds, color, samples=samples)
            alpha = layer.getchannel("A")
        else:
            alpha = _aa_polygon_mask(polygons, bounds, samples=samples)
            if alpha is None:
                continue
            if not is_mask and color[3] != 255:
                alpha = ImageChops.multiply(alpha, Image.new("L", alpha.size, color[3]))
            layer = Image.new("RGBA", alpha.size, (color[0], color[1], color[2], 0))
            layer.putalpha(alpha)

        if alpha.getbbox() is None:
            continue
        if is_mask:
            artwork.paste((0, 0, 0, 0), bounds, alpha)
        else:
            artwork.alpha_composite(layer, dest=(bounds[0], bounds[1]))
        rendered_any = True

    if not rendered_any:
        return None
    out = io.BytesIO()
    artwork.save(out, format="PNG", optimize=False)
    return out.getvalue()


def _premultiply_u8(image):
    import numpy as np
    from PIL import Image

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint16)
    alpha = rgba[..., 3:4]
    out = np.empty(rgba.shape, dtype=np.uint8)
    out[..., :3] = ((rgba[..., :3] * alpha + 127) // 255).astype(np.uint8)
    out[..., 3] = rgba[..., 3].astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def _projection_high_precision(png_bytes: bytes, section: str, car_id: int, *, game_folder: Path, scale: int, sharpen: bool) -> bytes:
    import numpy as np
    from PIL import Image, ImageFilter

    render_contract, slot, base_mask, projection, _mask_hash = _projection_record(section, int(car_id), game_folder)
    base_width, base_height = tuple(render_contract.ATLAS_SIZE)
    target_size = (base_width * scale, base_height * scale)
    with Image.open(io.BytesIO(png_bytes)) as source:
        artwork = source.convert("RGBA")
    if artwork.size != target_size:
        raise LiveryPreviewError(f"section canvas 크기가 올바르지 않습니다: {artwork.size}; 예상 {target_size}")

    affine = render_contract._atlas_to_local_affine(
        slot,
        target_size[0],
        target_size[1],
        float(projection.get("xorigin", 0.0)) * scale,
        float(projection.get("yorigin", 0.0)) * scale,
    )
    source_alpha_f = Image.fromarray(np.asarray(artwork.getchannel("A"), dtype=np.float32) / 255.0, mode="F")
    premul = _premultiply_u8(artwork)
    del artwork

    warped = premul.transform(target_size, Image.Transform.AFFINE, affine, resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
    del premul
    alpha_f = source_alpha_f.transform(target_size, Image.Transform.AFFINE, affine, resample=Image.Resampling.BICUBIC, fillcolor=0.0)
    del source_alpha_f

    mask = base_mask.convert("L")
    if mask.size != target_size:
        mask = mask.resize(target_size, Image.Resampling.LANCZOS)
    bounds = _scaled_bounds(render_contract._projection_pixel_bounds(projection), scale)
    warped = warped.crop(bounds)
    alpha_f = alpha_f.crop(bounds)
    mask_crop = mask.crop(bounds)
    del mask

    mask_factor = np.asarray(mask_crop, dtype=np.float32) / 255.0
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
    clipped = Image.fromarray(out, mode="RGBA")

    if sharpen:
        alpha_channel = clipped.getchannel("A")
        rgb = clipped.convert("RGB").filter(ImageFilter.UnsharpMask(radius=max(0.6, 0.45 * scale), percent=30, threshold=3))
        clipped = rgb.convert("RGBA")
        clipped.putalpha(alpha_channel)

    surface = Image.new("RGBA", clipped.size, (150, 154, 162, 0))
    surface.putalpha(mask_crop.point(lambda value: (int(value) * 72) // 255))
    combined = Image.alpha_composite(surface, clipped)
    buffer = io.BytesIO()
    combined.save(buffer, format="PNG", compress_level=3)
    return buffer.getvalue()


@lru_cache(maxsize=18)
def _render_cached(path_text: str, file_size: int, mtime_ns: int, section: str, game_folder_text: str, quality: str, sharpen: bool) -> RenderedLiverySection:
    quality = normalize_quality(quality)
    scale = quality_scale(quality)
    config = RenderConfig(scale=scale, sharpen=bool(sharpen)).normalized()
    plan = build_render_plan(config.scale, tile_size=config.tile_size, overlap=config.tile_overlap)
    if plan.strategy != "full":
        raise LiveryPreviewError("8×/16× tile plan은 준비되어 있지만 이번 v1.4 품질 파이프라인 테스트에서는 아직 실행하지 않습니다.")

    decoded = _decode_cached(path_text, file_size, mtime_ns)
    if section not in decoded.sections:
        raise LiveryPreviewError(f"지원하지 않는 리버리 영역입니다: {section}")
    layers = list(decoded.sections[section])
    if not layers:
        raise LiveryPreviewError("이 영역에는 표시할 리버리 배치가 없습니다.")

    try:
        analysis = _analysis_cached(path_text, file_size, mtime_ns)
    except LiveryAnalysisError as exc:
        raise LiveryPreviewError(f"리버리의 대상 차량을 확인하지 못했습니다: {exc}") from exc
    if analysis.car_id <= 0:
        raise LiveryPreviewError("C_livery에서 대상 Car ID를 확인할 수 없습니다.")

    cache_path = _cache_path(path_text, file_size, mtime_ns, section, game_folder_text, quality, sharpen)
    cached_png = _read_disk_cache(cache_path)
    if cached_png is not None:
        return RenderedLiverySection(section, cached_png, len(layers), 0, decoded.warnings)

    game_folder = Path(game_folder_text)
    _decoder, renderer = _load_backend()
    raster_count = sum(1 for layer in layers if bool(layer.get("is_raster_logo")))
    raster_resolver = None
    if raster_count:
        try:
            raster_resolver = raster_resolver_for_game(game_folder)
        except ExactLiveryPreviewError as exc:
            raise LiveryPreviewError(f"{section} 영역의 FH6 내장 래스터 데칼을 불러오지 못했습니다: {exc}") from exc
        _preflight_raster_layers(layers, raster_resolver)

    prepared_layers, invisible_count = _validate_exact_assets_and_filter_noops(renderer, layers, raster_resolver)
    if not prepared_layers:
        raise LiveryPreviewError("표시 가능한 native placement가 없습니다.")

    rendered = _render_native_high_precision(
        renderer,
        prepared_layers,
        width=plan.width,
        height=plan.height,
        scale=scale,
        config=config,
        raster_resolver=raster_resolver,
    )
    if not rendered:
        raise LiveryPreviewError(f"{section} 영역에서 표시 가능한 이미지를 만들지 못했습니다.")

    projected = _projection_high_precision(rendered, section, analysis.car_id, game_folder=game_folder, scale=scale, sharpen=sharpen)
    preview_png = _checkerboard_native_resolution(projected, scale)
    _write_disk_cache(cache_path, preview_png)

    warnings = list(decoded.warnings)
    if invisible_count:
        warnings.append(f"{section}: {invisible_count}개의 완전 투명 native placement를 제외했습니다.")
    warnings.append(f"Quality Pipeline · D renderer · {scale}× · adaptive local AA · {'sharpen on' if sharpen else 'exact'}")
    return RenderedLiverySection(section, preview_png, len(layers), 0, tuple(dict.fromkeys(warnings)))


def render_livery_section_quality_pipeline(path: Path | str, section: str, quality: str = DEFAULT_QUALITY, *, sharpen: bool = False) -> RenderedLiverySection:
    source = Path(path)
    if not source.is_file():
        raise LiveryPreviewError("C_livery 파일을 찾을 수 없습니다.")
    try:
        game_folder = require_fh6_game_folder()
    except ExactLiveryPreviewError as exc:
        raise LiveryPreviewError(str(exc)) from exc
    signature = _file_signature(source)
    with _CACHE_LOCK:
        return _render_cached(
            signature[0],
            signature[1],
            signature[2],
            str(section),
            str(game_folder.resolve()),
            normalize_quality(quality),
            bool(sharpen),
        )


def clear_quality_pipeline_cache() -> None:
    with _CACHE_LOCK:
        _render_cached.cache_clear()
