from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from fh6garage.preview3d.chassis_converter import convert_vehicle
from fh6garage.preview3d.wheel_morph_auto import AutomaticRimMorphResolution
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


def _asset(archive: Path):
    return SimpleNamespace(
        car_id=1006,
        model_code="FER_FXX_05",
        archive_path=str(archive),
        archive_name=archive.name,
        carbin_entries=("FER_FXX_05.carbin",),
    )


class ChassisConverterAutomaticRimMorphTests(unittest.TestCase):
    def _run_until_near_lod(self, automatic, *, explicit_weights=None, override=None):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_root = root / "game"
            runtime_root = root / "runtime"
            game_root.mkdir()
            runtime_root.mkdir()
            archive = game_root / "FER_FXX_05.zip"
            archive.write_bytes(b"fixture")
            stop = RuntimeError("stop-after-helper-selection")
            with (
                patch(
                    "fh6garage.preview3d.chassis_converter.resolve_automatic_stock_rim_morph",
                    return_value=automatic,
                ) as resolve_auto,
                patch(
                    "fh6garage.preview3d.chassis_converter.wheel_morph_environment",
                    return_value={},
                ) as morph_environment,
                patch(
                    "fh6garage.preview3d.chassis_converter._resolve_converter_helper",
                    return_value=(runtime_root / "helper.exe", "test-helper"),
                ) as resolve_helper,
                patch(
                    "fh6garage.preview3d.chassis_converter.prepare_near_lod_archive",
                    side_effect=stop,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "stop-after-helper-selection"):
                    convert_vehicle(
                        _asset(archive),
                        carbin_entry="FER_FXX_05.carbin",
                        work_root=runtime_root / "work",
                        rim_morph_weights=explicit_weights,
                        converter_override=override,
                    )
            return resolve_auto, morph_environment, resolve_helper

    def test_default_conversion_promotes_verified_automatic_weights(self):
        weights = _weights()
        automatic = AutomaticRimMorphResolution("applied", weights, "ok", "fixture/source")
        resolve_auto, morph_environment, resolve_helper = self._run_until_near_lod(automatic)

        resolve_auto.assert_called_once_with(1006, "FER_FXX_05", None)
        morph_environment.assert_called_once_with(1006, weights)
        resolve_helper.assert_called_once_with(None, weights, None)

    def test_automatic_fallback_preserves_original_converter_path(self):
        automatic = AutomaticRimMorphResolution(
            "car_unavailable", None, "missing from verified DB", "fixture/source"
        )
        resolve_auto, morph_environment, resolve_helper = self._run_until_near_lod(automatic)

        resolve_auto.assert_called_once_with(1006, "FER_FXX_05", None)
        morph_environment.assert_called_once_with(1006, None)
        resolve_helper.assert_called_once_with(None, None, None)

    def test_explicit_weights_do_not_invoke_automatic_resolver(self):
        weights = _weights()
        automatic = AutomaticRimMorphResolution("applied", weights, "unused")
        resolve_auto, morph_environment, resolve_helper = self._run_until_near_lod(
            automatic,
            explicit_weights=weights,
        )

        resolve_auto.assert_not_called()
        morph_environment.assert_called_once_with(1006, weights)
        resolve_helper.assert_called_once_with(None, weights, None)

    def test_explicit_converter_override_does_not_trigger_stock_database_resolution(self):
        automatic = AutomaticRimMorphResolution("applied", _weights(), "unused")
        override = Path("C:/diagnostic/helper.exe")
        resolve_auto, morph_environment, resolve_helper = self._run_until_near_lod(
            automatic,
            override=override,
        )

        resolve_auto.assert_not_called()
        morph_environment.assert_called_once_with(1006, None)
        resolve_helper.assert_called_once_with(None, None, override)


if __name__ == "__main__":
    unittest.main()
