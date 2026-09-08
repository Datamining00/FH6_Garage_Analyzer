from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from fh6garage.preview3d.tire_preview_integration import try_apply_stock_native_tire_preview


class _Spec:
    def __init__(self, car_id: int, tire_model_name: str) -> None:
        self.car_id = car_id
        self.tire_model_name = tire_model_name

    def as_dict(self) -> dict[str, object]:
        return {
            "car_id": self.car_id,
            "mode": "stock",
            "tire_model_name": self.tire_model_name,
        }


class _BoundaryReport:
    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fh6_native_tire_selector_boundary_roles_v1",
            "archive_read_only_unchanged": True,
            "modelbin_roles": {
                "tireL_vintage.modelbin": [
                    {
                        "selector": 0,
                        "geometric_role": "mixed_or_unclassified",
                        "confidence": "low",
                    }
                ]
            },
        }


class TirePreviewStructuralFallbackDiagnosticsTests(unittest.TestCase):
    def test_geometry_failure_persists_raw_selector_boundary_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local_app_data = root / "localappdata"
            car_id = 247
            model_code = "TOY_2000GT_69"
            source_archive = root / f"{model_code}.zip"
            with zipfile.ZipFile(source_archive, "w") as bundle:
                bundle.writestr(f"{model_code}.carbin", b"carbin")
            asset = SimpleNamespace(
                car_id=car_id,
                model_code=model_code,
                archive_path=source_archive,
                carbin_entries=(f"{model_code}.carbin",),
            )
            vehicle_glb = root / "vehicle.glb"
            vehicle_glb.write_bytes(b"glTF-source")
            tire_archive = root / "tire_vintage.zip"
            tire_archive.write_bytes(b"placeholder")
            trial = root / "trial"

            resolver = Mock()
            resolver.resolve.return_value = _Spec(car_id, "Vintage")
            boundary_report = _BoundaryReport()

            with (
                patch.dict("os.environ", {"LOCALAPPDATA": str(local_app_data)}, clear=False),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.ensure_stock_wheel_database",
                    return_value=root / "db.sqlite",
                ),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.FH6WheelSpecResolver",
                    return_value=resolver,
                ),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.resolve_tire_archive",
                    return_value=tire_archive,
                ),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.build_stock_tire_production_trial_geometry",
                    side_effect=RuntimeError("blocked_family_structural_validation_failed"),
                ),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.analyze_native_tire_selector_boundary_roles",
                    return_value=boundary_report,
                ) as analyze,
            ):
                result = try_apply_stock_native_tire_preview(
                    asset,
                    carbin_entry=f"{model_code}.carbin",
                    game_or_cars_path=root,
                    vehicle_glb=vehicle_glb,
                    work_root=trial,
                )

            self.assertEqual(result.status, "fallback_existing_vehicle_glb")
            self.assertEqual(Path(result.selected_vehicle_glb), vehicle_glb.resolve())
            analyze.assert_called_once_with(str(tire_archive.resolve()))

            manifest_path = Path(result.manifest_path or "")
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["failed_stage"], "build_tire_geometry")
            self.assertEqual(
                manifest["selector_boundary_report"],
                boundary_report.as_dict(),
            )
            self.assertIsNone(manifest["selector_boundary_report_error"])


if __name__ == "__main__":
    unittest.main()
