from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fh6garage.preview3d.chassis_converter import (
    ChassisConverterError,
    _resolve_converter_helper,
)
from fh6garage.preview3d.wheel_morph_helper import (
    WHEEL_MORPH_HELPER_REVISION,
    WheelMorphHelperError,
)
from fh6garage.preview3d.wheel_morph_weights import (
    AxleRimMorphWeights,
    VehicleRimMorphWeights,
)


def _weights() -> VehicleRimMorphWeights:
    return VehicleRimMorphWeights(
        car_id=1006,
        wheel_spec_mode="stock",
        front=AxleRimMorphWeights(
            axle="front",
            rim_diameter_in=19.0,
            tire_width_mm=245.0,
            diameter_weight=9.0 / 14.0,
            width_weight=0.755 / 0.9,
        ),
        rear=AxleRimMorphWeights(
            axle="rear",
            rim_diameter_in=19.0,
            tire_width_mm=345.0,
            diameter_weight=9.0 / 14.0,
            width_weight=0.655 / 0.9,
        ),
    )


class ChassisConverterWheelMorphHelperTests(unittest.TestCase):
    def test_default_path_still_uses_pinned_upstream_helper(self):
        upstream = Path("C:/test/Kfps.ChassisConverter.exe")
        with (
            patch("fh6garage.preview3d.chassis_converter.ensure_converter", return_value=upstream) as ensure,
            patch(
                "fh6garage.preview3d.chassis_converter.verified_bundled_wheel_morph_helper",
                side_effect=AssertionError("bundled helper must not be inspected for default conversion"),
            ),
        ):
            helper, revision = _resolve_converter_helper(None, None, None)
        self.assertEqual(helper, upstream)
        self.assertEqual(revision, "pinned_upstream")
        ensure.assert_called_once_with(None)

    def test_requested_rim_morph_uses_verified_bundled_helper(self):
        bundled = Path("C:/bundle/runtime/Kfps.ChassisConverter.WheelMorph.exe")
        with patch(
            "fh6garage.preview3d.chassis_converter.verified_bundled_wheel_morph_helper",
            return_value=bundled,
        ):
            helper, revision = _resolve_converter_helper(None, _weights(), None)
        self.assertEqual(helper, bundled)
        self.assertEqual(revision, WHEEL_MORPH_HELPER_REVISION)

    def test_requested_rim_morph_fails_when_bundle_is_missing(self):
        with patch(
            "fh6garage.preview3d.chassis_converter.verified_bundled_wheel_morph_helper",
            return_value=None,
        ):
            with self.assertRaises(ChassisConverterError):
                _resolve_converter_helper(None, _weights(), None)

    def test_invalid_bundled_helper_is_reported_as_converter_error(self):
        with patch(
            "fh6garage.preview3d.chassis_converter.verified_bundled_wheel_morph_helper",
            side_effect=WheelMorphHelperError("bad hash"),
        ):
            with self.assertRaises(ChassisConverterError):
                _resolve_converter_helper(None, _weights(), None)

    def test_explicit_override_remains_available_for_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            override = Path(temporary) / "diagnostic.exe"
            override.write_bytes(b"diagnostic")
            helper, revision = _resolve_converter_helper(None, _weights(), override)
        self.assertEqual(helper, override.resolve())
        self.assertEqual(revision, "explicit_override")


if __name__ == "__main__":
    unittest.main()
