from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path


PAINT_PROVENANCE_FORMAT = "fh6_livery_paint_provenance_v1"
PAINT_RECORD_SIZE = 27
PAINT_HEADER_SIZE = 10
MAX_PAINT_RECORDS = 256


class LiveryPaintProvenanceError(RuntimeError):
    pass


def _u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise LiveryPaintProvenanceError(f"u16 read exceeds payload at 0x{offset:x}")
    return int.from_bytes(data[offset : offset + 2], "little")


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise LiveryPaintProvenanceError(f"u32 read exceeds payload at 0x{offset:x}")
    return int.from_bytes(data[offset : offset + 4], "little")


def _u64(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 8 > len(data):
        raise LiveryPaintProvenanceError(f"u64 read exceeds payload at 0x{offset:x}")
    return int.from_bytes(data[offset : offset + 8], "little")


def _resolve_clivery(source: str | Path) -> Path:
    path = Path(source)
    if path.is_dir():
        path = path / "C_livery"
    if not path.is_file():
        raise LiveryPaintProvenanceError("C_livery file does not exist.")
    return path


def unwrap_forza_container_bytes(raw: bytes) -> bytes:
    """Inflate the read-only FH6 length-prefixed zlib container.

    Horizon C_livery samples normally use one block, but contiguous blocks are
    accepted defensively. Every advertised compressed/decompressed length is
    validated and trailing bytes are rejected instead of guessed.
    """
    if len(raw) < 8:
        raise LiveryPaintProvenanceError("C_livery container is shorter than its 8-byte header.")
    pos = 0
    chunks: list[bytes] = []
    while pos < len(raw):
        if pos + 8 > len(raw):
            raise LiveryPaintProvenanceError("C_livery has a truncated block header.")
        compressed_length = _u32(raw, pos)
        decompressed_length = _u32(raw, pos + 4)
        pos += 8
        if compressed_length <= 0 or decompressed_length <= 0:
            raise LiveryPaintProvenanceError("C_livery advertises an empty compressed block.")
        end = pos + compressed_length
        if end > len(raw):
            raise LiveryPaintProvenanceError("C_livery compressed block exceeds the source file.")
        try:
            payload = zlib.decompress(raw[pos:end])
        except zlib.error as exc:
            raise LiveryPaintProvenanceError(f"C_livery zlib inflate failed: {exc}") from exc
        if len(payload) != decompressed_length:
            raise LiveryPaintProvenanceError(
                "C_livery decompressed length mismatch: "
                f"header={decompressed_length}, actual={len(payload)}"
            )
        chunks.append(payload)
        pos = end
    return b"".join(chunks)


def _trailing_summary(data: bytes) -> dict:
    if not data:
        return {"size": 0, "hex": "", "sha256": hashlib.sha256(b"").hexdigest()}
    return {
        "size": len(data),
        "hex": data[:128].hex(),
        "hex_truncated": len(data) > 128,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _decode_record(payload: bytes, pos: int, index: int) -> dict:
    record = payload[pos : pos + PAINT_RECORD_SIZE]
    if len(record) != PAINT_RECORD_SIZE:
        raise LiveryPaintProvenanceError("Paint descriptor record is truncated.")
    primary_bgra = [int(v) for v in record[10:14]]
    secondary_bgra = [int(v) for v in record[15:19]]
    return {
        "index": index,
        "offset": pos,
        "raw_hex": record.hex(),
        "material_identifier_hex": record[0:8].hex(),
        "material_identifier_u64_le": _u64(record, 0),
        "value_type": int(record[8]),
        "primary_color_enabled_raw": int(record[9]),
        "primary_color_enabled": bool(record[9]),
        "primary_bgra": primary_bgra,
        "primary_rgba": [primary_bgra[2], primary_bgra[1], primary_bgra[0], primary_bgra[3]],
        "secondary_color_enabled_raw": int(record[14]),
        "secondary_color_enabled": bool(record[14]),
        "secondary_bgra": secondary_bgra,
        "secondary_rgba": [secondary_bgra[2], secondary_bgra[1], secondary_bgra[0], secondary_bgra[3]],
        "manufacturer_color_selector": _u32(record, 19),
        "finish_code": _u32(record, 23),
        "manufacturer_color_semantic": "unresolved_raw_value",
        "finish_semantic": "unresolved_raw_value",
    }


def _candidate_header(payload: bytes, start: int, limit: int) -> tuple[int, int] | None:
    if start < 0 or start + PAINT_HEADER_SIZE > len(payload) or start + PAINT_HEADER_SIZE > limit:
        return None
    table_mode = int(payload[start])
    record_type = int(payload[start + 1])
    if table_mode > 1 or record_type != 2:
        return None
    count = _u16(payload, start + 2)
    if count <= 0 or count > MAX_PAINT_RECORDS:
        return None
    materials_end = start + PAINT_HEADER_SIZE + count * PAINT_RECORD_SIZE
    if materials_end > len(payload) or materials_end > limit:
        return None
    return count, materials_end


def _locate_paint_header(payload: bytes, block_start: int, block_end: int) -> tuple[int, int, int, str] | None:
    direct = _candidate_header(payload, block_start, block_end)
    if direct is not None:
        count, materials_end = direct
        return block_start, count, materials_end, "direct_after_paint_yrvl"

    # Mirrors the bounded fallback used by ForzaLiveryStudio. It is deliberately
    # not a free-form whole-payload scan: only the final 4096 bytes of the proven
    # paint yrvl block are considered, and the historical trailer equation must
    # match exactly before the generic header validator is allowed to accept it.
    first_candidate = max(0, block_end - 4096)
    for start in range(block_end - 102, first_candidate - 1, -1):
        if start < block_start or start + 4 > len(payload):
            continue
        if int(payload[start]) > 1 or int(payload[start + 1]) != 2:
            continue
        count = _u16(payload, start + 2)
        if count <= 0 or count > MAX_PAINT_RECORDS:
            continue
        if start + 102 + count * PAINT_RECORD_SIZE != block_end:
            continue
        accepted = _candidate_header(payload, start, block_end)
        if accepted is not None:
            accepted_count, materials_end = accepted
            return start, accepted_count, materials_end, "forzaliverystudio_bounded_fallback"
    return None


def parse_livery_paint_provenance_payload(payload: bytes) -> dict:
    """Return raw FH6 livery paint descriptor provenance without rendering it.

    Tag navigation and 27-byte record framing follow the public
    ForzaLiveryStudio parser. Manufacturer-selector and finish-code meanings are
    intentionally left unresolved until separately validated against FH6 data.
    """
    if len(payload) < 0x1A or payload[:4] != b"vlrc":
        raise LiveryPaintProvenanceError("Payload is not an FH6 vlrc C_livery stream.")

    car_id = _u32(payload, 0x10)
    gyvl = payload.find(b"gyvl", 0x1A)
    if gyvl < 0 or gyvl + 0x15 > len(payload):
        raise LiveryPaintProvenanceError("C_livery has no complete embedded gyvl chunk.")

    stats_tag = payload.find(b"yrvl", gyvl + 0x15)
    if stats_tag < 0:
        raise LiveryPaintProvenanceError("C_livery has no section-counter yrvl after artwork.")
    paint_tag = payload.find(b"yrvl", stats_tag + 4)
    if paint_tag < 0:
        raise LiveryPaintProvenanceError("C_livery has no paint-descriptor yrvl after section counters.")
    paint_end = payload.find(b"yrvl", paint_tag + 4)
    if paint_end < 0 or paint_end <= paint_tag + 4:
        raise LiveryPaintProvenanceError("C_livery paint-descriptor yrvl has no following terminator block.")

    block_start = paint_tag + 4
    located = _locate_paint_header(payload, block_start, paint_end)
    base = {
        "format": PAINT_PROVENANCE_FORMAT,
        "status": "paint_header_unresolved" if located is None else "paint_descriptor_parsed",
        "rendering_applied": False,
        "source_contract": "forzaliverystudio_livery_codec_paint_yrvl",
        "car_id": car_id,
        "gyvl_offset": gyvl,
        "stats_yrvl_offset": stats_tag,
        "paint_yrvl_offset": paint_tag,
        "paint_block_start": block_start,
        "paint_block_end": paint_end,
        "interpretation_boundary": (
            "Raw descriptor framing/colors are inventoried only. Manufacturer selector and finish code "
            "are not mapped to paint semantics or shader parameters in Paint P1."
        ),
        "records": [],
        "issues": [],
    }
    if located is None:
        base["issues"].append("No structurally valid paint material table header was proven inside the paint yrvl block.")
        base["paint_block_raw"] = _trailing_summary(payload[block_start:paint_end])
        return base

    header_start, count, materials_end, location_method = located
    records = [
        _decode_record(payload, header_start + PAINT_HEADER_SIZE + i * PAINT_RECORD_SIZE, i)
        for i in range(count)
    ]
    base.update(
        {
            "header_offset": header_start,
            "header_location_method": location_method,
            "table_mode": int(payload[header_start]),
            "record_type": int(payload[header_start + 1]),
            "record_count": count,
            "header_reserved_hex": payload[header_start + 4 : header_start + 10].hex(),
            "records_end": materials_end,
            "records": records,
        }
    )

    trailer_pos = materials_end
    panel_identifiers: list[dict] = []
    if trailer_pos + 4 <= paint_end:
        panel_count = _u32(payload, trailer_pos)
        panels_end = trailer_pos + 4 + panel_count * 8
        base["panel_count_offset"] = trailer_pos
        base["panel_count"] = panel_count
        if panel_count <= 4096 and panels_end <= paint_end:
            for index in range(panel_count):
                pos = trailer_pos + 4 + index * 8
                raw = payload[pos : pos + 8]
                panel_identifiers.append(
                    {
                        "index": index,
                        "offset": pos,
                        "identifier_hex": raw.hex(),
                        "identifier_u64_le": int.from_bytes(raw, "little"),
                    }
                )
            base["panel_identifiers"] = panel_identifiers
            base["trailing_unknown"] = _trailing_summary(payload[panels_end:paint_end])
        else:
            base["panel_identifiers"] = []
            base["issues"].append(
                "Panel identifier count does not fit inside the proven paint yrvl block; trailer left opaque."
            )
            base["trailing_unknown"] = _trailing_summary(payload[trailer_pos:paint_end])
    else:
        base["panel_count"] = None
        base["panel_identifiers"] = []
        base["issues"].append("Paint descriptor ends immediately after material records; no panel-count field is available.")
        base["trailing_unknown"] = _trailing_summary(payload[trailer_pos:paint_end])
    return base


def diagnose_livery_paint(source: str | Path) -> dict:
    source_path = _resolve_clivery(source)
    raw = source_path.read_bytes()
    payload = unwrap_forza_container_bytes(raw)
    report = parse_livery_paint_provenance_payload(payload)
    report = dict(report)
    report.update(
        {
            "source_file": str(source_path),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "game_data_modified": False,
        }
    )
    return report


def write_livery_paint_diagnostic(source: str | Path, output: str | Path) -> Path:
    source_path = _resolve_clivery(source).resolve()
    output_path = Path(output).resolve()
    if output_path == source_path:
        raise LiveryPaintProvenanceError("Diagnostic output must not overwrite C_livery.")
    report = diagnose_livery_paint(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path
