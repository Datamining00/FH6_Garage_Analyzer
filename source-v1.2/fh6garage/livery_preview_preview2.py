from __future__ import annotations

import hashlib
import io
import os
import threading
from functools import lru_cache
from pathlib import Path

from .exact_livery_preview import (
    ExactLiveryPreviewError,
    apply_exact_vehicle_projection,
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
    _expanded_crop_box,
    _file_signature,
    _load_backend,
    _validate_exact_assets_and_filter_noops,
)


PREVIEW2_CACHE_VERSION = "v14-preview2-r1"
QUALITY_DIMENSIONS = {
    "fast": (2048, 1024),
    "balanced": (3072, 1536),
    "high": (4096, 2048),
}
DEFAULT_QUALITY = "balanced"
_CACHE_LOCK = threading.RLock()


def normalize_quality(value: str | None) -> str:
    quality = str(value or DEFAULT_QUALITY).strip().lower()
    return quality if quality in QUALITY_DIMENSIONS else DEFAULT_QUALITY


def _app_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FH6GarageAnalyzer"
    return Path.home() / ".fh6garage"


def _disk_cache_dir() -> Path:
    return _app_data_dir() / "livery_preview_cache" / PREVIEW2_CACHE_VERSION


def _cache_key(
    path_text: str,
    file_size: int,
    mtime_ns: int,
    section: str,
    game_folder_text: str,
    quality: str,
) -> str:
    payload = "|".join(
        (
            PREVIEW2_CACHE_VERSION,
            KFPS_VENDOR_COMMIT,
            str(Path(path_text).resolve()),
            str(int(file_size)),
            str(int(mtime_ns)),
            str(section),
            str(Path(game_folder_text).resolve()),
            normalize_quality(quality),
        )
    )
    return hashlib.sha256(payload.encode("utf-8", errors="surrogatepass")).hexdigest()


def _cache_path(*args) -> Path:
    return _disk_cache_dir() / f"{_cache_key(*args)}.png"


def _read_disk_cache(path: Path) -> bytes | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return data


def _prune_disk_cache(root: Path, *, max_files: int = 240, max_bytes: int = 512 * 1024 * 1024) -> None:
    try:
        files = [item for item in root.glob("*.png") if item.is_file()]
        entries = []
        total = 0
        for item in files:
            try:
                stat = item.stat()
            except OSError:
                continue
            entries.append((int(stat.st_mtime_ns), int(stat.st_size), item))
            total += int(stat.st_size)
        entries.sort()
        while entries and (len(entries) > max_files or total > max_bytes):
            _mtime, size, item = entries.pop(0)
            try:
                item.unlink()
                total -= size
            except OSError:
                pass
    except OSError:
        return


def _write_disk_cache(path: Path, data: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)
        _prune_disk_cache(path.parent)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except Exception:
            pass


def _resize_to_exact_atlas(png_bytes: bytes, quality: str) -> bytes:
    width, height = QUALITY_DIMENSIONS[normalize_quality(quality)]
    if (width, height) == (2048, 1024):
        return png_bytes

    try:
        from PIL import Image

        with Image.open(io.BytesIO(png_bytes)) as source:
            image = source.convert("RGBA")
            if image.size != (width, height):
                raise LiveryPreviewError(
                    f"고해상도 렌더 캔버스 크기가 올바르지 않습니다: {image.size}"
                )
            image = image.resize((2048, 1024), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", compress_level=3)
            return buffer.getvalue()
    except LiveryPreviewError:
        raise
    except Exception as exc:
        raise LiveryPreviewError(f"고해상도 리버리 다운샘플링에 실패했습니다: {exc}") from exc


def _checkerboard_preview_fast(png_bytes: bytes) -> bytes:
    try:
        from PIL import Image, ImageDraw

        with Image.open(io.BytesIO(png_bytes)) as source:
            artwork = source.convert("RGBA")

        alpha_bbox = artwork.getchannel("A").getbbox()
        if alpha_bbox:
            crop_box = _expanded_crop_box(alpha_bbox, artwork.size)
            if crop_box != (0, 0, artwork.width, artwork.height):
                artwork = artwork.crop(crop_box)

        background = Image.new("RGBA", artwork.size, (54, 56, 64, 255))
        draw = ImageDraw.Draw(background)
        tile = 32
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
        raise LiveryPreviewError(f"미리보기 배경 합성에 실패했습니다: {exc}") from exc


@lru_cache(maxsize=32)
def _render_cached(
    path_text: str,
    file_size: int,
    mtime_ns: int,
    section: str,
    game_folder_text: str,
    quality: str,
) -> RenderedLiverySection:
    quality = normalize_quality(quality)
    source = Path(path_text)
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

    prepared_layers, invisible_count = _validate_exact_assets_and_filter_noops(
        renderer,
        layers,
        raster_resolver,
    )
    if not prepared_layers:
        raise LiveryPreviewError(
            f"{section} 영역의 {len(layers):,}개 placement가 모두 완전 투명하여 표시할 픽셀이 없습니다."
        )

    width, height = QUALITY_DIMENSIONS[quality]
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
            f"{section} 영역의 native FH6 도형을 정확하게 렌더링하지 못했습니다: {exc}"
        ) from exc
    if not rendered:
        raise LiveryPreviewError(f"{section} 영역에서 표시 가능한 이미지를 만들지 못했습니다.")

    rendered = _resize_to_exact_atlas(rendered, quality)
    try:
        projected = apply_exact_vehicle_projection(
            rendered,
            section,
            analysis.car_id,
            game_folder=game_folder,
        )
    except ExactLiveryPreviewError as exc:
        raise LiveryPreviewError(str(exc)) from exc

    preview_png = _checkerboard_preview_fast(projected)
    _write_disk_cache(cache_path, preview_png)

    warnings = list(decoded.warnings)
    if invisible_count:
        warnings.append(
            f"{section}: {invisible_count}개의 완전 투명 native placement는 시각적 no-op으로 제외했습니다."
        )

    return RenderedLiverySection(
        section=section,
        png_bytes=preview_png,
        placement_count=len(layers),
        skipped_raster_logos=0,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def render_livery_section_preview2(
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


def clear_preview2_memory_cache() -> None:
    with _CACHE_LOCK:
        _render_cached.cache_clear()


def clear_preview2_disk_cache() -> None:
    root = _disk_cache_dir()
    try:
        for item in root.glob("*.png"):
            item.unlink(missing_ok=True)
    except OSError:
        pass
    clear_preview2_memory_cache()
