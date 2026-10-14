from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from fh6garage.preview3d.tire_morph_auto_inference import (
    TireMorphAutoInferenceError,
    infer_stock_native_tire_morph,
)
from fh6garage.preview3d.tire_morph_geometry import Aabb
from fh6garage.preview3d.wheel_spec import AxleWheelSpec, VehicleWheelSpec


def _spec(*, model: str = "Vintage", width: float = 200.0, aspect: float = 50.0, rim: float = 20.0):
    axle_front = AxleWheelSpec("front", width, aspect, rim)
    axle_rear = AxleWheelSpec("rear", width, aspect, rim)
    return VehicleWheelSpec(
        car_id=247,
        mode="stock",
        source_table="Drivable_Data_Car",
        car_body_id=247000,
        tire_compound_id=24,
        tire_model_name=model,
        front=axle_front,
        rear=axle_rear,
    )


def _state(span, center=(0.0, 0.0, 0.0)):
    minimum = tuple(center[i] - span[i] * 0.5 for i in range(3))
    maximum = tuple(center[i] + span[i] * 0.5 for i in range(3))
    return {
        "aabb": {
            "minimum": minimum,
            "maximum": maximum,
            "center": center,
            "span": span,
        }
    }


def _bake_report(path: Path):
    # Target OD for 200/50R20 is 0.708 m. Baseline OD is 0.60 m.
    # Selector 0 and 1 both expand the radial envelope; no family-role names are used.
    states = {
        "baseline": _state((1.0, 0.60, 0.60)),
        "selector0": _state((1.0, 0.80, 0.80)),
        "selector1": _state((1.0, 0.70, 0.70)),
        "selector2": _state((1.1, 0.60, 0.60)),
        "selector3": _state((1.0, 0.60, 0.60), (0.1, 0.0, 0.0)),
        "selector4": _state((1.0, 0.60, 0.60), (-0.1, 0.0, 0.0)),
    }
    modelbin = SimpleNamespace(entry="tireL_vintage.modelbin", states=states)
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return SimpleNamespace(
        archive_read_only_unchanged=True,
        archive_sha256=digest,
        modelbins=(modelbin,),
    )


class TireMorphAutoInferenceTests(unittest.TestCase):
    def test_vintage_name_uses_actual_geometry_not_family_whitelist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_vintage.zip"
            archive.write_bytes(b"native-tire-placeholder")
            bake = _bake_report(archive)

            def evaluate(_data, weights):
                radial = 0.60 + 0.20 * float(weights[0]) + 0.10 * float(weights[1])
                return Aabb(
                    minimum=(-0.5, -radial / 2.0, -radial / 2.0),
                    maximum=(0.5, radial / 2.0, radial / 2.0),
                    center=(0.0, 0.0, 0.0),
                    span=(1.0, radial, radial),
                )

            with (
                patch(
                    "fh6garage.preview3d.tire_morph_auto_inference.bake_tire_morph_selectors",
                    return_value=bake,
                ),
                patch(
                    "fh6garage.preview3d.tire_morph_auto_inference._read_modelbins",
                    return_value=(("tireL_vintage.modelbin", b"modelbin"),),
                ),
                patch(
                    "fh6garage.preview3d.tire_morph_auto_inference._evaluate_modelbin_aabb",
                    side_effect=evaluate,
                ),
            ):
                report = infer_stock_native_tire_morph(_spec(), archive)

            self.assertEqual(report.status, "generic_auto_inference_accepted")
            self.assertEqual(report.tire_model_name, "Vintage")
            self.assertEqual(report.active_selector_indices, (0, 1))
            self.assertEqual(report.weights.front.selector_weights[2:], (0.0, 0.0, 0.0))
            self.assertAlmostEqual(report.weights.front.scale_x, 0.2, places=6)
            self.assertLessEqual(report.front.maximum_radial_relative_error, 0.05)
            self.assertTrue(Path(report.persistent_report_path or "").is_file())

    def test_inference_rejects_required_selector_extrapolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "tire_vintage.zip"
            archive.write_bytes(b"native-tire-placeholder")
            bake = _bake_report(archive)
            impossible = _spec(width=200.0, aspect=200.0, rim=30.0)

            with (
                patch(
                    "fh6garage.preview3d.tire_morph_auto_inference.bake_tire_morph_selectors",
                    return_value=bake,
                ),
                patch(
                    "fh6garage.preview3d.tire_morph_auto_inference._read_modelbins",
                    return_value=(("tireL_vintage.modelbin", b"modelbin"),),
                ),
            ):
                with self.assertRaises(TireMorphAutoInferenceError) as caught:
                    infer_stock_native_tire_morph(impossible, archive)

            self.assertIn("extrapolation", str(caught.exception))
            self.assertTrue(Path(caught.exception.report_path or "").is_file())

    def test_nonstock_spec_fails_closed(self) -> None:
        spec = _spec()
        spec = VehicleWheelSpec(
            car_id=spec.car_id,
            mode="effective",
            source_table=spec.source_table,
            car_body_id=spec.car_body_id,
            tire_compound_id=spec.tire_compound_id,
            tire_model_name=spec.tire_model_name,
            front=spec.front,
            rear=spec.rear,
        )
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_vintage.zip"
            archive.write_bytes(b"x")
            with self.assertRaisesRegex(TireMorphAutoInferenceError, "stock mode"):
                infer_stock_native_tire_morph(spec, archive)


if __name__ == "__main__":
    unittest.main()
