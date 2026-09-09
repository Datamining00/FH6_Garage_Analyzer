from __future__ import annotations

import json
import tempfile
import unittest
import zlib
from pathlib import Path

from fh6garage.preview3d.livery_paint_provenance import (
    LiveryPaintProvenanceError,
    diagnose_livery_paint,
    parse_livery_paint_provenance_payload,
    unwrap_forza_container_bytes,
    write_livery_paint_diagnostic,
)


def _record(
    material: bytes,
    *,
    value_type: int = 3,
    primary_enabled: int = 1,
    primary=(10, 20, 30, 255),
    secondary_enabled: int = 1,
    secondary=(40, 50, 60, 200),
    manufacturer: int = 0x11223344,
    finish: int = 0x55667788,
) -> bytes:
    assert len(material) == 8
    return (
        material
        + bytes([value_type, primary_enabled])
        + bytes(primary)
        + bytes([secondary_enabled])
        + bytes(secondary)
        + int(manufacturer).to_bytes(4, "little")
        + int(finish).to_bytes(4, "little")
    )


def _paint_header(records: list[bytes], *, mode: int = 1, record_type: int = 2) -> bytes:
    return bytes([mode, record_type]) + len(records).to_bytes(2, "little") + b"\x00" * 6 + b"".join(records)


def _payload(paint_block: bytes, *, car_id: int = 2489) -> bytes:
    root = bytearray(0x1A)
    root[0:4] = b"vlrc"
    root[0x10:0x14] = int(car_id).to_bytes(4, "little")
    # The first yrvl precedes artwork; paint provenance navigation begins at gyvl.
    root += b"yrvl" + b"\x00" * 16
    root += b"gyvl" + b"\x00" * 0x11
    root += b"\x00" * 23
    root += b"yrvl" + b"\x00" * (11 * 4)
    root += b"yrvl" + paint_block
    root += b"yrvl" + b"\x00" * 4
    return bytes(root)


def _container(payload: bytes) -> bytes:
    compressed = zlib.compress(payload)
    return len(compressed).to_bytes(4, "little") + len(payload).to_bytes(4, "little") + compressed


class LiveryPaintProvenanceTests(unittest.TestCase):
    def test_direct_paint_header_preserves_raw_descriptor_fields(self):
        records = [
            _record(b"ABCDEFGH"),
            _record(
                b"12345678",
                value_type=9,
                primary_enabled=0,
                primary=(1, 2, 3, 4),
                secondary_enabled=1,
                secondary=(5, 6, 7, 8),
                manufacturer=0xAABBCCDD,
                finish=0x01020304,
            ),
        ]
        panels = [b"PANEL001", b"PANEL002"]
        paint_block = _paint_header(records) + len(panels).to_bytes(4, "little") + b"".join(panels) + b"\xAA\xBB"
        report = parse_livery_paint_provenance_payload(_payload(paint_block))

        self.assertEqual(report["format"], "fh6_livery_paint_provenance_v1")
        self.assertEqual(report["status"], "paint_descriptor_parsed")
        self.assertFalse(report["rendering_applied"])
        self.assertEqual(report["car_id"], 2489)
        self.assertEqual(report["header_location_method"], "direct_after_paint_yrvl")
        self.assertEqual(report["record_count"], 2)
        first = report["records"][0]
        self.assertEqual(first["material_identifier_hex"], b"ABCDEFGH".hex())
        self.assertEqual(first["value_type"], 3)
        self.assertEqual(first["primary_bgra"], [10, 20, 30, 255])
        self.assertEqual(first["primary_rgba"], [30, 20, 10, 255])
        self.assertEqual(first["secondary_bgra"], [40, 50, 60, 200])
        self.assertEqual(first["manufacturer_color_selector"], 0x11223344)
        self.assertEqual(first["finish_code"], 0x55667788)
        self.assertEqual(first["manufacturer_color_semantic"], "unresolved_raw_value")
        self.assertEqual(first["finish_semantic"], "unresolved_raw_value")
        self.assertEqual(report["panel_count"], 2)
        self.assertEqual([p["identifier_hex"] for p in report["panel_identifiers"]], [p.hex() for p in panels])
        self.assertEqual(report["trailing_unknown"]["hex"], "aabb")

    def test_bounded_forzaliverystudio_fallback_is_not_a_whole_payload_guess(self):
        record = _record(b"FALLBACK")
        # FLS fallback requires: header_start + 102 + count*27 == paint_end.
        # A non-header prefix makes the direct paintTag+4 probe fail.
        paint_block = b"\xFF\xEE\xDD" + _paint_header([record]) + b"\x00" * 92
        report = parse_livery_paint_provenance_payload(_payload(paint_block))
        self.assertEqual(report["status"], "paint_descriptor_parsed")
        self.assertEqual(report["header_location_method"], "forzaliverystudio_bounded_fallback")
        self.assertEqual(report["record_count"], 1)
        self.assertEqual(report["records"][0]["material_identifier_hex"], b"FALLBACK".hex())

    def test_unproven_header_stays_unresolved_instead_of_guessing(self):
        report = parse_livery_paint_provenance_payload(_payload(b"not-a-paint-table" + b"\x00" * 120))
        self.assertEqual(report["status"], "paint_header_unresolved")
        self.assertEqual(report["records"], [])
        self.assertFalse(report["rendering_applied"])
        self.assertTrue(report["issues"])

    def test_length_prefixed_container_is_strict_and_supports_contiguous_blocks(self):
        first = b"vlrc-part-one"
        second = b"part-two"
        raw = _container(first) + _container(second)
        self.assertEqual(unwrap_forza_container_bytes(raw), first + second)
        bad = bytearray(_container(first))
        bad[4:8] = (len(first) + 1).to_bytes(4, "little")
        with self.assertRaises(LiveryPaintProvenanceError):
            unwrap_forza_container_bytes(bytes(bad))

    def test_file_diagnostic_is_read_only_and_output_cannot_replace_source(self):
        paint_block = _paint_header([_record(b"READONLY")]) + (0).to_bytes(4, "little")
        payload = _payload(paint_block)
        raw = _container(payload)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "C_livery"
            source.write_bytes(raw)
            report = diagnose_livery_paint(source)
            self.assertFalse(report["game_data_modified"])
            self.assertEqual(report["status"], "paint_descriptor_parsed")
            self.assertEqual(source.read_bytes(), raw)

            output = root / "paint.json"
            written = write_livery_paint_diagnostic(source, output)
            parsed = json.loads(written.read_text(encoding="utf-8"))
            self.assertEqual(parsed["source_sha256"], report["source_sha256"])
            self.assertEqual(source.read_bytes(), raw)
            with self.assertRaises(LiveryPaintProvenanceError):
                write_livery_paint_diagnostic(source, source)


if __name__ == "__main__":
    unittest.main()
