from __future__ import annotations

import unittest
from pathlib import Path

from fh6garage.livery_raw_transform_anomaly_diagnostic import _selected_group_ids


class RawTransformAnomalyDiagnosticTests(unittest.TestCase):
    def test_unique_ff_group_selects_neighbours_without_hardcoded_section(self):
        call = {
            "requested_section": "Anything",
            "groups": [
                {"group_id": f"g{i}", "offset": i * 100, "flags": 0, "marker_hex": "20"}
                for i in range(10)
            ],
        }
        call["groups"][5]["flags"] = 0xFF
        selected = _selected_group_ids(call)
        self.assertEqual(selected, {"g2", "g3", "g4", "g5", "g6", "g7", "g8"})

    def test_extended_marker_is_anomaly_even_without_ff_flags(self):
        call = {
            "groups": [
                {"group_id": "before", "offset": 10, "flags": 0, "marker_hex": "20"},
                {
                    "group_id": "target",
                    "offset": 20,
                    "flags": 0,
                    "marker_hex": "0002000100000003",
                },
                {"group_id": "after", "offset": 30, "flags": 0, "marker_hex": "20"},
            ]
        }
        self.assertEqual(_selected_group_ids(call), {"before", "target", "after"})

    def test_app_installs_raw_trace_after_group_trace(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        text = app_path.read_text(encoding="utf-8")
        group_pos = text.index("install_group_transform_diagnostic()")
        raw_pos = text.index("install_raw_transform_anomaly_diagnostic()")
        self.assertGreater(raw_pos, group_pos)


if __name__ == "__main__":
    unittest.main()
