from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from fh6garage import performance_metrics, subsystem_log
from fh6garage.diagnostic_export import build_manifest, export_diagnostics


class _Settings:
    def value(self, key, default=None, _type=None):
        if key == "vehicle_data_source":
            return "user"
        return default


class _Window:
    settings = _Settings()

    def __init__(self):
        self.result = SimpleNamespace(
            liveries=[1, 2],
            tunings=[1],
            warnings=["warning"],
        )
        self._fh6_memory_state = SimpleNamespace(
            scanned_at="2026-09-01T00:00:00Z",
            consensus_status="HIGH",
            usable=True,
            active_livery_names=frozenset({"SECRET_LIVERY"}),
            soulbound_applied_names=frozenset({"SECRET_APPLIED"}),
            soulbound_unapplied_names=frozenset({"SECRET_UNAPPLIED"}),
            soulbound_review_names=frozenset({"SECRET_REVIEW"}),
            candidate_regions=4,
            read_bytes=1024,
            read_failures=2,
            elapsed_seconds=1.25,
            pid=99999,
            dominant_fingerprint="SECRET_FINGERPRINT",
        )

    def windowTitle(self):
        return "FH6 Assistant v1.4"


class DiagnosticExportTests(unittest.TestCase):
    def test_manifest_contains_counts_not_memory_identifiers(self):
        text = json.dumps(build_manifest(_Window()), ensure_ascii=False)
        self.assertIn('"vehicle_data_source": "user"', text)
        self.assertIn('"active_livery_count": 1', text)
        self.assertNotIn("SECRET_LIVERY", text)
        self.assertNotIn("SECRET_FINGERPRINT", text)
        self.assertNotIn("99999", text)

    def test_export_contains_only_expected_diagnostic_files(self):
        with tempfile.TemporaryDirectory() as temp:
            previous = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = temp
            try:
                diag = subsystem_log.log_path()
                diag.parent.mkdir(parents=True, exist_ok=True)
                diag.write_text("safe diagnostic\n", encoding="utf-8")
                diag.with_suffix(".log.1").write_text("rotated\n", encoding="utf-8")

                perf = performance_metrics.log_path()
                perf.parent.mkdir(parents=True, exist_ok=True)
                perf.write_text('{"name":"safe"}\n', encoding="utf-8")
                (performance_metrics.log_dir() / "latest.json").write_text(
                    '{"safe":true}\n', encoding="utf-8"
                )

                target = Path(temp) / "export.zip"
                exported = export_diagnostics(_Window(), target)
                self.assertEqual(exported, target)
                with zipfile.ZipFile(exported) as archive:
                    names = set(archive.namelist())
                    self.assertIn("manifest.json", names)
                    self.assertIn("diagnostic/diagnostic.log", names)
                    self.assertIn("diagnostic/diagnostic.log.1", names)
                    self.assertIn("performance/performance.jsonl", names)
                    self.assertIn("performance/latest.json", names)
                    manifest = archive.read("manifest.json").decode("utf-8")
                    self.assertNotIn(temp, manifest)
                    self.assertNotIn("SECRET_LIVERY", manifest)
            finally:
                if previous is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = previous

    def test_ui_patch_is_installed_after_subsystem_logging(self):
        root = Path(__file__).resolve().parents[1]
        bridge = (root / "fh6garage" / "v1_4_vehicle_update_thread_bridge_patch.py").read_text(encoding="utf-8")
        self.assertIn("apply_v1_4_diagnostic_export_patch", bridge)
        self.assertLess(
            bridge.index("apply_v1_4_subsystem_logging_patch(MainWindow)"),
            bridge.index("apply_v1_4_diagnostic_export_patch(MainWindow)"),
        )
        patch = (root / "fh6garage" / "v1_4_diagnostic_export_patch.py").read_text(encoding="utf-8")
        self.assertIn('findChild(QFrame, "sidebar")', patch)
        self.assertIn('setObjectName("fh6DiagnosticExportButton")', patch)


if __name__ == "__main__":
    unittest.main()
