from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from . import livery_preview as core
from . import livery_preview_mask_semantics as mask_semantics
from . import livery_preview_quality_pipeline as quality_pipeline
from . import livery_preview_tiled_quality as tiled_quality
from . import v1_4_preview_final_ui_patch as final_ui
from . import livery_simple_layer_native_debug as base
from .exact_livery_preview import require_fh6_game_folder
from .livery_preview import LiveryPreviewError


_PATCHED = False
_ORIGINAL_FINAL_RENDER: Callable | None = None


def _split_range(start: int, end: int, count: int = 8) -> list[tuple[int, int]]:
    start = int(start)
    end = int(end)
    count = max(1, min(int(count), max(1, end - start)))
    out: list[tuple[int, int]] = []
    length = end - start
    for index in range(count):
        left = start + (length * index) // count
        right = start + (length * (index + 1)) // count
        if right > left:
            out.append((left, right))
    return out


def _dark_occluder_score(png_bytes: bytes) -> float:
    """Return a cheap score for unusually large near-black visible coverage.

    The checkerboard background used by the preview starts above this threshold,
    so the score mostly reacts to actual very dark livery artwork.  It is only a
    probe-selection heuristic; it never changes the normal renderer.
    """
    import io
    from PIL import Image

    with Image.open(io.BytesIO(png_bytes)) as opened:
        image = opened.convert("RGB")
    image.thumbnail((320, 180), Image.Resampling.BILINEAR)
    total = max(1, image.width * image.height)
    dark = 0
    for red, green, blue in image.getdata():
        if red <= 28 and green <= 28 and blue <= 28:
            dark += 1
    return dark / total


def _layer_record(renderer: Any, layer_index: int, layer: dict[str, Any]) -> dict[str, Any]:
    try:
        type_code = int(layer.get("type", 0))
    except (TypeError, ValueError):
        type_code = 0
    word, identity = base._shape_identity(renderer, layer)
    try:
        source_offset = int(layer.get("source_offset"))
    except (TypeError, ValueError):
        source_offset = None

    resource = None
    resolver = getattr(renderer, "_resolve_vinyl_resource", None)
    if callable(resolver):
        try:
            resolved = resolver(type_code, layer)
            if resolved:
                resource = [str(resolved[0]), int(resolved[1])]
        except Exception:
            resource = None

    return {
        "layer_index": int(layer_index),
        "source_offset": source_offset,
        "source_section": layer.get("source_section") or layer.get("section"),
        "type": type_code,
        "type_low_word": int(type_code) & 0xFFFF,
        "shape_word": int(word),
        "shape_word_hex": f"0x{int(word) & 0xFFFF:04X}",
        "identity": identity,
        "resolved_resource": resource,
        "mask": bool(mask_semantics._is_mask(renderer, layer)),
        "source_marker": layer.get("source_marker") or layer.get("marker_hex"),
        "data": list(layer.get("data") or []),
        "color": list(layer.get("color") or []),
        "is_raster_logo": bool(layer.get("is_raster_logo")),
        "raster_id": layer.get("raster_id"),
    }


def _raw_window(source: Path, source_offset: int | None) -> dict[str, Any] | None:
    if source_offset is None:
        return None
    try:
        decoder, _renderer = core._load_backend()
        unwrap = getattr(decoder, "unwrap_forza_container", None)
        if not callable(unwrap):
            return None
        payload = bytes(unwrap(source))
        start = max(0, int(source_offset) - 64)
        end = min(len(payload), int(source_offset) + 128)
        return {
            "payload_length": len(payload),
            "start_offset": start,
            "end_offset": end,
            "target_offset": int(source_offset),
            "hex": payload[start:end].hex(" "),
        }
    except Exception as exc:
        return {"error": str(exc), "target_offset": int(source_offset)}


def _write_missing_mask_log(
    renderer: Any,
    layers: list[dict[str, Any]],
    layer_index: int,
    error_text: str,
) -> None:
    source_value = getattr(base._TLS, "simple_debug_source", None)
    section = str(getattr(base._TLS, "simple_debug_section", "") or "")
    if not source_value or not section:
        return
    source = Path(source_value)
    zero_index = int(layer_index) - 1
    if zero_index < 0 or zero_index >= len(layers):
        return

    target = _layer_record(renderer, layer_index, layers[zero_index])
    neighbor_start = max(0, zero_index - 3)
    neighbor_end = min(len(layers), zero_index + 4)
    neighbors = [
        _layer_record(renderer, index + 1, layers[index])
        for index in range(neighbor_start, neighbor_end)
    ]

    payload = {
        "diagnostic_version": 2,
        "source": str(source),
        "section": section,
        "error": str(error_text),
        "target": target,
        "neighbors": neighbors,
        "raw_payload_window": _raw_window(source, target.get("source_offset")),
        "note": "Fatal missing native mask. The mask is not skipped because doing so can corrupt the whole composition.",
    }
    output_dir = base._probe_output_dir(source)
    (output_dir / f"{section}-missing-native-mask.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _tolerant_validator_v2(renderer: Any, layers, raster_resolver):
    layer_list = list(layers)
    try:
        return base._tolerant_validator(renderer, layer_list, raster_resolver)
    except LiveryPreviewError as exc:
        text = str(exc)
        match = re.search(r"layer\s+(\d+).*?mask", text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            try:
                _write_missing_mask_log(renderer, layer_list, int(match.group(1)), text)
            except Exception:
                pass
        raise


def _generate_probe_v2(source: Path, section: str) -> None:
    try:
        signature = core._file_signature(source)
        decoded = core._decode_cached(*signature)
        layers = list(decoded.sections.get(section) or ())
        if len(layers) < 2:
            return
        analysis = core._analysis_cached(*signature)
        if int(getattr(analysis, "car_id", 0) or 0) <= 0:
            return
        game_folder = Path(require_fh6_game_folder())

        coarse_ranges = _split_range(0, len(layers), 8)
        coarse_rendered: list[tuple[str, bytes]] = []
        coarse_scores: list[dict[str, Any]] = []
        previous_log = getattr(base._TLS, "missing_native", None)
        base._TLS.missing_native = []
        try:
            for start, end in coarse_ranges:
                label = f"layers {start + 1}-{end}"
                png = base._render_subset(source, section, layers[start:end], analysis.car_id, game_folder)
                coarse_rendered.append((label, png))
                coarse_scores.append(
                    {
                        "start_layer": start + 1,
                        "end_layer": end,
                        "dark_score": _dark_occluder_score(png),
                    }
                )
        finally:
            base._TLS.missing_native = previous_log

        output_dir = base._probe_output_dir(source)
        (output_dir / f"{section}-8way-layer-probe.png").write_bytes(base._make_contact_sheet(coarse_rendered))

        selected_index = max(range(len(coarse_scores)), key=lambda index: coarse_scores[index]["dark_score"])
        selected_start, selected_end = coarse_ranges[selected_index]
        refined_ranges = _split_range(selected_start, selected_end, 8)
        refined_rendered: list[tuple[str, bytes]] = []

        previous_log = getattr(base._TLS, "missing_native", None)
        base._TLS.missing_native = []
        try:
            for start, end in refined_ranges:
                label = f"layers {start + 1}-{end}"
                png = base._render_subset(source, section, layers[start:end], analysis.car_id, game_folder)
                refined_rendered.append((label, png))
        finally:
            base._TLS.missing_native = previous_log

        (output_dir / f"{section}-8way-layer-probe-refined.png").write_bytes(
            base._make_contact_sheet(refined_rendered)
        )
        metadata = {
            "diagnostic_version": 2,
            "source": str(source),
            "section": section,
            "layer_count": len(layers),
            "coarse_ranges": coarse_scores,
            "auto_selected_coarse_range": {
                "start_layer": selected_start + 1,
                "end_layer": selected_end,
                "reason": "largest near-black visible coverage in coarse probe",
            },
            "refined_ranges": [
                {"start_layer": start + 1, "end_layer": end}
                for start, end in refined_ranges
            ],
            "note": "The refined sheet is diagnostic only and does not alter normal livery rendering.",
        }
        (output_dir / f"{section}-8way-layer-probe-refined.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        try:
            output_dir = base._probe_output_dir(source)
            (output_dir / f"{section}-8way-layer-probe-refined-error.txt").write_text(
                str(exc), encoding="utf-8"
            )
        except Exception:
            pass


def _scaled_render_v2(path: Path | str, section: str, scale: int = 4):
    original = _ORIGINAL_FINAL_RENDER
    if original is None:
        raise LiveryPreviewError("simple layer/native debug v2 renderer가 아직 설치되지 않았습니다.")
    previous_source = getattr(base._TLS, "simple_debug_source", None)
    previous_section = getattr(base._TLS, "simple_debug_section", None)
    base._TLS.simple_debug_source = str(Path(path))
    base._TLS.simple_debug_section = str(section)
    try:
        return original(path, section, scale)
    finally:
        if previous_source is None:
            try:
                delattr(base._TLS, "simple_debug_source")
            except AttributeError:
                pass
        else:
            base._TLS.simple_debug_source = previous_source
        if previous_section is None:
            try:
                delattr(base._TLS, "simple_debug_section")
            except AttributeError:
                pass
        else:
            base._TLS.simple_debug_section = previous_section


def install_simple_layer_native_debug_v2() -> None:
    global _PATCHED, _ORIGINAL_FINAL_RENDER
    if _PATCHED:
        return

    base.install_simple_layer_native_debug()

    # The v1 probe scheduler resolves this module global at thread start, so a
    # direct replacement upgrades the same simple background workflow to an
    # automatically refined second pass.
    base._generate_probe = _generate_probe_v2

    # Preserve v1's visible-shape skip policy, but capture fatal missing masks
    # with enough local context to diagnose bad identity/alignment separately.
    core._validate_exact_assets_and_filter_noops = _tolerant_validator_v2
    quality_pipeline._validate_exact_assets_and_filter_noops = _tolerant_validator_v2
    mask_semantics.validate_exact_assets_and_filter_noops = _tolerant_validator_v2
    tiled_quality.validate_exact_assets_and_filter_noops = _tolerant_validator_v2

    _ORIGINAL_FINAL_RENDER = final_ui.render_livery_section_scaled
    final_ui.render_livery_section_scaled = _scaled_render_v2

    _PATCHED = True
