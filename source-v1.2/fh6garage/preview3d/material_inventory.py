from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MATERIAL_INVENTORY_REVISION = 1
KFPS_CONVERTER_COMMIT = "6f53ca3c584d78659d06d4b4a39561db67d79345"
KFPS_SCENE_FORMAT = "kfps_local_chassis_scene_v3"

_KFPS_MESH_KEYS = (
    "kfps_role",
    "kfps_source_entry",
    "kfps_material_name",
    "kfps_part_type",
    "kfps_instance_identity",
    "kfps_stock_part",
    "kfps_part_option_ids",
    "kfps_draw_groups",
    "kfps_allowed_sides",
    "kfps_projection_sides",
    "kfps_material_binding_hash",
)


class MaterialInventoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class MaterialBindingRecord:
    mesh_index: int
    mesh_name: str
    node_indices: tuple[int, ...]
    primitive_count: int
    triangle_primitive_count: int
    uv_channels: tuple[int, ...]
    role: str
    source_entry: str
    material_name: str
    part_type: str
    instance_identity: str
    material_binding_hash: str | None
    material_binding_value: int | None
    material_binding_status: str
    node_mesh_extras_match: bool


@dataclass(frozen=True)
class MaterialInventoryReport:
    revision: int
    source_name: str
    source_size: int
    asset_generator: str
    scene_format: str
    mesh_count: int
    node_count: int
    gltf_material_count: int
    primitive_material_references: int
    resolved_binding_hashes: int
    zero_binding_hashes: int
    missing_binding_hashes: int
    malformed_binding_hashes: int
    extras_mismatch_meshes: int
    records: tuple[MaterialBindingRecord, ...]
    game_data_modified: bool = False


def _read_document(path: Path) -> tuple[dict[str, Any], int]:
    try:
        source_size = int(path.stat().st_size)
        source = path.open("rb")
    except OSError as exc:
        raise MaterialInventoryError(f"Could not open GLB material inventory source: {exc}") from exc

    with source:
        header = source.read(12)
        if len(header) != 12 or header[:4] != b"glTF":
            raise MaterialInventoryError("Material inventory source is not a GLB file.")
        version, total_length = struct.unpack_from("<II", header, 4)
        if version != 2 or total_length < 20 or total_length > source_size:
            raise MaterialInventoryError("Material inventory source is an unsupported or truncated GLB.")

        offset = 12
        document: dict[str, Any] | None = None
        while offset + 8 <= total_length:
            chunk_header = source.read(8)
            if len(chunk_header) != 8:
                raise MaterialInventoryError("GLB chunk header is truncated.")
            chunk_length, chunk_type = struct.unpack("<II", chunk_header)
            offset += 8
            if chunk_length < 0 or offset + chunk_length > total_length:
                raise MaterialInventoryError("GLB chunk exceeds the declared file length.")
            if chunk_type == 0x4E4F534A and document is None:
                raw = source.read(chunk_length)
                if len(raw) != chunk_length:
                    raise MaterialInventoryError("GLB JSON chunk is truncated.")
                try:
                    decoded = json.loads(raw.rstrip(b" \x00").decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise MaterialInventoryError(f"GLB JSON chunk is invalid: {exc}") from exc
                if not isinstance(decoded, dict):
                    raise MaterialInventoryError("GLB JSON root is not an object.")
                document = decoded
            else:
                source.seek(chunk_length, 1)
            offset += chunk_length

        if document is None:
            raise MaterialInventoryError("GLB contains no JSON document.")
        return document, source_size


def _extras(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _kfps_projection(extras: dict[str, Any]) -> dict[str, Any]:
    return {key: extras.get(key) for key in _KFPS_MESH_KEYS if key in extras}


def _binding_hash(value: Any) -> tuple[str | None, int | None, str]:
    # Pinned KFPS GlbWriter.cs emits MaterialBindingHash.ToString("X16").
    # Do not infer a hash from a material name when this structural field is absent.
    if value is None:
        return None, None, "missing"
    if not isinstance(value, str) or len(value) != 16:
        return None, None, "malformed"
    try:
        numeric = int(value, 16)
    except ValueError:
        return None, None, "malformed"
    normalized = f"{numeric:016X}"
    return normalized, numeric, "zero" if numeric == 0 else "resolved"


def _scene_format(document: dict[str, Any]) -> str:
    scenes = document.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return ""
    scene_index = document.get("scene", 0)
    try:
        scene = scenes[int(scene_index)]
    except (TypeError, ValueError, IndexError):
        return ""
    if not isinstance(scene, dict):
        return ""
    return str(_extras(scene.get("extras")).get("kfps_format") or "")


def build_material_inventory(path: str | Path) -> MaterialInventoryReport:
    """Inspect KFPS GLB material linkage without modifying the GLB or FH6 data."""
    source_path = Path(path)
    document, source_size = _read_document(source_path)

    meshes = document.get("meshes")
    nodes = document.get("nodes")
    materials = document.get("materials")
    mesh_rows = meshes if isinstance(meshes, list) else []
    node_rows = nodes if isinstance(nodes, list) else []
    material_rows = materials if isinstance(materials, list) else []

    nodes_by_mesh: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for node_index, node in enumerate(node_rows):
        if not isinstance(node, dict) or not isinstance(node.get("mesh"), int):
            continue
        mesh_index = int(node["mesh"])
        nodes_by_mesh.setdefault(mesh_index, []).append((node_index, _extras(node.get("extras"))))

    records: list[MaterialBindingRecord] = []
    primitive_material_references = 0
    resolved = zero = missing = malformed = mismatches = 0

    for mesh_index, mesh in enumerate(mesh_rows):
        if not isinstance(mesh, dict):
            continue
        mesh_extras = _extras(mesh.get("extras"))
        projected_mesh_extras = _kfps_projection(mesh_extras)
        node_bindings = nodes_by_mesh.get(mesh_index, [])
        extras_match = bool(node_bindings) and all(
            _kfps_projection(node_extras) == projected_mesh_extras
            for _, node_extras in node_bindings
        )
        if not extras_match:
            mismatches += 1

        primitives = mesh.get("primitives")
        primitive_rows = primitives if isinstance(primitives, list) else []
        triangle_primitives = 0
        uv_channels: set[int] = set()
        for primitive in primitive_rows:
            if not isinstance(primitive, dict):
                continue
            if int(primitive.get("mode", 4)) == 4:
                triangle_primitives += 1
            if "material" in primitive:
                primitive_material_references += 1
            attributes = primitive.get("attributes")
            if not isinstance(attributes, dict):
                continue
            for semantic in attributes:
                if not isinstance(semantic, str) or not semantic.startswith("TEXCOORD_"):
                    continue
                try:
                    uv_channels.add(int(semantic.split("_", 1)[1]))
                except (TypeError, ValueError):
                    continue

        binding_hash, binding_value, binding_status = _binding_hash(
            mesh_extras.get("kfps_material_binding_hash")
        )
        if binding_status == "resolved":
            resolved += 1
        elif binding_status == "zero":
            zero += 1
        elif binding_status == "missing":
            missing += 1
        else:
            malformed += 1

        records.append(
            MaterialBindingRecord(
                mesh_index=mesh_index,
                mesh_name=str(mesh.get("name") or ""),
                node_indices=tuple(index for index, _ in node_bindings),
                primitive_count=len(primitive_rows),
                triangle_primitive_count=triangle_primitives,
                uv_channels=tuple(sorted(uv_channels)),
                role=str(mesh_extras.get("kfps_role") or ""),
                source_entry=str(mesh_extras.get("kfps_source_entry") or ""),
                material_name=str(mesh_extras.get("kfps_material_name") or ""),
                part_type=str(mesh_extras.get("kfps_part_type") or ""),
                instance_identity=str(mesh_extras.get("kfps_instance_identity") or ""),
                material_binding_hash=binding_hash,
                material_binding_value=binding_value,
                material_binding_status=binding_status,
                node_mesh_extras_match=extras_match,
            )
        )

    asset = document.get("asset")
    asset_generator = str(asset.get("generator") or "") if isinstance(asset, dict) else ""
    return MaterialInventoryReport(
        revision=MATERIAL_INVENTORY_REVISION,
        source_name=source_path.name,
        source_size=source_size,
        asset_generator=asset_generator,
        scene_format=_scene_format(document),
        mesh_count=len(mesh_rows),
        node_count=len(node_rows),
        gltf_material_count=len(material_rows),
        primitive_material_references=primitive_material_references,
        resolved_binding_hashes=resolved,
        zero_binding_hashes=zero,
        missing_binding_hashes=missing,
        malformed_binding_hashes=malformed,
        extras_mismatch_meshes=mismatches,
        records=tuple(records),
        game_data_modified=False,
    )
