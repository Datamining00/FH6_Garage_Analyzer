from __future__ import annotations

"""Global wheel/tire assembly correction for FH6 Assistant.

This module replaces the four-spindle/AABB-centering trial path with a native
transform-chain path:

* KFPS emits the exact resolved WheelStyle instance transforms it used for rims.
* Native tire modelbin RigidBoneIndex/Skeleton transforms are preserved.
* Stock tire dimensions are applied about the model-local origin, not an AABB
  center guessed to be a spindle pivot.
* Every resolved WheelStyle instance receives a tire; the wheel count is dynamic.
* The same KFPS render-space conversion (-X, Y, Z) is applied after the exact
  WheelStyle effective transform is baked.

No vehicle id, model name, fixed translation, rotation, scale, or four-wheel
assumption participates in placement.
"""

from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
from typing import Any, Callable, Mapping, Sequence
import zipfile

from . import chassis_converter as chassis
from . import tire_preview_integration as legacy_integration
from . import tire_production_trial_geometry as legacy_geometry
from . import tire_spindle_glb_merge as legacy_merge
from . import tire_viewer_matrix_bake as legacy_bake
from .modelbin_morph import MESH_TAG, _iter_bundle_blobs
from .tire_asset import resolve_tire_archive
from .tire_morph_geometry import (
    INDEX_BUFFER_TAG,
    INPUT_LAYOUT_TAG,
    VERTEX_BUFFER_TAG,
    VERTEX_LAYOUT_TAG,
    TireMorphGeometryError,
    _aabb,
    _compact_geometry,
    _decode_positions,
    _glb_bytes,
    _mesh_indices,
    _parse_global_indices,
    _parse_layout,
    _parse_mesh,
    _parse_vertex_buffer,
    _read_int32_char_string,
    _resolve_layout,
)
from .wheel_morph_helper import (
    WHEEL_MORPH_HELPER_REVISION,
    WheelMorphHelperError,
    verified_bundled_wheel_morph_helper,
)
from .wheel_spec import FH6WheelSpecResolver
from .wheel_spec_database import ensure_stock_wheel_database


NATIVE_TRANSFORM_CHAIN_REVISION = "native_transform_chain_dynamic_wheels_v1"
SKELETON_TAG = 0x536B656C  # Skel
WHEEL_STYLE_PART_TYPE = 44
_PATCH_MARKER = "_fh6_native_transform_chain_dynamic_wheels_installed"
_ORIGINAL_HELPER_RESOLVER = "_fh6_native_transform_chain_original_helper_resolver"


class NativeTransformChainError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_matrix() -> tuple[float, ...]:
    return (
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )


def _finite_matrix(raw: object, *, label: str) -> tuple[float, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)) or len(raw) != 16:
        raise NativeTransformChainError(f"{label} must contain exactly 16 values")
    matrix = tuple(float(value) for value in raw)
    if not all(math.isfinite(value) for value in matrix):
        raise NativeTransformChainError(f"{label} contains a non-finite value")
    return matrix


def _matrix_multiply(a: Sequence[float], b: Sequence[float]) -> tuple[float, ...]:
    """System.Numerics-compatible row-major matrix multiplication a * b."""
    left = _finite_matrix(a, label="left matrix")
    right = _finite_matrix(b, label="right matrix")
    values = []
    for row in range(4):
        for column in range(4):
            values.append(
                sum(left[row * 4 + k] * right[k * 4 + column] for k in range(4))
            )
    return tuple(values)


def _transform_point_row(point: Sequence[float], matrix: Sequence[float]) -> tuple[float, float, float]:
    m = _finite_matrix(matrix, label="point transform")
    x, y, z = (float(value) for value in point[:3])
    result = (
        x * m[0] + y * m[4] + z * m[8] + m[12],
        x * m[1] + y * m[5] + z * m[9] + m[13],
        x * m[2] + y * m[6] + z * m[10] + m[14],
    )
    if not all(math.isfinite(value) for value in result):
        raise NativeTransformChainError("native rigid-bone transform produced a non-finite point")
    return result


def _parse_native_skeleton(data: bytes, blobs: Sequence[Any]) -> tuple[tuple[str, int, tuple[float, ...]], ...]:
    candidates = [blob for blob in blobs if int(getattr(blob, "tag", -1)) == SKELETON_TAG]
    if not candidates:
        return ()
    if len(candidates) != 1:
        raise NativeTransformChainError(f"native tire modelbin has {len(candidates)} Skeleton blobs; expected at most one")
    blob = candidates[0]
    cursor = int(blob.data_offset)
    end = cursor + int(blob.data_size)
    if cursor < 0 or end > len(data) or cursor + 2 > end:
        raise NativeTransformChainError("native tire Skeleton blob is truncated")
    bone_count = struct.unpack_from("<H", data, cursor)[0]
    cursor += 2
    if bone_count > 4096:
        raise NativeTransformChainError(f"native tire Skeleton has implausible bone count {bone_count}")
    bones: list[tuple[str, int, tuple[float, ...]]] = []
    for index in range(bone_count):
        try:
            name, cursor = _read_int32_char_string(data, cursor, end, f"Skeleton bone {index} name")
        except TireMorphGeometryError as exc:
            raise NativeTransformChainError(str(exc)) from exc
        if cursor + 6 + 64 > end:
            raise NativeTransformChainError(f"Skeleton bone {index} is truncated")
        parent_id, _first_child, _next_index = struct.unpack_from("<hhh", data, cursor)
        cursor += 6
        matrix = tuple(float(value) for value in struct.unpack_from("<16f", data, cursor))
        cursor += 64
        _finite_matrix(matrix, label=f"Skeleton bone {index} matrix")
        bones.append((name, int(parent_id), matrix))
    return tuple(bones)


def _bone_world_matrices(
    bones: Sequence[tuple[str, int, tuple[float, ...]]],
) -> tuple[tuple[float, ...], ...]:
    if not bones:
        return ()
    cache: list[tuple[float, ...] | None] = [None] * len(bones)
    visiting = [False] * len(bones)

    def resolve(index: int) -> tuple[float, ...]:
        ready = cache[index]
        if ready is not None:
            return ready
        if visiting[index]:
            raise NativeTransformChainError("native tire skeleton contains a parent cycle")
        visiting[index] = True
        _name, parent_id, local = bones[index]
        world = local
        if 0 <= parent_id < len(bones):
            world = _matrix_multiply(local, resolve(parent_id))
        visiting[index] = False
        cache[index] = world
        return world

    return tuple(resolve(index) for index in range(len(bones)))


def _mesh_rigid_bone_index(data: bytes, blob: Any) -> int:
    cursor = int(blob.data_offset)
    end = cursor + int(blob.data_size)
    version_major = int(blob.version_major)
    version_minor = int(blob.version_minor)
    if (version_major, version_minor) >= (1, 13):
        if cursor + 4 > end:
            raise NativeTransformChainError(f"Mesh {blob.blob_index} material-group header is truncated")
        group_count = struct.unpack_from("<i", data, cursor)[0]
        cursor += 4
    else:
        group_count = 1
    if group_count < 0 or group_count > 4096:
        raise NativeTransformChainError(f"Mesh {blob.blob_index} has invalid material-group count {group_count}")
    group_size = 8 if (version_major, version_minor) >= (1, 9) else 2
    cursor += group_count * group_size
    if cursor + 2 > end:
        raise NativeTransformChainError(f"Mesh {blob.blob_index} RigidBoneIndex is truncated")
    return int(struct.unpack_from("<h", data, cursor)[0])


def _native_modelbin_geometry(
    data: bytes,
    *,
    entry: str,
    source_entry: str,
    axle_spec: Any,
    output_dir: Path,
) -> dict[str, Any]:
    try:
        _bundle_major, _bundle_minor, blobs = _iter_bundle_blobs(data)
        index_blobs = [blob for blob in blobs if blob.tag == INDEX_BUFFER_TAG]
        if not index_blobs:
            raise NativeTransformChainError(f"{source_entry}: modelbin has no IndB")
        index_raw, _index_stride = _parse_global_indices(data, index_blobs[0])
        layouts = tuple(
            _parse_layout(data, blob)
            for blob in blobs
            if blob.tag in (VERTEX_LAYOUT_TAG, INPUT_LAYOUT_TAG)
        )
        buffers = tuple(_parse_vertex_buffer(data, blob) for blob in blobs if blob.tag == VERTEX_BUFFER_TAG)
        by_buffer_blob = {item.blob_index: item for item in buffers}
        mesh_pairs = tuple(
            (blob, _parse_mesh(data, blob)) for blob in blobs if blob.tag == MESH_TAG
        )
        skeleton = _parse_native_skeleton(data, blobs)
        bone_worlds = _bone_world_matrices(skeleton)
    except (TireMorphGeometryError, NativeTransformChainError) as exc:
        raise NativeTransformChainError(f"{source_entry}: {exc}") from exc

    aggregate_local: list[tuple[float, float, float]] = []
    aggregate_indices: list[int] = []
    segments: list[tuple[int, int, tuple[float, ...], int, str]] = []
    selected_mesh_count = 0

    for blob, mesh in mesh_pairs:
        if (mesh.lod_flags & 3) == 0 or mesh.index_count <= 0:
            continue
        try:
            source_indices = _mesh_indices(index_raw, mesh)
            if not source_indices:
                continue
            min_index = min(source_indices)
            max_index = max(source_indices)
            layout, _layout_resolution = _resolve_layout(mesh, layouts)
            base_positions, _position_format, _vb_resolution = _decode_positions(
                mesh, layout, buffers, by_buffer_blob, min_index, max_index
            )
            compact_positions, compact_indices = _compact_geometry(
                base_positions, source_indices, min_index
            )
        except TireMorphGeometryError as exc:
            raise NativeTransformChainError(
                f"{source_entry}: mesh {mesh.blob_index}: {exc}"
            ) from exc

        rigid_index = _mesh_rigid_bone_index(data, blob)
        if 0 <= rigid_index < len(bone_worlds):
            rigid_world = bone_worlds[rigid_index]
            rigid_name = skeleton[rigid_index][0]
        else:
            rigid_world = _identity_matrix()
            rigid_name = ""

        start = len(aggregate_local)
        aggregate_local.extend(tuple(map(float, point)) for point in compact_positions)
        aggregate_indices.extend(start + int(index) for index in compact_indices)
        segments.append((start, len(compact_positions), rigid_world, rigid_index, rigid_name))
        selected_mesh_count += 1

    if not aggregate_local or not aggregate_indices or selected_mesh_count <= 0:
        raise NativeTransformChainError(f"{source_entry}: modelbin has no decodable LOD0 tire geometry")

    before = _aabb(aggregate_local)
    target_width = float(axle_spec.tire_width_mm) / 1000.0
    target_outer = float(axle_spec.tire_outer_diameter_mm) / 1000.0
    spans = tuple(float(value) for value in before.span)
    if not all(math.isfinite(value) and value > 1.0e-9 for value in spans):
        raise NativeTransformChainError(f"{source_entry}: invalid local tire span {spans!r}")
    if not all(math.isfinite(value) and value > 0.0 for value in (target_width, target_outer)):
        raise NativeTransformChainError(f"{source_entry}: invalid stock tire dimensions")

    scales = (
        target_width / spans[0],
        target_outer / spans[1],
        target_outer / spans[2],
    )
    if not all(math.isfinite(value) and value > 0.0 for value in scales):
        raise NativeTransformChainError(f"{source_entry}: invalid stock normalization scale {scales!r}")

    # Preserve the native model origin. Do not replace it with the AABB center.
    normalized_local = [
        (
            float(point[0]) * scales[0],
            float(point[1]) * scales[1],
            float(point[2]) * scales[2],
        )
        for point in aggregate_local
    ]

    final_positions = list(normalized_local)
    rigid_indices: list[int] = []
    rigid_names: list[str] = []
    for start, count, rigid_world, rigid_index, rigid_name in segments:
        rigid_indices.append(rigid_index)
        rigid_names.append(rigid_name)
        if rigid_world == _identity_matrix():
            continue
        for local_index in range(start, start + count):
            final_positions[local_index] = _transform_point_row(
                final_positions[local_index], rigid_world
            )

    final_aabb = _aabb(final_positions)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = Path(entry.replace("\\", "/")).stem
    glb_path = output_dir / f"{axle_spec.axle}__{safe_stem}__native_chain.glb"
    try:
        glb_path.write_bytes(_glb_bytes(final_positions, aggregate_indices))
    except (OSError, TireMorphGeometryError) as exc:
        raise NativeTransformChainError(f"could not write native tire derivative {glb_path}: {exc}") from exc

    return {
        "axle": str(axle_spec.axle),
        "entry": entry.replace("\\", "/"),
        "source_entry": source_entry.replace("\\", "/"),
        "modelbin_sha256": hashlib.sha256(data).hexdigest(),
        "selected_mesh_count": selected_mesh_count,
        "vertex_count": len(final_positions),
        "index_count": len(aggregate_indices),
        "normalization_scale_xyz": [float(value) for value in scales],
        "target_width_m": target_width,
        "target_outer_diameter_m": target_outer,
        "pre_normalization_aabb": before.as_dict(),
        "aabb": final_aabb.as_dict(),
        "rigid_bone_indices": rigid_indices,
        "rigid_bone_names": rigid_names,
        "native_rigid_bone_transform_applied": True,
        "native_origin_preserved": True,
        "aabb_center_used_as_pivot": False,
        "morph_mode": "native_base_stock_dimensions_plus_rigid_bone",
        "glb_path": str(glb_path),
    }


def _build_native_tire_geometry_report(spec: Any, tire_archive: Path, output_dir: Path) -> dict[str, Any]:
    before_sha = _sha256(tire_archive)
    model_name = str(spec.tire_model_name or "").strip()
    with zipfile.ZipFile(tire_archive, "r") as bundle:
        selected = legacy_geometry._select_native_modelbins(bundle, model_name)
    if not selected:
        raise NativeTransformChainError("native tire archive yielded no modelbin candidates")

    def build_axle(axle_spec: Any) -> dict[str, Any]:
        modelbins = [
            _native_modelbin_geometry(
                data,
                entry=entry,
                source_entry=source_entry,
                axle_spec=axle_spec,
                output_dir=output_dir,
            )
            for entry, source_entry, data in selected
        ]
        return {
            "axle": str(axle_spec.axle),
            "target_width_m": float(axle_spec.tire_width_mm) / 1000.0,
            "target_outer_diameter_m": float(axle_spec.tire_outer_diameter_mm) / 1000.0,
            "modelbins": modelbins,
        }

    front = build_axle(spec.front)
    rear = build_axle(spec.rear)
    after_sha = _sha256(tire_archive)
    if after_sha != before_sha:
        raise NativeTransformChainError("read-only native tire generation changed the source tire archive")
    report = {
        "format": "fh6_native_tire_geometry_transform_chain_v1",
        "status": "native_tire_geometry_ready",
        "revision": NATIVE_TRANSFORM_CHAIN_REVISION,
        "car_id": int(spec.car_id),
        "tire_model_name": model_name,
        "archive_path": str(tire_archive),
        "archive_sha256": before_sha,
        "archive_read_only_unchanged": True,
        "front": front,
        "rear": rear,
        "native_rigid_bone_transform_applied": True,
        "native_origin_preserved": True,
        "aabb_center_used_as_pivot": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "native_tire_geometry_transform_chain.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def _entry_side(entry: str) -> str:
    stem = Path(str(entry).replace("\\", "/")).stem.casefold()
    if stem.startswith("tirel_"):
        return "left"
    if stem.startswith("tirer_"):
        return "right"
    return "unknown"


def _axle_derivatives(report: Mapping[str, Any], axle: str) -> dict[str, Mapping[str, Any]]:
    payload = report.get(axle)
    if not isinstance(payload, Mapping):
        raise NativeTransformChainError(f"native tire geometry report is missing {axle} data")
    result: dict[str, Mapping[str, Any]] = {}
    for item in payload.get("modelbins") or ():
        if not isinstance(item, Mapping):
            continue
        side = _entry_side(str(item.get("entry") or ""))
        if side in ("left", "right") and side not in result:
            result[side] = item
    if not result:
        raise NativeTransformChainError(f"native tire geometry report has no {axle} derivatives")
    return result


def _named_side(bone_name: str) -> str | None:
    compact = re.sub(r"[^a-z0-9]", "", str(bone_name).casefold())
    if "left" in compact or compact.endswith(("lf", "lr", "lm")):
        return "left"
    if "right" in compact or compact.endswith(("rf", "rr", "rm")):
        return "right"
    return None


def _classify_dynamic_wheel_anchors(raw_anchors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_anchors):
        identity = str(raw.get("instance_identity") or "").strip()
        if not identity:
            raise NativeTransformChainError(f"WheelStyle anchor {index} has no instance_identity")
        if identity in seen:
            raise NativeTransformChainError(f"duplicate WheelStyle anchor identity: {identity}")
        seen.add(identity)
        carbin = _finite_matrix(raw.get("carbin_transform_row_major"), label=f"{identity} carbin transform")
        effective = _finite_matrix(raw.get("effective_transform_row_major"), label=f"{identity} effective transform")
        anchors.append(
            {
                **dict(raw),
                "instance_identity": identity,
                "carbin_transform_row_major": list(carbin),
                "effective_transform_row_major": list(effective),
                "_x": float(carbin[12]),
                "_z": float(carbin[14]),
                "_named_side": _named_side(str(raw.get("bone_name") or "")),
            }
        )
    if not anchors:
        raise NativeTransformChainError(
            "KFPS converter returned no resolved WheelStyle anchors; exact rim/tire transform parity cannot be proven"
        )

    z_values = [item["_z"] for item in anchors]
    front_z = max(z_values)
    z_span = max(z_values) - min(z_values)
    front_tolerance = max(1.0e-4, abs(z_span) * 0.01)

    named_left_x = [item["_x"] for item in anchors if item["_named_side"] == "left"]
    named_right_x = [item["_x"] for item in anchors if item["_named_side"] == "right"]
    left_center = sum(named_left_x) / len(named_left_x) if named_left_x else None
    right_center = sum(named_right_x) / len(named_right_x) if named_right_x else None
    lateral_scale = max([abs(item["_x"]) for item in anchors] + [1.0])
    center_tolerance = max(1.0e-5, lateral_scale * 1.0e-3)

    classified: list[dict[str, Any]] = []
    for item in anchors:
        axle = "front" if abs(item["_z"] - front_z) <= front_tolerance else "rear"
        side = item["_named_side"]
        inference = "bone_name"
        if side is None:
            x = float(item["_x"])
            if abs(x) <= center_tolerance:
                side = "center"
                inference = "carbin_lateral_center"
            elif left_center is not None and right_center is not None:
                side = "left" if abs(x - left_center) <= abs(x - right_center) else "right"
                inference = "calibrated_carbin_lateral_position"
            else:
                side = "left" if x < 0.0 else "right"
                inference = "carbin_lateral_sign"
        classified.append(
            {
                **{key: value for key, value in item.items() if not key.startswith("_")},
                "axle": axle,
                "side": side,
                "axle_inference": "frontmost_carbin_z_cluster" if axle == "front" else "nonfront_carbin_z_cluster",
                "side_inference": inference,
            }
        )
    return classified


def _select_derivative(
    geometry_report: Mapping[str, Any], axle: str, side: str
) -> tuple[Mapping[str, Any], str]:
    candidates = _axle_derivatives(geometry_report, axle)
    if side == "right" and "right" in candidates:
        return candidates["right"], "exact_side_model"
    if side == "left" and "left" in candidates:
        return candidates["left"], "exact_side_model"
    if side == "center":
        if "left" in candidates:
            return candidates["left"], "center_wheel_canonical_left_model"
        return next(iter(candidates.values())), "center_wheel_only_native_model"
    if "left" in candidates:
        return candidates["left"], "single_left_model_reused_by_exact_wheel_anchor"
    if side == "left" and "right" in candidates:
        raise NativeTransformChainError(
            f"{axle}/left wheel has only a right-side tire derivative; refusing an unproven mirror"
        )
    return next(iter(candidates.values())), "only_native_model_reused_by_exact_wheel_anchor"


def _build_dynamic_attachment_contract(
    car_id: int,
    geometry_report: Mapping[str, Any],
    converter_diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    raw_anchors = converter_diagnostics.get("wheel_style_anchors")
    if not isinstance(raw_anchors, list):
        raise NativeTransformChainError(
            "converter diagnostics do not contain wheel_style_anchors; bundled transform-audit helper is required"
        )
    anchors = _classify_dynamic_wheel_anchors(
        [item for item in raw_anchors if isinstance(item, Mapping)]
    )
    attachments: list[dict[str, Any]] = []
    for index, anchor in enumerate(anchors):
        axle = str(anchor["axle"])
        side = str(anchor["side"])
        derivative, source_mode = _select_derivative(geometry_report, axle, side)
        path = str(derivative.get("glb_path") or "")
        if not path or not Path(path).is_file():
            raise NativeTransformChainError(
                f"WheelStyle anchor {anchor['instance_identity']} has no usable {axle}/{side} tire derivative"
            )
        bone = str(anchor.get("bone_name") or "").strip() or f"wheel_instance_{index}"
        effective = _finite_matrix(
            anchor.get("effective_transform_row_major"),
            label=f"{anchor['instance_identity']} effective transform",
        )
        carbin = _finite_matrix(
            anchor.get("carbin_transform_row_major"),
            label=f"{anchor['instance_identity']} carbin transform",
        )
        attachments.append(
            {
                "attachment_id": str(anchor["instance_identity"]),
                "spindle_bone": bone,
                "axle": axle,
                "side": side,
                "side_inference": anchor.get("side_inference"),
                "axle_inference": anchor.get("axle_inference"),
                "carbin_resource_path": str(anchor.get("resource_path") or ""),
                "source_entry": str(anchor.get("source_entry") or ""),
                "carbin_transform_matrix_row_major": list(carbin),
                "effective_transform_matrix_row_major": list(effective),
                "placement_transform_matrix_row_major": list(effective),
                "placement_transform_source": "exact_kfps_wheelstyle_effective_instance_transform",
                "derived_tire_entry": str(derivative.get("entry") or ""),
                "derived_tire_glb_path": path,
                "derived_tire_source_side": _entry_side(str(derivative.get("entry") or "")),
                "side_source_mode": source_mode,
            }
        )
    if not attachments:
        raise NativeTransformChainError("dynamic WheelStyle inventory contains no tire attachments")
    return {
        "format": "fh6_native_tire_dynamic_wheel_attachment_contract_v1",
        "status": "dynamic_wheel_attachment_contract_ready",
        "revision": NATIVE_TRANSFORM_CHAIN_REVISION,
        "car_id": int(car_id),
        "attachment_part_type": WHEEL_STYLE_PART_TYPE,
        "attachment_count": len(attachments),
        "attachments": attachments,
        "wheel_count_source": "resolved_kfps_wheelstyle_instance_inventory",
        "four_wheel_assumption": False,
        "native_tire_rigid_bone_applied": True,
        "exact_kfps_effective_instance_transform_used": True,
        "procedural_translation_applied": False,
        "procedural_rotation_applied": False,
        "vehicle_specific_offset_applied": False,
    }


def _merge_dynamic_tires(
    vehicle_glb_path: Path,
    contract: Mapping[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    attachments = contract.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        raise NativeTransformChainError("dynamic tire contract has no attachments")
    source = vehicle_glb_path.resolve()
    output = output_path.resolve()
    source_sha = _sha256(source)
    document, binary = legacy_merge._read_glb(source)
    scene_index = legacy_merge._validate_vehicle_document(document)
    document = __import__("copy").deepcopy(document)
    scene = document["scenes"][scene_index]
    scene.setdefault("nodes", [])
    if not isinstance(scene["nodes"], list):
        raise NativeTransformChainError("vehicle scene nodes field is invalid")

    merged: list[dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, Mapping):
            raise NativeTransformChainError("dynamic tire attachment is not an object")
        attachment_id = str(item.get("attachment_id") or "")
        derivative = Path(str(item.get("derived_tire_glb_path") or "")).expanduser().resolve()
        if not derivative.is_file():
            raise NativeTransformChainError(f"{attachment_id}: tire derivative does not exist: {derivative}")
        derivative_document, derivative_binary = legacy_merge._read_glb(derivative)
        legacy_merge._validate_derivative_document(derivative_document, path=derivative)
        compat = dict(item)
        compat["carbin_transform_matrix_row_major"] = list(
            _finite_matrix(
                item.get("placement_transform_matrix_row_major"),
                label=f"{attachment_id} placement transform",
            )
        )
        binary, node_index, mesh_index = legacy_merge._append_derivative(
            document, binary, derivative_document, derivative_binary, compat
        )
        scene["nodes"].append(node_index)
        node = document["nodes"][node_index]
        extras = dict(node.get("extras") or {})
        extras.update(
            {
                "attachment_id": attachment_id,
                "instance_identity": attachment_id,
                "placement_transform_source": "exact_kfps_wheelstyle_effective_instance_transform",
            }
        )
        node["extras"] = extras
        merged.append(
            {
                "attachment_id": attachment_id,
                "spindle_bone": str(item.get("spindle_bone") or ""),
                "axle": str(item.get("axle") or ""),
                "side": str(item.get("side") or ""),
                "node_index": node_index,
                "mesh_index": mesh_index,
                "source_tire_glb": str(derivative),
                "placement_transform_matrix_row_major": compat["carbin_transform_matrix_row_major"],
            }
        )

    legacy_merge._write_glb(output, document, binary)
    verify, _ = legacy_merge._read_glb(output)
    expected_nodes = len((legacy_merge._read_glb(source)[0].get("nodes") or ())) + len(attachments)
    if len(verify.get("nodes") or ()) < expected_nodes:
        output.unlink(missing_ok=True)
        raise NativeTransformChainError("merged vehicle GLB did not retain every dynamic tire node")
    if _sha256(source) != source_sha:
        output.unlink(missing_ok=True)
        raise NativeTransformChainError("dynamic tire merge modified the source vehicle GLB")
    return {
        "format": "fh6_native_tire_dynamic_glb_merge_v1",
        "status": "dynamic_tire_glb_ready",
        "revision": NATIVE_TRANSFORM_CHAIN_REVISION,
        "source_vehicle_glb": str(source),
        "output_vehicle_glb": str(output),
        "attachment_count": len(attachments),
        "merged_tire_nodes": merged,
        "source_vehicle_glb_unchanged": True,
    }


def _bake_dynamic_tire_nodes(glb_path: Path) -> dict[str, Any]:
    path = glb_path.resolve()
    sha_before = _sha256(path)
    document, binary = legacy_bake._read_glb(path)
    nodes = document.get("nodes") or []
    meshes = document.get("meshes") or []
    if not isinstance(nodes, list) or not isinstance(meshes, list):
        raise NativeTransformChainError("merged GLB has malformed nodes/meshes")
    targets: list[tuple[int, dict[str, Any]]] = []
    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        extras = node.get("extras") or {}
        if isinstance(extras, Mapping) and extras.get("fh6_native_tire_trial") is True:
            targets.append((node_index, node))
    if not targets:
        raise NativeTransformChainError("merged GLB contains no dynamic native tire nodes")

    mesh_indices = [int(node.get("mesh", -1)) for _, node in targets]
    if len(set(mesh_indices)) != len(mesh_indices) or any(index < 0 or index >= len(meshes) for index in mesh_indices):
        raise NativeTransformChainError("dynamic tire nodes must reference unique valid meshes")

    np = legacy_bake.np
    transformed_vertices = 0
    reversed_triangles = 0
    original_matrices: dict[str, list[float]] = {}
    for node_index, node in targets:
        extras = dict(node.get("extras") or {})
        key = str(extras.get("attachment_id") or extras.get("spindle_bone") or f"node_{node_index}")
        original_matrix = [float(value) for value in node.get("matrix") or ()]
        matrix = legacy_bake._glTF_matrix(original_matrix, bone=key)
        original_matrices[key] = original_matrix
        mesh = meshes[int(node["mesh"])]
        if not isinstance(mesh, Mapping):
            raise NativeTransformChainError(f"{key}: referenced tire mesh is invalid")
        primitives = mesh.get("primitives") or ()
        if not isinstance(primitives, Sequence) or not primitives:
            raise NativeTransformChainError(f"{key}: tire mesh has no primitives")
        for primitive in primitives:
            if not isinstance(primitive, Mapping) or int(primitive.get("mode", 4)) != 4:
                raise NativeTransformChainError(f"{key}: tire primitive is not a triangle list")
            attrs = primitive.get("attributes") or {}
            if "POSITION" not in attrs or "indices" not in primitive:
                raise NativeTransformChainError(f"{key}: tire primitive lacks POSITION/indices")
            accessor, start, stride, positions = legacy_bake._float_vec3_accessor(
                document, binary, int(attrs["POSITION"])
            )
            homogeneous = np.concatenate(
                (positions, np.ones((len(positions), 1), dtype=np.float64)), axis=1
            )
            render_positions = (matrix @ homogeneous.T).T[:, :3]
            render_positions[:, 0] *= -1.0
            if not np.isfinite(render_positions).all():
                raise NativeTransformChainError(f"{key}: final tire POSITION contains a non-finite value")
            legacy_bake._write_vec3(binary, start, stride, render_positions)
            if len(render_positions):
                accessor["min"] = [float(value) for value in render_positions.min(axis=0)]
                accessor["max"] = [float(value) for value in render_positions.max(axis=0)]
            transformed_vertices += len(render_positions)
            reversed_triangles += legacy_bake._reverse_triangle_winding(
                document, binary, int(primitive["indices"])
            )
        node.pop("matrix", None)
        extras["fh6_viewer_matrix_baked"] = True
        extras["fh6_viewer_matrix_bake_revision"] = NATIVE_TRANSFORM_CHAIN_REVISION
        extras["fh6_kfps_render_space_reflection_applied"] = True
        extras["fh6_kfps_render_space_rule"] = "(-x,y,z)"
        node["extras"] = extras

    legacy_bake._write_glb(path, document, binary)
    return {
        "format": "fh6_native_tire_dynamic_matrix_bake_v1",
        "status": "dynamic_tire_matrices_baked",
        "revision": NATIVE_TRANSFORM_CHAIN_REVISION,
        "glb_path": str(path),
        "sha256_before": sha_before,
        "sha256_after": _sha256(path),
        "node_count": len(targets),
        "vertex_count": int(transformed_vertices),
        "triangle_winding_reversed_count": int(reversed_triangles),
        "original_effective_matrices": original_matrices,
        "kfps_render_space_rule": "(-x,y,z)",
    }


def _persistent_audit_path(car_id: int) -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) / "FH6GarageAnalyzer" / "preview3d_runtime" if base else Path.home() / ".fh6garageanalyzer" / "preview3d_runtime"
    return root / "diagnostics" / "transform_chain" / f"car_{int(car_id)}" / "kfps_transform_audit.json"


def _write_json_best_effort(path: Path, payload: Mapping[str, Any]) -> str | None:
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(json.dumps(dict(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(path)
        return str(path)
    except (OSError, TypeError, ValueError):
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _try_apply_v5(
    asset: Any,
    *,
    carbin_entry: str,
    game_or_cars_path: str | Path,
    vehicle_glb: str | Path,
    work_root: str | Path,
    converter_diagnostics: Mapping[str, Any] | None = None,
    progress: Callable[[str], None] | None = None,
) -> Any:
    source_glb = Path(vehicle_glb).expanduser().resolve()
    car_id = legacy_integration._car_id(asset)
    if car_id <= 0:
        return legacy_integration._passthrough(
            asset, source_glb, "not_applicable", "vehicle has no valid positive Car ID"
        )

    converter_diag = dict(converter_diagnostics or {})
    trial_root = Path(work_root).expanduser().resolve()
    persistent_manifest = legacy_integration._persistent_diagnostic_manifest_path(car_id)
    stage = "validate_converter_transform_inventory"
    diagnostic: dict[str, Any] = {
        "format": "fh6_native_tire_transform_chain_integration_v1",
        "revision": NATIVE_TRANSFORM_CHAIN_REVISION,
        "status": "in_progress",
        "car_id": car_id,
        "model_code": legacy_integration._model_code(asset),
        "source_vehicle_glb": str(source_glb),
        "selected_vehicle_glb": str(source_glb),
        "carbin_entry": str(carbin_entry),
        "wheel_style_anchor_count": int(converter_diag.get("wheel_style_anchor_count", 0) or 0),
        "wheel_style_anchors": converter_diag.get("wheel_style_anchors"),
        "transform_audit_count": int(converter_diag.get("transform_audit_count", 0) or 0),
        "transform_audit_path": None,
        "geometry_report": None,
        "attachment_contract": None,
        "merge_report": None,
        "viewer_matrix_bake": None,
        "failed_stage": None,
        "error_type": None,
        "error": None,
        "fallback_on_failure": True,
        "four_wheel_assumption": False,
        "aabb_center_used_as_pivot": False,
        "exact_kfps_effective_instance_transform_used": True,
        "native_tire_rigid_bone_transform_applied": True,
    }

    audit_payload = {
        "format": "fh6_kfps_transform_chain_audit_v1",
        "revision": NATIVE_TRANSFORM_CHAIN_REVISION,
        "car_id": car_id,
        "model_code": legacy_integration._model_code(asset),
        "wheel_style_anchors": converter_diag.get("wheel_style_anchors") or [],
        "transform_audit": converter_diag.get("transform_audit") or [],
    }
    audit_path = _write_json_best_effort(_persistent_audit_path(car_id), audit_payload)
    diagnostic["transform_audit_path"] = audit_path

    try:
        anchors = converter_diag.get("wheel_style_anchors")
        if not isinstance(anchors, list) or not anchors:
            raise NativeTransformChainError(
                "exact KFPS WheelStyle transform inventory is unavailable; refusing legacy four-spindle placement"
            )
        if not source_glb.is_file():
            raise FileNotFoundError(f"converted vehicle GLB does not exist: {source_glb}")

        stage = "resolve_stock_wheel_spec"
        database_path = ensure_stock_wheel_database(progress)
        spec = FH6WheelSpecResolver(database_path).resolve(car_id)
        tire_model_name = str(spec.tire_model_name or "").strip()
        if not tire_model_name:
            raise NativeTransformChainError("stock wheel database returned no TireModelName")
        diagnostic["wheel_spec"] = spec.as_dict()
        diagnostic["tire_model_name"] = tire_model_name

        stage = "resolve_tire_archive"
        tire_archive = resolve_tire_archive(game_or_cars_path, tire_model_name)
        diagnostic["tire_archive"] = str(tire_archive)

        stage = "prepare_trial_directory"
        shutil.rmtree(trial_root, ignore_errors=True)
        trial_root.mkdir(parents=True, exist_ok=False)

        stage = "build_native_tire_geometry_with_rigid_bones"
        geometry_report = _build_native_tire_geometry_report(
            spec, tire_archive, trial_root / "tire_geometry"
        )
        diagnostic["geometry_report"] = geometry_report

        stage = "build_dynamic_wheel_attachment_contract"
        contract = _build_dynamic_attachment_contract(car_id, geometry_report, converter_diag)
        diagnostic["attachment_contract"] = contract
        attachment_count = int(contract["attachment_count"])
        diagnostic["attachment_count"] = attachment_count

        stage = "merge_dynamic_tire_glb"
        output_glb = trial_root / f"{source_glb.stem}__native_tires_dynamic.glb"
        merge_report = _merge_dynamic_tires(source_glb, contract, output_glb)
        diagnostic["merge_report"] = merge_report
        diagnostic["selected_vehicle_glb"] = str(output_glb)

        stage = "bake_exact_kfps_wheel_transforms"
        bake_report = _bake_dynamic_tire_nodes(output_glb)
        diagnostic["viewer_matrix_bake"] = bake_report
        if int(bake_report.get("node_count", 0)) != attachment_count:
            raise NativeTransformChainError(
                "dynamic tire matrix bake count does not match resolved WheelStyle instance count"
            )
        if int(bake_report.get("vertex_count", 0)) <= 0 or int(bake_report.get("triangle_winding_reversed_count", 0)) <= 0:
            raise NativeTransformChainError("dynamic tire bake produced no drawable geometry")

        diagnostic.update(
            {
                "status": "stock_native_tire_transform_chain_applied",
                "failed_stage": None,
                "detail": (
                    f"TireModelName={tire_model_name}; dynamic_wheels={attachment_count}; "
                    f"vertices={int(bake_report['vertex_count'])}; "
                    f"triangles={int(bake_report['triangle_winding_reversed_count'])}"
                ),
            }
        )
        temporary_manifest = legacy_integration._write_manifest_best_effort(
            trial_root / "native_tire_preview_integration.json", diagnostic
        )
        persistent = legacy_integration._write_manifest_best_effort(persistent_manifest, diagnostic)
        manifest = persistent or temporary_manifest
        legacy_integration._notify(
            progress,
            f"Native tire transform-chain 적용 완료: {attachment_count} wheel instance(s)",
        )
        return legacy_integration.TirePreviewIntegrationResult(
            status="stock_native_tire_transform_chain_applied",
            revision=NATIVE_TRANSFORM_CHAIN_REVISION,
            car_id=car_id,
            model_code=legacy_integration._model_code(asset),
            source_vehicle_glb=str(source_glb),
            selected_vehicle_glb=str(output_glb),
            applied=True,
            fallback_used=False,
            production_renderer_enabled=False,
            detail=str(diagnostic["detail"]),
            manifest_path=manifest,
        )
    except Exception as exc:
        diagnostic.update(
            {
                "status": "fallback_existing_vehicle_glb",
                "selected_vehicle_glb": str(source_glb),
                "failed_stage": stage,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "detail": f"{type(exc).__name__}: {exc}",
            }
        )
        temporary_manifest = legacy_integration._write_manifest_best_effort(
            trial_root / "native_tire_preview_integration.json", diagnostic
        )
        persistent = legacy_integration._write_manifest_best_effort(persistent_manifest, diagnostic)
        manifest = persistent or temporary_manifest
        legacy_integration._notify(
            progress,
            f"Native tire transform-chain FALLBACK: stage={stage}; {type(exc).__name__}: {exc}",
        )
        return legacy_integration._passthrough(
            asset,
            source_glb,
            "fallback_existing_vehicle_glb",
            f"{type(exc).__name__}: {exc}",
            manifest_path=manifest,
        )


def _make_v5_convert_wrapper(original_convert: Callable[..., Any]) -> Callable[..., Any]:
    def convert_with_native_transform_chain(
        asset: Any,
        progress: Callable[[str], None] | None = None,
        *,
        carbin_entry: str | None = None,
        work_root: str | Path | None = None,
        rim_morph_weights: Any = None,
        converter_override: str | Path | None = None,
    ) -> Any:
        result = original_convert(
            asset,
            progress,
            carbin_entry=carbin_entry,
            work_root=work_root,
            rim_morph_weights=rim_morph_weights,
            converter_override=converter_override,
        )
        if rim_morph_weights is not None or converter_override is not None:
            return result
        car_id = legacy_integration._car_id(asset)
        if car_id <= 0:
            return result
        selected_carbin = str(carbin_entry or "").strip()
        if not selected_carbin:
            entries = tuple(str(item) for item in getattr(asset, "carbin_entries", ()) or ())
            if len(entries) != 1:
                return result
            selected_carbin = entries[0]
        source_archive = Path(getattr(asset, "archive_path")).expanduser().resolve()
        converter_root = (
            Path(work_root).expanduser().resolve()
            if work_root is not None
            else Path(result.output_path).expanduser().resolve().parent
        )
        # Resolve the public entrypoint at call time: production installs the
        # persistent tire cache around the v3 implementation there.
        integration = legacy_integration.try_apply_stock_native_tire_preview(
            asset,
            carbin_entry=selected_carbin,
            game_or_cars_path=source_archive.parent,
            vehicle_glb=result.output_path,
            work_root=converter_root / "native_tire_preview" / f"car_{car_id}",
            converter_diagnostics=dict(getattr(result, "diagnostics", {}) or {}),
            progress=progress,
        )
        result_with_diagnostics = legacy_integration._with_tire_diagnostics(result, integration)
        if not integration.applied:
            return result_with_diagnostics
        return replace(
            result_with_diagnostics,
            output_path=str(Path(integration.selected_vehicle_glb).resolve()),
        )

    convert_with_native_transform_chain.__name__ = getattr(original_convert, "__name__", "convert_vehicle")
    convert_with_native_transform_chain.__doc__ = getattr(original_convert, "__doc__", None)
    return convert_with_native_transform_chain


def _install_verified_helper_for_all_scene_conversions() -> None:
    if hasattr(chassis, _ORIGINAL_HELPER_RESOLVER):
        return
    original = chassis._resolve_converter_helper
    setattr(chassis, _ORIGINAL_HELPER_RESOLVER, original)

    def resolve_helper(progress: Any, rim_morph_weights: Any, converter_override: Any) -> tuple[Path, str]:
        if converter_override is not None:
            return original(progress, rim_morph_weights, converter_override)
        try:
            helper = verified_bundled_wheel_morph_helper()
        except WheelMorphHelperError as exc:
            if rim_morph_weights is not None:
                raise chassis.ChassisConverterError(f"Bundled rim/transform helper is invalid: {exc}") from exc
            helper = None
        if helper is not None:
            return helper, WHEEL_MORPH_HELPER_REVISION
        return original(progress, rim_morph_weights, converter_override)

    chassis._resolve_converter_helper = resolve_helper


def install_native_transform_chain_patch() -> bool:
    if bool(getattr(legacy_integration, _PATCH_MARKER, False)):
        return False
    _install_verified_helper_for_all_scene_conversions()
    legacy_integration.GLOBAL_NATIVE_TIRE_PREVIEW_REVISION = NATIVE_TRANSFORM_CHAIN_REVISION
    legacy_integration.FXX_NATIVE_TIRE_PREVIEW_REVISION = NATIVE_TRANSFORM_CHAIN_REVISION
    legacy_integration.try_apply_stock_native_tire_preview = _try_apply_v5
    legacy_integration.try_apply_validated_fxx_native_tire_preview = _try_apply_v5
    legacy_integration.make_stock_native_tire_convert_wrapper = _make_v5_convert_wrapper
    legacy_integration.make_validated_fxx_tire_convert_wrapper = _make_v5_convert_wrapper
    setattr(legacy_integration, _PATCH_MARKER, True)
    return True


__all__ = [
    "NATIVE_TRANSFORM_CHAIN_REVISION",
    "NativeTransformChainError",
    "install_native_transform_chain_patch",
]
