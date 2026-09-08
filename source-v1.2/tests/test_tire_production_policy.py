from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fh6garage.preview3d import tire_production_policy as policy
from fh6garage.preview3d.tire_morph_auto_inference import TireMorphAutoInferenceError
from fh6garage.preview3d.tire_morph_weights import stock_vehicle_tire_morph_weights
from fh6garage.preview3d.tire_production_policy import evaluate_stock_tire_production_candidate
from fh6garage.preview3d.wheel_spec import AxleWheelSpec, VehicleWheelSpec


def _spec(
    *,
    car_id: int = 247,
    mode: str = "stock",
    model: str = "Vintage",
    front_width: float = 165.0,
) -> VehicleWheelSpec:
    return VehicleWheelSpec(
        car_id=car_id,
        mode=mode,
        source_table="Data_Car",
        car_body_id=None,
        tire_compound_id=13,
        tire_model_name=model,
        front=AxleWheelSpec("front", front_width, 75.0, 15.0),
        rear=AxleWheelSpec("rear", 165.0, 75.0, 15.0),
    )


def _write_archive(path: Path, *modelbins: bytes) -> str:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, payload in enumerate(modelbins):
            archive.writestr(f"arbitrary_{index}.modelbin", payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inference(spec: VehicleWheelSpec, archive: Path):
    weights = stock_vehicle_tire_morph_weights(spec)
    payload = {
        "format": "fh6_generic_native_tire_morph_auto_inference_v1",
        "status": "generic_auto_inference_accepted",
    }
    return SimpleNamespace(
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        archive_read_only_unchanged=True,
        weights=weights,
        persistent_report_path="diagnostic.json",
        as_dict=lambda: dict(payload),
    )


class TireProductionPolicyTests(unittest.TestCase):
    def test_any_stock_tire_family_is_globally_admitted_when_inference_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_Vintage.zip"
            _write_archive(archive, b"native")
            spec = _spec()
            inferred = _inference(spec, archive)
            with patch.object(policy, "infer_stock_native_tire_morph", return_value=inferred):
                result = evaluate_stock_tire_production_candidate(spec, archive)

        self.assertEqual(result.status, "production_trial_eligible")
        self.assertTrue(result.production_trial_eligible)
        self.assertIs(result.weights, inferred.weights)
        self.assertIn("no tire-family whitelist", result.detail)

    def test_selector_inference_failure_uses_global_geometry_normalization_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_Vintage.zip"
            _write_archive(archive, b"native")
            error = TireMorphAutoInferenceError(
                "selector response unavailable",
                report={"status": "auto_inference_rejected"},
            )
            with patch.object(policy, "infer_stock_native_tire_morph", side_effect=error):
                result = evaluate_stock_tire_production_candidate(_spec(), archive)

        self.assertEqual(result.status, "production_trial_eligible")
        self.assertTrue(result.production_trial_eligible)
        self.assertIsNotNone(result.weights)
        self.assertIsNotNone(result.auto_inference_report)
        assert result.auto_inference_report is not None
        self.assertEqual(
            result.auto_inference_report["status"],
            "selector_auto_inference_unavailable_using_geometry_normalization",
        )
        self.assertIn("normalization", result.detail)

    def test_global_policy_is_not_car_specific(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_UnknownFamily.zip"
            _write_archive(archive, b"unknown")
            spec = _spec(car_id=9001, model="UnknownFamily")
            with patch.object(
                policy,
                "infer_stock_native_tire_morph",
                side_effect=TireMorphAutoInferenceError("no compatible selector response"),
            ):
                result = evaluate_stock_tire_production_candidate(spec, archive)

        self.assertTrue(result.production_trial_eligible)
        self.assertEqual(result.car_id, 9001)
        self.assertEqual(result.tire_model_name, "UnknownFamily")

    def test_nonstock_spec_remains_blocked(self) -> None:
        with patch.object(policy, "infer_stock_native_tire_morph") as infer:
            result = evaluate_stock_tire_production_candidate(
                _spec(mode="effective"),
                Path("does-not-exist.zip"),
            )
        self.assertEqual(result.status, "blocked_nonstock_spec")
        self.assertFalse(result.production_trial_eligible)
        infer.assert_not_called()

    def test_archive_name_must_match_automatic_tire_model_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_Other.zip"
            _write_archive(archive, b"native")
            result = evaluate_stock_tire_production_candidate(_spec(model="Vintage"), archive)
        self.assertEqual(result.status, "blocked_archive_model_mismatch")
        self.assertFalse(result.production_trial_eligible)


if __name__ == "__main__":
    unittest.main()
