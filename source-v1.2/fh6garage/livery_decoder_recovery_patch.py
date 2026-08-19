from __future__ import annotations

from pathlib import Path
from typing import Any


_PATCH_FLAG = "_fh6assistant_flat_section_recovery_v1"


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little", signed=False)


def _flat_group_candidates(body: bytes, target: int) -> list[tuple[int, int, int]]:
    """Return structurally strict flat markerless-group candidates.

    The recovery path intentionally accepts only the safest C_livery layout:
    a markerless root group whose declared child count equals the section's
    placement count, whose child bitmap/control bytes are empty, and whose
    children are direct 32-byte shape/raster records. Complex/nested sections
    stay on the normal KFPS decoder path.
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

    # FH6 uses the compact one-byte child-block field whenever it fits. Do not
    # reinterpret that same byte sequence as a wide header: small all-zero flat
    # groups can otherwise produce two candidates at the exact same offset.
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
        if pos + 32 > end:
            return None
        lead = body[pos : pos + 2]
        # Flat recovery is deliberately strict: direct FH6 livery placements
        # must use the full 32-byte 00/01 02 record form. Markerless 31-byte
        # shapes and nested/group records remain the normal decoder's job.
        if lead not in (b"\x00\x02", b"\x01\x02"):
            return None

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
        root.items.append(node)
        pos += 32

    raw_layers = decoder.flatten_tree(root, layer_start=0, section=section)
    if len(raw_layers) != int(target):
        return None
    json_layers, identity_warnings = decoder.layers_to_kfps_json_layers(raw_layers, game="fh6")
    if len(json_layers) != int(target):
        return None
    return json_layers, tuple(str(item) for item in identity_warnings), pos


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
    minimum_position = -1

    for section, target_value in zip(section_names, counts):
        target = int(target_value)
        if target <= 0:
            continue
        candidates = [item for item in _flat_group_candidates(body, target) if item[0] > minimum_position]
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
        minimum_position = group_pos
        standard_count = len(by_section.get(section, ()))
        recovered[section] = list(json_layers)
        identity_notes.extend(warnings)
        if standard_count != target:
            recovery_notes.append(
                f"{section}: decoder recovery restored {target:,}/{target:,} placements "
                f"from verified flat section bytes (standard decoder: {standard_count:,})."
            )
        elif standard_count == target:
            # Count equality alone does not prove the original parser started at
            # the correct section. Replacing a structurally verified flat section
            # also protects following sections after an earlier boundary error.
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
            "strategy": "verified-flat-root-direct-children",
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

        quality_pipeline.CACHE_VERSION = "v14-quality-pipeline-r2-decoder-recovery"
        tiled_quality.CACHE_VERSION = "v14-tiled-quality-r3-decoder-recovery"
        quality_pipeline.clear_quality_pipeline_cache()
        tiled_quality.clear_tiled_quality_cache()
    except Exception:
        # Cache revision is defensive. A failure here must not disable decoding.
        pass


def apply_livery_decoder_recovery_patch() -> None:
    """Patch the pinned KFPS decoder with a conservative structural recovery path."""
    from .livery_preview import _load_backend

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    original = decoder.decode_forza_source

    def decode_forza_source_with_recovery(path, allow_locked: bool = False, game: str | None = "fh6"):
        decoded = original(path, allow_locked=allow_locked, game=game)
        try:
            return _recover_flat_sections(decoder, Path(getattr(decoded, "source_path", path)), decoded)
        except Exception as exc:
            # Never make the normal upstream decoder less reliable. Recovery is
            # opportunistic; failures fall back to the untouched decoded result.
            report = dict(getattr(decoded, "report", {}) or {})
            warnings = [str(item) for item in list(report.get("warnings") or ())]
            warnings.append(f"FH6 Assistant flat-section recovery skipped: {exc}")
            report["warnings"] = list(dict.fromkeys(warnings))
            decoded.report = report
            return decoded

    decoder.decode_forza_source = decode_forza_source_with_recovery
    setattr(decoder, _PATCH_FLAG, True)
    _bump_render_cache_revision()
