from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from fh6garage.preview3d.native_material_textures import (
    NATIVE_MATERIAL_TEXTURE_RESOLUTION_REVISION,
    collect_native_texture_paths,
    resolve_native_material_textures,
)


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

            report = resolve_native_material_textures(glb, vehicle)
            self.assertEqual(report.revision, NATIVE_MATERIAL_TEXTURE_RESOLUTION_REVISION)
            self.assertEqual(report.status, "resolved_all")
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

            report = resolve_native_material_textures(glb, vehicle)
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

            report = resolve_native_material_textures(glb, vehicle)
            self.assertEqual(report.status, "unresolved")
            self.assertEqual(report.textures[0].status, "game_namespace_unavailable")
            self.assertFalse(report.game_data_modified)


if __name__ == "__main__":
    unittest.main()
