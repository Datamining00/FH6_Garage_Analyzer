from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from fh6garage.livery_decoder_recovery_patch import (
    _decode_direct_children,
    _flat_group_candidates,
    apply_livery_decoder_recovery_patch,
)
from fh6garage.livery_preview import _load_backend


def _shape_record(shape_id: int, *, lead: bytes = b"\x00\x02", x: float = 0.0) -> bytes:
    assert lead in (b"\x00\x02", b"\x01\x02")
    return (
        lead
        + struct.pack("<H", int(shape_id))
        + struct.pack("<ffffff", 0.0, float(x), 0.0, 1.0, 1.0, 0.0)
        + bytes((128, 128, 128, 255))
    )


def _markerless_shape_record(shape_id: int, *, x: float = 0.0) -> bytes:
    # Valid 31-byte FH6 placement form: 02 + u16 id + six floats + BGRA.
    return (
        b"\x02"
        + struct.pack("<H", int(shape_id))
        + struct.pack("<ffffff", 0.0, float(x), 0.0, 1.0, 1.0, 0.0)
        + bytes((128, 128, 128, 255))
    )


def _flat_section(records: list[bytes]) -> bytes:
    count = len(records)
    child_blocks = (count + 7) // 8
    if child_blocks <= 0xFF:
        header = struct.pack("<HB", count, child_blocks)
    else:
        header = struct.pack("<HH", count, child_blocks)
    return header + bytes(child_blocks) + b"\x00\x00" + b"".join(records) + bytes(18)


def _synthetic_clivery() -> bytes:
    left = _flat_section(
        [
            _shape_record(101, x=1.0),
            _markerless_shape_record(102, x=2.0),
            _shape_record(103, x=3.0),
        ]
    )
    right = _flat_section(
        [
            _shape_record(104, x=11.0),
            _markerless_shape_record(105, x=12.0),
            _shape_record(106, x=13.0),
        ]
    )
    body = bytes(23 * 3) + left + right + bytes(23 * 6)
    header = bytearray(0x20)
    header[:4] = b"vlrc"
    header[0x10:0x14] = struct.pack("<I", 3107)
    gyvl_header = b"gyvl" + bytes(0x15 - 4)
    counts = (0, 0, 0, 3, 3, 0, 0, 0, 0, 0, 0)
    return bytes(header) + gyvl_header + body + b"yrvl" + struct.pack("<11I", *counts)


class LiveryDecoderRecoveryTests(unittest.TestCase):
    def test_flat_direct_section_recovers_full_and_markerless_records(self) -> None:
        decoder, _renderer = _load_backend()
        records = [
            _shape_record(101),
            _markerless_shape_record(102),
            _shape_record(103, lead=b"\x01\x02"),
        ]
        body = _flat_section(records)
        candidates = _flat_group_candidates(body, 3)
        self.assertEqual(len(candidates), 1)
        _group_pos, child_start, _header_size = candidates[0]
        recovered = _decode_direct_children(decoder, body, child_start, 3, "Left")
        self.assertIsNotNone(recovered)
        layers, _warnings, child_end = recovered
        self.assertEqual(len(layers), 3)
        self.assertEqual(child_end, child_start + 32 + 31 + 32)
        self.assertTrue(bool(layers[1].get("mask")))
        self.assertEqual([layer.get("source_section") for layer in layers], ["Left"] * 3)

    def test_wide_three_thousand_section_recovers_three_markerless_records(self) -> None:
        decoder, _renderer = _load_backend()
        markerless = {997, 1998, 2999}
        records = [
            (
                _markerless_shape_record(101 + (index % 8), x=float(index % 1000))
                if index in markerless
                else _shape_record(101 + (index % 8), x=float(index % 1000))
            )
            for index in range(3000)
        ]
        body = bytes(137) + _flat_section(records) + bytes(41)
        candidates = _flat_group_candidates(body, 3000)
        self.assertEqual(len(candidates), 1)
        group_pos, child_start, header_size = candidates[0]
        self.assertEqual(group_pos, 137)
        self.assertEqual(header_size, 4)
        self.assertEqual(child_start - group_pos, 4 + 375 + 2)
        recovered = _decode_direct_children(decoder, body, child_start, 3000, "Left")
        self.assertIsNotNone(recovered)
        layers, _warnings, child_end = recovered
        self.assertEqual(len(layers), 3000)
        self.assertEqual(child_end, child_start + 3000 * 32 - len(markerless))
        self.assertTrue(all(layer.get("source_section") == "Left" for layer in layers))

    def test_decoder_patch_structurally_verifies_repeated_flat_sections(self) -> None:
        apply_livery_decoder_recovery_patch()
        decoder, _renderer = _load_backend()
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "C_livery"
            source.write_bytes(_synthetic_clivery())
            decoded = decoder.decode_forza_source(source, allow_locked=True, game="fh6")

        by_section = {name: [] for name in decoder.LIVERY_SECTION_NAMES}
        for layer in decoded.layers:
            section = str(layer.get("source_section") or "")
            if section in by_section:
                by_section[section].append(layer)
        self.assertEqual(len(by_section["Left"]), 3)
        self.assertEqual(len(by_section["Right"]), 3)
        recovered = decoded.report.get("fh6assistant_recovered_sections") or {}
        self.assertEqual(recovered["Left"]["decoded"], 3)
        self.assertEqual(recovered["Right"]["decoded"], 3)
        self.assertEqual(
            recovered["Right"]["strategy"],
            "verified-flat-root-mixed-direct-children",
        )


if __name__ == "__main__":
    unittest.main()
