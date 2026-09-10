from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from fh6garage.preview3d.tire_preview_cache_patch import (
    make_native_tire_preview_cache_wrapper,
)
from fh6garage.preview3d.tire_preview_integration import TirePreviewIntegrationResult


@dataclass(frozen=True)
class _Spec:
    car_id: int = 1006
    tire_model_name: str = "Slick"

    def as_dict(self) -> dict:
        return {
            "car_id": self.car_id,
            "tire_model_name": self.tire_model_name,
            "width_mm": 325.0,
            "outer_diameter_mm": 690.0,
        }


class _Resolver:
    def __init__(self, _path: Path) -> None:
        pass

    def resolve(self, car_id: int) -> _Spec:
        return _Spec(car_id=int(car_id))


class NativeTirePreviewCacheTests(unittest.TestCase):
    def test_second_identical_open_reuses_merged_tire_glb(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"LOCALAPPDATA": temp}, clear=False
        ):
            root = Path(temp)
            vehicle_archive = root / "FER_FXX_05.zip"
            vehicle_archive.write_bytes(b"vehicle-archive")
            vehicle_glb = root / "vehicle.glb"
            vehicle_glb.write_bytes(b"glTF" + b"\0" * 32)
            database = root / "wheel.sqlite"
            database.write_bytes(b"SQLite fixture")
            tire_archive = root / "Slick.zip"
            tire_archive.write_bytes(b"tire-archive")
            caller_work_root = root / "caller-temp"

            asset = SimpleNamespace(
                car_id=1006,
                model_code="FER_FXX_05",
                archive_path=vehicle_archive,
            )
            integration = SimpleNamespace(
                GLOBAL_NATIVE_TIRE_PREVIEW_REVISION="fixture-v1",
                ensure_stock_wheel_database=lambda progress=None: database,
                FH6WheelSpecResolver=_Resolver,
                resolve_tire_archive=lambda _root, _name: tire_archive,
                TirePreviewIntegrationResult=TirePreviewIntegrationResult,
            )
            calls = Mock()

            def original(
                asset,
                *,
                carbin_entry,
                game_or_cars_path,
                vehicle_glb,
                work_root,
                progress=None,
            ):
                calls()
                work_root = Path(work_root)
                work_root.mkdir(parents=True, exist_ok=True)
                selected = work_root / "vehicle__native_tires.glb"
                selected.write_bytes(b"glTF" + b"\0" * 64)
                return TirePreviewIntegrationResult(
                    status="stock_native_tire_preview_applied",
                    revision="fixture-v1",
                    car_id=int(asset.car_id),
                    model_code=str(asset.model_code),
                    source_vehicle_glb=str(vehicle_glb),
                    selected_vehicle_glb=str(selected),
                    applied=True,
                    fallback_used=False,
                    production_renderer_enabled=False,
                    detail="fixture",
                    manifest_path=None,
                )

            cached = make_native_tire_preview_cache_wrapper(original, integration)
            kwargs = dict(
                carbin_entry="FER_FXX_05.carbin",
                game_or_cars_path=root,
                vehicle_glb=vehicle_glb,
                work_root=caller_work_root,
            )
            first = cached(asset, **kwargs)
            second = cached(asset, **kwargs)

            self.assertTrue(first.applied)
            self.assertTrue(second.applied)
            self.assertEqual(second.status, "stock_native_tire_preview_cache_hit")
            self.assertEqual(Path(first.selected_vehicle_glb), Path(second.selected_vehicle_glb))
            self.assertEqual(calls.call_count, 1)
            self.assertFalse(str(first.selected_vehicle_glb).startswith(str(caller_work_root)))

    def test_changed_tire_archive_invalidates_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"LOCALAPPDATA": temp}, clear=False
        ):
            root = Path(temp)
            vehicle_archive = root / "vehicle.zip"
            vehicle_archive.write_bytes(b"vehicle")
            vehicle_glb = root / "vehicle.glb"
            vehicle_glb.write_bytes(b"glTF" + b"\0" * 32)
            database = root / "wheel.sqlite"
            database.write_bytes(b"db")
            tire_archive = root / "Slick.zip"
            tire_archive.write_bytes(b"tire-v1")
            asset = SimpleNamespace(car_id=1006, model_code="FER_FXX_05", archive_path=vehicle_archive)
            integration = SimpleNamespace(
                GLOBAL_NATIVE_TIRE_PREVIEW_REVISION="fixture-v1",
                ensure_stock_wheel_database=lambda progress=None: database,
                FH6WheelSpecResolver=_Resolver,
                resolve_tire_archive=lambda _root, _name: tire_archive,
                TirePreviewIntegrationResult=TirePreviewIntegrationResult,
            )
            calls = Mock()

            def original(asset, *, vehicle_glb, work_root, **kwargs):
                calls()
                work_root = Path(work_root)
                work_root.mkdir(parents=True, exist_ok=True)
                selected = work_root / "native.glb"
                selected.write_bytes(b"glTF" + b"\0" * 32)
                return TirePreviewIntegrationResult(
                    "stock_native_tire_preview_applied", "fixture-v1", int(asset.car_id),
                    str(asset.model_code), str(vehicle_glb), str(selected), True, False,
                    False, "fixture", None,
                )

            cached = make_native_tire_preview_cache_wrapper(original, integration)
            kwargs = dict(
                carbin_entry="FER_FXX_05.carbin",
                game_or_cars_path=root,
                vehicle_glb=vehicle_glb,
                work_root=root / "temp",
            )
            cached(asset, **kwargs)
            tire_archive.write_bytes(b"tire-v2-longer")
            cached(asset, **kwargs)
            self.assertEqual(calls.call_count, 2)


if __name__ == "__main__":
    unittest.main()
