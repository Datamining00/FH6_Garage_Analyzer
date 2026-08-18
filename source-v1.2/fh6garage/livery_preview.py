from __future__ import annotations

import importlib
import io
import sys
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .exact_livery_preview import (
    ExactLiveryPreviewError,
    apply_exact_vehicle_projection,
    raster_resolver_for_game,
    require_fh6_game_folder,
)
from .livery_analysis import LiveryAnalysisError, analyze_livery_file


KFPS_VENDOR_COMMIT = "8965780b8966e09d2f2a17e4d0684cdd44d7437c"


class LiveryPreviewError(RuntimeError):
    """Raised when an FH6 livery section cannot be decoded or rendered."""


@dataclass(frozen=True, slots=True)
class DecodedLiveryPreview:
    sections: dict[str, tuple[dict[str, Any], ...]]
    warnings: tuple[str, ...]
    total_layers: int
    raster_logo_count: int


@dataclass(frozen=True, slots=True)
class RenderedLiverySection:
    section: str
    png_bytes: bytes
    placement_count: int
    skipped_raster_logos: int
    warnings: tuple[str, ...]


_CACHE_LOCK = threading.RLock()


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _vendor_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    source_vendor = _source_root() / "vendor" / "kfps"
    candidates.append(source_vendor)
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / "vendor" / "kfps")
    return tuple(candidates)


def _prepare_vendor_import_path() -> None:
    """Expose the pinned KFPS source tree during source-mode development."""
    for candidate in _vendor_candidates():
        if candidate.is_dir():
            text = str(candidate)
            if text not in sys.path:
                sys.path.insert(0, text)
            return


def preview_backend_available() -> bool:
    try:
        _load_backend()
        return True
    except LiveryPreviewError:
        return False


def _load_backend():
    _prepare_vendor_import_path()
    try:
        decoder = importlib.import_module("tools.cgroup.forza_source_decoder")
        renderer = importlib.import_module("json_preview_renderer")
    except Exception as exc:
        raise LiveryPreviewError(
            "리버리 미리보기 구성요소를 불러오지 못했습니다. "
            "v1.4 정식 빌드에서 다시 시도해 주세요."
        ) from exc
    return decoder, renderer


def _file_signature(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise LiveryPreviewError(f"C_livery 파일 정보를 읽지 못했습니다: {exc}") from exc
    return str(path.resolve()), int(stat.st_size), int(stat.st_mtime_ns)


@lru_cache(maxsize=16)
def _decode_cached(path_text: str, file_size: int, mtime_ns: int) -> DecodedLiveryPreview:
    del file_size, mtime_ns
    decoder, _renderer = _load_backend()
    source = Path(path_text)
    try:
        decoded = decoder.decode_forza_source(source, allow_locked=True, game="fh6")
    except Exception as exc:
        raise LiveryPreviewError(f"C_livery placement 해석에 실패했습니다: {exc}") from exc

    section_names = tuple(getattr(decoder, "LIVERY_SECTION_NAMES", ()))
    if not section_names:
        raise LiveryPreviewError("리버리 영역 정의를 찾지 못했습니다.")

    mutable: dict[str, list[dict[str, Any]]] = {name: [] for name in section_names}
    raster_logo_count = 0
    for layer in list(getattr(decoded, "layers", ()) or ()):
        if not isinstance(layer, dict):
            continue
        section = str(layer.get("source_section") or "")
        if section not in mutable:
            continue
        mutable[section].append(layer)
        if bool(layer.get("is_raster_logo")):
            raster_logo_count += 1

    report = getattr(decoded, "report", {}) or {}
    warnings: list[str] = []
    for key in ("warnings", "privacy_warnings", "identity_warnings"):
        value = report.get(key) if isinstance(report, dict) else None
        if isinstance(value, (list, tuple)):
            warnings.extend(str(item) for item in value if str(item).strip())

    sections = {name: tuple(items) for name, items in mutable.items()}
    total_layers = sum(len(items) for items in sections.values())
    return DecodedLiveryPreview(
        sections=sections,
        warnings=tuple(dict.fromkeys(warnings)),
        total_layers=total_layers,
        raster_logo_count=raster_logo_count,
    )


def decode_livery_preview(path: Path | str) -> DecodedLiveryPreview:
    source = Path(path)
    if not source.is_file():
        raise LiveryPreviewError("C_livery 파일을 찾을 수 없습니다.")
    signature = _file_signature(source)
    with _CACHE_LOCK:
        return _decode_cached(*signature)


def _expanded_crop_box(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
    *,
    padding: int = 32,
    minimum_size: tuple[int, int] = (480, 240),
) -> tuple[int, int, int, int]:
    """Expand a visible bounding box while keeping enough surrounding context."""
    image_width, image_height = image_size
    left, top, right, bottom = bbox

    def axis(start: int, end: int, limit: int, pad: int, minimum: int) -> tuple[int, int]:
        padded_start = max(0, int(start) - pad)
        padded_end = min(limit, int(end) + pad)
        target = min(limit, max(padded_end - padded_start, minimum))
        center = (float(start) + float(end)) / 2.0
        new_start = int(round(center - target / 2.0))
        new_start = max(0, min(new_start, limit - target))
        return new_start, new_start + target

    crop_left, crop_right = axis(left, right, image_width, padding, minimum_size[0])
    crop_top, crop_bottom = axis(top, bottom, image_height, padding, minimum_size[1])
    return crop_left, crop_top, crop_right, crop_bottom


def _checkerboard_preview(png_bytes: bytes) -> bytes:
    """Composite the exact masked projection over a neutral checkerboard."""
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
        output.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    except Exception as exc:
        raise LiveryPreviewError(f"미리보기 배경 합성에 실패했습니다: {exc}") from exc


def render_livery_section(path: Path | str, section: str) -> RenderedLiverySection:
    """Render one section using native shapes and the target car's exact FH6 mask."""
    source = Path(path)
    decoded = decode_livery_preview(source)
    if section not in decoded.sections:
        raise LiveryPreviewError(f"지원하지 않는 리버리 영역입니다: {section}")

    layers = list(decoded.sections[section])
    if not layers:
        raise LiveryPreviewError("이 영역에는 표시할 리버리 배치가 없습니다.")

    try:
        analysis = analyze_livery_file(source)
    except LiveryAnalysisError as exc:
        raise LiveryPreviewError(f"리버리의 대상 차량을 확인하지 못했습니다: {exc}") from exc
    if analysis.car_id <= 0:
        raise LiveryPreviewError(
            "C_livery에서 대상 Car ID를 확인할 수 없어 차량별 projection을 적용할 수 없습니다."
        )

    try:
        game_folder = require_fh6_game_folder()
    except ExactLiveryPreviewError as exc:
        raise LiveryPreviewError(str(exc)) from exc

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

    try:
        # Fail closed: every vector geometry and every raster decal must resolve.
        # Never substitute circles/rectangles for unknown native resources.
        rendered = renderer.render_typecode_layers_canvas(
            layers,
            width=2048,
            height=1024,
            raster_resolver=raster_resolver,
            strict_assets=True,
        )
    except Exception as exc:
        raise LiveryPreviewError(
            f"{section} 영역의 native FH6 도형을 정확하게 렌더링하지 못했습니다: {exc}"
        ) from exc
    if not rendered:
        raise LiveryPreviewError(f"{section} 영역에서 표시 가능한 이미지를 만들지 못했습니다.")

    try:
        projected = apply_exact_vehicle_projection(
            rendered,
            section,
            analysis.car_id,
            game_folder=game_folder,
        )
    except ExactLiveryPreviewError as exc:
        raise LiveryPreviewError(str(exc)) from exc

    return RenderedLiverySection(
        section=section,
        png_bytes=_checkerboard_preview(projected),
        placement_count=len(layers),
        skipped_raster_logos=0,
        warnings=decoded.warnings,
    )


def clear_livery_preview_cache() -> None:
    with _CACHE_LOCK:
        _decode_cached.cache_clear()
