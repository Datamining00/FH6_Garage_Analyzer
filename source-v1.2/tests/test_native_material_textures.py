from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fh6garage.preview3d.native_material_textures import (
    NATIVE_MATERIAL_TEXTURE_RESOLUTION_REVISION,
    collect_native_texture_paths,
    resolve_native_material_textures,
)


ROOT = Path(__file__).resolve().parents[1]
CHASSIS_CONVERTER = ROOT / "fh6garage" / "preview3d" / "chassis_converter.py"
NATIVE_TEXTURES = ROOT / "fh6garage" / "preview3d" / "native_material_textures.py"
BUNDLE_TAG = 0x47727562


def _swatch_payload(label: bytes = b"test") -> bytes:
    return struct.pack("<I", BUNDLE_TAG) + label


def _write_glb(path: Path, texture_paths: list[str]) -> None:
    document = {
        "asset": {"version": "2.0"},
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {},
                        "extras": {
                            "kfps_material_appearance": {
                                "resolutionMode": "embedded_material_shader_parameters",
                                "texturePaths": texture_paths,
                            }
                        },
                    }
                ]
            }
        ],
    }
    raw = json.dumps(document, separators=(",", ":")).encode("utf-8")
    raw += b" " * ((-len(raw)) % 4)
    total = 12 + 8 + len(raw)
    path.write_bytes(
        b"glTF"
        + struct.pack("<II", 2, total)
        + struct.pack("<II", len(raw), 0x4E4F534A)
        + raw
    )


class NativeMaterialTextureResolutionTests(unittest.TestCase):
    def test_collects_exact_texture_provenance_without_semantic_guessing(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            _write_glb(
                glb,
                [
                    r"Game:\media\textures\paint\body.swatchbin",
                    r"Game:\media\textures\paint\BODY.swatchbin",
                    r"Game:\media\textures\normal\body_n.swatchbin",
                ],
            )
            self.assertEqual(
                collect_native_texture_paths(glb),
                (
                    r"Game:\media\textures\paint\body.swatchbin",
                    r"Game:\media\textures\normal\body_n.swatchbin",
                ),
            )

    def test_resolves_exact_derived_textures_zip_and_keeps_game_archive_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "FH6"
            cars = root / "Content" / "media" / "cars"
            cars.mkdir(parents=True)
            vehicle = cars / "TEST_CAR.zip"
            with zipfile.ZipFile(vehicle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("scene/TEST_CAR.modelbin", b"model")
            before = hashlib.sha256(vehicle.read_bytes()).hexdigest()

            textures = root / "Content" / "media" / "textures.zip"
            payload = _swatch_payload(b"native texture")
            with zipfile.ZipFile(textures, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("paint/body.swatchbin", payload)

            glb = Path(temp) / "cache" / "car.glb"
            glb.parent.mkdir()
            _write_glb(glb, [r"Game:\media\textures\paint\body.swatchbin"])

            report = resolve_native_material_textures(glb, vehicle, decode_native=False)
            self.assertEqual(report.revision, NATIVE_MATERIAL_TEXTURE_RESOLUTION_REVISION)
            self.assertEqual(report.status, "resolved_all")
            self.assertEqual(report.decode_status, "not_requested")
            self.assertEqual(report.resolved_count, 1)
            item = report.textures[0]
            self.assertEqual(item.status, "resolved_payload")
            self.assertEqual(item.resolution_mode, "derived_zip_exact")
            self.assertEqual(item.archive_entry, "paint/body.swatchbin")
            self.assertEqual(item.payload_sha256, hashlib.sha256(payload).hexdigest())
            self.assertEqual(Path(item.cache_path).read_bytes(), payload)
            self.assertEqual(hashlib.sha256(vehicle.read_bytes()).hexdigest(), before)
            self.assertFalse(report.game_data_modified)
            self.assertTrue(Path(report.manifest_path).is_file())

    def test_decodes_resolved_payload_to_sha_addressed_dds_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "FH6"
            cars = root / "Content" / "media" / "cars"
            cars.mkdir(parents=True)
            vehicle = cars / "TEST_CAR.zip"
            with zipfile.ZipFile(vehicle, "w") as archive:
                archive.writestr("scene/a.modelbin", b"x")
            before = hashlib.sha256(vehicle.read_bytes()).hexdigest()

            payload = _swatch_payload(b"native decode")
            textures = root / "Content" / "media" / "textures.zip"
            with zipfile.ZipFile(textures, "w") as archive:
                archive.writestr("paint/body.swatchbin", payload)

            cache = Path(temp) / "cache"
            cache.mkdir()
            glb = cache / "car.glb"
            _write_glb(glb, [r"Game:\media\textures\paint\body.swatchbin"])
            helper = Path(temp) / "Kfps.ChassisConverter.WheelMorph.exe"
            helper.write_bytes(b"MZ-test-helper")

            dds_bytes = b"DDS " + bytes(144) + b"native-dds-payload"
            dds_sha = hashlib.sha256(dds_bytes).hexdigest()

            def fake_run(args, **kwargs):
                self.assertEqual(args[1], "--decode-swatchbin")
                self.assertTrue(str(args[2]).endswith(".swatchbin"))
                output = Path(args[3])
                output.write_bytes(dds_bytes)
                diagnostic = {
                    "status": "decoded_dds",
                    "width": 1024,
                    "height": 512,
                    "depth": 1,
                    "mipLevels": 10,
                    "dxgiFormat": 99,
                    "dxgiFormatName": "DXGI_FORMAT_BC7_UNORM_SRGB",
                    "ddsSha256": dds_sha,
                }
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=json.dumps(diagnostic),
                    stderr="",
                )

            with patch(
                "fh6garage.preview3d.native_material_textures.subprocess.run",
                side_effect=fake_run,
            ) as mocked_run:
                report = resolve_native_material_textures(
                    glb,
                    vehicle,
                    cache_root=cache,
                    decoder_helper=helper,
                )
            self.assertEqual(mocked_run.call_count, 1)
            self.assertEqual(report.status, "resolved_all")
            self.assertEqual(report.decode_status, "decoded_all")
            self.assertEqual(report.decoded_count, 1)
            item = report.textures[0]
            self.assertEqual(item.decode_status, "decoded_dds")
            self.assertEqual(item.dds_sha256, dds_sha)
            self.assertEqual(item.dds_size, len(dds_bytes))
            self.assertEqual(item.width, 1024)
            self.assertEqual(item.height, 512)
            self.assertEqual(item.mip_levels, 10)
            self.assertEqual(item.dxgi_format, 99)
            self.assertEqual(item.dxgi_format_name, "DXGI_FORMAT_BC7_UNORM_SRGB")
            self.assertEqual(Path(item.dds_path).read_bytes(), dds_bytes)
            self.assertEqual(Path(item.dds_path).stem, hashlib.sha256(payload).hexdigest())
            self.assertEqual(hashlib.sha256(vehicle.read_bytes()).hexdigest(), before)

            with patch(
                "fh6garage.preview3d.native_material_textures.subprocess.run"
            ) as mocked_run:
                cached = resolve_native_material_textures(
                    glb,
                    vehicle,
                    cache_root=cache,
                    decoder_helper=helper,
                )
            mocked_run.assert_not_called()
            self.assertEqual(cached.decode_status, "decoded_all")
            self.assertEqual(cached.textures[0].decode_status, "decoded_dds_cached")
            self.assertEqual(cached.textures[0].dds_sha256, dds_sha)

    def test_ambiguous_filename_fallback_does_not_guess(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "FH6"
            cars = root / "Content" / "media" / "cars"
            cars.mkdir(parents=True)
            vehicle = cars / "TEST_CAR.zip"
            with zipfile.ZipFile(vehicle, "w") as archive:
                archive.writestr("scene/a.modelbin", b"x")

            for folder in ("library_a", "library_b"):
                zip_path = root / "Content" / "media" / folder / "textures.zip"
                zip_path.parent.mkdir(parents=True)
                with zipfile.ZipFile(zip_path, "w") as archive:
                    archive.writestr("somewhere/body.swatchbin", _swatch_payload(folder.encode()))

            glb = Path(temp) / "cache" / "car.glb"
            glb.parent.mkdir()
            _write_glb(glb, [r"Game:\unresolved\body.swatchbin"])

            report = resolve_native_material_textures(glb, vehicle, decode_native=False)
            self.assertEqual(report.status, "unresolved")
            self.assertEqual(report.resolved_count, 0)
            self.assertEqual(
                report.textures[0].status,
                "ambiguous_priority_archive_filename",
            )
            self.assertIsNone(report.textures[0].cache_path)

    def test_offline_vehicle_archive_fails_closed_without_game_namespace(self):
        with tempfile.TemporaryDirectory() as temp:
            vehicle = Path(temp) / "TEST_CAR.zip"
            with zipfile.ZipFile(vehicle, "w") as archive:
                archive.writestr("scene/a.modelbin", b"x")
            glb = Path(temp) / "car.glb"
            _write_glb(glb, [r"Game:\media\textures\paint\body.swatchbin"])

            report = resolve_native_material_textures(glb, vehicle, decode_native=False)
            self.assertEqual(report.status, "unresolved")
            self.assertEqual(report.textures[0].status, "game_namespace_unavailable")
            self.assertFalse(report.game_data_modified)

    def test_chassis_converter_integrates_resolver_without_making_it_geometry_fatal(self):
        text = CHASSIS_CONVERTER.read_text(encoding="utf-8")
        native = NATIVE_TEXTURES.read_text(encoding="utf-8")
        self.assertIn("resolve_native_material_textures", text)
        self.assertIn('diagnostics["native_material_texture_status"]', text)
        self.assertIn('"resolver_error"', text)
        self.assertIn('"game_data_modified": False', text)
        self.assertIn("return ConversionResult", text)
        self.assertIn("_automatic_decoder_helper", native)
        self.assertIn("verified_bundled_wheel_morph_helper", native)
        self.assertIn('"--decode-swatchbin"', native)
        self.assertIn('decode_status="decoder_unavailable"', native)


if __name__ == "__main__":
    unittest.main()
