from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from fh6garage.preview3d.native_material_render_plan import (
    NATIVE_MATERIAL_RENDER_PLAN_REVISION,
    NativeMaterialRenderPlanError,
    build_native_material_render_plan,
)
from fh6garage.preview3d.native_dds import DDS_DX10_HEADER_SIZE


def _write_glb(
    path: Path,
    bindings: list[dict[str, str]],
    *,
    role: str = "trim",
    material_name: str = "body_trim",
    uv_tiling: tuple[float, float] | None = (1.0, 1.0),
    include_uv0: bool = True,
) -> None:
    appearance = {
        "resolutionMode": "embedded_material_shader_parameters",
        "textureBindings": bindings,
        "texturePaths": [item["TexturePath"] for item in bindings],
    }
    if uv_tiling is not None:
        appearance["uvTiling"] = [float(uv_tiling[0]), float(uv_tiling[1])]
    document = {
        "asset": {"version": "2.0"},
        "meshes": [
            {
                "name": "body_mesh",
                "primitives": [
                    {"attributes": {"TEXCOORD_0": 0} if include_uv0 else {}}
                ],
                "extras": {
                    "kfps_role": role,
                    "kfps_material_name": material_name,
                    "kfps_material_appearance": appearance,
                },
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


def _write_bc7_dds(path: Path, *, srgb: bool = True) -> str:
    header = bytearray(DDS_DX10_HEADER_SIZE)
    header[:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x000A1007)
    struct.pack_into("<I", header, 12, 4)
    struct.pack_into("<I", header, 16, 4)
    struct.pack_into("<I", header, 24, 1)
    struct.pack_into("<I", header, 28, 1)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 0x4)
    header[84:88] = b"DX10"
    struct.pack_into("<I", header, 108, 0x1000)
    struct.pack_into("<IIIII", header, 128, 99 if srgb else 98, 3, 0, 1, 0)
    path.write_bytes(bytes(header) + bytes(range(16)))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(
    glb: Path,
    textures: list[dict],
    *,
    read_only: bool = True,
    format_name: str = "fh6_native_material_texture_resolution_v3",
) -> Path:
    manifest = glb.with_suffix(glb.suffix + ".native_textures.json")
    manifest.write_text(
        json.dumps(
            {
                "format": format_name,
                "revision": 3,
                "status": "resolved_all",
                "decode_status": "decoded_all",
                "textures": textures,
                "bindings": [],
                "game_data_modified": not read_only,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def _payload(texture_path: str, dds_path: Path, dds_sha: str) -> dict:
    return {
        "texture_path": texture_path,
        "normalized_path": texture_path.replace("Game:\\", "").replace("\\", "/"),
        "status": "resolved_payload",
        "resolution_mode": "derived_zip_exact",
        "payload_sha256": "1" * 64,
        "payload_size": 123,
        "cache_path": str(dds_path.with_suffix(".swatchbin")),
        "decode_status": "decoded_dds",
        "dds_path": str(dds_path),
        "dds_sha256": dds_sha,
        "dds_size": dds_path.stat().st_size,
    }


class NativeMaterialRenderPlanTests(unittest.TestCase):
    def test_joins_exact_mesh_binding_to_verified_dds_and_uv0_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            glb = root / "car.glb"
            texture_path = r"Game:\media\textures\trim\body.swatchbin"
            _write_glb(
                glb,
                [
                    {
                        "ParameterHash": "85F59336",
                        "PathHash": "1111222233334444",
                        "TexturePath": texture_path,
                    }
                ],
                uv_tiling=(2.0, 3.0),
            )
            dds = root / "body.dds"
            dds_sha = _write_bc7_dds(dds, srgb=True)
            _write_manifest(glb, [_payload(texture_path, dds, dds_sha)])

            plan = build_native_material_render_plan(glb)
            self.assertEqual(plan.revision, NATIVE_MATERIAL_RENDER_PLAN_REVISION)
            self.assertEqual(plan.status, "ready")
            self.assertEqual(plan.binding_count, 1)
            self.assertEqual(plan.recognized_binding_count, 1)
            self.assertEqual(plan.unknown_binding_count, 0)
            self.assertEqual(plan.selection_count, 1)
            self.assertEqual(plan.issue_count, 0)
            selection = plan.selections[0]
            self.assertEqual(selection.mesh_index, 0)
            self.assertEqual(selection.mesh_name, "body_mesh")
            self.assertEqual(selection.mesh_role, "trim")
            self.assertEqual(selection.material_name, "body_trim")
            self.assertEqual(selection.semantic, "base_color")
            self.assertEqual(selection.parameter_name, "DiffuseTexture")
            self.assertEqual(selection.parameter_hash, "85F59336")
            self.assertEqual(selection.texture_path, texture_path)
            self.assertEqual(selection.dds_sha256, dds_sha)
            self.assertEqual(selection.dxgi_format, 99)
            self.assertEqual(selection.compression_family, "bc7")
            self.assertTrue(selection.is_srgb)
            self.assertEqual(selection.uv_channel, 0)
            self.assertEqual(selection.uv_tiling_u, 2.0)
            self.assertEqual(selection.uv_tiling_v, 3.0)
            self.assertEqual(
                selection.uv_transform_mode,
                "kfps_baked_texcoord_transform_vflip_plus_material_tiling",
            )
            self.assertFalse(plan.game_data_modified)

    def test_carpaint_base_texture_does_not_replace_dynamic_paint_or_livery_albedo(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            glb = root / "car.glb"
            texture_path = r"Game:\media\textures\paint\body.swatchbin"
            _write_glb(
                glb,
                [{"ParameterHash": "85F59336", "PathHash": "1", "TexturePath": texture_path}],
                role="paint",
                material_name="carpaint",
            )
            dds = root / "body.dds"
            dds_sha = _write_bc7_dds(dds)
            _write_manifest(glb, [_payload(texture_path, dds, dds_sha)])

            plan = build_native_material_render_plan(glb)
            self.assertEqual(plan.status, "unavailable")
            self.assertEqual(plan.selection_count, 0)
            self.assertEqual(plan.issue_count, 1)
            self.assertEqual(plan.issues[0].status, "dynamic_paint_base_color_authoritative")

    def test_missing_uv_tiling_or_uv0_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            texture_path = r"Game:\media\textures\trim\body.swatchbin"
            binding = {"ParameterHash": "85F59336", "PathHash": "1", "TexturePath": texture_path}
            dds = root / "body.dds"
            dds_sha = _write_bc7_dds(dds)

            glb = root / "missing_tiling.glb"
            _write_glb(glb, [binding], uv_tiling=None)
            _write_manifest(glb, [_payload(texture_path, dds, dds_sha)])
            plan = build_native_material_render_plan(glb)
            self.assertEqual(plan.selection_count, 0)
            self.assertEqual(plan.issues[0].status, "material_uv_contract_unavailable")
            self.assertIn("tiling provenance is missing", plan.issues[0].detail)

            glb = root / "missing_uv0.glb"
            _write_glb(glb, [binding], include_uv0=False)
            _write_manifest(glb, [_payload(texture_path, dds, dds_sha)])
            plan = build_native_material_render_plan(glb)
            self.assertEqual(plan.selection_count, 0)
            self.assertEqual(plan.issues[0].status, "material_uv_contract_unavailable")
            self.assertIn("TEXCOORD_0", plan.issues[0].detail)

    def test_multiple_distinct_paths_for_one_semantic_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            glb = root / "car.glb"
            path_a = r"Game:\media\textures\trim\a.swatchbin"
            path_b = r"Game:\media\textures\trim\b.swatchbin"
            _write_glb(
                glb,
                [
                    {"ParameterHash": "85F59336", "PathHash": "1", "TexturePath": path_a},
                    {"ParameterHash": "10350BBC", "PathHash": "2", "TexturePath": path_b},
                ],
            )
            for name, texture_path in (("a", path_a), ("b", path_b)):
                dds = root / f"{name}.dds"
                sha = _write_bc7_dds(dds)
                if name == "a":
                    payload_a = _payload(texture_path, dds, sha)
                else:
                    payload_b = _payload(texture_path, dds, sha)
            _write_manifest(glb, [payload_a, payload_b])

            plan = build_native_material_render_plan(glb)
            self.assertEqual(plan.status, "unavailable")
            self.assertEqual(plan.selection_count, 0)
            self.assertEqual(plan.issue_count, 1)
            issue = plan.issues[0]
            self.assertEqual(issue.status, "ambiguous_semantic_bindings")
            self.assertEqual(issue.semantic, "base_color")
            self.assertEqual(set(issue.texture_paths), {path_a, path_b})

    def test_unknown_hash_is_preserved_as_unknown_not_filename_inferred(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            glb = root / "car.glb"
            misleading = r"Game:\media\textures\paint\definitely_diffuse.swatchbin"
            _write_glb(
                glb,
                [{"ParameterHash": "DEADBEEF", "PathHash": "1", "TexturePath": misleading}],
            )
            _write_manifest(glb, [])
            plan = build_native_material_render_plan(glb)
            self.assertEqual(plan.status, "no_recognized_bindings")
            self.assertEqual(plan.binding_count, 1)
            self.assertEqual(plan.recognized_binding_count, 0)
            self.assertEqual(plan.unknown_binding_count, 1)
            self.assertEqual(plan.selection_count, 0)

    def test_dds_sha_mismatch_is_issue_not_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            glb = root / "car.glb"
            texture_path = r"Game:\media\textures\trim\body.swatchbin"
            _write_glb(
                glb,
                [{"ParameterHash": "85F59336", "PathHash": "1", "TexturePath": texture_path}],
            )
            dds = root / "body.dds"
            _write_bc7_dds(dds)
            payload = _payload(texture_path, dds, "0" * 64)
            _write_manifest(glb, [payload])

            plan = build_native_material_render_plan(glb)
            self.assertEqual(plan.status, "unavailable")
            self.assertEqual(plan.selection_count, 0)
            self.assertEqual(plan.issues[0].status, "dds_unavailable")
            self.assertIn("SHA-256", plan.issues[0].detail)

    def test_manifest_must_be_v3_and_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            glb = root / "car.glb"
            _write_glb(glb, [])
            _write_manifest(glb, [], format_name="fh6_native_material_texture_resolution_v2")
            with self.assertRaisesRegex(NativeMaterialRenderPlanError, "Unsupported native texture manifest"):
                build_native_material_render_plan(glb)

            _write_manifest(glb, [], read_only=False)
            with self.assertRaisesRegex(NativeMaterialRenderPlanError, "read-only game-data contract"):
                build_native_material_render_plan(glb)


if __name__ == "__main__":
    unittest.main()
