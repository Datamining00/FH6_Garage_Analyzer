from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from fh6garage.preview3d.tire_preview_integration import (
    TirePreviewIntegrationResult,
    install_validated_fxx_native_tire_preview,
    make_stock_native_tire_convert_wrapper,
    make_validated_fxx_tire_convert_wrapper,
    try_apply_stock_native_tire_preview,
    try_apply_validated_fxx_native_tire_preview,
)


class _Spec:
    def __init__(self, car_id: int, tire_model_name: str = "Slick") -> None:
        self.car_id = car_id
        self.tire_model_name = tire_model_name

    def as_dict(self) -> dict:
        return {"car_id": self.car_id, "tire_model_name": self.tire_model_name}


class _Report:
    def __init__(self, payload: dict | None = None, *, ready: bool = True):
        self.payload = payload or {"status": "ok"}
        self.trial_vehicle_glb_ready = ready

    def as_dict(self) -> dict:
        return dict(self.payload)


@dataclass(frozen=True)
class _Conversion:
    output_path: str
    helper_path: str
    diagnostics: dict


def _asset(
    root: Path,
    *,
    car_id: int = 1006,
    model_code: str = "FER_FXX_05",
) -> SimpleNamespace:
    archive = root / f"{model_code}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{model_code}.carbin", b"real-carbin-bytes")
    return SimpleNamespace(
        car_id=car_id,
        model_code=model_code,
        archive_path=archive,
        carbin_entries=(f"{model_code}.carbin",),
    )


class TirePreviewIntegrationTests(unittest.TestCase):
    def test_invalid_car_id_is_passthrough_without_touching_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = _asset(root, car_id=0, model_code="INVALID")
            glb = root / "vehicle.glb"
            glb.write_bytes(b"glTF-test")
            with patch(
                "fh6garage.preview3d.tire_preview_integration.ensure_stock_wheel_database"
            ) as database:
                result = try_apply_stock_native_tire_preview(
                    asset,
                    carbin_entry="INVALID.carbin",
                    game_or_cars_path=root,
                    vehicle_glb=glb,
                    work_root=root / "trial",
                )
            self.assertEqual(result.status, "not_applicable")
            self.assertFalse(result.applied)
            self.assertFalse(result.fallback_used)
            self.assertEqual(Path(result.selected_vehicle_glb), glb.resolve())
            database.assert_not_called()

    def test_non_fxx_vehicle_can_select_drawable_native_tire_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = _asset(root, car_id=1229, model_code="TEST_CAR")
            glb = root / "vehicle.glb"
            glb.write_bytes(b"glTF-source")
            source_before = glb.read_bytes()
            tire = root / "tire_slick.zip"
            tire.write_bytes(b"zip-placeholder")
            trial = root / "trial"
            captured: dict[str, bytes] = {}

            resolver = Mock()
            resolver.resolve.return_value = _Spec(1229)
            geometry = _Report({"status": "production_trial_geometry_ready", "car_id": 1229})
            attachment = _Report({"status": "spindle_attachment_contract_ready", "car_id": 1229})

            def attach(carbin_data, geometry_payload, *, output_path):
                captured["carbin"] = carbin_data
                Path(output_path).write_text("{}", encoding="utf-8")
                return attachment

            def merge(source_glb, contract_payload, output_glb):
                Path(output_glb).write_bytes(b"glTF-merged")
                return _Report({"status": "spindle_tire_trial_glb_ready"}, ready=True)

            viewer_bake_payload = {
                "format": "fh6_native_tire_viewer_matrix_bake_v2",
                "status": "native_tire_trial_node_matrices_baked",
                "node_count": 4,
                "vertex_count": 8100,
                "triangle_winding_reversed_count": 2700,
                "kfps_render_space_reflection_applied": True,
                "procedural_translation_applied": False,
                "procedural_rotation_applied": False,
                "procedural_scale_applied": False,
            }
            viewer_bake = Mock(return_value=viewer_bake_payload)

            with (
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
                    return_value=tire,
                ),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.build_stock_tire_production_trial_geometry",
                    return_value=geometry,
                ),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.build_tire_spindle_attachment_contract",
                    side_effect=attach,
                ),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.merge_tire_spindle_trial_glb",
                    side_effect=merge,
                ),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.bake_native_tire_trial_node_matrices",
                    viewer_bake,
                ),
            ):
                result = try_apply_stock_native_tire_preview(
                    asset,
                    carbin_entry="TEST_CAR.carbin",
                    game_or_cars_path=root,
                    vehicle_glb=glb,
                    work_root=trial,
                )

            self.assertTrue(result.applied)
            self.assertFalse(result.fallback_used)
            self.assertEqual(result.status, "stock_native_tire_preview_applied")
            self.assertEqual(result.car_id, 1229)
            self.assertIn("baked_vertices=8100", result.detail)
            self.assertIn("baked_triangles=2700", result.detail)
            self.assertEqual(captured["carbin"], b"real-carbin-bytes")
            self.assertEqual(glb.read_bytes(), source_before)
            self.assertEqual(Path(result.selected_vehicle_glb).read_bytes(), b"glTF-merged")
            self.assertTrue(Path(result.manifest_path).is_file())
            resolver.resolve.assert_called_once_with(1229)
            viewer_bake.assert_called_once_with(Path(result.selected_vehicle_glb))
            manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "stock_native_tire_preview_applied")
            self.assertEqual(manifest["car_id"], 1229)
            self.assertEqual(manifest["viewer_matrix_bake"], viewer_bake_payload)
            self.assertEqual(manifest["baked_tire_vertex_count"], 8100)
            self.assertEqual(manifest["baked_tire_triangle_count"], 2700)

    def test_zero_drawable_bake_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = _asset(root, car_id=1229, model_code="TEST_CAR")
            glb = root / "vehicle.glb"
            glb.write_bytes(b"glTF-source")
            tire = root / "tire_slick.zip"
            tire.write_bytes(b"placeholder")
            resolver = Mock()
            resolver.resolve.return_value = _Spec(1229)
            geometry = _Report({"status": "production_trial_geometry_ready", "car_id": 1229})
            attachment = _Report({"status": "spindle_attachment_contract_ready", "car_id": 1229})

            def merge(source_glb, contract_payload, output_glb):
                Path(output_glb).write_bytes(b"glTF-merged")
                return _Report({"status": "spindle_tire_trial_glb_ready"}, ready=True)

            with (
                patch("fh6garage.preview3d.tire_preview_integration.ensure_stock_wheel_database", return_value=root / "db.sqlite"),
                patch("fh6garage.preview3d.tire_preview_integration.FH6WheelSpecResolver", return_value=resolver),
                patch("fh6garage.preview3d.tire_preview_integration.resolve_tire_archive", return_value=tire),
                patch("fh6garage.preview3d.tire_preview_integration.build_stock_tire_production_trial_geometry", return_value=geometry),
                patch("fh6garage.preview3d.tire_preview_integration.build_tire_spindle_attachment_contract", return_value=attachment),
                patch("fh6garage.preview3d.tire_preview_integration.merge_tire_spindle_trial_glb", side_effect=merge),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.bake_native_tire_trial_node_matrices",
                    return_value={"node_count": 4, "vertex_count": 0, "triangle_winding_reversed_count": 0},
                ),
            ):
                result = try_apply_stock_native_tire_preview(
                    asset,
                    carbin_entry="TEST_CAR.carbin",
                    game_or_cars_path=root,
                    vehicle_glb=glb,
                    work_root=root / "trial",
                )
            self.assertFalse(result.applied)
            self.assertTrue(result.fallback_used)
            self.assertIn("no drawable tire geometry", result.detail)

    def test_global_failure_falls_back_to_existing_glb_and_cleans_trial(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = _asset(root, car_id=2000, model_code="OTHER")
            glb = root / "vehicle.glb"
            glb.write_bytes(b"glTF-source")
            tire = root / "tire_b_Horizon.zip"
            tire.write_bytes(b"placeholder")
            trial = root / "trial"
            resolver = Mock()
            resolver.resolve.return_value = _Spec(2000, "b_Horizon")

            with (
                patch("fh6garage.preview3d.tire_preview_integration.ensure_stock_wheel_database", return_value=root / "db.sqlite"),
                patch("fh6garage.preview3d.tire_preview_integration.FH6WheelSpecResolver", return_value=resolver),
                patch("fh6garage.preview3d.tire_preview_integration.resolve_tire_archive", return_value=tire),
                patch(
                    "fh6garage.preview3d.tire_preview_integration.build_stock_tire_production_trial_geometry",
                    side_effect=RuntimeError("blocked_selector_signature_mismatch"),
                ),
            ):
                result = try_apply_stock_native_tire_preview(
                    asset,
                    carbin_entry="OTHER.carbin",
                    game_or_cars_path=root,
                    vehicle_glb=glb,
                    work_root=trial,
                )

            self.assertEqual(result.status, "fallback_existing_vehicle_glb")
            self.assertFalse(result.applied)
            self.assertTrue(result.fallback_used)
            self.assertEqual(Path(result.selected_vehicle_glb), glb.resolve())
            self.assertFalse(trial.exists())

    def test_wrapper_replaces_successful_non_fxx_conversion_output_and_records_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = _asset(root, car_id=1229, model_code="OTHER")
            source = root / "vehicle.glb"
            source.write_bytes(b"source")
            selected = root / "vehicle__native_tires.glb"
            selected.write_bytes(b"merged")

            original = Mock(return_value=_Conversion(str(source), "helper.exe", {"converter": "ok"}))
            wrapped = make_stock_native_tire_convert_wrapper(original)
            applied = TirePreviewIntegrationResult(
                status="stock_native_tire_preview_applied",
                revision="test",
                car_id=1229,
                model_code="OTHER",
                source_vehicle_glb=str(source),
                selected_vehicle_glb=str(selected),
                applied=True,
                fallback_used=False,
                production_renderer_enabled=False,
                detail="ok",
                manifest_path=None,
            )
            with patch(
                "fh6garage.preview3d.tire_preview_integration.try_apply_stock_native_tire_preview",
                return_value=applied,
            ) as integrate:
                result = wrapped(asset, carbin_entry="OTHER.carbin", work_root=root / "geometry")
            self.assertEqual(Path(result.output_path), selected.resolve())
            self.assertEqual(result.helper_path, "helper.exe")
            self.assertEqual(result.diagnostics["converter"], "ok")
            self.assertEqual(result.diagnostics["native_tire_preview"], applied.as_dict())
            integrate.assert_called_once()

    def test_wrapper_records_fallback_reason_without_replacing_base_glb(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = _asset(root, car_id=2000, model_code="OTHER")
            source = root / "vehicle.glb"
            source.write_bytes(b"source")
            original = Mock(return_value=_Conversion(str(source), "helper.exe", {"converter": "ok"}))
            wrapped = make_stock_native_tire_convert_wrapper(original)
            fallback = TirePreviewIntegrationResult(
                status="fallback_existing_vehicle_glb",
                revision="test",
                car_id=2000,
                model_code="OTHER",
                source_vehicle_glb=str(source),
                selected_vehicle_glb=str(source),
                applied=False,
                fallback_used=True,
                production_renderer_enabled=False,
                detail="blocked test family",
                manifest_path=None,
            )
            with patch(
                "fh6garage.preview3d.tire_preview_integration.try_apply_stock_native_tire_preview",
                return_value=fallback,
            ):
                result = wrapped(asset, carbin_entry="OTHER.carbin", work_root=root / "geometry")
            self.assertEqual(result.output_path, str(source))
            self.assertEqual(result.diagnostics["native_tire_preview"], fallback.as_dict())

    def test_explicit_converter_override_skips_global_native_tire_integration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = _asset(root, car_id=1229, model_code="OTHER")
            source = root / "vehicle.glb"
            source.write_bytes(b"source")
            original = Mock(return_value=_Conversion(str(source), "helper.exe", {}))
            wrapped = make_stock_native_tire_convert_wrapper(original)
            with patch(
                "fh6garage.preview3d.tire_preview_integration.try_apply_stock_native_tire_preview"
            ) as integrate:
                result = wrapped(
                    asset,
                    carbin_entry="OTHER.carbin",
                    converter_override="diagnostic.exe",
                )
            self.assertEqual(result.output_path, str(source))
            integrate.assert_not_called()

    def test_legacy_fxx_api_names_delegate_to_global_implementation(self) -> None:
        self.assertIsNotNone(install_validated_fxx_native_tire_preview)
        self.assertIsNotNone(make_validated_fxx_tire_convert_wrapper)
        self.assertIsNotNone(try_apply_validated_fxx_native_tire_preview)

    def test_finalverify1_3d_tab_keeps_lazy_compatibility_installer(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "fh6garage"
            / "v1_4_finalverify1_preview_patch.py"
        ).read_text(encoding="utf-8")
        installer = "install_validated_fxx_native_tire_preview()"
        controller_import = "from .preview3d.integration import Preview3DController"
        self.assertIn(installer, source)
        self.assertIn(controller_import, source)
        self.assertLess(source.index(installer), source.index(controller_import))


if __name__ == "__main__":
    unittest.main()
