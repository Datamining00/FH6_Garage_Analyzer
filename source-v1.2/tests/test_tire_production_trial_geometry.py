from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fh6garage.preview3d import tire_production_policy as policy
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


def _write_archive(path: Path) -> str:
    payload = _bundle()
    entries = (
        ("tireL_slick.modelbin", payload),
        ("tireR_slick.modelbin", payload),
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    hashes = sorted(hashlib.sha256(data).hexdigest() for _name, data in entries)
    return hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()


class TireProductionTrialGeometryTests(unittest.TestCase):
    def test_exact_gated_stock_fxx_builds_detached_front_rear_glbs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_slick.zip"
            identity = _write_archive(archive)
            archive_before = _sha256(archive)
            output = root / "trial"

            with patch.object(policy, "_VALIDATED_SLICK_GEOMETRY_IDENTITY", identity):
                report = build_stock_tire_production_trial_geometry(
                    _spec(),
                    archive,
                    output,
                )

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
            self.assertTrue(
                all(float(item.aabb["span"][0]) > 0.0 for item in report.front.modelbins)
            )
            self.assertTrue(
                all(float(item.aabb["span"][0]) > 0.0 for item in report.rear.modelbins)
            )

    def test_blocked_candidate_creates_no_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_slick.zip"
            _write_archive(archive)
            output = root / "trial"

            with self.assertRaisesRegex(
                TireProductionTrialGeometryError,
                "blocked_nonstock_spec",
            ):
                build_stock_tire_production_trial_geometry(
                    _spec(mode="effective"),
                    archive,
                    output,
                )

            self.assertFalse(output.exists())

    def test_unvalidated_geometry_identity_creates_no_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_slick.zip"
            _write_archive(archive)
            output = root / "trial"

            with self.assertRaisesRegex(
                TireProductionTrialGeometryError,
                "blocked_geometry_identity_mismatch",
            ):
                build_stock_tire_production_trial_geometry(_spec(), archive, output)

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
