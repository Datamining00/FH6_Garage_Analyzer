from __future__ import annotations

import unittest

from fh6garage.memory_snapshot_guard import detect_suspicious_snapshot_drop


class MemorySnapshotGuardTests(unittest.TestCase):
    def test_normal_single_livery_change_is_not_suspicious(self) -> None:
        self.assertIsNone(detect_suspicious_snapshot_drop(327, 326))

    def test_small_baseline_is_not_used_for_guarding(self) -> None:
        self.assertIsNone(detect_suspicious_snapshot_drop(40, 10))

    def test_large_absolute_drop_but_retained_majority_is_not_suspicious(self) -> None:
        self.assertIsNone(detect_suspicious_snapshot_drop(327, 250))

    def test_large_relative_and_absolute_drop_is_suspicious(self) -> None:
        diagnostic = detect_suspicious_snapshot_drop(327, 150)
        self.assertIsNotNone(diagnostic)
        assert diagnostic is not None
        self.assertEqual(diagnostic.previous_count, 327)
        self.assertEqual(diagnostic.current_count, 150)
        self.assertEqual(diagnostic.dropped_count, 177)
        self.assertAlmostEqual(diagnostic.retained_ratio, 150 / 327)

    def test_exact_threshold_is_suspicious(self) -> None:
        diagnostic = detect_suspicious_snapshot_drop(100, 60)
        self.assertIsNotNone(diagnostic)
        assert diagnostic is not None
        self.assertEqual(diagnostic.dropped_count, 40)

    def test_negative_counts_are_safely_clamped(self) -> None:
        self.assertIsNone(detect_suspicious_snapshot_drop(-1, -100))


if __name__ == "__main__":
    unittest.main()
