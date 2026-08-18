from __future__ import annotations

import importlib
import io
import sys
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


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
    """Expose the pinned KFPS source tree during source-mode development.

    PyInstaller bundles the selected KFPS modules as hidden imports. In source
    mode the exact upstream tree is placed under ``vendor/kfps`` by the v1.4
    build workflow, so adding that directory to ``sys.path`` keeps both modes
    on the same decoder/renderer implementation.
    """
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


def _checkerboard_preview(png_bytes: bytes) -> bytes:
    """Composite transparent artwork over a neutral checkerboard for visibility."""
    try:
        from PIL import Image, ImageDraw

        with Image.open(io.BytesIO(png_bytes)) as source:
            artwork = source.convert("RGBA")
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
    source = Path(path)
    decoded = decode_livery_preview(source)
    if section not in decoded.sections:
        raise LiveryPreviewError(f"지원하지 않는 리버리 영역입니다: {section}")

    layers = list(decoded.sections[section])
    if not layers:
        raise LiveryPreviewError("이 영역에는 표시할 리버리 배치가 없습니다.")

    _decoder, renderer = _load_backend()
    skipped_raster = sum(1 for layer in layers if bool(layer.get("is_raster_logo")))
    try:
        rendered = renderer.render_typecode_layers_canvas(
            layers,
            width=2048,
            height=1024,
            strict_assets=False,
        )
    except Exception as exc:
        raise LiveryPreviewError(f"{section} 영역 렌더링에 실패했습니다: {exc}") from exc
    if not rendered:
        raise LiveryPreviewError(f"{section} 영역에서 표시 가능한 이미지를 만들지 못했습니다.")

    visible_png = _checkerboard_preview(rendered)
    warnings = list(decoded.warnings)
    if skipped_raster:
        warnings.append(
            f"게임 내장 래스터 로고 {skipped_raster}개는 현재 미리보기에서 생략되었습니다."
        )
    return RenderedLiverySection(
        section=section,
        png_bytes=visible_png,
        placement_count=len(layers),
        skipped_raster_logos=skipped_raster,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def clear_livery_preview_cache() -> None:
    with _CACHE_LOCK:
        _decode_cached.cache_clear()
