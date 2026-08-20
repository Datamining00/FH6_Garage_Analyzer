from __future__ import annotations

import hashlib
import io
import json
import threading
from pathlib import Path
from typing import Any

from . import livery_preview as core
from . import livery_preview_mask_semantics as mask_semantics
from . import livery_preview_quality_pipeline as quality_pipeline
from . import livery_preview_tiled_quality as tiled_quality
from . import v1_4_preview_final_ui_patch as final_ui
from .exact_livery_preview import ExactLiveryPreviewError, raster_resolver_for_game, require_fh6_game_folder
from .livery_preview import LiveryPreviewError
from .livery_preview_native_resolution_test import _checkerboard_native_resolution
from .livery_preview_preview2 import _app_data_dir, _preflight_raster_layers


_PATCHED = False
_TLS = threading.local()
_PROBE_LOCK = threading.Lock()
_PROBE_STARTED: set[tuple[str, str, int, int]] = set()

_ORIGINAL_CORE_VALIDATOR = core._validate_exact_assets_and_filter_noops
_ORIGINAL_SCALED_RENDER = tiled_quality.render_livery_section_scaled


def _is_missing_native_error(exc: Exception) -> bool:
    text = str(exc)
    return (
        "native FH6 도형" in text
        or "native resource" in text
        or "exact native resource" in text
    )


def _shape_identity(renderer: Any, layer: dict[str, Any]) -> tuple[int, str]:
    try:
        type_code = int(layer.get("type", 0))
    except (TypeError, ValueError):
        type_code = 0
    shape_word_for = getattr(renderer, "_shape_word_from_shape", None)
    if callable(shape_word_for):
        try:
            word = int(shape_word_for(layer, type_code)) & 0xFFFF
            return word, f"shape word 0x{word:04X}"
        except Exception:
            pass
    return 0, f"type {type_code}"


def _record_missing_native(renderer: Any, layer_index: int, layer: dict[str, Any]) -> None:
    log = getattr(_TLS, "missing_native", None)
    if not isinstance(log, list):
        return
    word, identity = _shape_identity(renderer, layer)
    try:
        source_offset = int(layer.get("source_offset"))
    except (TypeError, ValueError):
        source_offset = None
    try:
        type_code = int(layer.get("type", 0))
    except (TypeError, ValueError):
        type_code = 0
    log.append(
        {
            "layer_index": int(layer_index),
            "source_offset": source_offset,
            "type": type_code,
            "shape_word": word,
            "identity": identity,
            "mask": False,
        }
    )


def _tolerant_validator(renderer: Any, layers, raster_resolver):
    """Skip only missing *visible* native shapes; missing masks remain fatal.

    This is intentionally a runtime test policy, not a permanent decoder rule.
    Every layer is delegated to the existing strict validator one at a time so
    all existing alpha, raster, and mask semantics remain unchanged.
    """

    visible: list[dict[str, Any]] = []
    skipped_or_invisible = 0

    for layer_index, layer in enumerate(list(layers), 1):
        try:
            one_visible, one_skipped = _ORIGINAL_CORE_VALIDATOR(renderer, [layer], raster_resolver)
        except LiveryPreviewError as exc:
            if not _is_missing_native_error(exc):
                raise
            if mask_semantics._is_mask(renderer, layer):
                word, identity = _shape_identity(renderer, layer)
                del word
                raise LiveryPreviewError(
                    f"layer {layer_index}의 mask에 정확한 native FH6 도형 리소스가 없습니다: {identity}"
                ) from exc
            _record_missing_native(renderer, layer_index, layer)
            skipped_or_invisible += 1
            continue

        visible.extend(one_visible)
        skipped_or_invisible += int(one_skipped)

    return visible, skipped_or_invisible


def _probe_output_dir(source: Path) -> Path:
    digest = hashlib.sha256(str(source.resolve()).encode("utf-8", errors="surrogatepass")).hexdigest()[:16]
    folder = _app_data_dir() / "livery_layer_probe" / f"{source.parent.name}-{digest}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _render_subset(source: Path, section: str, layers: list[dict[str, Any]], car_id: int, game_folder: Path) -> bytes:
    _decoder, renderer = core._load_backend()
    raster_resolver = None
    if any(bool(layer.get("is_raster_logo")) for layer in layers):
        raster_resolver = raster_resolver_for_game(game_folder)
        _preflight_raster_layers(layers, raster_resolver)

    prepared, _skipped = _tolerant_validator(renderer, layers, raster_resolver)
    if not prepared:
        from PIL import Image

        blank = Image.new("RGB", (768, 384), (58, 60, 68))
        out = io.BytesIO()
        blank.save(out, format="PNG")
        return out.getvalue()

    config = quality_pipeline.RenderConfig(
        scale=1,
        sharpen=False,
        base_samples=1,
        detail_samples=2,
    ).normalized()
    rendered = quality_pipeline._render_native_high_precision(
        renderer,
        prepared,
        width=2048,
        height=1024,
        scale=1,
        config=config,
        raster_resolver=raster_resolver,
    )
    if not rendered:
        raise LiveryPreviewError("layer probe에서 표시 가능한 이미지를 만들지 못했습니다.")
    projected = quality_pipeline._projection_high_precision(
        rendered,
        section,
        int(car_id),
        game_folder=game_folder,
        scale=1,
        sharpen=False,
    )
    return _checkerboard_native_resolution(projected, 1)


def _make_contact_sheet(images: list[tuple[str, bytes]]) -> bytes:
    from PIL import Image, ImageDraw

    cell_w, cell_h = 480, 270
    label_h = 28
    columns = 4
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGB", (cell_w * columns, (cell_h + label_h) * rows), (36, 38, 44))
    draw = ImageDraw.Draw(sheet)

    for index, (label, png_bytes) in enumerate(images):
        col = index % columns
        row = index // columns
        x0 = col * cell_w
        y0 = row * (cell_h + label_h)
        draw.rectangle((x0, y0, x0 + cell_w - 1, y0 + label_h - 1), fill=(28, 30, 36))
        draw.text((x0 + 8, y0 + 7), label, fill=(235, 235, 240))
        with Image.open(io.BytesIO(png_bytes)) as opened:
            image = opened.convert("RGB")
        image.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
        px = x0 + (cell_w - image.width) // 2
        py = y0 + label_h + (cell_h - image.height) // 2
        sheet.paste(image, (px, py))

    out = io.BytesIO()
    sheet.save(out, format="PNG", compress_level=3)
    return out.getvalue()


def _generate_probe(source: Path, section: str) -> None:
    try:
        signature = core._file_signature(source)
        decoded = core._decode_cached(*signature)
        layers = list(decoded.sections.get(section) or ())
        if len(layers) < 2:
            return
        analysis = core._analysis_cached(*signature)
        if int(getattr(analysis, "car_id", 0) or 0) <= 0:
            return
        game_folder = require_fh6_game_folder()

        chunk_count = min(8, len(layers))
        ranges: list[tuple[int, int]] = []
        for chunk_index in range(chunk_count):
            start = (len(layers) * chunk_index) // chunk_count
            end = (len(layers) * (chunk_index + 1)) // chunk_count
            if end > start:
                ranges.append((start, end))

        rendered: list[tuple[str, bytes]] = []
        _TLS.missing_native = []
        for start, end in ranges:
            label = f"layers {start + 1}-{end}"
            png = _render_subset(source, section, layers[start:end], analysis.car_id, Path(game_folder))
            rendered.append((label, png))

        output_dir = _probe_output_dir(source)
        sheet_path = output_dir / f"{section}-8way-layer-probe.png"
        sheet_path.write_bytes(_make_contact_sheet(rendered))
        metadata = {
            "source": str(source),
            "section": section,
            "layer_count": len(layers),
            "ranges": [
                {"start_layer": start + 1, "end_layer": end}
                for start, end in ranges
            ],
            "note": "Find the panel containing the incorrect blocking shape; the next pass can isolate only that range.",
        }
        (output_dir / f"{section}-8way-layer-probe.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        try:
            output_dir = _probe_output_dir(source)
            (output_dir / f"{section}-8way-layer-probe-error.txt").write_text(str(exc), encoding="utf-8")
        except Exception:
            pass


def _schedule_probe(source: Path, section: str) -> None:
    if section not in {"Left", "Right"}:
        return
    try:
        stat = source.stat()
        key = (str(source.resolve()), str(section), int(stat.st_size), int(stat.st_mtime_ns))
    except OSError:
        return
    with _PROBE_LOCK:
        if key in _PROBE_STARTED:
            return
        _PROBE_STARTED.add(key)
    thread = threading.Thread(
        target=_generate_probe,
        args=(source, section),
        name=f"fh6-layer-probe-{section.lower()}",
        daemon=True,
    )
    thread.start()


def _write_missing_native_log(source: Path, section: str, entries: list[dict[str, Any]]) -> None:
    if not entries:
        return
    output_dir = _probe_output_dir(source)
    payload = {
        "source": str(source),
        "section": section,
        "policy": "missing visible native shapes are skipped; missing native masks remain fatal",
        "skipped_missing_native": entries,
    }
    (output_dir / f"{section}-missing-native-skipped.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _scaled_render_with_simple_debug(path: Path | str, section: str, scale: int = 4):
    source = Path(path)
    _TLS.missing_native = []
    try:
        result = _ORIGINAL_SCALED_RENDER(source, section, scale)
        entries = list(getattr(_TLS, "missing_native", []) or [])
        _write_missing_native_log(source, section, entries)
        _schedule_probe(source, section)
        return result
    finally:
        _TLS.missing_native = []


def install_simple_layer_native_debug() -> None:
    global _PATCHED
    if _PATCHED:
        return

    core._validate_exact_assets_and_filter_noops = _tolerant_validator
    quality_pipeline._validate_exact_assets_and_filter_noops = _tolerant_validator
    mask_semantics.validate_exact_assets_and_filter_noops = _tolerant_validator
    tiled_quality.validate_exact_assets_and_filter_noops = _tolerant_validator

    # The final preview UI imported this callable directly, so patch its module
    # binding as well. The normal full render remains unchanged except for the
    # missing-visible-native policy; the 8-way probe is generated in background.
    final_ui.render_livery_section_scaled = _scaled_render_with_simple_debug

    try:
        core.clear_livery_preview_cache()
    except Exception:
        pass
    try:
        quality_pipeline.clear_quality_pipeline_cache()
    except Exception:
        pass
    try:
        tiled_quality.clear_tiled_quality_cache()
    except Exception:
        pass

    _PATCHED = True
