from __future__ import annotations

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from fh6garage.livery_analysis import (
    LIVERY_SECTION_NAMES,
    LiveryAnalysisError,
    analyze_livery_bytes,
    analyze_livery_file,
)


COUNTS = (12, 5, 30, 101, 99, 4, 0, 2, 0, 7, 8)


def _payload(counts=COUNTS, car_id: int = 0) -> bytes:
    header = bytearray(b"vlrc" + b"\x00" * 24)
    struct.pack_into("<I", header, 0x10, int(car_id))
    return (
        bytes(header)
        + b"gyvl"
        + b"\x11" * 73
        + b"yrvl"
        + struct.pack("<" + "I" * len(LIVERY_SECTION_NAMES), *counts)
        + b"\x00" * 16
    )


def _container(payload: bytes) -> bytes:
    compressed = zlib.compress(payload)
    return struct.pack("<II", len(compressed), len(payload)) + compressed


class LiveryAnalysisTests(unittest.TestCase):
    def test_reads_raw_payload_section_counts(self) -> None:
        result = analyze_livery_bytes(_payload())
        self.assertEqual(result.section_counts["Front"], 12)
        self.assertEqual(result.section_counts["Left"], 101)
        self.assertEqual(result.section_counts["FrontWindshield"], 0)
        self.assertEqual(result.total_placements, sum(COUNTS))
        self.assertEqual(result.populated_sections, 9)

    def test_reads_target_car_id_from_vlrc_header(self) -> None:
        result = analyze_livery_bytes(_payload(car_id=3650))
        self.assertEqual(result.car_id, 3650)

    def test_reads_zlib_container(self) -> None:
        result = analyze_livery_bytes(_container(_payload(car_id=3650)))
        self.assertEqual(result.total_placements, sum(COUNTS))
        self.assertEqual(tuple(result.section_counts), LIVERY_SECTION_NAMES)
        self.assertEqual(result.car_id, 3650)

    def test_reads_file_without_modifying_it(self) -> None:
        raw = _container(_payload())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "C_livery"
            path.write_bytes(raw)
            before = path.read_bytes()
            result = analyze_livery_file(path)
            after = path.read_bytes()
        self.assertEqual(result.total_placements, sum(COUNTS))
        self.assertEqual(before, after)

    def test_rejects_missing_livery_markers(self) -> None:
        with self.assertRaises(LiveryAnalysisError):
            analyze_livery_bytes(b"vlrc" + b"\x00" * 100)

    def test_rejects_implausible_count_total(self) -> None:
        counts = (9_999_999, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        with self.assertRaises(LiveryAnalysisError):
            analyze_livery_bytes(_payload(counts))


if __name__ == "__main__":
    unittest.main()
