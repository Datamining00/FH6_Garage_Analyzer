from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from fh6garage.preview3d.tire_production_policy import evaluate_stock_tire_production_candidate
from fh6garage.preview3d.wheel_spec import AxleWheelSpec, VehicleWheelSpec


def _spec(
    *,
    car_id: int = 247,
    mode: str = "stock",
    model: str = "Vintage",
) -> VehicleWheelSpec:
    return VehicleWheelSpec(
        car_id=car_id,
        mode=mode,
        source_table="Data_Car",
        car_body_id=None,
        tire_compound_id=13,
        tire_model_name=model,
        front=AxleWheelSpec("front", 165.0, 75.0, 15.0),
        rear=AxleWheelSpec("rear", 165.0, 75.0, 15.0),
    )


def _write_archive(path: Path, *modelbins: bytes) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, payload in enumerate(modelbins):
            archive.writestr(f"arbitrary_{index}.modelbin", payload)


class TireProductionPolicyTests(unittest.TestCase):
    def test_any_stock_tire_family_is_globally_admitted_without_selector_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_Vintage.zip"
            _write_archive(archive, b"native")
            result = evaluate_stock_tire_production_candidate(_spec(), archive)

        self.assertEqual(result.status, "production_trial_eligible")
        self.assertTrue(result.production_trial_eligible)
        self.assertIsNotNone(result.weights)
        assert result.weights is not None
        self.assertEqual(result.weights.front.selector_weights, (0.0, 0.0, 0.0, 0.0, 0.0))
        self.assertEqual(result.weights.rear.selector_weights, (0.0, 0.0, 0.0, 0.0, 0.0))
        self.assertEqual(result.weights.front.scale_x, 1.0)
        self.assertEqual(result.weights.rear.scale_x, 1.0)
        self.assertIn("automatic file resolution", result.detail)
        self.assertIn("no tire-family", result.detail)
        self.assertEqual(result.auto_inference_report["status"], "not_required")

    def test_global_policy_is_not_car_or_family_specific(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_UnknownFamily.zip"
            _write_archive(archive, b"unknown")
            result = evaluate_stock_tire_production_candidate(
                _spec(car_id=9001, model="UnknownFamily"),
                archive,
            )

        self.assertTrue(result.production_trial_eligible)
        self.assertEqual(result.car_id, 9001)
        self.assertEqual(result.tire_model_name, "UnknownFamily")

    def test_nonstock_spec_remains_blocked(self) -> None:
        result = evaluate_stock_tire_production_candidate(
            _spec(mode="effective"),
            Path("does-not-exist.zip"),
        )
        self.assertEqual(result.status, "blocked_nonstock_spec")
        self.assertFalse(result.production_trial_eligible)

    def test_archive_name_must_match_automatic_tire_model_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_Other.zip"
            _write_archive(archive, b"native")
            result = evaluate_stock_tire_production_candidate(_spec(model="Vintage"), archive)
        self.assertEqual(result.status, "blocked_archive_model_mismatch")
        self.assertFalse(result.production_trial_eligible)

    def test_archive_without_modelbin_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_Vintage.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("readme.txt", b"no geometry")
            result = evaluate_stock_tire_production_candidate(_spec(), archive)
        self.assertEqual(result.status, "blocked_archive_invalid")
        self.assertFalse(result.production_trial_eligible)


if __name__ == "__main__":
    unittest.main()
