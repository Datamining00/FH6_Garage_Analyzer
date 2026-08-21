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


def _shape_record(
    shape_id: int,
    *,
    lead: bytes = b"\x00\x02",
    x: float = 0.0,
    bgra: tuple[int, int, int, int] = (128, 128, 128, 255),
) -> bytes:
    assert lead in (b"\x00\x02", b"\x01\x02")
    # FH6 direct livery placement: lead + u16 id + rotation/x/y/sx/sy/skew + BGRA.
    return (
        lead
        + struct.pack("<H", int(shape_id))
        + struct.pack("<ffffff", 0.0, float(x), 0.0, 1.0, 1.0, 0.0)
        + bytes(bgra)
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
            _shape_record(102, lead=b"\x01\x02", x=2.0),
            _shape_record(103, x=3.0),
        ]
    )
    right = _flat_section(
        [
            _shape_record(104, x=11.0),
            _shape_record(105, x=12.0),
            _shape_record(106, x=13.0),
        ]
    )
    # Front/Back/Top empty, then Left and Right populated, remaining six slots empty.
    body = bytes(23 * 3) + left + right + bytes(23 * 6)
    header = bytearray(0x20)
    header[:4] = b"vlrc"
    header[0x10:0x14] = struct.pack("<I", 3107)
    gyvl_header = b"gyvl" + bytes(0x15 - 4)
    counts = (0, 0, 0, 3, 3, 0, 0, 0, 0, 0, 0)
    return bytes(header) + gyvl_header + body + b"yrvl" + struct.pack("<11I", *counts)


class LiveryDecoderRecoveryTests(unittest.TestCase):
    def test_flat_direct_section_recovers_all_records_and_mask_lead(self) -> None:
        decoder, _renderer = _load_backend()
        records = [
            _shape_record(101),
            _shape_record(102, lead=b"\x01\x02"),
            _shape_record(103),
        ]
        body = _flat_section(records)
        candidates = _flat_group_candidates(body, 3)
        self.assertEqual(len(candidates), 1)
        _group_pos, child_start, _header_size = candidates[0]
        recovered = _decode_direct_children(decoder, body, child_start, 3, "Left")
        self.assertIsNotNone(recovered)
        layers, _warnings, child_end = recovered
        self.assertEqual(len(layers), 3)
        self.assertEqual(child_end, child_start + 3 * 32)
        self.assertTrue(bool(layers[0].get("mask")))
        self.assertEqual(layers[0]["data"][6], 1)
        self.assertEqual(
            layers[0].get("fh6assistant_mask_evidence"),
            "verified_flat_0102_previous_direct_shape",
        )
        self.assertEqual([layer.get("source_section") for layer in layers], ["Left"] * 3)

    def test_chromatic_previous_direct_shape_keeps_0102_mask(self) -> None:
        decoder, _renderer = _load_backend()
        records = [
            # Stored BGRA 00 00 FF FF is semantic red and therefore chromatic.
            _shape_record(101, bgra=(0, 0, 255, 255)),
            _shape_record(102, lead=b"\x01\x02"),
        ]
        body = _flat_section(records)
        candidates = _flat_group_candidates(body, 2)
        self.assertEqual(len(candidates), 1)
        _group_pos, child_start, _header_size = candidates[0]
        recovered = _decode_direct_children(decoder, body, child_start, 2, "Front")
        self.assertIsNotNone(recovered)
        layers, _warnings, child_end = recovered
        self.assertEqual(child_end, child_start + 2 * 32)
        self.assertEqual(layers[0]["color"], [255, 0, 0, 255])
        self.assertTrue(layers[0]["mask"])
        self.assertEqual(layers[0]["data"][6], 1)
        self.assertEqual(
            layers[0].get("fh6assistant_mask_evidence"),
            "verified_flat_0102_previous_direct_shape",
        )
        self.assertFalse(bool(layers[1].get("mask")))

    def test_wide_three_thousand_section_recovers_all_direct_records(self) -> None:
        decoder, _renderer = _load_backend()
        records = [
            _shape_record(101 + (index % 8), x=float(index % 1000))
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
        self.assertEqual(child_end, child_start + 3000 * 32)
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


if __name__ == "__main__":
    unittest.main()
