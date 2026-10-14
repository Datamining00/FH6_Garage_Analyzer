from __future__ import annotations

import types
import unittest
from pathlib import Path

from fh6garage.memory_applied_state import MemoryScanResult
from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.v1_3_2_memory_filter_coordination_patch import _classify_soulbound_from_memory


def _record(name: str, car_id: int) -> LiveryRecord:
    return LiveryRecord(
        container_name=name,
        container_path=Path("."),
        kind="SoulBoundLivery",
        header=HeaderInfo(car_id=car_id),
    )


class SoulBoundMemoryClassificationTests(unittest.TestCase):
    def test_exact_memory_membership_is_primary_without_cache_dependency(self) -> None:
        window = types.SimpleNamespace(
            result=types.SimpleNamespace(
                liveries=[
                    _record("SoulBoundLivery_0295_20260821131718", 295),
                    _record("SoulBoundLivery_0316_20260715095153", 316),
                ]
            )
        )
        result = MemoryScanResult(
            pid=1234,
            status="HIGH",
            active_livery_names=frozenset({"Livery_0295_20260821131718"}),
        )

        applied, unapplied, review = _classify_soulbound_from_memory(window, result)

        self.assertEqual(applied, {"Livery_0295_20260821131718"})
        self.assertEqual(unapplied, {"Livery_0316_20260715095153"})
        self.assertEqual(review, set())

    def test_review_is_reserved_for_unusable_identity(self) -> None:
        window = types.SimpleNamespace(
            result=types.SimpleNamespace(
                liveries=[_record("SoulBoundLivery_invalid", 1)]
            )
        )
        result = MemoryScanResult(
            pid=1234,
            status="HIGH",
            active_livery_names=frozenset(),
        )

        applied, unapplied, review = _classify_soulbound_from_memory(window, result)

        self.assertEqual(applied, set())
        self.assertEqual(unapplied, set())
        self.assertEqual(review, {"SoulBoundLivery_invalid"})


if __name__ == "__main__":
    unittest.main()
