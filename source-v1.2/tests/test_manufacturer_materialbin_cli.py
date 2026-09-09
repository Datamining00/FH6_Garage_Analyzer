from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fh6garage.preview3d import manufacturer_materialbin_cli as cli
from fh6garage.preview3d.wheel_morph_helper import (
    WHEEL_MORPH_HELPER_REVISION,
    WHEEL_MORPH_HELPER_SHA256,
)


class ManufacturerMaterialbinCliTests(unittest.TestCase):
    def _inputs(self, root: Path) -> tuple[Path, Path, Path]:
        glb = root / "car.glb"
        paint = root / "C_livery"
        vehicle = root / "CAR_TEST.zip"
        glb.write_bytes(b"glb")
        paint.write_bytes(b"paint")
        vehicle.write_bytes(b"zip")
        return glb, paint, vehicle

    def test_packaged_cli_writes_read_only_evidence_and_helper_identity(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            glb, paint, vehicle = self._inputs(root)
            cache = root / "diagnostic-cache"
            output = root / "result.json"
            p3d = {
                "status": "manufacturer_overlay_candidates_diagnosed",
                "exact_candidate_count": 0,
            }
            traced = {
                "format": "fh6_manufacturer_materialbin_diagnostics_v1",
                "revision": 1,
                "status": "manufacturer_materialbin_payloads_diagnosed",
                "candidate_count": 1,
                "exact_resolved_count": 1,
                "blocked_count": 0,
                "unresolved_count": 0,
                "rendering_enabled": False,
                "rendering_applied": False,
                "game_data_modified": False,
                "traces": [],
                "issues": [],
            }
            with patch.object(cli, "diagnose_manufacturer_overlay", return_value=p3d) as diagnose, patch.object(
                cli, "trace_manufacturer_materialbin_payloads", return_value=traced
            ) as trace:
                rc = cli.run_manufacturer_materialbin_diagnostic(
                    [
                        "--glb", str(glb),
                        "--paint", str(paint),
                        "--vehicle", str(vehicle),
                        "--cache", str(cache),
                        "--output", str(output),
                    ]
                )

            self.assertEqual(rc, 0)
            diagnose.assert_called_once_with(glb.resolve(), paint.resolve(), vehicle.resolve())
            trace.assert_called_once_with(p3d, vehicle.resolve(), cache.resolve())
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["validation_status"], "exact_swatch_chain_resolved")
            self.assertEqual(report["helper_revision"], WHEEL_MORPH_HELPER_REVISION)
            self.assertEqual(report["helper_sha256"], WHEEL_MORPH_HELPER_SHA256)
            self.assertFalse(report["game_data_modified"])
            self.assertFalse(report["rendering_enabled"])
            self.assertEqual(report["glb_file"], str(glb.resolve()))
            self.assertEqual(report["paint_source"], str(paint.resolve()))
            self.assertEqual(report["vehicle_archive"], str(vehicle.resolve()))

    def test_self_check_verifies_packaged_helper_without_game_inputs(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            helper = root / "Kfps.ChassisConverter.WheelMorph.exe"
            helper.write_bytes(b"verified-by-mock")
            output = root / "self-check.json"
            with patch.object(cli, "verified_bundled_wheel_morph_helper", return_value=helper.resolve()):
                rc = cli.run_manufacturer_materialbin_diagnostic(
                    ["--self-check", "--output", str(output)]
                )
            self.assertEqual(rc, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "packaged_p3f_self_check_passed")
            self.assertEqual(report["validation_status"], "packaged_contract_ready")
            self.assertEqual(report["helper_revision"], WHEEL_MORPH_HELPER_REVISION)
            self.assertEqual(report["helper_sha256"], WHEEL_MORPH_HELPER_SHA256)
            self.assertFalse(report["rendering_enabled"])
            self.assertFalse(report["game_data_modified"])

    def test_self_check_fails_closed_when_verified_helper_is_missing(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "self-check.json"
            with patch.object(cli, "verified_bundled_wheel_morph_helper", return_value=None):
                rc = cli.run_manufacturer_materialbin_diagnostic(
                    ["--self-check", "--output", str(output)]
                )
            self.assertEqual(rc, 4)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "packaged_p3f_self_check_failed")
            self.assertEqual(report["validation_status"], "packaged_contract_unavailable")
            self.assertFalse(report["game_data_modified"])

    def test_validation_status_distinguishes_no_candidate_blocked_and_unresolved(self):
        self.assertEqual(
            cli._validation_status({"status": "manufacturer_materialbin_payloads_diagnosed", "candidate_count": 0}),
            "no_materialbin_candidate",
        )
        self.assertEqual(
            cli._validation_status({
                "status": "manufacturer_materialbin_payloads_diagnosed",
                "candidate_count": 1,
                "blocked_count": 1,
            }),
            "materialbin_chain_blocked",
        )
        self.assertEqual(
            cli._validation_status({
                "status": "manufacturer_materialbin_payloads_diagnosed",
                "candidate_count": 1,
                "blocked_count": 0,
            }),
            "materialbin_chain_unresolved",
        )
        self.assertEqual(cli._validation_status({"status": "other"}), "diagnostic_unavailable")

    def test_output_cannot_overwrite_source_input(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            glb, paint, vehicle = self._inputs(root)
            rc = cli.run_manufacturer_materialbin_diagnostic(
                [
                    "--glb", str(glb),
                    "--paint", str(paint),
                    "--vehicle", str(vehicle),
                    "--cache", str(root / "cache"),
                    "--output", str(paint),
                ]
            )
            self.assertEqual(rc, 2)
            self.assertEqual(paint.read_bytes(), b"paint")

    def test_diagnostic_exception_writes_fail_closed_json_without_game_write_claim(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            glb, paint, vehicle = self._inputs(root)
            output = root / "failure.json"
            with patch.object(cli, "diagnose_manufacturer_overlay", side_effect=RuntimeError("boom")):
                rc = cli.run_manufacturer_materialbin_diagnostic(
                    [
                        "--glb", str(glb),
                        "--paint", str(paint),
                        "--vehicle", str(vehicle),
                        "--cache", str(root / "cache"),
                        "--output", str(output),
                    ]
                )
            self.assertEqual(rc, 5)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "manufacturer_materialbin_diagnostic_failed")
            self.assertEqual(report["validation_status"], "diagnostic_execution_failed")
            self.assertFalse(report["game_data_modified"])


if __name__ == "__main__":
    unittest.main()
