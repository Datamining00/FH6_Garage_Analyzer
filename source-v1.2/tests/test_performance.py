from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fh6garage.performance import PerformanceRecorder

# The performance build is diagnostic-only; these tests remain filesystem-local and network-free.


class PerformanceRecorderTests(unittest.TestCase):
    def test_nested_timings_and_report_files(self) -> None:
        recorder = PerformanceRecorder()
        recorder.reset()

        with recorder.measure("scan.save", {"liveries": 12}):
            with recorder.measure(
                "scan.livery_sha256",
                {"container": "Livery_247_test", "bytes": 1024},
            ):
                pass
        recorder.record(
            "ui.livery_grid_build",
            0.012,
            details={"cards": 12},
        )

        events = recorder.events()
        self.assertEqual(len(events), 3)
        self.assertTrue(all(event.duration_ms >= 0 for event in events))
        self.assertEqual(
            {event.name for event in events},
            {"scan.save", "scan.livery_sha256", "ui.livery_grid_build"},
        )

        with tempfile.TemporaryDirectory() as temp:
            txt_path, json_path = recorder.save_report(Path(temp))
            self.assertTrue(txt_path.is_file())
            self.assertTrue(json_path.is_file())

            text = txt_path.read_text(encoding="utf-8")
            self.assertIn("Performance Report", text)
            self.assertIn("scan.save", text)
            self.assertIn("scan.livery_sha256", text)
            self.assertIn("Timers can be nested", text)

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["format_version"], 1)
            self.assertEqual(len(payload["events"]), 3)
            hash_event = next(
                event
                for event in payload["events"]
                if event["name"] == "scan.livery_sha256"
            )
            self.assertEqual(hash_event["details"]["bytes"], 1024)

    def test_paths_are_reduced_to_final_component(self) -> None:
        recorder = PerformanceRecorder()
        recorder.record(
            "test.path",
            0.001,
            details={"path": Path("private") / "folder" / "item.bin"},
        )
        event = recorder.events()[0]
        self.assertEqual(event.details["path"], "item.bin")

    def test_reset_discards_events(self) -> None:
        recorder = PerformanceRecorder()
        recorder.record("test", 0.1)
        self.assertEqual(len(recorder.events()), 1)
        recorder.reset()
        self.assertEqual(recorder.events(), [])


if __name__ == "__main__":
    unittest.main()
