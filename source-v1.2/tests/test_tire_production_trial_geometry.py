from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fh6garage.preview3d.tire_morph_weights import stock_vehicle_tire_morph_weights
from fh6garage.preview3d.tire_production_trial_geometry import (
    TireProductionTrialGeometryError,
    build_stock_tire_production_trial_geometry,
)
from fh6garage.preview3d.wheel_spec import AxleWheelSpec, VehicleWheelSpec
from tests.test_tire_morph_geometry import _bundle


def _spec(*, mode: str = "stock") -> VehicleWheelSpec:
    return VehicleWheelSpec(
        car_id=1006,
        mode=mode,
        source_table="Data_Car",
        car_body_id=None,
        tire_compound_id=13,
        tire_model_name="Slick",
        front=AxleWheelSpec("front", 245.0, 35.0, 19.0),
        rear=AxleWheelSpec("rear", 345.0, 35.0, 19.0),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_archive(path: Path) -> None:
    payload = _bundle()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("tireL_slick.modelbin", payload)
        archive.writestr("tireR_slick.modelbin", payload)


def _eligibility(spec: VehicleWheelSpec, archive: Path, *, eligible: bool = True):
    return SimpleNamespace(
        production_trial_eligible=eligible,
        production_renderer_enabled=False,
        weights=stock_vehicle_tire_morph_weights(spec) if eligible else None,
        status="production_trial_eligible" if eligible else "blocked_generic_auto_inference_failed",
        detail="generic auto inference test",
        policy_revision="stock_native_tire_generic_auto_inference_v1",
        archive_sha256=_sha256(archive),
    )


class TireProductionTrialGeometryTests(unittest.TestCase):
    def test_generic_gated_stock_tire_builds_detached_front_rear_glbs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_slick.zip"
            _write_archive(archive)
            archive_before = _sha256(archive)
            output = root / "trial"
            spec = _spec()

            with patch(
                "fh6garage.preview3d.tire_production_trial_geometry.evaluate_stock_tire_production_candidate",
                return_value=_eligibility(spec, archive),
            ):
                report = build_stock_tire_production_trial_geometry(spec, archive, output)

            self.assertEqual(report.status, "production_trial_geometry_ready")
            self.assertEqual(report.eligibility_status, "production_trial_eligible")
            self.assertTrue(report.archive_read_only_unchanged)
            self.assertEqual(_sha256(archive), archive_before)
            self.assertTrue(report.derived_geometry_only)
            self.assertTrue(report.trial_renderer_input_ready)
            self.assertFalse(report.production_renderer_enabled)
            self.assertFalse(report.spindle_attachment_enabled)
            self.assertEqual(report.front.selector_weights[2:], (0.0, 0.0, 0.0))
            self.assertEqual(report.rear.selector_weights[2:], (0.0, 0.0, 0.0))
            self.assertAlmostEqual(report.front.scale_x, 0.245)
            self.assertAlmostEqual(report.rear.scale_x, 0.345)
            self.assertEqual(len(report.front.modelbins), 2)
            self.assertEqual(len(report.rear.modelbins), 2)
            self.assertTrue(Path(report.manifest_path).is_file())

            glbs = [
                item.glb_path
                for axle in (report.front, report.rear)
                for item in axle.modelbins
            ]
            self.assertEqual(len(glbs), 4)
            self.assertTrue(all(path is not None and Path(path).is_file() for path in glbs))
            self.assertTrue(all(item.selected_mesh_count > 0 for item in report.front.modelbins))
            self.assertTrue(all(item.selected_mesh_count > 0 for item in report.rear.modelbins))

    def test_blocked_candidate_creates_no_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_slick.zip"
            _write_archive(archive)
            output = root / "trial"
            spec = _spec()

            with (
                patch(
                    "fh6garage.preview3d.tire_production_trial_geometry.evaluate_stock_tire_production_candidate",
                    return_value=_eligibility(spec, archive, eligible=False),
                ),
                self.assertRaisesRegex(
                    TireProductionTrialGeometryError,
                    "blocked_generic_auto_inference_failed",
                ),
            ):
                build_stock_tire_production_trial_geometry(spec, archive, output)

            self.assertFalse(output.exists())

    def test_archive_change_after_eligibility_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_slick.zip"
            _write_archive(archive)
            output = root / "trial"
            spec = _spec()
            eligibility = _eligibility(spec, archive)
            eligibility = SimpleNamespace(**{**eligibility.__dict__, "archive_sha256": "0" * 64})

            with (
                patch(
                    "fh6garage.preview3d.tire_production_trial_geometry.evaluate_stock_tire_production_candidate",
                    return_value=eligibility,
                ),
                self.assertRaisesRegex(
                    TireProductionTrialGeometryError,
                    "archive changed after production eligibility",
                ),
            ):
                build_stock_tire_production_trial_geometry(spec, archive, output)


if __name__ == "__main__":
    unittest.main()
