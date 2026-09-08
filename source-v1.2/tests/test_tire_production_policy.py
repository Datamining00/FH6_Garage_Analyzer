from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fh6garage.preview3d import tire_production_policy as policy
from fh6garage.preview3d.tire_production_policy import (
    evaluate_stock_tire_production_candidate,
)
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
    hashes = sorted(hashlib.sha256(payload).hexdigest() for payload in modelbins)
    return hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()


def _structural_report(archive: Path, *, compatible: bool = True):
    pattern = list(policy._EXPECTED_SELECTOR_ROLE_PATTERN)
    if not compatible:
        pattern[0] = "mixed_or_unclassified"
    roles = tuple(
        SimpleNamespace(selector=index, geometric_role=role, confidence="high")
        for index, role in enumerate(pattern)
    )
    return SimpleNamespace(
        archive_read_only_unchanged=True,
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        modelbin_roles={"tireL_unknown.modelbin": roles},
        left_right_role_match=None,
    )


class TireProductionPolicyTests(unittest.TestCase):
    def test_validated_stock_fxx_slick_is_eligible(self) -> None:
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

    def test_slick_is_no_longer_car_specific(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_slick.zip"
            identity = _write_archive(archive, b"slick")
            with patch.object(policy, "_VALIDATED_SLICK_GEOMETRY_IDENTITY", identity):
                result = evaluate_stock_tire_production_candidate(
                    _spec(car_id=1229),
                    archive,
                )
        self.assertEqual(result.status, "production_trial_eligible")
        self.assertTrue(result.production_trial_eligible)
        self.assertEqual(result.car_id, 1229)

    def test_topology_compatible_family_is_globally_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_a.zip"
            identity = _write_archive(archive, b"a")
            with patch.dict(
                policy._TOPOLOGY_COMPATIBLE_IDENTITIES,
                {"a": identity},
                clear=True,
            ):
                result = evaluate_stock_tire_production_candidate(
                    _spec(car_id=2001, model="a"),
                    archive,
                )
        self.assertEqual(result.status, "production_trial_eligible")
        self.assertTrue(result.production_trial_eligible)
        self.assertIn("selector-topology", result.detail)

    def test_unlisted_structurally_compatible_family_is_admitted_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_unknown.zip"
            _write_archive(archive, b"unknown")
            report = _structural_report(archive, compatible=True)
            with patch.object(
                policy,
                "analyze_native_tire_selector_boundary_roles",
                return_value=report,
            ) as analyze:
                result = evaluate_stock_tire_production_candidate(
                    _spec(car_id=4000, model="unknown"), archive
                )
        self.assertEqual(result.status, "production_trial_eligible")
        self.assertTrue(result.production_trial_eligible)
        self.assertIn("runtime read-only selector-boundary validation", result.detail)
        analyze.assert_called_once()

    def test_unlisted_structural_role_mismatch_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_unknown.zip"
            _write_archive(archive, b"unknown")
            report = _structural_report(archive, compatible=False)
            with patch.object(
                policy,
                "analyze_native_tire_selector_boundary_roles",
                return_value=report,
            ):
                result = evaluate_stock_tire_production_candidate(
                    _spec(model="unknown"), archive
                )
        self.assertEqual(result.status, "blocked_family_structural_validation_failed")
        self.assertFalse(result.production_trial_eligible)
        self.assertIn("does not match", result.detail)

    def test_nonstock_spec_fails_closed_before_archive_use(self) -> None:
        result = evaluate_stock_tire_production_candidate(
            _spec(mode="effective"),
            Path("does-not-exist.zip"),
        )
        self.assertEqual(result.status, "blocked_nonstock_spec")
        self.assertFalse(result.production_trial_eligible)
        self.assertIsNone(result.weights)

    def test_supported_family_geometry_identity_mismatch_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_slick.zip"
            _write_archive(archive, b"unexpected")
            result = evaluate_stock_tire_production_candidate(_spec(), archive)
        self.assertEqual(result.status, "blocked_geometry_identity_mismatch")
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

    def test_stock_dimension_variation_uses_vehicle_specific_width(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_slick.zip"
            identity = _write_archive(archive, b"slick")
            with patch.object(policy, "_VALIDATED_SLICK_GEOMETRY_IDENTITY", identity):
                result = evaluate_stock_tire_production_candidate(
                    _spec(car_id=3000, front_width=255.0),
                    archive,
                )
        self.assertTrue(result.production_trial_eligible)
        assert result.weights is not None
        self.assertAlmostEqual(result.weights.front.scale_x, 0.255)
        self.assertAlmostEqual(result.weights.rear.scale_x, 0.345)


if __name__ == "__main__":
    unittest.main()
