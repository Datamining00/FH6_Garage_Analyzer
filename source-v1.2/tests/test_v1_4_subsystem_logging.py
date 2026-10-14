from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage import subsystem_log


class SubsystemLoggingContractTests(unittest.TestCase):
    def test_all_rc_subsystem_prefixes_are_declared(self) -> None:
        self.assertEqual(
            subsystem_log._ALLOWED,
            {"SCAN", "INDEX", "THUMBNAIL", "POPULATE", "MEMORY", "NAVIGATION", "PERFORMANCE", "THREAD"},
        )

    def test_writer_uses_prefix_and_sanitizes_newlines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "diagnostic.log"
            with patch.object(subsystem_log, "log_path", return_value=target):
                subsystem_log.log_event("SCAN", "scan.complete", detail="a\nb", count=3)
            text = target.read_text(encoding="utf-8")
            self.assertIn("[SCAN] scan.complete", text)
            self.assertIn("count=3", text)
            self.assertIn("detail=a b", text)
            self.assertEqual(text.count("\n"), 1)

    def test_unknown_prefix_cannot_escape_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "diagnostic.log"
            with patch.object(subsystem_log, "log_path", return_value=target):
                subsystem_log.log_event("UNKNOWN", "event")
            self.assertIn("[PERFORMANCE] event", target.read_text(encoding="utf-8"))

    def test_runtime_patch_covers_every_subsystem(self) -> None:
        source = (Path(__file__).parents[1] / "fh6garage" / "v1_4_subsystem_logging_patch.py").read_text(encoding="utf-8")
        for prefix in subsystem_log._ALLOWED:
            self.assertIn(f'"{prefix}"', source)

    def test_vehicle_bridge_installs_logging_patch(self) -> None:
        source = (Path(__file__).parents[1] / "fh6garage" / "v1_4_vehicle_update_thread_bridge_patch.py").read_text(encoding="utf-8")
        self.assertIn("apply_v1_4_subsystem_logging_patch(MainWindow)", source)


if __name__ == "__main__":
    unittest.main()
