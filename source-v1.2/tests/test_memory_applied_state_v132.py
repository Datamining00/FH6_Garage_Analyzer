from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fh6garage import memory_applied_state as memory


class MemoryAppliedStateTests(unittest.TestCase):
    def test_accepts_tuning_tail_with_same_car(self) -> None:
        data = b"xxLivery_0247_20260804172812Tuning_0247_20260804170000yy"
        records = memory.scan_buffer(data, 0x2000)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].livery_name, "Livery_0247_20260804172812")
        self.assertEqual(records[0].car_id, 247)

    def test_accepts_guid_tail(self) -> None:
        data = (
            b"Livery_0247_20260804172812"
            b"00000000-0000-0000-0000-000000000000"
        )
        records = memory.scan_buffer(data, 0)
        self.assertEqual(len(records), 1)

    def test_rejects_tuning_tail_with_different_car(self) -> None:
        data = b"Livery_0247_20260804172812Tuning_0260_20260804170000"
        self.assertEqual(memory.scan_buffer(data, 0), [])

    def test_repeated_largest_snapshot_is_high_confidence(self) -> None:
        first = memory.RegionScan(
            memory.Region(0x1000, 100, 4),
            [
                memory.StrictRecord(1, "Livery_0001_20260101000000", 1),
                memory.StrictRecord(2, "Livery_0002_20260101000000", 2),
            ],
            memory.ReadStats(),
        )
        second = memory.RegionScan(
            memory.Region(0x2000, 100, 4),
            [
                memory.StrictRecord(3, "Livery_0001_20260101000000", 1),
                memory.StrictRecord(4, "Livery_0002_20260101000000", 2),
            ],
            memory.ReadStats(),
        )
        transient = memory.RegionScan(
            memory.Region(0x3000, 100, 4),
            [memory.StrictRecord(5, "Livery_0001_20260101000000", 1)],
            memory.ReadStats(),
        )

        status, names, _digest, regions, _note = memory._consensus(
            [first, second, transient]
        )
        self.assertEqual(status, "HIGH")
        self.assertEqual(len(names), 2)
        self.assertEqual(regions, (0x1000, 0x2000))

    def test_soulbound_container_normalizes_to_livery_name(self) -> None:
        self.assertEqual(
            memory.normalized_livery_name(
                "SoulBoundLivery_0295_20260821131718"
            ),
            "Livery_0295_20260821131718",
        )

    def test_persisted_state_round_trip(self) -> None:
        result = memory.MemoryScanResult(
            pid=123,
            status="HIGH",
            active_livery_names=frozenset({"Livery_0001_20260101000000"}),
        )
        state = memory.build_persisted_state(
            result,
            soulbound_applied_names={"Livery_0002_20260101000000"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "memory-state.json"
            self.assertTrue(memory.save_applied_state(state, path))
            self.assertEqual(memory.load_applied_state(path), state)


if __name__ == "__main__":
    unittest.main()
