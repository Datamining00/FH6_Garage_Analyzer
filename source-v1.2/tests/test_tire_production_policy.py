from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fh6garage.preview3d import tire_production_policy as policy
from fh6garage.preview3d.tire_production_policy import (
    evaluate_stock_tire_production_candidate,
)
from fh6garage.preview3d.wheel_spec import AxleWheelSpec, VehicleWheelSpec


def _spec(*, car_id: int = 1006, mode: str = "stock", model: str = "Slick") -> VehicleWheelSpec:
    return VehicleWheelSpec(
        car_id=car_id,
        mode=mode,
        source_table="Data_Car",
        car_body_id=None,
        tire_compound_id=13,
        tire_model_name=model,
        front=AxleWheelSpec("front", 245.0, 35.0, 19.0),
        rear=AxleWheelSpec("rear", 345.0, 35.0, 19.0),
    )


def _write_archive(path: Path, *modelbins: bytes) -> str:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, payload in enumerate(modelbins):
            archive.writestr(f"tire{index}.modelbin", payload)
    hashes = sorted(hashlib.sha256(payload).hexdigest() for payload in modelbins)
    return hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()


class TireProductionPolicyTests(unittest.TestCase):
    def test_exact_validated_stock_fxx_slick_becomes_trial_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_slick.zip"
            identity = _write_archive(archive, b"left", b"right")
            with patch.object(policy, "_VALIDATED_SLICK_GEOMETRY_IDENTITY", identity):
                result = evaluate_stock_tire_production_candidate(_spec(), archive)

        self.assertEqual(result.status, "production_trial_eligible")
        self.assertTrue(result.production_trial_eligible)
        self.assertFalse(result.production_renderer_enabled)
        self.assertIsNotNone(result.weights)
        assert result.weights is not None
        self.assertEqual(result.weights.front.selector_weights[2:], (0.0, 0.0, 0.0))
        self.assertEqual(result.weights.rear.selector_weights[2:], (0.0, 0.0, 0.0))
        self.assertAlmostEqual(result.weights.front.scale_x, 0.245)
        self.assertAlmostEqual(result.weights.rear.scale_x, 0.345)

    def test_nonstock_spec_fails_closed_before_archive_use(self) -> None:
        result = evaluate_stock_tire_production_candidate(
            _spec(mode="effective"),
            Path("does-not-exist.zip"),
        )
        self.assertEqual(result.status, "blocked_nonstock_spec")
        self.assertFalse(result.production_trial_eligible)
        self.assertIsNone(result.weights)

    def test_slick_geometry_identity_mismatch_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_slick.zip"
            _write_archive(archive, b"unexpected")
            result = evaluate_stock_tire_production_candidate(_spec(), archive)
        self.assertEqual(result.status, "blocked_geometry_identity_mismatch")
        self.assertFalse(result.production_trial_eligible)

    def test_validated_geometry_is_still_car_specific_until_more_dimension_checks_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_slick.zip"
            identity = _write_archive(archive, b"slick")
            with patch.object(policy, "_VALIDATED_SLICK_GEOMETRY_IDENTITY", identity):
                result = evaluate_stock_tire_production_candidate(
                    _spec(car_id=1229),
                    archive,
                )
        self.assertEqual(result.status, "blocked_car_dimension_validation_missing")
        self.assertFalse(result.production_trial_eligible)

    def test_topology_only_family_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_a.zip"
            identity = _write_archive(archive, b"a")
            with patch.dict(policy._TOPOLOGY_ONLY_IDENTITIES, {"a": identity}, clear=True):
                result = evaluate_stock_tire_production_candidate(
                    _spec(model="a"),
                    archive,
                )
        self.assertEqual(result.status, "blocked_dimension_formula_not_corroborated")
        self.assertFalse(result.production_trial_eligible)

    def test_structural_mismatch_family_is_explicitly_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_b_Horizon.zip"
            identity = _write_archive(archive, b"horizon")
            with patch.dict(
                policy._STRUCTURAL_MISMATCH_IDENTITIES,
                {"b_horizon": identity},
                clear=True,
            ):
                result = evaluate_stock_tire_production_candidate(
                    _spec(model="b_Horizon"),
                    archive,
                )
        self.assertEqual(result.status, "blocked_selector_signature_mismatch")
        self.assertFalse(result.production_trial_eligible)

    def test_fxx_dimension_drift_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_slick.zip"
            identity = _write_archive(archive, b"slick")
            spec = _spec()
            spec = VehicleWheelSpec(
                car_id=spec.car_id,
                mode=spec.mode,
                source_table=spec.source_table,
                car_body_id=spec.car_body_id,
                tire_compound_id=spec.tire_compound_id,
                tire_model_name=spec.tire_model_name,
                front=AxleWheelSpec("front", 255.0, 35.0, 19.0),
                rear=spec.rear,
            )
            with patch.object(policy, "_VALIDATED_SLICK_GEOMETRY_IDENTITY", identity):
                result = evaluate_stock_tire_production_candidate(spec, archive)
        self.assertEqual(result.status, "blocked_validated_dimension_mismatch")
        self.assertFalse(result.production_trial_eligible)


if __name__ == "__main__":
    unittest.main()
