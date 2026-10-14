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
    collect_native_texture_bindings,
    collect_native_texture_paths,
    resolve_native_material_textures,
)


ROOT = Path(__file__).resolve().parents[1]
CHASSIS_CONVERTER = ROOT / "fh6garage" / "preview3d" / "chassis_converter.py"
NATIVE_TEXTURES = ROOT / "fh6garage" / "preview3d" / "native_material_textures.py"
BUNDLE_TAG = 0x47727562


def _swatch_payload(label: bytes = b"test") -> bytes:
    return struct.pack("<I", BUNDLE_TAG) + label


def _write_document_glb(path: Path, document: dict) -> None:
    raw = json.dumps(document, separators=(",", ":")).encode("utf-8")
    raw += b" " * ((-len(raw)) % 4)
    total = 12 + 8 + len(raw)
    path.write_bytes(
        b"glTF"
        + struct.pack("<II", 2, total)
        + struct.pack("<II", len(raw), 0x4E4F534A)
        + raw
    )


def _write_glb(
    path: Path,
    texture_paths: list[str],
    *,
    texture_bindings: list[dict[str, str]] | None = None,
    mesh_name: str = "body_mesh",
    material_name: str = "carpaint",
) -> None:
    """Write the production KFPS layout: material appearance lives on mesh extras."""
    appearance: dict[str, object] = {
        "resolutionMode": "embedded_material_shader_parameters",
        "texturePaths": texture_paths,
    }
    if texture_bindings is not None:
        appearance["textureBindings"] = texture_bindings
    document = {
        "asset": {"version": "2.0"},
        "meshes": [
            {
                "name": mesh_name,
                "primitives": [{"attributes": {}}],
                "extras": {
                    "kfps_material_name": material_name,
                    "kfps_material_appearance": appearance,
                },
            }
        ],
    }
    _write_document_glb(path, document)


def _write_legacy_primitive_glb(path: Path, texture_paths: list[str]) -> None:
    """Retain compatibility coverage for early diagnostic/test GLBs."""
    document = {
        "asset": {"version": "2.0"},
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {},
                        "extras": {
                            "kfps_material_name": "legacy_material",
                            "kfps_material_appearance": {
                                "resolutionMode": "embedded_material_shader_parameters",
                                "texturePaths": texture_paths,
                            },
                        },
                    }
                ]
            }
        ],
    }
    _write_document_glb(path, document)


class NativeMaterialTextureResolutionTests(unittest.TestCase):
    def test_collects_production_mesh_level_paths_and_deduplicates_case(self):
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

    def test_legacy_primitive_level_appearance_remains_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "legacy.glb"
            path = r"Game:\media\textures\paint\legacy.swatchbin"
            _write_legacy_primitive_glb(glb, [path])
            self.assertEqual(collect_native_texture_paths(glb), (path,))

    def test_collects_exact_texture_bindings_with_hash_semantics_per_mesh_material(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            diffuse = r"Game:\media\textures\paint\body.swatchbin"
            normal = r"Game:\media\textures\normal\body_n.swatchbin"
            unknown = r"Game:\media\textures\misc\unknown.swatchbin"
            _write_glb(
                glb,
                [diffuse, normal, unknown],
                texture_bindings=[
                    {
                        "ParameterHash": "85F59336",
                        "PathHash": "1111222233334444",
                        "TexturePath": diffuse,
                    },
                    {
                        "ParameterHash": "39731A8A",
                        "PathHash": "5555666677778888",
                        "TexturePath": normal,
                    },
                    {
                        "ParameterHash": "DEADBEEF",
                        "PathHash": "9999AAAABBBBCCCC",
                        "TexturePath": unknown,
                    },
                ],
                mesh_name="body_mesh",
                material_name="carpaint",
            )

            bindings = collect_native_texture_bindings(glb)
            self.assertEqual(len(bindings), 3)

            first = bindings[0]
            self.assertEqual(first.mesh_name, "body_mesh")
            self.assertEqual(first.material_name, "carpaint")
            self.assertEqual(first.parameter_hash, "85F59336")
            self.assertEqual(first.path_hash, "1111222233334444")
            self.assertEqual(first.texture_path, diffuse)
            self.assertEqual(first.parameter_name, "DiffuseTexture")
            self.assertEqual(first.semantic, "base_color")
            self.assertEqual(first.semantic_resolution_mode, "forzatechstudio_namehash_exact")

            second = bindings[1]
            self.assertEqual(second.parameter_name, "NormalMap")
            self.assertEqual(second.semantic, "normal")

            third = bindings[2]
            self.assertEqual(third.parameter_hash, "DEADBEEF")
            self.assertIsNone(third.parameter_name)
            self.assertEqual(third.semantic, "unknown")
            self.assertEqual(third.semantic_resolution_mode, "unmapped_parameter_hash")

            # Semantics come from ParameterHash only; the unknown path is not
            # reclassified from its filename or folder name.
            self.assertEqual(
                collect_native_texture_paths(glb),
                (diffuse, normal, unknown),
            )

    def test_mesh_level_appearance_is_authoritative_over_primitive_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "car.glb"
            mesh_path = r"Game:\media\textures\paint\mesh.swatchbin"
            primitive_path = r"Game:\media\textures\paint\primitive.swatchbin"
            document = {
                "asset": {"version": "2.0"},
                "meshes": [
                    {
                        "name": "body",
                        "extras": {
                            "kfps_material_name": "mesh_material",
                            "kfps_material_appearance": {
                                "texturePaths": [mesh_path],
                            },
                        },
                        "primitives": [
                            {
                                "attributes": {},
                                "extras": {
                                    "kfps_material_name": "primitive_material",
                                    "kfps_material_appearance": {
                                        "texturePaths": [primitive_path],
                                    },
                                },
                            }
                        ],
                    }
                ],
            }
            _write_document_glb(glb, document)
            self.assertEqual(collect_native_texture_paths(glb), (mesh_path,))

    def test_resolves_exact_derived_textures_zip_and_writes_binding_manifest(self):
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
            texture_path = r"Game:\media\textures\paint\body.swatchbin"
            _write_glb(
                glb,
                [texture_path],
                texture_bindings=[
                    {
                        "ParameterHash": "85F59336",
                        "PathHash": "1111222233334444",
                        "TexturePath": texture_path,
                    }
                ],
            )

            report = resolve_native_material_textures(glb, vehicle, decode_native=False)
            self.assertEqual(report.revision, NATIVE_MATERIAL_TEXTURE_RESOLUTION_REVISION)
            self.assertEqual(report.status, "resolved_all")
            self.assertEqual(report.decode_status, "not_requested")
            self.assertEqual(report.resolved_count, 1)
            self.assertEqual(report.binding_count, 1)
            self.assertEqual(report.recognized_binding_count, 1)
            self.assertEqual(report.unknown_binding_count, 0)
            self.assertEqual(report.bindings[0].semantic, "base_color")

            item = report.textures[0]
            self.assertEqual(item.status, "resolved_payload")
            self.assertEqual(item.resolution_mode, "derived_zip_exact")
            self.assertEqual(item.archive_entry, "paint/body.swatchbin")
            self.assertEqual(item.payload_sha256, hashlib.sha256(payload).hexdigest())
            self.assertEqual(Path(item.cache_path).read_bytes(), payload)
            self.assertEqual(hashlib.sha256(vehicle.read_bytes()).hexdigest(), before)
            self.assertFalse(report.game_data_modified)
            self.assertTrue(Path(report.manifest_path).is_file())

            manifest = json.loads(Path(report.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["format"], "fh6_native_material_texture_resolution_v3")
            self.assertEqual(manifest["binding_count"], 1)
            self.assertEqual(manifest["recognized_binding_count"], 1)
            self.assertEqual(manifest["bindings"][0]["parameter_name"], "DiffuseTexture")
            self.assertEqual(manifest["bindings"][0]["semantic"], "base_color")

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
        self.assertIn("collect_native_texture_bindings", native)
        self.assertIn("forzatechstudio_namehash_exact", (ROOT / "fh6garage" / "preview3d" / "native_texture_semantics.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
