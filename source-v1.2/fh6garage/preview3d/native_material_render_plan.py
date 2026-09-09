from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .native_dds import NativeDdsError, NativeDdsTexture, parse_native_dds
from .native_material_textures import _read_glb_json
from .native_texture_semantics import classify_native_texture_parameter

NATIVE_MATERIAL_RENDER_PLAN_REVISION = 1
_SUPPORTED_MANIFEST_FORMAT = "fh6_native_material_texture_resolution_v3"


class NativeMaterialRenderPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeMaterialTextureSelection:
    mesh_index: int
    mesh_name: str
    material_name: str
    semantic: str
    parameter_hash: str
    parameter_name: str
    texture_path: str
    dds_path: str
    dds_sha256: str
    width: int
    height: int
    mip_levels: int
    dxgi_format: int
    compression_family: str
    is_srgb: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NativeMaterialTextureIssue:
    mesh_index: int | None
    mesh_name: str
    material_name: str
    semantic: str
    status: str
    detail: str
    texture_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["texture_paths"] = list(self.texture_paths)
        return data


@dataclass(frozen=True)
class NativeMaterialRenderPlan:
    revision: int
    status: str
    manifest_path: str
    binding_count: int
    recognized_binding_count: int
    unknown_binding_count: int
    selection_count: int
    issue_count: int
    selections: tuple[NativeMaterialTextureSelection, ...]
    issues: tuple[NativeMaterialTextureIssue, ...]
    game_data_modified: bool = False

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["selections"] = [item.as_dict() for item in self.selections]
        data["issues"] = [item.as_dict() for item in self.issues]
        return data


def _path_key(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").casefold()


def _mapping_value(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    folded = {str(key).casefold(): value for key, value in mapping.items()}
    for name in names:
        if name.casefold() in folded:
            return folded[name.casefold()]
    return None


def _load_manifest(glb: Path) -> tuple[Path, dict[str, Any]]:
    manifest = glb.with_suffix(glb.suffix + ".native_textures.json")
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NativeMaterialRenderPlanError(
            f"Native texture manifest does not exist: {manifest}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeMaterialRenderPlanError(
            f"Native texture manifest could not be read: {manifest}: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise NativeMaterialRenderPlanError("Native texture manifest root is not an object.")
    if document.get("format") != _SUPPORTED_MANIFEST_FORMAT:
        raise NativeMaterialRenderPlanError(
            "Unsupported native texture manifest format: "
            f"{document.get('format')!r}; expected {_SUPPORTED_MANIFEST_FORMAT!r}."
        )
    if document.get("game_data_modified") is not False:
        raise NativeMaterialRenderPlanError(
            "Native texture manifest does not carry the required read-only game-data contract."
        )
    return manifest, document


def _texture_payload_index(manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    index: dict[str, dict[str, Any]] = {}
    conflicts: set[str] = set()
    raw_textures = manifest.get("textures")
    if not isinstance(raw_textures, list):
        return index, conflicts
    for raw in raw_textures:
        if not isinstance(raw, dict):
            continue
        key = _path_key(raw.get("texture_path"))
        if not key:
            continue
        previous = index.get(key)
        if previous is not None and previous != raw:
            conflicts.add(key)
            index.pop(key, None)
            continue
        if key not in conflicts:
            index[key] = raw
    return index, conflicts


def _verified_dds(payload: dict[str, Any]) -> NativeDdsTexture:
    if payload.get("status") != "resolved_payload":
        raise NativeMaterialRenderPlanError(
            f"Texture payload is not resolved: {payload.get('status')!r}."
        )
    if payload.get("decode_status") not in {"decoded_dds", "decoded_dds_cached"}:
        raise NativeMaterialRenderPlanError(
            f"Texture payload has no decoded DDS derivative: {payload.get('decode_status')!r}."
        )
    dds_text = str(payload.get("dds_path") or "").strip()
    expected_sha = str(payload.get("dds_sha256") or "").strip().casefold()
    if not dds_text or len(expected_sha) != 64:
        raise NativeMaterialRenderPlanError("Decoded DDS path or SHA-256 is missing from the manifest.")
    dds = Path(dds_text).expanduser().resolve()
    try:
        data = dds.read_bytes()
    except OSError as exc:
        raise NativeMaterialRenderPlanError(f"Decoded DDS could not be read: {dds}: {exc}") from exc
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != expected_sha:
        raise NativeMaterialRenderPlanError(
            "Decoded DDS SHA-256 no longer matches the manifest: "
            f"expected {expected_sha}, got {actual_sha}."
        )
    try:
        texture = parse_native_dds(dds)
    except NativeDdsError as exc:
        raise NativeMaterialRenderPlanError(str(exc)) from exc
    if not texture.is_simple_2d:
        raise NativeMaterialRenderPlanError(
            "Decoded DDS is not an ordinary 2D texture and is not enabled for material sampling."
        )
    return texture


def _mesh_binding_groups(document: dict[str, Any]) -> tuple[dict[tuple[int, str], list[dict[str, str]]], int, int, int]:
    groups: dict[tuple[int, str], list[dict[str, str]]] = {}
    binding_count = 0
    recognized = 0
    unknown = 0
    meshes = document.get("meshes")
    if not isinstance(meshes, list):
        return groups, binding_count, recognized, unknown

    for mesh_index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            continue
        extras = mesh.get("extras")
        if not isinstance(extras, dict):
            continue
        appearance = extras.get("kfps_material_appearance")
        if not isinstance(appearance, dict):
            continue
        raw_bindings = _mapping_value(appearance, "textureBindings", "TextureBindings")
        if not isinstance(raw_bindings, list):
            continue
        for raw in raw_bindings:
            if not isinstance(raw, dict):
                continue
            texture_path = str(_mapping_value(raw, "texturePath", "TexturePath") or "").strip()
            if not texture_path:
                continue
            parameter = classify_native_texture_parameter(
                _mapping_value(raw, "parameterHash", "ParameterHash")
            )
            binding_count += 1
            if parameter.semantic == "unknown" or not parameter.parameter_name:
                unknown += 1
                continue
            recognized += 1
            groups.setdefault((mesh_index, parameter.semantic), []).append(
                {
                    "parameter_hash": parameter.parameter_hash,
                    "parameter_name": parameter.parameter_name,
                    "texture_path": texture_path,
                }
            )
    return groups, binding_count, recognized, unknown


def build_native_material_render_plan(glb_path: str | Path) -> NativeMaterialRenderPlan:
    """Join exact mesh TextureBindings to verified decoded DDS derivatives.

    This stage deliberately does not choose UV channels, upload OpenGL textures,
    or collapse multiple texture layers.  A mesh/semantic with more than one
    distinct Texture2D path is marked ambiguous and receives no selection.
    """
    glb = Path(glb_path).expanduser().resolve()
    manifest_path, manifest = _load_manifest(glb)
    document = _read_glb_json(glb)
    payloads, payload_conflicts = _texture_payload_index(manifest)
    groups, binding_count, recognized_count, unknown_count = _mesh_binding_groups(document)

    selections: list[NativeMaterialTextureSelection] = []
    issues: list[NativeMaterialTextureIssue] = []
    meshes = document.get("meshes") if isinstance(document.get("meshes"), list) else []

    for (mesh_index, semantic), candidates in sorted(groups.items(), key=lambda item: item[0]):
        mesh = meshes[mesh_index] if 0 <= mesh_index < len(meshes) and isinstance(meshes[mesh_index], dict) else {}
        extras = mesh.get("extras") if isinstance(mesh, dict) else {}
        extras = extras if isinstance(extras, dict) else {}
        mesh_name = str(mesh.get("name") or "") if isinstance(mesh, dict) else ""
        material_name = str(extras.get("kfps_material_name") or "")

        unique: dict[str, dict[str, str]] = {}
        for candidate in candidates:
            key = _path_key(candidate["texture_path"])
            if key and key not in unique:
                unique[key] = candidate
        if len(unique) != 1:
            issues.append(
                NativeMaterialTextureIssue(
                    mesh_index=mesh_index,
                    mesh_name=mesh_name,
                    material_name=material_name,
                    semantic=semantic,
                    status="ambiguous_semantic_bindings",
                    detail=(
                        "More than one distinct Texture2D path is bound to the same mesh semantic; "
                        "no layer was guessed."
                    ),
                    texture_paths=tuple(candidate["texture_path"] for candidate in unique.values()),
                )
            )
            continue

        key, candidate = next(iter(unique.items()))
        if key in payload_conflicts:
            issues.append(
                NativeMaterialTextureIssue(
                    mesh_index=mesh_index,
                    mesh_name=mesh_name,
                    material_name=material_name,
                    semantic=semantic,
                    status="conflicting_payload_records",
                    detail="The native texture manifest contains conflicting records for this Texture2D path.",
                    texture_paths=(candidate["texture_path"],),
                )
            )
            continue
        payload = payloads.get(key)
        if payload is None:
            issues.append(
                NativeMaterialTextureIssue(
                    mesh_index=mesh_index,
                    mesh_name=mesh_name,
                    material_name=material_name,
                    semantic=semantic,
                    status="payload_record_missing",
                    detail="No native texture payload record matches the exact Texture2D path.",
                    texture_paths=(candidate["texture_path"],),
                )
            )
            continue
        try:
            texture = _verified_dds(payload)
        except NativeMaterialRenderPlanError as exc:
            issues.append(
                NativeMaterialTextureIssue(
                    mesh_index=mesh_index,
                    mesh_name=mesh_name,
                    material_name=material_name,
                    semantic=semantic,
                    status="dds_unavailable",
                    detail=str(exc),
                    texture_paths=(candidate["texture_path"],),
                )
            )
            continue

        selections.append(
            NativeMaterialTextureSelection(
                mesh_index=mesh_index,
                mesh_name=mesh_name,
                material_name=material_name,
                semantic=semantic,
                parameter_hash=candidate["parameter_hash"],
                parameter_name=candidate["parameter_name"],
                texture_path=candidate["texture_path"],
                dds_path=texture.path,
                dds_sha256=str(payload.get("dds_sha256") or "").casefold(),
                width=texture.width,
                height=texture.height,
                mip_levels=texture.mip_levels,
                dxgi_format=texture.dxgi_format,
                compression_family=texture.compression_family,
                is_srgb=texture.is_srgb,
            )
        )

    if selections and issues:
        status = "partial"
    elif selections:
        status = "ready"
    elif recognized_count:
        status = "unavailable"
    elif binding_count:
        status = "no_recognized_bindings"
    else:
        status = "no_texture_bindings"

    return NativeMaterialRenderPlan(
        revision=NATIVE_MATERIAL_RENDER_PLAN_REVISION,
        status=status,
        manifest_path=str(manifest_path),
        binding_count=binding_count,
        recognized_binding_count=recognized_count,
        unknown_binding_count=unknown_count,
        selection_count=len(selections),
        issue_count=len(issues),
        selections=tuple(selections),
        issues=tuple(issues),
        game_data_modified=False,
    )
