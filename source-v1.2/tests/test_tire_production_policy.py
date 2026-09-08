from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fh6garage.preview3d.tire_morph_auto_inference import TireMorphAutoInferenceError
from fh6garage.preview3d.tire_morph_weights import stock_vehicle_tire_morph_weights
from fh6garage.preview3d.tire_production_policy import evaluate_stock_tire_production_candidate
from fh6garage.preview3d.wheel_spec import AxleWheelSpec, VehicleWheelSpec


def _spec(
    *,
    car_id: int = 1006,
    mode: str = "stock",
    model: str = "Slick",
    front_width: float = 245.0,
) -> VehicleWheelSpec:
    return VehicleWheelSpec(
        car_id=car_id,
        mode=mode,
        source_table="Data_Car",
        car_body_id=None,
        tire_compound_id=13,
        tire_model_name=model,
        front=AxleWheelSpec("front", front_width, 35.0, 19.0),
        rear=AxleWheelSpec("rear", 345.0, 35.0, 19.0),
    )


def _write_archive(path: Path, *modelbins: bytes) -> str:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, payload in enumerate(modelbins):
            archive.writestr(f"tire{index}.modelbin", payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inference(spec: VehicleWheelSpec, archive: Path):
    weights = stock_vehicle_tire_morph_weights(spec)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    payload = {
        "format": "fh6_generic_native_tire_morph_auto_inference_v1",
        "status": "generic_auto_inference_accepted",
        "car_id": spec.car_id,
        "tire_model_name": spec.tire_model_name,
    }
    return SimpleNamespace(
        archive_sha256=sha,
        archive_read_only_unchanged=True,
        weights=weights,
        persistent_report_path="diagnostic.json",
        as_dict=lambda: dict(payload),
    )


class TireProductionPolicyTests(unittest.TestCase):
    def test_slick_is_eligible_by_generic_auto_inference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_slick.zip"
            _write_archive(archive, b"left", b"right")
            spec = _spec()
            with patch(
                "fh6garage.preview3d.tire_production_policy.infer_stock_native_tire_morph",
                return_value=_inference(spec, archive),
            ) as infer:
                result = evaluate_stock_tire_production_candidate(spec, archive)

        self.assertEqual(result.status, "production_trial_eligible")
        self.assertTrue(result.production_trial_eligible)
        self.assertFalse(result.production_renderer_enabled)
        self.assertIsNotNone(result.weights)
        self.assertIn("no tire-family whitelist", result.detail)
        infer.assert_called_once()

    def test_vintage_is_not_family_whitelisted_or_signature_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_vintage.zip"
            _write_archive(archive, b"vintage")
            spec = _spec(car_id=247, model="Vintage")
            with patch(
                "fh6garage.preview3d.tire_production_policy.infer_stock_native_tire_morph",
                return_value=_inference(spec, archive),
            ):
                result = evaluate_stock_tire_production_candidate(spec, archive)

        self.assertEqual(result.status, "production_trial_eligible")
        self.assertTrue(result.production_trial_eligible)
        self.assertEqual(result.tire_model_name, "Vintage")

    def test_previously_mismatched_family_can_pass_if_geometry_inference_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_b_Horizon.zip"
            _write_archive(archive, b"horizon")
            spec = _spec(car_id=2000, model="b_Horizon")
            with patch(
                "fh6garage.preview3d.tire_production_policy.infer_stock_native_tire_morph",
                return_value=_inference(spec, archive),
            ):
                result = evaluate_stock_tire_production_candidate(spec, archive)

        self.assertTrue(result.production_trial_eligible)
        self.assertEqual(result.status, "production_trial_eligible")

    def test_generic_auto_inference_failure_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_vintage.zip"
            _write_archive(archive, b"vintage")
            spec = _spec(car_id=247, model="Vintage")
            error = TireMorphAutoInferenceError(
                "outer diameter residual too high; report=diagnostic.json",
                report={"status": "auto_inference_rejected"},
                report_path="diagnostic.json",
            )
            with patch(
                "fh6garage.preview3d.tire_production_policy.infer_stock_native_tire_morph",
                side_effect=error,
            ):
                result = evaluate_stock_tire_production_candidate(spec, archive)

        self.assertEqual(result.status, "blocked_generic_auto_inference_failed")
        self.assertFalse(result.production_trial_eligible)
        self.assertIsNone(result.weights)
        self.assertEqual(result.auto_inference_report, {"status": "auto_inference_rejected"})

    def test_nonstock_spec_fails_closed_before_inference(self) -> None:
        with patch(
            "fh6garage.preview3d.tire_production_policy.infer_stock_native_tire_morph"
        ) as infer:
            result = evaluate_stock_tire_production_candidate(
                _spec(mode="effective"),
                Path("does-not-exist.zip"),
            )
        self.assertEqual(result.status, "blocked_nonstock_spec")
        self.assertFalse(result.production_trial_eligible)
        self.assertIsNone(result.weights)
        infer.assert_not_called()

    def test_archive_model_name_mismatch_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_other.zip"
            _write_archive(archive, b"other")
            result = evaluate_stock_tire_production_candidate(_spec(model="Slick"), archive)
        self.assertEqual(result.status, "blocked_archive_model_mismatch")
        self.assertFalse(result.production_trial_eligible)

    def test_stock_dimension_variation_uses_inferred_vehicle_weights(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_slick.zip"
            _write_archive(archive, b"slick")
            spec = _spec(car_id=3000, front_width=255.0)
            inferred = _inference(spec, archive)
            with patch(
                "fh6garage.preview3d.tire_production_policy.infer_stock_native_tire_morph",
                return_value=inferred,
            ):
                result = evaluate_stock_tire_production_candidate(spec, archive)
        self.assertTrue(result.production_trial_eligible)
        assert result.weights is not None
        self.assertAlmostEqual(result.weights.front.scale_x, 0.255)
        self.assertAlmostEqual(result.weights.rear.scale_x, 0.345)


if __name__ == "__main__":
    unittest.main()
