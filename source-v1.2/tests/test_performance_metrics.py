from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage.performance_metrics import read_metrics, record_metric


class PerformanceMetricsTests(unittest.TestCase):
    def test_latest_metric_is_persisted_without_unbounded_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"FH6_ASSISTANT_PERF_DIR": temp_dir}
        ):
            record_metric("startup_scan", 12.3456, livery_count=400)
            record_metric("startup_scan", 9.5, livery_count=401)
            payload = read_metrics()
            metric = payload["metrics"]["startup_scan"]
            self.assertEqual(metric["duration_ms"], 9.5)
            self.assertEqual(metric["livery_count"], 401)
            self.assertTrue((Path(temp_dir) / "performance_last.json").is_file())


if __name__ == "__main__":
    unittest.main()
