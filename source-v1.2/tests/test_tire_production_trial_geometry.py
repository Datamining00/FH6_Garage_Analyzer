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


def _spec(*, mode: str = "stock", model: str = "Vintage") -> VehicleWheelSpec:
    return VehicleWheelSpec(
        car_id=247,
        mode=mode,
        source_table="Data_Car",
        car_body_id=None,
        tire_compound_id=13,
        tire_model_name=model,
        front=AxleWheelSpec("front", 165.0, 75.0, 15.0),
        rear=AxleWheelSpec("rear", 165.0, 75.0, 15.0),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_archive(path: Path, *, names: tuple[str, ...]) -> None:
    payload = _bundle()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, payload)


def _eligibility(spec: VehicleWheelSpec, archive: Path, *, eligible: bool = True):
    return SimpleNamespace(
        production_trial_eligible=eligible,
        production_renderer_enabled=False,
        weights=stock_vehicle_tire_morph_weights(spec) if eligible else None,
        status="production_trial_eligible" if eligible else "blocked_nonstock_spec",
        detail="global automatic tire generation test",
        policy_revision="stock_native_tire_global_auto_recognition_v3",
        archive_sha256=_sha256(archive),
    )


def _span(item) -> tuple[float, float, float]:
    return tuple(float(value) for value in item.aabb["span"])


class TireProductionTrialGeometryTests(unittest.TestCase):
    def test_unlabelled_single_modelbin_is_auto_recognized_as_canonical_left(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_Vintage.zip"
            _write_archive(archive, names=("weird_native_tire_geometry.modelbin",))
            archive_before = _sha256(archive)
            output = root / "trial"
            spec = _spec()

            with patch(
                "fh6garage.preview3d.tire_production_trial_geometry.evaluate_stock_tire_production_candidate",
                return_value=_eligibility(spec, archive),
            ):
                report = build_stock_tire_production_trial_geometry(spec, archive, output)

            self.assertEqual(report.status, "production_trial_geometry_ready")
            self.assertEqual(_sha256(archive), archive_before)
            self.assertEqual(len(report.front.modelbins), 1)
            self.assertEqual(len(report.rear.modelbins), 1)
            front = report.front.modelbins[0]
            rear = report.rear.modelbins[0]
            self.assertEqual(front.entry, "tireL_Vintage.modelbin")
            self.assertEqual(front.source_entry, "weird_native_tire_geometry.modelbin")
            self.assertEqual(rear.entry, "tireL_Vintage.modelbin")
            self.assertIn("stock_dimension_normalization", front.morph_mode)
            self.assertTrue(Path(front.glb_path or "").is_file())
            self.assertTrue(Path(rear.glb_path or "").is_file())

            target_width = 0.165
            target_outer = (15.0 * 25.4 + 2.0 * 165.0 * 0.75) / 1000.0
            for item in (front, rear):
                span = _span(item)
                self.assertAlmostEqual(span[0], target_width, places=6)
                self.assertAlmostEqual(span[1], target_outer, places=6)
                self.assertAlmostEqual(span[2], target_outer, places=6)

    def test_native_left_right_pair_is_preserved_without_family_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_Vintage.zip"
            _write_archive(
                archive,
                names=("tireL_vintage.modelbin", "tireR_vintage.modelbin"),
            )
            output = root / "trial"
            spec = _spec()

            with patch(
                "fh6garage.preview3d.tire_production_trial_geometry.evaluate_stock_tire_production_candidate",
                return_value=_eligibility(spec, archive),
            ):
                report = build_stock_tire_production_trial_geometry(spec, archive, output)

            self.assertEqual(
                {item.entry for item in report.front.modelbins},
                {"tireL_Vintage.modelbin", "tireR_Vintage.modelbin"},
            )
            self.assertEqual(len(report.front.modelbins), 2)
            self.assertEqual(len(report.rear.modelbins), 2)
            self.assertEqual(
                len(
                    [
                        item.glb_path
                        for axle in (report.front, report.rear)
                        for item in axle.modelbins
                    ]
                ),
                4,
            )

    def test_blocked_nonstock_candidate_creates_no_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_Vintage.zip"
            _write_archive(archive, names=("tireL_vintage.modelbin",))
            output = root / "trial"
            spec = _spec()

            with (
                patch(
                    "fh6garage.preview3d.tire_production_trial_geometry.evaluate_stock_tire_production_candidate",
                    return_value=_eligibility(spec, archive, eligible=False),
                ),
                self.assertRaisesRegex(TireProductionTrialGeometryError, "blocked_nonstock_spec"),
            ):
                build_stock_tire_production_trial_geometry(spec, archive, output)

            self.assertFalse(output.exists())

    def test_archive_change_after_auto_recognition_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_Vintage.zip"
            _write_archive(archive, names=("tireL_vintage.modelbin",))
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
                    "archive changed after automatic recognition",
                ),
            ):
                build_stock_tire_production_trial_geometry(spec, archive, output)


if __name__ == "__main__":
    unittest.main()
