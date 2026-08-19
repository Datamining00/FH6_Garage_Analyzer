from __future__ import annotations

import unittest

from fh6garage.livery_analysis import LIVERY_SECTION_NAMES
from fh6garage.livery_render_integrity_patch import (
    _integrity_failure_for_section,
    _raster_provenance_failure,
)


def _counts(**overrides):
    values = {name: 0 for name in LIVERY_SECTION_NAMES}
    values.update({key: int(value) for key, value in overrides.items()})
    return values


def _sections(**sizes):
    result = {name: tuple() for name in LIVERY_SECTION_NAMES}
    for name, size in sizes.items():
        result[name] = tuple({"source_section": name} for _ in range(int(size)))
    return result


class _FakeDecoder:
    @staticmethod
    def is_livery_logo_at(body: bytes, offset: int, end: int) -> bool:
        if offset < 0 or offset + 4 > end:
            return False
        if body[offset : offset + 2] not in (b"\x00\x02", b"\x01\x02"):
            return False
        raw = int.from_bytes(body[offset + 2 : offset + 4], "little", signed=False)
        return bool(raw & 0x8000) and bool(raw & 0x7FFF)


def _raster_record(raster_id: int) -> bytes:
    return b"\x00\x02" + (0x8000 | int(raster_id)).to_bytes(2, "little") + bytes(28)


class LiveryRenderIntegrityTests(unittest.TestCase):
    def test_direct_mismatch_blocks_requested_section(self) -> None:
        failure = _integrity_failure_for_section(
            _counts(Left=3000),
            _sections(Left=2991),
            "Left",
        )
        self.assertEqual(failure, ("Left", 3000, 2991, False))

    def test_previous_mismatch_blocks_later_section_even_when_later_count_matches(self) -> None:
        failure = _integrity_failure_for_section(
            _counts(Left=3000, Right=3000),
            _sections(Left=2991, Right=3000),
            "Right",
        )
        self.assertEqual(failure, ("Left", 3000, 2991, True))

    def test_later_mismatch_does_not_block_earlier_verified_section(self) -> None:
        failure = _integrity_failure_for_section(
            _counts(Top=10, Left=3000),
            _sections(Top=10, Left=2991),
            "Top",
        )
        self.assertIsNone(failure)

    def test_recovered_exact_counts_allow_later_section(self) -> None:
        failure = _integrity_failure_for_section(
            _counts(Left=3000, Right=3000),
            _sections(Left=3000, Right=3000),
            "Right",
        )
        self.assertIsNone(failure)

    def test_raster_provenance_accepts_matching_source_record(self) -> None:
        body = _raster_record(50)
        failure = _raster_provenance_failure(
            _FakeDecoder,
            body,
            [{"is_raster_logo": True, "raster_id": 50, "source_offset": 0}],
        )
        self.assertIsNone(failure)

    def test_raster_provenance_detects_decoder_id_mismatch(self) -> None:
        body = _raster_record(50)
        failure = _raster_provenance_failure(
            _FakeDecoder,
            body,
            [{"is_raster_logo": True, "raster_id": 3005, "source_offset": 0}],
        )
        self.assertIsNotNone(failure)
        self.assertIn("source bytes identify raster 50", failure[2])

    def test_raster_provenance_detects_non_raster_source_bytes(self) -> None:
        body = b"\x00\x02" + (101).to_bytes(2, "little") + bytes(28)
        failure = _raster_provenance_failure(
            _FakeDecoder,
            body,
            [{"is_raster_logo": True, "raster_id": 3005, "source_offset": 0}],
        )
        self.assertIsNotNone(failure)
        self.assertIn("not a raster placement", failure[2])


if __name__ == "__main__":
    unittest.main()
