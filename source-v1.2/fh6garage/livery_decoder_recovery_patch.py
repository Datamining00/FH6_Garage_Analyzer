from __future__ import annotations

from pathlib import Path
from typing import Any


_PATCH_FLAG = "_fh6assistant_flat_section_recovery_v3"


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little", signed=False)


def _flat_group_candidates(body: bytes, target: int) -> list[tuple[int, int, int]]:
    """Return structurally strict flat markerless-group candidates.

    The fallback path accepts a markerless root group whose declared child count
    equals the section placement count and whose child bitmap/control bytes are
    empty. Its direct children may use either the normal 32-byte 00/01 02 livery
    placement form or the valid 31-byte markerless 02 shape form used by FH6.
    Complex/nested sections are handled by the exact-target sequential walk first.
    """
    target = int(target)
    if target <= 0:
        return []
    child_blocks = (target + 7) // 8
    end = len(body)
    results: list[tuple[int, int, int]] = []

    def add_candidate(pos: int, header_size: int) -> None:
        bitmap_start = pos + header_size
        control_start = bitmap_start + child_blocks
        child_start = control_start + 2
        if child_start > end:
            return
        bitmap = body[bitmap_start:control_start]
        control = body[control_start:child_start]
        if len(bitmap) != child_blocks or any(bitmap) or control != b"\x00\x00":
            return
        results.append((pos, child_start, header_size))

    if child_blocks <= 0xFF:
        pattern = target.to_bytes(2, "little") + bytes((child_blocks,))
        start = 0
        while True:
            pos = body.find(pattern, start)
            if pos < 0:
                break
            add_candidate(pos, 3)
            start = pos + 1
    else:
        pattern = target.to_bytes(2, "little") + child_blocks.to_bytes(2, "little")
        start = 0
        while True:
            pos = body.find(pattern, start)
            if pos < 0:
                break
            add_candidate(pos, 4)
            start = pos + 1

    return sorted(set(results))


def _decode_direct_children(decoder, body: bytes, child_start: int, target: int, section: str):
    """Decode one proven-flat section without heuristic group walking."""
    end = len(body)
    pos = int(child_start)
    root = decoder.GroupNode(source="livery_section_recovered", offset=pos, section=section)

    for _index in range(int(target)):
        if pos >= end:
            return None

        full_record = body[pos : pos + 2] in (b"\x00\x02", b"\x01\x02")
        markerless_record = body[pos : pos + 1] == b"\x02"
        if full_record:
            if pos + 32 > end:
                return None
            lead = body[pos : pos + 2]
            if lead == b"\x01\x02" and root.items:
                previous = root.items[-1]
                if isinstance(previous, decoder.ShapeNode):
                    previous.mask = True
                    previous.flags |= 0x40

            flags = 0x01 if lead == b"\x01\x02" else 0
            if decoder.is_livery_logo_at(body, pos, end):
                node = decoder.decode_livery_logo_at(body, pos, is_mask=False, flags=flags)
            elif decoder.is_valid_shape_at(body, pos, end):
                node = decoder.decode_shape_at(body, pos, is_mask=False, flags=flags)
            else:
                return None
            record_size = 32
        elif markerless_record:
            if pos + 31 > end or not decoder.is_valid_shape_at(body, pos, end):
                return None
            node = decoder.decode_shape_at(body, pos, is_mask=False, flags=0)
            record_size = 31
        else:
            return None

        root.items.append(node)
        pos += record_size

    raw_layers = decoder.flatten_tree(root, layer_start=0, section=section)
    if len(raw_layers) != int(target):
        return None
    json_layers, identity_warnings = decoder.layers_to_kfps_json_layers(raw_layers, game="fh6")
    if len(json_layers) != int(target):
        return None
    return json_layers, tuple(str(item) for item in identity_warnings), pos


def _decode_exact_target_stream(decoder, body: bytes, counts: list[int]):
    """Walk all eleven C_livery sections without the upstream reserved-tail guess.

    KFPS' normal decoder protects itself with a tail estimate that assumes every
    later placement occupies 32 bytes. FH6 also has 31-byte placements and group/
    transform records, so that estimate can stop a section early or let it walk
    into the next one. This alternate pass uses the same upstream grammar and
    transform composition, but the declared per-section placement counts are the
    stop condition. It is accepted only if every populated section closes cleanly
    and the final slot lands exactly at the end of the embedded gyvl body.
    """
    section_names = tuple(getattr(decoder, "LIVERY_SECTION_NAMES", ()))
    if not section_names or len(counts) < len(section_names):
        return None

    end = len(body)
    pos = 0
    all_raw_layers: list[dict[str, Any]] = []
    section_ranges: dict[str, dict[str, int]] = {}
    empty_size = int(getattr(decoder, "LIVERY_EMPTY_SLOT_SIZE", 23))
    populated_remnant = int(getattr(decoder, "LIVERY_POPULATED_REMNANT_SIZE", 18))

    for slot, section in enumerate(section_names):
        target = int(counts[slot])
        section_start = pos
        if target <= 0:
            pos += empty_size
            if pos > end:
                return None
            section_ranges[section] = {
                "declared": 0,
                "decoded": 0,
                "start": section_start,
                "end": pos,
            }
            continue

        section_root = decoder.GroupNode(source="livery_section_exact_target", offset=pos, section=section)
        holder = decoder.GroupNode(source="livery_holder_exact_target")
        holder.items.append(section_root)
        state = decoder.WalkState(stack=[holder, section_root])
        guard = 0
        max_guard = max(4096, end * 2 + 4096)

        while state.decoded_shapes < target and pos < end and guard < max_guard:
            guard += 1
            decoder.close_complete_stack(state.stack)
            if len(state.stack) < 2:
                return None

            at_section_root = state.stack[-1] is section_root
            if at_section_root and not state.pending_transform:
                markerless = decoder.valid_markerless_group_at(
                    body,
                    pos,
                    end,
                    allow_count_one=True,
                    livery=True,
                )
                if markerless:
                    next_pos = decoder.push_markerless_group(
                        body,
                        pos,
                        end,
                        markerless,
                        state,
                        livery=True,
                    )
                    if next_pos <= pos:
                        return None
                    pos = next_pos
                    continue

            next_pos = decoder.walk_step(
                body,
                pos,
                end,
                state,
                livery=True,
                livery_invert_odd_rotation=slot != 2,
            )
            if next_pos <= pos:
                return None
            pos = next_pos

        if state.decoded_shapes != target:
            return None

        decoder.close_complete_stack(state.stack)
        # holder + section root must be the only frames left. An unfinished
        # nested group means the target was reached by crossing a structural
        # boundary and therefore cannot be trusted.
        if len(state.stack) != 2 or state.pending_transform is not None:
            return None

        raw_layers = decoder.flatten_tree(section_root, layer_start=0, section=section)
        if len(raw_layers) != target:
            return None
        for layer in raw_layers:
            layer["section_start"] = section_start
        all_raw_layers.extend(raw_layers)

        child_end = pos
        pos += populated_remnant
        if pos > end:
            return None
        section_ranges[section] = {
            "declared": target,
            "decoded": len(raw_layers),
            "start": section_start,
            "child_end": child_end,
            "end": pos,
        }

    # Exact body consumption is the key safety gate. If even one byte remains or
    # a section overshot, keep the original decoder result instead of guessing.
    if pos != end:
        return None

    expected_total = sum(max(0, int(value)) for value in counts[: len(section_names)])
    if len(all_raw_layers) != expected_total:
        return None
    json_layers, identity_warnings = decoder.layers_to_kfps_json_layers(all_raw_layers, game="fh6")
    if len(json_layers) != expected_total:
        return None
    return (
        json_layers,
        tuple(str(item) for item in identity_warnings),
        section_ranges,
    )


def _recover_exact_target_stream(decoder, source: Path, decoded: Any) -> tuple[Any, bool]:
    if str(getattr(decoded, "source_kind", "")).casefold() != "clivery":
        return decoded, False

    payload = decoder.unwrap_forza_container(Path(source))
    body, counts, _meta = decoder.extract_livery_payload(payload)
    attempt = _decode_exact_target_stream(decoder, body, counts)
    if attempt is None:
        return decoded, False

    json_layers, identity_notes, section_ranges = attempt
    decoded.layers = list(json_layers)
    report = dict(getattr(decoded, "report", {}) or {})
    old_warnings = [str(item) for item in list(report.get("warnings") or ())]
    structural_prefixes = tuple(
        f"{section}:" for section in tuple(getattr(decoder, "LIVERY_SECTION_NAMES", ()))
    )
    filtered = [
        warning for warning in old_warnings
        if not warning.startswith(structural_prefixes)
    ]
    filtered.append(
        "FH6 Assistant: exact-target sequential section walk verified all declared placements and consumed the complete livery body."
    )
    report["warnings"] = list(dict.fromkeys(filtered))
    if identity_notes:
        current_identity = [str(item) for item in list(report.get("identity_warnings") or ())]
        current_identity.extend(identity_notes)
        report["identity_warnings"] = list(dict.fromkeys(current_identity))
    report["decoded_layers"] = len(json_layers)
    report["fh6assistant_structural_stream_recovery"] = {
        "strategy": "exact-target-sequential-walk",
        "sections": section_ranges,
        "body_size": len(body),
        "consumed": len(body),
    }
    decoded.report = report
    return decoded, True


def _recover_flat_sections(decoder, source: Path, decoded: Any) -> Any:
    if str(getattr(decoded, "source_kind", "")).casefold() != "clivery":
        return decoded

    payload = decoder.unwrap_forza_container(Path(source))
    body, counts, _meta = decoder.extract_livery_payload(payload)
    section_names = tuple(getattr(decoder, "LIVERY_SECTION_NAMES", ()))
    if not section_names or len(counts) < len(section_names):
        return decoded

    original_layers = [layer for layer in list(getattr(decoded, "layers", ()) or ()) if isinstance(layer, dict)]
    by_section: dict[str, list[dict[str, Any]]] = {name: [] for name in section_names}
    unknown: list[dict[str, Any]] = []
    for layer in original_layers:
        section = str(layer.get("source_section") or "")
        if section in by_section:
            by_section[section].append(layer)
        else:
            unknown.append(layer)

    recovered: dict[str, list[dict[str, Any]]] = {}
    recovery_notes: list[str] = []
    identity_notes: list[str] = []
    minimum_group_position = 0
    populated_remnant = int(getattr(decoder, "LIVERY_POPULATED_REMNANT_SIZE", 18))

    for section, target_value in zip(section_names, counts):
        target = int(target_value)
        if target <= 0:
            continue
        candidates = [
            item for item in _flat_group_candidates(body, target)
            if item[0] >= minimum_group_position
        ]
        accepted = None
        for group_pos, child_start, _header_size in candidates:
            attempt = _decode_direct_children(decoder, body, child_start, target, section)
            if attempt is None:
                continue
            json_layers, warnings, child_end = attempt
            accepted = (group_pos, child_end, json_layers, warnings)
            break
        if accepted is None:
            continue

        group_pos, child_end, json_layers, warnings = accepted
        minimum_group_position = child_end + populated_remnant
        standard_count = len(by_section.get(section, ()))
        recovered[section] = list(json_layers)
        identity_notes.extend(warnings)
        if standard_count != target:
            recovery_notes.append(
                f"{section}: decoder recovery restored {target:,}/{target:,} placements "
                f"from verified flat section bytes (standard decoder: {standard_count:,})."
            )
        else:
            recovery_notes.append(
                f"{section}: verified flat section boundary and {target:,}/{target:,} placements."
            )

    if not recovered:
        return decoded

    rebuilt: list[dict[str, Any]] = []
    for section in section_names:
        rebuilt.extend(recovered.get(section, by_section.get(section, ())))
    rebuilt.extend(unknown)
    decoded.layers = rebuilt

    report = dict(getattr(decoded, "report", {}) or {})
    old_warnings = [str(item) for item in list(report.get("warnings") or ())]
    recovered_names = set(recovered)
    filtered_warnings: list[str] = []
    for warning in old_warnings:
        if any(
            warning.startswith(f"{section}: decoded ")
            or warning.startswith(f"{section}: parser stack closed")
            for section in recovered_names
        ):
            continue
        filtered_warnings.append(warning)
    filtered_warnings.extend(recovery_notes)
    report["warnings"] = list(dict.fromkeys(filtered_warnings))
    if identity_notes:
        current_identity = [str(item) for item in list(report.get("identity_warnings") or ())]
        current_identity.extend(identity_notes)
        report["identity_warnings"] = list(dict.fromkeys(current_identity))
    report["decoded_layers"] = len(rebuilt)
    report["fh6assistant_recovered_sections"] = {
        section: {
            "declared": int(counts[section_names.index(section)]),
            "decoded": len(recovered[section]),
            "strategy": "verified-flat-root-mixed-direct-children",
        }
        for section in recovered
    }
    decoded.report = report
    return decoded


def _bump_render_cache_revision() -> None:
    """Keep corrected decoder output from reusing PNGs rendered by old parsing."""
    try:
        from . import livery_preview_quality_pipeline as quality_pipeline
        from . import livery_preview_tiled_quality as tiled_quality

        quality_pipeline.CACHE_VERSION = "v14-quality-pipeline-r4-structural-walk"
        tiled_quality.CACHE_VERSION = "v14-tiled-quality-r6-structural-walk"
        quality_pipeline.clear_quality_pipeline_cache()
        tiled_quality.clear_tiled_quality_cache()
    except Exception:
        pass


def apply_livery_decoder_recovery_patch() -> None:
    """Patch the pinned KFPS decoder with conservative structural recovery paths."""
    from .livery_preview import _load_backend

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    original = decoder.decode_forza_source

    def decode_forza_source_with_recovery(path, allow_locked: bool = False, game: str | None = "fh6"):
        decoded = original(path, allow_locked=allow_locked, game=game)
        source = Path(getattr(decoded, "source_path", path))
        try:
            decoded, exact_stream = _recover_exact_target_stream(decoder, source, decoded)
            if exact_stream:
                return decoded
            return _recover_flat_sections(decoder, source, decoded)
        except Exception as exc:
            report = dict(getattr(decoded, "report", {}) or {})
            warnings = [str(item) for item in list(report.get("warnings") or ())]
            warnings.append(f"FH6 Assistant structural recovery skipped: {exc}")
            report["warnings"] = list(dict.fromkeys(warnings))
            decoded.report = report
            return decoded

    decoder.decode_forza_source = decode_forza_source_with_recovery
    setattr(decoder, _PATCH_FLAG, True)
    _bump_render_cache_revision()
