from __future__ import annotations

import hashlib
import io
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
from .livery_preview_preview2 import (
    _preflight_raster_layers,
    _read_disk_cache,
    _write_disk_cache,
    _app_data_dir,
)


CACHE_VERSION = "v14-native-resolution-test-r1"
QUALITY_SCALES = {
    "fast": 1,
    "balanced": 2,
    "high": 4,
}
DEFAULT_QUALITY = "high"
_CACHE_LOCK = threading.RLock()


def normalize_quality(value: str | None) -> str:
    quality = str(value or DEFAULT_QUALITY).strip().lower()
    return quality if quality in QUALITY_SCALES else DEFAULT_QUALITY


def quality_scale(value: str | None) -> int:
    return QUALITY_SCALES[normalize_quality(value)]


def _disk_cache_dir() -> Path:
    return _app_data_dir() / "livery_preview_cache" / CACHE_VERSION


def _cache_path(
    path_text: str,
    file_size: int,
    mtime_ns: int,
    section: str,
    game_folder_text: str,
    quality: str,
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
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8", errors="surrogatepass")).hexdigest()
    return _disk_cache_dir() / f"{digest}.png"


def _scaled_crop_box(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
    scale: int,
) -> tuple[int, int, int, int]:
    image_width, image_height = image_size
    left, top, right, bottom = bbox
    padding = 32 * scale
    minimum_width = min(image_width, 480 * scale)
    minimum_height = min(image_height, 240 * scale)

    def axis(start: int, end: int, limit: int, pad: int, minimum: int) -> tuple[int, int]:
        padded_start = max(0, int(start) - pad)
        padded_end = min(limit, int(end) + pad)
        target = min(limit, max(padded_end - padded_start, minimum))
        center = (float(start) + float(end)) / 2.0
        new_start = int(round(center - target / 2.0))
        new_start = max(0, min(new_start, limit - target))
        return new_start, new_start + target

    crop_left, crop_right = axis(left, right, image_width, padding, minimum_width)
    crop_top, crop_bottom = axis(top, bottom, image_height, padding, minimum_height)
    return crop_left, crop_top, crop_right, crop_bottom


def _checkerboard_native_resolution(png_bytes: bytes, scale: int) -> bytes:
    try:
        from PIL import Image, ImageDraw

        with Image.open(io.BytesIO(png_bytes)) as source:
            artwork = source.convert("RGBA")

        alpha_bbox = artwork.getchannel("A").getbbox()
        if alpha_bbox:
            crop_box = _scaled_crop_box(alpha_bbox, artwork.size, scale)
            if crop_box != (0, 0, artwork.width, artwork.height):
                artwork = artwork.crop(crop_box)

        background = Image.new("RGBA", artwork.size, (54, 56, 64, 255))
        draw = ImageDraw.Draw(background)
        tile = max(16, 32 * scale)
        lighter = (78, 80, 90, 255)
        for y in range(0, artwork.height, tile):
            for x in range(0, artwork.width, tile):
                if ((x // tile) + (y // tile)) % 2 == 0:
                    draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=lighter)

        output = Image.alpha_composite(background, artwork).convert("RGB")
        buffer = io.BytesIO()
        output.save(buffer, format="PNG", compress_level=3)
        return buffer.getvalue()
    except Exception as exc:
        raise LiveryPreviewError(f"고해상도 미리보기 배경 합성에 실패했습니다: {exc}") from exc


def _projection_native_resolution(
    png_bytes: bytes,
    section: str,
    car_id: int,
    *,
    game_folder: Path,
    scale: int,
) -> bytes:
    """Apply the exact FH6 section projection while retaining the scaled output.

    Unlike Preview 2, this test intentionally does not resize the completed crop
    back to the canonical 2048x1024 projection resolution. The section coordinate
    system, transform, mask and layer semantics remain identical; only the output
    raster density is retained at 1x, 2x or 4x for direct visual comparison.
    """
    from PIL import Image, ImageChops

    scale = int(scale)
    if scale not in (1, 2, 4):
        raise LiveryPreviewError("Native Resolution Test는 1×, 2×, 4×만 지원합니다.")

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
        if scale == 1:
            clipped = render_contract._masked_atlas_layer(artwork, base_mask, slot, projection)
            mask_crop = base_mask.convert("L").crop(base_bounds)
            clipped_crop = clipped.crop(base_bounds)
            surface = Image.new("RGBA", clipped_crop.size, (150, 154, 162, 0))
            surface.putalpha(mask_crop.point(lambda value: (int(value) * 72) // 255))
            combined = Image.alpha_composite(surface, clipped_crop)
        else:
            affine = render_contract._atlas_to_local_affine(
                slot,
                target_size[0],
                target_size[1],
                float(projection.get("xorigin", 0.0)) * scale,
                float(projection.get("yorigin", 0.0)) * scale,
            )
            warped = artwork.transform(
                target_size,
                Image.Transform.AFFINE,
                affine,
                resample=Image.Resampling.BILINEAR,
                fillcolor=(0, 0, 0, 0),
            )
            del artwork

            mask = base_mask.convert("L").resize(target_size, Image.Resampling.BILINEAR)
            multiplied_alpha = ImageChops.multiply(warped.getchannel("A"), mask)
            warped.putalpha(multiplied_alpha)

            scaled_bounds = tuple(int(round(value * scale)) for value in base_bounds)
            clipped_crop = warped.crop(scaled_bounds)
            mask_crop = mask.crop(scaled_bounds)
            del warped, mask, multiplied_alpha

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
            f"{section} 영역의 native-resolution projection 적용에 실패했습니다: {exc}"
        ) from exc


@lru_cache(maxsize=12)
def _render_cached(
    path_text: str,
    file_size: int,
    mtime_ns: int,
    section: str,
    game_folder_text: str,
    quality: str,
) -> RenderedLiverySection:
    quality = normalize_quality(quality)
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
        raise LiveryPreviewError(
            "C_livery에서 대상 Car ID를 확인할 수 없어 차량별 projection을 적용할 수 없습니다."
        )

    cache_path = _cache_path(
        path_text,
        file_size,
        mtime_ns,
        section,
        game_folder_text,
        quality,
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
        raise LiveryPreviewError(
            f"{section} 영역의 {len(layers):,}개 placement가 모두 완전 투명하여 표시할 픽셀이 없습니다."
        )

    width = 2048 * scale
    height = 1024 * scale
    try:
        rendered = renderer.render_typecode_layers_canvas(
            prepared_layers,
            width=width,
            height=height,
            raster_resolver=raster_resolver,
            strict_assets=False,
        )
    except Exception as exc:
        raise LiveryPreviewError(
            f"{section} 영역의 native FH6 도형을 {scale}× 해상도로 렌더링하지 못했습니다: {exc}"
        ) from exc
    if not rendered:
        raise LiveryPreviewError(f"{section} 영역에서 표시 가능한 이미지를 만들지 못했습니다.")

    projected = _projection_native_resolution(
        rendered,
        section,
        analysis.car_id,
        game_folder=game_folder,
        scale=scale,
    )
    preview_png = _checkerboard_native_resolution(projected, scale)
    _write_disk_cache(cache_path, preview_png)

    warnings = list(decoded.warnings)
    if invisible_count:
        warnings.append(
            f"{section}: {invisible_count}개의 완전 투명 native placement는 시각적 no-op으로 제외했습니다."
        )
    warnings.append(
        f"Native Resolution Test: 최종 projection crop을 {scale}× raster density로 유지했습니다."
    )

    return RenderedLiverySection(
        section=section,
        png_bytes=preview_png,
        placement_count=len(layers),
        skipped_raster_logos=0,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def render_livery_section_native_resolution_test(
    path: Path | str,
    section: str,
    quality: str = DEFAULT_QUALITY,
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
        )


def clear_native_resolution_test_cache() -> None:
    with _CACHE_LOCK:
        _render_cached.cache_clear()
