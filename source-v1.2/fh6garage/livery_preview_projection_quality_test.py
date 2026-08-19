from __future__ import annotations

import concurrent.futures
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


CACHE_VERSION = "v14-projection-quality-test-r1"
MODES = ("a", "b", "c", "d")
DEFAULT_MODE = "a"
_CACHE_LOCK = threading.RLock()


def normalize_mode(value: str | None) -> str:
    mode = str(value or DEFAULT_MODE).strip().lower()
    return mode if mode in MODES else DEFAULT_MODE


def mode_label(mode: str | None) -> str:
    return {
        "a": "A · 현재 4× 기준",
        "b": "B · BICUBIC projection",
        "c": "C · BICUBIC + premultiplied alpha",
        "d": "D · C + subpixel/high-precision alpha",
    }[normalize_mode(mode)]


def _disk_cache_dir() -> Path:
    return _app_data_dir() / "livery_preview_cache" / CACHE_VERSION


def _cache_path(
    path_text: str,
    file_size: int,
    mtime_ns: int,
    section: str,
    game_folder_text: str,
    quality: str,
    mode: str,
) -> Path:
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
            normalize_mode(mode),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8", errors="surrogatepass")).hexdigest()
    return _disk_cache_dir() / f"{digest}.png"


def _scaled_bounds(base_bounds: tuple[int, int, int, int], scale: int) -> tuple[int, int, int, int]:
    return tuple(int(round(value * scale)) for value in base_bounds)


def _premultiply_rgba(image):
    import numpy as np
    from PIL import Image

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint16)
    alpha = rgba[..., 3:4]
    out = np.empty_like(rgba, dtype=np.uint8)
    out[..., :3] = ((rgba[..., :3] * alpha + 127) // 255).astype(np.uint8)
    out[..., 3] = rgba[..., 3].astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def _unpremultiply_u8(image):
    import numpy as np
    from PIL import Image

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint16)
    alpha = rgba[..., 3]
    rgb = rgba[..., :3]
    out = np.zeros(rgba.shape, dtype=np.uint8)
    nonzero = alpha > 0
    if np.any(nonzero):
        denominator = alpha[nonzero, None]
        values = (rgb[nonzero] * 255 + denominator // 2) // denominator
        out[..., :3][nonzero] = np.clip(values, 0, 255).astype(np.uint8)
    out[..., 3] = alpha.astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def _mask_premultiplied_u8(image, mask):
    from PIL import Image, ImageChops

    r, g, b, a = image.convert("RGBA").split()
    masked = Image.merge(
        "RGBA",
        (
            ImageChops.multiply(r, mask),
            ImageChops.multiply(g, mask),
            ImageChops.multiply(b, mask),
            ImageChops.multiply(a, mask),
        ),
    )
    return _unpremultiply_u8(masked)


def _mask_premultiplied_float(image, mask):
    import numpy as np
    from PIL import Image

    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    factor = np.asarray(mask.convert("L"), dtype=np.float32) / 255.0
    rgba[..., :3] *= factor[..., None]
    rgba[..., 3] *= factor

    alpha = rgba[..., 3]
    out = np.zeros(rgba.shape, dtype=np.uint8)
    nonzero = alpha > 1.0e-6
    if np.any(nonzero):
        restored = rgba[..., :3][nonzero] * (255.0 / alpha[nonzero, None])
        out[..., :3][nonzero] = np.clip(np.rint(restored), 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(np.rint(alpha), 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def _projection_variant(
    png_bytes: bytes,
    section: str,
    car_id: int,
    *,
    game_folder: Path,
    scale: int,
    mode: str,
) -> bytes:
    """Retain 1x/2x/4x output while isolating projection/alpha quality changes."""
    from PIL import Image, ImageChops

    mode = normalize_mode(mode)
    scale = int(scale)
    render_contract, slot, base_mask, projection, _mask_hash = _projection_record(
        section, int(car_id), game_folder
    )
    base_width, base_height = tuple(render_contract.ATLAS_SIZE)
    target_size = (base_width * scale, base_height * scale)

    try:
        with Image.open(io.BytesIO(png_bytes)) as source:
            artwork = source.convert("RGBA")
        if artwork.size != target_size:
            raise LiveryPreviewError(
                f"section canvas 크기가 올바르지 않습니다: {artwork.size}; 예상 {target_size}"
            )

        base_bounds = render_contract._projection_pixel_bounds(projection)
        if scale == 1 and mode == "a":
            clipped = render_contract._masked_atlas_layer(artwork, base_mask, slot, projection)
            mask_crop = base_mask.convert("L").crop(base_bounds)
            clipped_crop = clipped.crop(base_bounds)
        else:
            affine = render_contract._atlas_to_local_affine(
                slot,
                target_size[0],
                target_size[1],
                float(projection.get("xorigin", 0.0)) * scale,
                float(projection.get("yorigin", 0.0)) * scale,
            )
            artwork_resample = (
                Image.Resampling.BILINEAR if mode == "a" else Image.Resampling.BICUBIC
            )
            mask_resample = (
                Image.Resampling.BILINEAR
                if mode == "a"
                else (Image.Resampling.LANCZOS if mode == "d" else Image.Resampling.BICUBIC)
            )

            if mode in {"c", "d"}:
                artwork = _premultiply_rgba(artwork)
            warped = artwork.transform(
                target_size,
                Image.Transform.AFFINE,
                affine,
                resample=artwork_resample,
                fillcolor=(0, 0, 0, 0),
            )
            del artwork

            mask = base_mask.convert("L")
            if mask.size != target_size:
                mask = mask.resize(target_size, mask_resample)

            if mode == "a" or mode == "b":
                warped.putalpha(ImageChops.multiply(warped.getchannel("A"), mask))
            elif mode == "c":
                warped = _mask_premultiplied_u8(warped, mask)
            else:
                warped = _mask_premultiplied_float(warped, mask)

            bounds = _scaled_bounds(base_bounds, scale)
            clipped_crop = warped.crop(bounds)
            mask_crop = mask.crop(bounds)
            del warped, mask

        surface = Image.new("RGBA", clipped_crop.size, (150, 154, 162, 0))
        surface.putalpha(mask_crop.point(lambda value: (int(value) * 72) // 255))
        combined = Image.alpha_composite(surface, clipped_crop)

        buffer = io.BytesIO()
        combined.save(buffer, format="PNG", compress_level=3)
        return buffer.getvalue()
    except LiveryPreviewError:
        raise
    except Exception as exc:
        raise LiveryPreviewError(
            f"{section} 영역의 projection-quality {mode.upper()} 처리에 실패했습니다: {exc}"
        ) from exc


def _aa_polygon_mask(polygons, bounds, *, samples: int = 2):
    """Rasterize vector coverage in a local supersampled buffer and Lanczos reduce it."""
    from PIL import Image, ImageDraw

    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None
    samples = max(1, int(samples))
    mask_hi = Image.new("L", (width * samples, height * samples), 0)
    draw = ImageDraw.Draw(mask_hi)
    for polygon in polygons:
        points = [
            ((float(x) - left) * samples, (float(y) - top) * samples)
            for x, y in polygon
        ]
        if len(points) >= 3:
            draw.polygon(points, fill=255)
    if mask_hi.getbbox() is None:
        return None
    if samples == 1:
        return mask_hi
    return mask_hi.resize((width, height), Image.Resampling.LANCZOS)


def _aa_vertex_alpha_layer(renderer, canvas_alpha, bounds, color, *, samples: int = 2):
    """Supersample KFPS float32 barycentric alpha so gradient edges gain subpixel coverage."""
    from PIL import Image

    samples = max(1, int(samples))
    if samples == 1:
        return renderer._rasterize_vertex_alpha_triangles(canvas_alpha, bounds, color)
    scaled_triangles = []
    for points, values in canvas_alpha:
        scaled_triangles.append(([(x * samples, y * samples) for x, y in points], values))
    scaled_bounds = tuple(int(value * samples) for value in bounds)
    high = renderer._rasterize_vertex_alpha_triangles(
        scaled_triangles,
        scaled_bounds,
        color,
    )
    target = (bounds[2] - bounds[0], bounds[3] - bounds[1])
    return high.resize(target, Image.Resampling.LANCZOS)


def _render_typecode_layers_high_precision(
    renderer,
    shapes,
    *,
    width: int,
    height: int,
    raster_resolver=None,
    cancel_event=None,
):
    """KFPS-compatible 4x renderer with local subpixel coverage for native vectors."""
    from PIL import Image, ImageChops

    width = max(1, min(8192, int(width)))
    height = max(1, min(8192, int(height)))
    world_bounds = (-1024.0, -512.0, 1024.0, 512.0)
    min_x, min_y, max_x, max_y = world_bounds

    def to_canvas(point):
        return (
            (point[0] - min_x) * width / (max_x - min_x),
            (max_y - point[1]) * height / (max_y - min_y),
        )

    def layer_bounds(polygons):
        xs = [point[0] for polygon in polygons for point in polygon]
        ys = [point[1] for polygon in polygons for point in polygon]
        if not xs or not ys:
            return None
        left = max(0, math.floor(min(xs)) - 3)
        top = max(0, math.floor(min(ys)) - 3)
        right = min(width, math.ceil(max(xs)) + 4)
        bottom = min(height, math.ceil(max(ys)) + 4)
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
                continue
            try:
                raster_id = int(shape.get("raster_id") or 0)
                source = raster_resolver(raster_id) if raster_id > 0 else None
                layer = (
                    renderer._render_raster_layer_canvas(
                        source,
                        data,
                        color,
                        (width, height),
                        world_bounds,
                    )
                    if source is not None
                    else None
                )
            except (TypeError, ValueError, OSError):
                layer = None
            if layer is None:
                continue
            if is_mask:
                alpha = layer.getchannel("A")
                if alpha.getbbox():
                    artwork.paste((0, 0, 0, 0), (0, 0, width, height), alpha)
                    rendered_any = True
            else:
                artwork.alpha_composite(layer)
                rendered_any = True
            continue

        word = renderer._shape_word_from_shape(shape, type_code)
        resource = renderer._resolve_vinyl_resource(type_code, shape)
        alpha_triangles = renderer._resource_alpha_triangles(*resource) if resource else None
        if not alpha_triangles:
            triangles = renderer._resource_triangles(*resource) if resource else None
            if not triangles:
                triangles = renderer._fallback_triangles(word)
            alpha_triangles = [(triangle, (255, 255, 255)) for triangle in triangles]

        transformed_alpha = [
            (renderer._transform_resource_polygon(points, data), values)
            for points, values in alpha_triangles
        ]
        polygons = [
            [to_canvas(point) for point in points]
            for points, _values in transformed_alpha
            if len(points) >= 3
        ]
        if not polygons:
            continue
        canvas_alpha = [
            (polygon, transformed_alpha[index][1])
            for index, polygon in enumerate(polygons)
        ]
        bounds = layer_bounds(polygons)
        if bounds is None:
            continue

        has_vertex_alpha = any(
            any(value != 255 for value in values)
            for _polygon, values in canvas_alpha
        )
        if has_vertex_alpha:
            layer = _aa_vertex_alpha_layer(renderer, canvas_alpha, bounds, color, samples=2)
            alpha = layer.getchannel("A")
        else:
            alpha = _aa_polygon_mask(polygons, bounds, samples=2)
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
    if cancel_event is not None and cancel_event.is_set():
        raise concurrent.futures.CancelledError()
    buffer = io.BytesIO()
    artwork.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


@lru_cache(maxsize=24)
def _render_cached(
    path_text: str,
    file_size: int,
    mtime_ns: int,
    section: str,
    game_folder_text: str,
    quality: str,
    mode: str,
) -> RenderedLiverySection:
    quality = normalize_quality(quality)
    mode = normalize_mode(mode)
    scale = quality_scale(quality)
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

    cache_path = _cache_path(
        path_text,
        file_size,
        mtime_ns,
        section,
        game_folder_text,
        quality,
        mode,
    )
    cached_png = _read_disk_cache(cache_path)
    if cached_png is not None:
        return RenderedLiverySection(
            section=section,
            png_bytes=cached_png,
            placement_count=len(layers),
            skipped_raster_logos=0,
            warnings=decoded.warnings,
        )

    game_folder = Path(game_folder_text)
    _decoder, renderer = _load_backend()
    raster_count = sum(1 for layer in layers if bool(layer.get("is_raster_logo")))
    raster_resolver = None
    if raster_count:
        try:
            raster_resolver = raster_resolver_for_game(game_folder)
        except ExactLiveryPreviewError as exc:
            raise LiveryPreviewError(
                f"{section} 영역의 FH6 내장 래스터 데칼을 불러오지 못했습니다: {exc}"
            ) from exc
        _preflight_raster_layers(layers, raster_resolver)

    prepared_layers, invisible_count = _validate_exact_assets_and_filter_noops(
        renderer,
        layers,
        raster_resolver,
    )
    if not prepared_layers:
        raise LiveryPreviewError("표시 가능한 native placement가 없습니다.")

    width = 2048 * scale
    height = 1024 * scale
    try:
        if mode == "d":
            rendered = _render_typecode_layers_high_precision(
                renderer,
                prepared_layers,
                width=width,
                height=height,
                raster_resolver=raster_resolver,
            )
        else:
            rendered = renderer.render_typecode_layers_canvas(
                prepared_layers,
                width=width,
                height=height,
                raster_resolver=raster_resolver,
                strict_assets=False,
            )
    except Exception as exc:
        raise LiveryPreviewError(
            f"{section} 영역의 {mode_label(mode)} 렌더링에 실패했습니다: {exc}"
        ) from exc
    if not rendered:
        raise LiveryPreviewError(f"{section} 영역에서 표시 가능한 이미지를 만들지 못했습니다.")

    projected = _projection_variant(
        rendered,
        section,
        analysis.car_id,
        game_folder=game_folder,
        scale=scale,
        mode=mode,
    )
    preview_png = _checkerboard_native_resolution(projected, scale)
    _write_disk_cache(cache_path, preview_png)

    warnings = list(decoded.warnings)
    if invisible_count:
        warnings.append(
            f"{section}: {invisible_count}개의 완전 투명 native placement를 제외했습니다."
        )
    warnings.append(f"Projection Quality Test · {mode_label(mode)} · {scale}× retained output")
    return RenderedLiverySection(
        section=section,
        png_bytes=preview_png,
        placement_count=len(layers),
        skipped_raster_logos=0,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def render_livery_section_projection_quality_test(
    path: Path | str,
    section: str,
    quality: str = "high",
    *,
    mode: str = DEFAULT_MODE,
) -> RenderedLiverySection:
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
            normalize_mode(mode),
        )


def clear_projection_quality_test_cache() -> None:
    with _CACHE_LOCK:
        _render_cached.cache_clear()
