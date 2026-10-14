from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fh6garage import runtime_policy


class RuntimePolicyTests(unittest.TestCase):
    def _detect(self, cpu: int, memory_gib: int):
        with (
            patch.object(runtime_policy.os, "cpu_count", return_value=cpu),
            patch.object(
                runtime_policy,
                "_physical_memory_bytes",
                return_value=memory_gib * 1024**3,
            ),
            patch.dict(
                os.environ,
                {
                    "FH6_ASSISTANT_SCAN_WORKERS": "",
                    "FH6_ASSISTANT_PIXMAP_CACHE_MB": "",
                },
            ),
        ):
            return runtime_policy.detect_runtime_policy()

    def test_low_end_policy_is_sequential_and_small(self) -> None:
        policy = self._detect(2, 4)
        self.assertEqual(policy.scan_workers, 1)
        self.assertEqual(policy.pixmap_cache_bytes, 24 * 1024**2)

    def test_midrange_policy_remains_conservative(self) -> None:
        policy = self._detect(8, 16)
        self.assertEqual(policy.scan_workers, 3)
        self.assertEqual(policy.pixmap_cache_bytes, 96 * 1024**2)

    def test_high_end_policy_caps_workers(self) -> None:
        policy = self._detect(32, 64)
        self.assertEqual(policy.scan_workers, 4)
        self.assertEqual(policy.pixmap_cache_bytes, 128 * 1024**2)

    def test_environment_overrides_are_bounded(self) -> None:
        with (
            patch.object(runtime_policy.os, "cpu_count", return_value=16),
            patch.object(
                runtime_policy,
                "_physical_memory_bytes",
                return_value=32 * 1024**3,
            ),
            patch.dict(
                os.environ,
                {
                    "FH6_ASSISTANT_SCAN_WORKERS": "99",
                    "FH6_ASSISTANT_PIXMAP_CACHE_MB": "1",
                },
            ),
        ):
            policy = runtime_policy.detect_runtime_policy()
        self.assertEqual(policy.scan_workers, 8)
        self.assertEqual(policy.pixmap_cache_bytes, 8 * 1024**2)


if __name__ == "__main__":
    unittest.main()
