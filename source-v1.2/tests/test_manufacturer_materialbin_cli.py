from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fh6garage.preview3d import manufacturer_materialbin_cli as cli
from fh6garage.preview3d.chassis_converter import ConversionResult
from fh6garage.preview3d.vehicle_index import VehicleAsset
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

    @staticmethod
    def _trace_report() -> dict:
        return {
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
            traced = self._trace_report()
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
            self.assertEqual(report["auto_input_preparation"]["glb_mode"], "explicit")
            self.assertEqual(report["auto_input_preparation"]["paint_mode"], "explicit")

    def test_vehicle_only_mode_auto_prepares_glb_and_matching_livery(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            glb, paint, vehicle = self._inputs(root)
            cache = root / "diagnostic-cache"
            output = root / "auto-result.json"
            asset = VehicleAsset(
                car_id=1006,
                model_code="FER_FXX_05",
                archive_path=str(vehicle.resolve()),
                archive_name=vehicle.name,
                carbin_entries=("FER_FXX_05.carbin",),
                mask_xml=None,
                mask_assets=(),
            )
            p3d = {
                "status": "manufacturer_overlay_candidates_diagnosed",
                "exact_candidate_count": 1,
            }
            traced = self._trace_report()
            paint_meta = {
                "mode": "automatic_car_id_match",
                "car_id": 1006,
                "selected_paint": str(paint.resolve()),
                "game_data_modified": False,
            }
            glb_meta = {
                "mode": "automatic_vehicle_zip_conversion",
                "car_id": 1006,
                "generated_glb": str(glb.resolve()),
                "game_data_modified": False,
            }
            with patch.object(cli, "load_vehicle_asset", return_value=asset) as load_asset, patch.object(
                cli, "_auto_select_paint", return_value=(paint.resolve(), paint_meta)
            ) as select_paint, patch.object(
                cli, "_auto_generate_glb", return_value=(glb.resolve(), glb_meta)
            ) as generate_glb, patch.object(
                cli, "diagnose_manufacturer_overlay", return_value=p3d
            ) as diagnose, patch.object(
                cli, "trace_manufacturer_materialbin_payloads", return_value=traced
            ):
                rc = cli.run_manufacturer_materialbin_diagnostic(
                    [
                        "--vehicle", str(vehicle),
                        "--cache", str(cache),
                        "--output", str(output),
                    ]
                )

            self.assertEqual(rc, 0)
            load_asset.assert_called_once_with(vehicle.resolve())
            select_paint.assert_called_once_with(1006, None)
            generate_glb.assert_called_once_with(asset, cache.resolve())
            diagnose.assert_called_once_with(glb.resolve(), paint.resolve(), vehicle.resolve())
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["auto_input_preparation"]["glb_mode"], "automatic")
            self.assertEqual(report["auto_input_preparation"]["paint_mode"], "automatic")
            self.assertEqual(report["auto_input_preparation"]["paint"]["car_id"], 1006)
            self.assertEqual(report["auto_input_preparation"]["glb"]["car_id"], 1006)
            self.assertEqual(report["glb_file"], str(glb.resolve()))
            self.assertEqual(report["paint_source"], str(paint.resolve()))

    def test_auto_livery_prefers_manufacturer_ready_matching_car(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            containers = root / "current" / "ContainersRoot"
            factory_dir = containers / "BaseLivery_1006_20260101000000"
            custom_dir = containers / "Livery_1006_20260909000000"
            wrong_dir = containers / "Livery_1260_20260909000001"
            for folder in (factory_dir, custom_dir, wrong_dir):
                folder.mkdir(parents=True)
                (folder / "C_livery").write_bytes(b"paint")

            def provenance(source):
                parent = Path(source).parent.name
                if parent.startswith("BaseLivery_1006"):
                    return {
                        "status": "paint_descriptor_parsed",
                        "car_id": 1006,
                        "records": [
                            {
                                "primary_color_enabled": False,
                                "manufacturer_color_selector": 2,
                            }
                        ],
                    }
                if parent.startswith("Livery_1006"):
                    return {
                        "status": "paint_descriptor_parsed",
                        "car_id": 1006,
                        "records": [
                            {
                                "primary_color_enabled": True,
                                "manufacturer_color_selector": 0xFFFFFFFF,
                            }
                        ],
                    }
                return {
                    "status": "paint_descriptor_parsed",
                    "car_id": 1260,
                    "records": [],
                }

            with patch.object(cli, "diagnose_livery_paint", side_effect=provenance):
                selected, metadata = cli._auto_select_paint(1006, root)

            self.assertEqual(selected, (factory_dir / "C_livery").resolve())
            self.assertEqual(metadata["candidate_count"], 2)
            self.assertEqual(metadata["parseable_matching_count"], 2)
            self.assertEqual(metadata["manufacturer_ready_count"], 1)
            self.assertEqual(metadata["selected_kind"], "BaseLivery")
            self.assertTrue(metadata["selected_manufacturer_ready"])
            self.assertEqual(
                metadata["selection_reason"],
                "manufacturer_ready_then_kind_then_newest",
            )

    def test_auto_glb_uses_verified_packaged_helper_and_cache_output(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            vehicle = root / "FER_FXX_05.zip"
            vehicle.write_bytes(b"zip")
            helper = root / "Kfps.ChassisConverter.WheelMorph.exe"
            helper.write_bytes(b"helper")
            generated = root / "cache" / "AutoInputs" / "car_1006_FER_FXX_05" / "car_1006_FER_FXX_05.glb"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"glTF" + b"\x00" * 8)
            asset = VehicleAsset(
                car_id=1006,
                model_code="FER_FXX_05",
                archive_path=str(vehicle.resolve()),
                archive_name=vehicle.name,
                carbin_entries=("FER_FXX_05.carbin",),
                mask_xml=None,
                mask_assets=(),
            )
            conversion = ConversionResult(
                output_path=str(generated.resolve()),
                helper_path=str(helper.resolve()),
                diagnostics={"scene_assembled": True},
            )
            with patch.object(
                cli, "verified_bundled_wheel_morph_helper", return_value=helper.resolve()
            ), patch.object(cli, "convert_vehicle", return_value=conversion) as convert:
                glb, metadata = cli._auto_generate_glb(asset, root / "cache")

            self.assertEqual(glb, generated.resolve())
            convert.assert_called_once_with(
                asset,
                carbin_entry="FER_FXX_05.carbin",
                work_root=root / "cache" / "AutoInputs" / "car_1006_FER_FXX_05",
                converter_override=helper.resolve(),
            )
            self.assertEqual(metadata["car_id"], 1006)
            self.assertEqual(metadata["generated_glb"], str(generated.resolve()))
            self.assertFalse(metadata["game_data_modified"])

    def test_auto_prepare_failure_writes_fail_closed_evidence(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, vehicle = self._inputs(root)
            output = root / "failure.json"
            asset = VehicleAsset(
                car_id=1006,
                model_code="FER_FXX_05",
                archive_path=str(vehicle.resolve()),
                archive_name=vehicle.name,
                carbin_entries=("FER_FXX_05.carbin",),
                mask_xml=None,
                mask_assets=(),
            )
            with patch.object(cli, "load_vehicle_asset", return_value=asset), patch.object(
                cli, "_auto_select_paint", side_effect=cli.P3FAutoInputError("no matching livery")
            ):
                rc = cli.run_manufacturer_materialbin_diagnostic(
                    [
                        "--vehicle", str(vehicle),
                        "--cache", str(root / "cache"),
                        "--output", str(output),
                    ]
                )
            self.assertEqual(rc, 6)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "p3f_input_preparation_failed")
            self.assertEqual(report["validation_status"], "input_preparation_failed")
            self.assertIn("no matching livery", report["detail"])
            self.assertFalse(report["game_data_modified"])

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
