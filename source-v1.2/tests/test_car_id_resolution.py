from __future__ import annotations

import struct
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from fh6garage.models import HeaderInfo
from fh6garage.parsers import parse_forza_header
from fh6garage.performance_metrics import PerformanceMetrics
from fh6garage.scan_backend import ScanJob
from fh6garage.scanner import (
    _ContainerAnalysis,
    _aggregate_container_analyses,
    _container_car_id,
    _resolve_car_id,
    scan_save,
)


FURAI_HEADER_1 = bytes.fromhex(
    "07 00 00 00 05 00 00 00 46 00 6f 00 72 00 7a 00 "
    "61 00 00 00 00 00 ea 07 08 00 00 00 10 00 09 00 "
    "16 00 2f 00 09 01 03 00 00 00 98 03 38 23 f3 01 "
    "09 00 04 00 00 00 55 00 53 00 45 00 52 00 00 00 "
    "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 00 00 00 01 02 00 00 00 00 "
    "00 00 00 3f 01 00 00 cd 04 00 00 37 3b b4 92 8f "
    "c7 95 4f bb 38 cf 10 10 41 a8 bc e7 e3 3d 99 4e "
    "40 b8 55 6b 1e fa 02 b0 f5"
)

FURAI_HEADER_2 = bytes.fromhex(
    "07 00 00 00 06 00 00 00 46 00 6f 00 72 00 7a 00 "
    "61 00 32 00 00 00 00 00 ea 07 08 00 00 00 10 00 "
    "09 00 16 00 39 00 bb 02 03 00 00 00 98 03 38 23 "
    "f3 01 09 00 04 00 00 00 55 00 53 00 45 00 52 00 "
    "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 00 00 00 00 00 00 00 01 02 00 00 "
    "00 00 00 00 00 3f 01 00 00 cd 04 00 00 b3 ab 5c "
    "a5 29 da bf 48 b6 d3 d3 97 74 de 63 8d 3d 99 4e "
    "40 b8 55 6b 1e fa 02 b0 f5"
)


def _utf16(value: str) -> bytes:
    return struct.pack("<I", len(value)) + value.encode("utf-16le")


def _legacy_fixture_header(kind: str, car_id: int, identity: int) -> bytes:
    common = (
        struct.pack("<HIHHHHH", 2026, 8, 25, 10, 20, 30, 40)
        + (b"\0" * 10)
        + struct.pack("<H", 3)
    )
    tail = (
        b"\0" * 8,
        struct.pack("<I", 2),
        struct.pack("<I", car_id),
        uuid.UUID(int=identity).bytes,
    )
    return b"".join(
        (
            struct.pack("<I", 7),
            _utf16(f"{kind} item"),
            _utf16("description"),
            common,
            _utf16("creator"),
            *tail,
        )
    )


class _FakeCarDatabase:
    def __init__(self, known: set[int]):
        self.known = known

    def is_known(self, car_id: int) -> bool:
        return car_id in self.known

    def get(self, car_id: int):
        label = "2008 Mazda Furai" if car_id == 1229 else f"Car ID {car_id}"
        return SimpleNamespace(label=label)


class CarIdResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        # 1229 = 2008 Mazda Furai in the bundled FH6 CarOrdinal database.
        self.db = _FakeCarDatabase({1229, 343})

    def test_extracts_carordinal_from_livery_container_name(self) -> None:
        self.assertEqual(
            _container_car_id("Livery_1229_20260816092247", "Livery"),
            1229,
        )

    def test_furai_sample_one_parses_verified_creator_relative_fields(self) -> None:
        header = parse_forza_header(FURAI_HEADER_1, "Livery")

        self.assertEqual(header.car_id, 1229)
        self.assertEqual(header.parsed_car_id, 1229)
        self.assertEqual(header.type_value, 319)
        self.assertEqual(
            header.asset_guid,
            "373bb492-8fc7-954f-bb38-cf101041a8bc",
        )
        self.assertEqual(header.created, "2026-08-16 09:22:47.265")

        # Historical values stay byte-for-byte compatible for local identities.
        self.assertEqual(
            header.guid,
            "a8bce7e3-3d99-4e40-b855-6b1efa02b0f5",
        )
        self.assertEqual(header.decal_count, 951799701)
        self.assertEqual(header.platform_code, 9)

    def test_furai_sample_two_parses_verified_creator_relative_fields(self) -> None:
        header = parse_forza_header(FURAI_HEADER_2, "Livery")

        self.assertEqual(header.car_id, 1229)
        self.assertEqual(header.parsed_car_id, 1229)
        self.assertEqual(header.type_value, 319)
        self.assertEqual(
            header.asset_guid,
            "b3ab5ca5-29da-bf48-b6d3-d39774de638d",
        )
        self.assertEqual(header.created, "2026-08-16 09:22:57.699")
        self.assertEqual(
            header.guid,
            "74de638d-3d99-4e40-b855-6b1efa02b0f5",
        )

    def test_legacy_livery_fixture_keeps_tail_parser_compatibility(self) -> None:
        data = _legacy_fixture_header("Livery", 343, 42)
        header = parse_forza_header(data, "Livery")

        self.assertEqual(header.car_id, 343)
        self.assertEqual(header.parsed_car_id, 343)
        self.assertEqual(
            header.guid,
            "00000000-0000-0000-0000-00000000002a",
        )
        self.assertEqual(header.decal_count, 2)
        self.assertEqual(header.platform_code, 3)
        self.assertEqual(header.asset_guid, "")
        self.assertIsNone(header.type_value)

    def test_tuning_fixture_remains_on_legacy_tail_parser(self) -> None:
        data = _legacy_fixture_header("Tuning", 343, 43)
        header = parse_forza_header(data, "Tuning")

        self.assertEqual(header.car_id, 343)
        self.assertEqual(header.parsed_car_id, 343)
        self.assertEqual(
            header.guid,
            "00000000-0000-0000-0000-00000000002b",
        )
        self.assertIsNone(header.decal_count)
        self.assertEqual(header.asset_guid, "")
        self.assertIsNone(header.type_value)

    def test_container_fallback_still_recovers_invalid_header_id(self) -> None:
        self.assertEqual(
            _resolve_car_id(
                "Livery_1229_20260816092247",
                "Livery",
                1091571919,
                self.db,
            ),
            1229,
        )

    def test_container_fallback_still_handles_second_invalid_header_id(self) -> None:
        self.assertEqual(
            _resolve_car_id(
                "Livery_1229_20260816092257",
                "Livery",
                2547241910,
                self.db,
            ),
            1229,
        )

    def test_scan_save_reads_both_supplied_furai_samples_without_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            save_root = Path(tmp) / "save"
            containers = save_root / "current" / "ContainersRoot"
            containers.mkdir(parents=True)

            samples = (
                ("Livery_1229_20260816092247", FURAI_HEADER_1),
                ("Livery_1229_20260816092257", FURAI_HEADER_2),
            )
            for name, header_bytes in samples:
                folder = containers / name
                folder.mkdir()
                (folder / "header").write_bytes(header_bytes)
                (folder / "C_livery").write_bytes(b"sample")

            result = scan_save(save_root, self.db)

            self.assertEqual([item.car_id for item in result.liveries], [1229, 1229])
            self.assertEqual(len(result.car_summaries), 1)
            self.assertEqual(result.car_summaries[0].car_id, 1229)
            self.assertEqual(result.car_summaries[0].label, "2008 Mazda Furai")
            self.assertEqual(result.car_summaries[0].livery_count, 2)
            self.assertFalse(any("1091571919" in warning for warning in result.warnings))
            self.assertFalse(any("2547241910" in warning for warning in result.warnings))

    def test_scanner_preserves_parsed_car_id_across_fallback_and_warm_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_root = root / "save"
            containers = save_root / "current" / "ContainersRoot"
            folder = containers / "Livery_1229_20260816092247"
            folder.mkdir(parents=True)
            (folder / "header").write_bytes(_legacy_fixture_header("Livery", 343, 44))
            (folder / "C_livery").write_bytes(b"sample")
            cache_dir = root / "cache"

            cold = scan_save(save_root, self.db, cache_base_dir=cache_dir)
            self.assertEqual(len(cold.liveries), 1)
            self.assertEqual(cold.liveries[0].header.parsed_car_id, 343)
            self.assertEqual(cold.liveries[0].car_id, 1229)
            cold_counters = cold.diagnostics["scan"]["counters"]
            self.assertGreater(cold_counters.get("header_cache_misses", 0), 0)

            warm = scan_save(save_root, self.db, cache_base_dir=cache_dir)
            self.assertEqual(len(warm.liveries), 1)
            self.assertEqual(warm.liveries[0].header.parsed_car_id, 343)
            self.assertEqual(warm.liveries[0].car_id, 1229)
            warm_counters = warm.diagnostics["scan"]["counters"]
            self.assertGreater(warm_counters.get("header_cache_hits", 0), 0)

    def test_aggregate_resolution_does_not_mutate_parser_header(self) -> None:
        parser_header = HeaderInfo(car_id=343, parsed_car_id=343)
        analysis = _ContainerAnalysis(
            job=ScanJob(
                container=Path("Livery_1229_20260816092247"),
                kind="Livery",
                estimated_bytes=0,
            ),
            header=parser_header,
        )

        liveries, tunings, warnings = _aggregate_container_analyses(
            [analysis],
            self.db,
            PerformanceMetrics(),
        )

        self.assertEqual(len(liveries), 1)
        self.assertFalse(tunings)
        self.assertTrue(warnings)
        self.assertIs(analysis.header, parser_header)
        self.assertEqual(parser_header.car_id, 343)
        self.assertEqual(parser_header.parsed_car_id, 343)
        self.assertIsNot(liveries[0].header, parser_header)
        self.assertEqual(liveries[0].car_id, 1229)
        self.assertEqual(liveries[0].header.parsed_car_id, 343)

    def test_legacy_result_is_unchanged_when_container_name_has_no_ordinal(self) -> None:
        self.assertEqual(
            _resolve_car_id("Livery_unknown", "Livery", 343, self.db),
            343,
        )

    def test_kind_mismatch_does_not_override_header(self) -> None:
        self.assertEqual(
            _resolve_car_id("Tuning_1229_123", "Livery", 343, self.db),
            343,
        )

    def test_unknown_container_ordinal_does_not_replace_known_header(self) -> None:
        self.assertEqual(
            _resolve_car_id("Livery_999999_123", "Livery", 343, self.db),
            343,
        )


if __name__ == "__main__":
    unittest.main()
