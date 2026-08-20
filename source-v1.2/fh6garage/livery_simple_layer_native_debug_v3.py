from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

from . import livery_preview as core
from . import livery_preview_mask_semantics as mask_semantics
from . import livery_simple_layer_native_debug as base
from . import livery_simple_layer_native_debug_v2 as v2
from .exact_livery_preview import require_fh6_game_folder


_PATCHED = False


def _direct_shape_word_at(payload: bytes, pos: int) -> int | None:
    if pos < 0 or pos >= len(payload):
        return None
    if payload[pos : pos + 2] in (b"\x00\x02", b"\x01\x02"):
        if pos + 4 > len(payload):
            return None
        return struct.unpack_from("<H", payload, pos + 2)[0]
    if payload[pos] == 0x02:
        if pos + 3 > len(payload):
            return None
        return struct.unpack_from("<H", payload, pos + 1)[0]
    return None


def _locate_source_record_in_payload(
    payload: bytes,
    relative_source_offset: int | None,
    shape_word: int | None,
) -> dict[str, Any] | None:
    if relative_source_offset is None:
        return None
    gyvl_offset = payload.find(b"gyvl")
    layer_data_base = gyvl_offset + 0x15 if gyvl_offset >= 0 else 0
    expected = layer_data_base + int(relative_source_offset)
    target_word = None if shape_word is None else int(shape_word) & 0xFFFF

    candidates: list[int] = []
    if 0 <= expected < len(payload):
        candidates.append(expected)
    for distance in range(1, 129):
        for pos in (expected - distance, expected + distance):
            if 0 <= pos < len(payload):
                candidates.append(pos)

    matched_offset = None
    observed_word = None
    for pos in candidates:
        word = _direct_shape_word_at(payload, pos)
        if word is None:
            continue
        if target_word is None or word == target_word:
            matched_offset = pos
            observed_word = word
            break

    if matched_offset is None:
        word = _direct_shape_word_at(payload, expected)
        observed_word = word

    return {
        "gyvl_offset": gyvl_offset,
        "layer_data_base": layer_data_base,
        "relative_source_offset": int(relative_source_offset),
        "expected_absolute_offset": expected,
        "matched_absolute_offset": matched_offset,
        "matched_shape_word": observed_word,
        "matched": matched_offset is not None,
    }


def _raw_window_v3(
    source: Path,
    source_offset: int | None,
    shape_word: int | None,
) -> dict[str, Any] | None:
    if source_offset is None:
        return None
    try:
        decoder, _renderer = core._load_backend()
        unwrap = getattr(decoder, "unwrap_forza_container", None)
        if not callable(unwrap):
            return None
        payload = bytes(unwrap(source))
        location = _locate_source_record_in_payload(payload, source_offset, shape_word)
        if not location:
            return None
        absolute = location.get("matched_absolute_offset")
        if absolute is None:
            absolute = location.get("expected_absolute_offset")
        absolute = int(absolute)
        start = max(0, absolute - 64)
        end = min(len(payload), absolute + 128)
        return {
            "payload_length": len(payload),
            "location": location,
            "start_offset": start,
            "end_offset": end,
            "absolute_target_offset": absolute,
            "hex": payload[start:end].hex(" "),
        }
    except Exception as exc:
        return {"error": str(exc), "relative_source_offset": int(source_offset)}


def _angle_distance(a: float, b: float) -> float:
    delta = abs((float(a) - float(b)) % 360.0)
    return min(delta, 360.0 - delta)


def _mirror_similarity(target: dict[str, Any], candidate: dict[str, Any]) -> float:
    td = list(target.get("data") or [])
    cd = list(candidate.get("data") or [])
    if len(td) < 5 or len(cd) < 5:
        return float("inf")

    tx, ty, tsx, tsy, trot = (float(td[i]) for i in range(5))
    cx, cy, csx, csy, crot = (float(cd[i]) for i in range(5))

    def rel(a: float, b: float, floor: float = 1.0) -> float:
        return abs(a - b) / max(floor, abs(a), abs(b))

    mirrored_rot = (-trot) % 360.0
    return (
        rel(abs(cx), abs(tx))
        + rel(cy, ty)
        + rel(abs(csx), abs(tsx), 0.05)
        + rel(abs(csy), abs(tsy), 0.05)
        + (_angle_distance(crot, mirrored_rot) / 180.0)
    )


def _opposite_mask_candidates(
    source: Path,
    section: str,
    target: dict[str, Any],
    limit: int = 12,
) -> list[dict[str, Any]]:
    opposite = {"Left": "Right", "Right": "Left"}.get(section)
    if not opposite:
        return []
    try:
        signature = core._file_signature(source)
        decoded = core._decode_cached(*signature)
        layers = list(decoded.sections.get(opposite) or ())
        _decoder, renderer = core._load_backend()
    except Exception:
        return []

    ranked: list[tuple[float, dict[str, Any]]] = []
    for index, layer in enumerate(layers, 1):
        try:
            if not mask_semantics._is_mask(renderer, layer):
                continue
            record = v2._layer_record(renderer, index, layer)
            score = _mirror_similarity(target, record)
            if not math.isfinite(score):
                continue
            record["mirror_similarity_score"] = score
            ranked.append((score, record))
        except Exception:
            continue
    ranked.sort(key=lambda item: item[0])
    return [record for _score, record in ranked[: max(1, int(limit))]]


def _write_missing_mask_log_v3(
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

    target = v2._layer_record(renderer, layer_index, layers[zero_index])
    neighbor_start = max(0, zero_index - 3)
    neighbor_end = min(len(layers), zero_index + 4)
    neighbors = [
        v2._layer_record(renderer, index + 1, layers[index])
        for index in range(neighbor_start, neighbor_end)
    ]
    raw = _raw_window_v3(source, target.get("source_offset"), target.get("shape_word"))
    opposite = _opposite_mask_candidates(source, section, target)

    payload = {
        "diagnostic_version": 3,
        "source": str(source),
        "section": section,
        "error": str(error_text),
        "target": target,
        "neighbors": neighbors,
        "raw_payload_window": raw,
        "opposite_section_mask_candidates": opposite,
        "note": (
            "Fatal missing native mask. v3 resolves body-relative source offsets to the actual "
            "decompressed C_livery record and ranks mask candidates from the opposite side by "
            "mirrored transform similarity. The mask is still not skipped."
        ),
    }
    output_dir = base._probe_output_dir(source)
    (output_dir / f"{section}-missing-native-mask-v3.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _render_scored_ranges(
    source: Path,
    section: str,
    layers: list[dict[str, Any]],
    ranges: list[tuple[int, int]],
    car_id: int,
    game_folder: Path,
) -> tuple[list[tuple[str, bytes]], list[dict[str, Any]]]:
    rendered: list[tuple[str, bytes]] = []
    scored: list[dict[str, Any]] = []
    previous_log = getattr(base._TLS, "missing_native", None)
    base._TLS.missing_native = []
    try:
        for start, end in ranges:
            label = f"layers {start + 1}-{end}" if end - start > 1 else f"layer {start + 1}"
            png = base._render_subset(source, section, layers[start:end], car_id, game_folder)
            score = v2._dark_occluder_score(png)
            rendered.append((label, png))
            scored.append({"start_layer": start + 1, "end_layer": end, "dark_score": score})
    finally:
        base._TLS.missing_native = previous_log
    return rendered, scored


def _generate_probe_v3(source: Path, section: str) -> None:
    try:
        signature = core._file_signature(source)
        decoded = core._decode_cached(*signature)
        layers = list(decoded.sections.get(section) or ())
        if len(layers) < 2:
            return
        analysis = core._analysis_cached(*signature)
        car_id = int(getattr(analysis, "car_id", 0) or 0)
        if car_id <= 0:
            return
        game_folder = Path(require_fh6_game_folder())
        output_dir = base._probe_output_dir(source)

        coarse_ranges = v2._split_range(0, len(layers), 8)
        coarse_rendered, coarse_scores = _render_scored_ranges(
            source, section, layers, coarse_ranges, car_id, game_folder
        )
        (output_dir / f"{section}-8way-layer-probe.png").write_bytes(
            base._make_contact_sheet(coarse_rendered)
        )
        selected = max(coarse_scores, key=lambda item: item["dark_score"])
        current = (int(selected["start_layer"]) - 1, int(selected["end_layer"]))

        refined_ranges = v2._split_range(current[0], current[1], 8)
        refined_rendered, refined_scores = _render_scored_ranges(
            source, section, layers, refined_ranges, car_id, game_folder
        )
        (output_dir / f"{section}-8way-layer-probe-refined.png").write_bytes(
            base._make_contact_sheet(refined_rendered)
        )
        selected_refined = max(refined_scores, key=lambda item: item["dark_score"])
        current = (int(selected_refined["start_layer"]) - 1, int(selected_refined["end_layer"]))

        trace: list[dict[str, Any]] = []
        pass_index = 3
        last_rendered = refined_rendered
        last_scores = refined_scores
        while current[1] - current[0] > 8:
            ranges = v2._split_range(current[0], current[1], 8)
            last_rendered, last_scores = _render_scored_ranges(
                source, section, layers, ranges, car_id, game_folder
            )
            (output_dir / f"{section}-occluder-pass-{pass_index}.png").write_bytes(
                base._make_contact_sheet(last_rendered)
            )
            selected_pass = max(last_scores, key=lambda item: item["dark_score"])
            trace.append(
                {
                    "pass": pass_index,
                    "ranges": last_scores,
                    "selected": selected_pass,
                }
            )
            current = (
                int(selected_pass["start_layer"]) - 1,
                int(selected_pass["end_layer"]),
            )
            pass_index += 1

        individual_ranges = [(index, index + 1) for index in range(current[0], current[1])]
        individual_rendered, individual_scores = _render_scored_ranges(
            source, section, layers, individual_ranges, car_id, game_folder
        )
        (output_dir / f"{section}-occluder-candidates.png").write_bytes(
            base._make_contact_sheet(individual_rendered)
        )

        _decoder, renderer = core._load_backend()
        candidates: list[dict[str, Any]] = []
        for score in sorted(individual_scores, key=lambda item: item["dark_score"], reverse=True):
            index = int(score["start_layer"])
            record = v2._layer_record(renderer, index, layers[index - 1])
            record["dark_score"] = score["dark_score"]
            candidates.append(record)

        metadata = {
            "diagnostic_version": 3,
            "source": str(source),
            "section": section,
            "layer_count": len(layers),
            "coarse_ranges": coarse_scores,
            "refined_ranges": refined_scores,
            "recursive_trace": trace,
            "final_candidate_range": {
                "start_layer": current[0] + 1,
                "end_layer": current[1],
            },
            "individual_candidates_ranked": candidates,
            "note": (
                "v3 recursively follows the range with the largest near-black coverage until at most "
                "eight layers remain, then renders those layers individually. Diagnostic only."
            ),
        }
        (output_dir / f"{section}-occluder-candidates.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        try:
            output_dir = base._probe_output_dir(source)
            (output_dir / f"{section}-occluder-v3-error.txt").write_text(str(exc), encoding="utf-8")
        except Exception:
            pass


def install_simple_layer_native_debug_v3() -> None:
    global _PATCHED
    if _PATCHED:
        return
    v2.install_simple_layer_native_debug_v2()

    # Reuse the same background scheduler but deepen only the suspicious dark
    # range until individual candidate layers are available.
    base._generate_probe = _generate_probe_v3

    # v2's validator resolves this module-global function at runtime. Replacing
    # it upgrades the fatal-mask report without changing the fail-closed policy.
    v2._write_missing_mask_log = _write_missing_mask_log_v3

    _PATCHED = True
