from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
import unittest
import zipfile

from fh6garage.preview3d.tire_stock_geometry_validation import (
    TireStockGeometryValidationError,
    validate_stock_tire_geometry,
)
from fh6garage.preview3d.wheel_spec import AxleWheelSpec, VehicleWheelSpec
from tests.test_tire_morph_geometry import _bundle


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stock_spec() -> VehicleWheelSpec:
    return VehicleWheelSpec(
        car_id=1006,
        mode="stock",
        source_table="fixture",
        car_body_id=None,
        tire_compound_id=1,
        tire_model_name="Street",
        front=AxleWheelSpec(
            axle="front",
            tire_width_mm=255.0,
            tire_aspect_ratio=35.0,
            rim_diameter_in=19.0,
        ),
        rear=AxleWheelSpec(
            axle="rear",
            tire_width_mm=335.0,
            tire_aspect_ratio=30.0,
            rim_diameter_in=20.0,
        ),
    )


def _archive(path: Path) -> None:
    modelbin = _bundle()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("tireL_street.modelbin", modelbin)
        archive.writestr("tireR_street.modelbin", modelbin)


class TireStockGeometryValidationTests(unittest.TestCase):
    def test_stock_reconstruction_applies_width_scale_and_fails_closed_on_bad_radius(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_street.zip"
            _archive(archive)
            before = _sha256(archive)

            report = validate_stock_tire_geometry(archive, _stock_spec())

            after = _sha256(archive)

        self.assertEqual(before, after)
        self.assertTrue(report.archive_read_only_unchanged)
        self.assertFalse(report.production_mapping_enabled)
        self.assertEqual(
            report.complete_mapping_status,
            "diagnostic_stock_dimensions_not_corroborated",
        )
        self.assertEqual(len(report.front.modelbins), 2)
        front = report.front.modelbins[0]
        # The synthetic fixture has a 1.0 m base X span. scale_x=255/1000
        # therefore reconstructs an exact 255 mm width and proves the post-morph
        # width scale is actually applied by this diagnostic.
        self.assertAlmostEqual(front.reconstructed_width_mm, 255.0, places=6)
        self.assertAlmostEqual(front.width_error_percent, 0.0, places=6)
        # Its Y/Z morphs are deliberately non-tire-like, so radius validation
        # must fail rather than promote a width-only match.
        self.assertFalse(front.corroborated)
        self.assertFalse(report.front.corroborated)
        self.assertFalse(report.rear.corroborated)

    def test_effective_spec_is_rejected(self):
        stock = _stock_spec()
        effective = VehicleWheelSpec(
            car_id=stock.car_id,
            mode="effective",
            source_table=stock.source_table,
            car_body_id=stock.car_body_id,
            tire_compound_id=stock.tire_compound_id,
            tire_model_name=stock.tire_model_name,
            front=stock.front,
            rear=stock.rear,
        )
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_street.zip"
            _archive(archive)
            with self.assertRaisesRegex(TireStockGeometryValidationError, "mode='stock'"):
                validate_stock_tire_geometry(archive, effective)

    def test_invalid_tolerance_is_rejected_before_geometry_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "tire_street.zip"
            _archive(archive)
            with self.assertRaisesRegex(TireStockGeometryValidationError, "tolerance_percent"):
                validate_stock_tire_geometry(
                    archive,
                    _stock_spec(),
                    tolerance_percent=0.0,
                )


if __name__ == "__main__":
    unittest.main()
