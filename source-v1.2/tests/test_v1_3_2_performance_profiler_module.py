from __future__ import annotations

import unittest
from pathlib import Path


class V132PerformanceProfilerModuleContractTests(unittest.TestCase):
    def test_profiler_implementation_is_physically_separated_with_legacy_reexport(self) -> None:
        root = Path(__file__).resolve().parents[1]
        legacy = (
            root / "fh6garage" / "v1_3_2_thread_affinity_patch.py"
        ).read_text(encoding="utf-8")
        profiler = (
            root / "fh6garage" / "v1_3_2_performance_profiler.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "from .v1_3_2_performance_profiler import apply_v1_3_2_performance_profiler",
            legacy,
        )
        self.assertNotIn(
            "def apply_v1_3_2_performance_profiler(MainWindow) -> None:",
            legacy,
        )
        self.assertIn(
            "def apply_v1_3_2_performance_profiler(MainWindow) -> None:",
            profiler,
        )


if __name__ == "__main__":
    unittest.main()
