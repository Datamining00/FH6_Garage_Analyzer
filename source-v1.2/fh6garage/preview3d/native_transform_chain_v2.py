from __future__ import annotations

"""Second-generation native wheel/tire assembly rules.

This layer removes two assumptions that remained in the first native transform
chain implementation:

* a native tire model origin is not assumed to be the wheel centre; the tire's
  rotational geometry is identified from the decoded model itself and mapped to
  the stock width, bead/rim diameter and outer diameter around its structural
  centreline;
* a vehicle is not reduced to a front/rear wheel pair.  Actual WheelStyle
  instances are paired by side/longitudinal position into an ordered dynamic
  axle inventory while the existing front/rear database schema remains only the
  source of stock dimensions.

No Car ID, model code, tire family, fixed translation/rotation, or additional
spindle name is part of these rules.
"""

import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from . import native_transform_chain_patch as v1
from . import tire_preview_integration as legacy_integration
from .modelbin_morph import MESH_TAG, _iter_bundle_blobs
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
    _resolve_layout,
)


NATIVE_TRANSFORM_CHAIN_V2_REVISION = "native_transform_chain_structural_tire_dynamic_axles_v2"
_PATCH_MARKER = "_fh6_native_transform_chain_structural_tire_dynamic_axles_installed"


class NativeTransformChainV2Error(v1.NativeTransformChainError):
    pass


def _structural_tire_axes(
    positions: Sequence[Sequence[float]],
) -> tuple[int, tuple[int, int], dict[str, Any]]:
    """Infer axial/radial axes from rotational symmetry of the decoded geometry.

    The two axes with the most nearly equal spans define the radial plane.  A
    numerically tied result is rejected instead of selecting an arbitrary axis.
    """
    bounds = _aabb(positions)
    spans = tuple(float(value) for value in bounds.span)
    if not all(math.isfinite(value) and value > 0.0 for value in spans):
        raise NativeTransformChainV2Error(f"invalid tire geometry span {spans!r}")

    candidates: list[tuple[float, tuple[int, int]]] = []
    for first, second in ((0, 1), (0, 2), (1, 2)):
        scale = max(spans[first], spans[second])
        candidates.append((abs(spans[first] - spans[second]) / scale, (first, second)))
    candidates.sort(key=lambda item: item[0])
    best_score, radial_axes = candidates[0]
    second_score = candidates[1][0]
    numeric_tie = 64.0 * sys.float_info.epsilon * max(1.0, abs(best_score), abs(second_score))
    if abs(second_score - best_score) <= numeric_tie:
        raise NativeTransformChainV2Error(
            "tire rotational axes are numerically ambiguous; refusing an arbitrary axis choice"
        )
    axial_axis = next(axis for axis in range(3) if axis not in radial_axes)
    return axial_axis, radial_axes, {
        "axial_axis": axial_axis,
        "radial_axes": list(radial_axes),
        "axis_inference": "closest_pair_of_geometry_spans",
        "axis_pair_relative_span_error": best_score,
        "source_span_xyz": list(spans),
    }


def _map_annular_tire_to_stock(
    positions: Sequence[Sequence[float]],
    axle_spec: Any,
) -> tuple[list[tuple[float, float, float]], dict[str, Any]]:
    """Map a decoded tire annulus to stock width, bead diameter and outer diameter."""
    if not positions:
        raise NativeTransformChainV2Error("cannot map an empty tire geometry")

    axial_axis, radial_axes, axis_report = _structural_tire_axes(positions)
    before = _aabb(positions)
    minimum = tuple(float(value) for value in before.minimum)
    maximum = tuple(float(value) for value in before.maximum)
    axial_center = (minimum[axial_axis] + maximum[axial_axis]) * 0.5
    axial_span = maximum[axial_axis] - minimum[axial_axis]
    radial_center = (
        (minimum[radial_axes[0]] + maximum[radial_axes[0]]) * 0.5,
        (minimum[radial_axes[1]] + maximum[radial_axes[1]]) * 0.5,
    )

    radii: list[float] = []
    for point in positions:
        u = float(point[radial_axes[0]]) - radial_center[0]
        w = float(point[radial_axes[1]]) - radial_center[1]
        radius = math.hypot(u, w)
        if not math.isfinite(radius):
            raise NativeTransformChainV2Error("tire geometry contains a non-finite radial coordinate")
        radii.append(radius)
    source_inner = min(radii)
    source_outer = max(radii)
    radial_span = source_outer - source_inner

    target_width = float(axle_spec.tire_width_mm) / 1000.0
    target_inner = float(axle_spec.rim_diameter_mm) / 2000.0
    target_outer = float(axle_spec.tire_outer_diameter_mm) / 2000.0
    if not all(math.isfinite(value) and value > 0.0 for value in (axial_span, source_inner, radial_span)):
        raise NativeTransformChainV2Error(
            f"decoded tire has invalid structural dimensions: axial={axial_span!r}, "
            f"inner_radius={source_inner!r}, radial_span={radial_span!r}"
        )
    if not all(math.isfinite(value) and value > 0.0 for value in (target_width, target_inner, target_outer)):
        raise NativeTransformChainV2Error("stock wheel database returned invalid tire/rim dimensions")
    if target_inner >= target_outer:
        raise NativeTransformChainV2Error(
            f"stock rim radius {target_inner:g} is not smaller than tire outer radius {target_outer:g}"
        )

    mapped: list[tuple[float, float, float]] = []
    for point, radius in zip(positions, radii):
        if radius <= 0.0:
            raise NativeTransformChainV2Error(
                "decoded tire contains a vertex on the inferred rotation axis; annular mapping is undefined"
            )
        values = [float(point[0]), float(point[1]), float(point[2])]
        values[axial_axis] = (
            (values[axial_axis] - axial_center) * target_width / axial_span
        )
        normalized_radius = (radius - source_inner) / radial_span
        target_radius = target_inner + normalized_radius * (target_outer - target_inner)
        radial_scale = target_radius / radius
        values[radial_axes[0]] = (
            (values[radial_axes[0]] - radial_center[0]) * radial_scale
        )
        values[radial_axes[1]] = (
            (values[radial_axes[1]] - radial_center[1]) * radial_scale
        )
        if not all(math.isfinite(value) for value in values):
            raise NativeTransformChainV2Error("stock annular mapping produced a non-finite tire vertex")
        mapped.append((values[0], values[1], values[2]))

    after = _aabb(mapped)
    after_min = tuple(float(value) for value in after.minimum)
    after_max = tuple(float(value) for value in after.maximum)
    after_axial_center = (after_min[axial_axis] + after_max[axial_axis]) * 0.5
    after_axial_span = after_max[axial_axis] - after_min[axial_axis]
    mapped_radii = [
        math.hypot(float(point[radial_axes[0]]), float(point[radial_axes[1]]))
        for point in mapped
    ]
    mapped_inner = min(mapped_radii)
    mapped_outer = max(mapped_radii)
    numeric_abs = max(1.0e-9, 128.0 * sys.float_info.epsilon * max(target_width, target_outer))
    if not math.isclose(after_axial_center, 0.0, rel_tol=0.0, abs_tol=numeric_abs):
        raise NativeTransformChainV2Error(
            f"mapped tire axial centre is not at the wheel origin: {after_axial_center!r}"
        )
    if not math.isclose(after_axial_span, target_width, rel_tol=1.0e-9, abs_tol=numeric_abs):
        raise NativeTransformChainV2Error("mapped tire width does not match the stock width")
    if not math.isclose(mapped_inner, target_inner, rel_tol=1.0e-9, abs_tol=numeric_abs):
        raise NativeTransformChainV2Error("mapped tire bead radius does not match the stock rim radius")
    if not math.isclose(mapped_outer, target_outer, rel_tol=1.0e-9, abs_tol=numeric_abs):
        raise NativeTransformChainV2Error("mapped tire outer radius does not match the stock outer radius")

    report = {
        **axis_report,
        "geometry_mapping_mode": "structure_inferred_annular_stock_mapping",
        "pre_mapping_aabb": before.as_dict(),
        "aabb": after.as_dict(),
        "source_axial_center": axial_center,
        "source_radial_center": list(radial_center),
        "source_inner_diameter_m": source_inner * 2.0,
        "source_outer_diameter_m": source_outer * 2.0,
        "target_width_m": target_width,
        "target_inner_diameter_m": target_inner * 2.0,
        "target_outer_diameter_m": target_outer * 2.0,
        "mapped_axial_center": after_axial_center,
        "mapped_inner_diameter_m": mapped_inner * 2.0,
        "mapped_outer_diameter_m": mapped_outer * 2.0,
        "vehicle_specific_offset_applied": False,
        "family_specific_scale_applied": False,
        "aabb_center_used_as_pivot": False,
    }
    return mapped, report


def _native_modelbin_geometry_v2(
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
            raise NativeTransformChainV2Error(f"{source_entry}: modelbin has no IndB")
        index_raw, _index_stride = _parse_global_indices(data, index_blobs[0])
        layouts = tuple(
            _parse_layout(data, blob)
            for blob in blobs
            if blob.tag in (VERTEX_LAYOUT_TAG, INPUT_LAYOUT_TAG)
        )
        buffers = tuple(
            _parse_vertex_buffer(data, blob) for blob in blobs if blob.tag == VERTEX_BUFFER_TAG
        )
        by_buffer_blob = {item.blob_index: item for item in buffers}
        mesh_pairs = tuple((blob, _parse_mesh(data, blob)) for blob in blobs if blob.tag == MESH_TAG)
        skeleton = v1._parse_native_skeleton(data, blobs)
        bone_worlds = v1._bone_world_matrices(skeleton)
    except (TireMorphGeometryError, v1.NativeTransformChainError) as exc:
        raise NativeTransformChainV2Error(f"{source_entry}: {exc}") from exc

    aggregate_model: list[tuple[float, float, float]] = []
    aggregate_indices: list[int] = []
    rigid_indices: list[int] = []
    rigid_names: list[str] = []
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
            raise NativeTransformChainV2Error(
                f"{source_entry}: mesh {mesh.blob_index}: {exc}"
            ) from exc

        rigid_index = v1._mesh_rigid_bone_index(data, blob)
        if 0 <= rigid_index < len(bone_worlds):
            rigid_world = bone_worlds[rigid_index]
            rigid_name = skeleton[rigid_index][0]
        else:
            rigid_world = v1._identity_matrix()
            rigid_name = ""
        rigid_indices.append(rigid_index)
        rigid_names.append(rigid_name)

        start = len(aggregate_model)
        if rigid_world == v1._identity_matrix():
            model_positions = [tuple(map(float, point)) for point in compact_positions]
        else:
            model_positions = [v1._transform_point_row(point, rigid_world) for point in compact_positions]
        aggregate_model.extend(model_positions)
        aggregate_indices.extend(start + int(index) for index in compact_indices)
        selected_mesh_count += 1

    if not aggregate_model or not aggregate_indices or selected_mesh_count <= 0:
        raise NativeTransformChainV2Error(f"{source_entry}: modelbin has no decodable LOD0 tire geometry")

    final_positions, mapping = _map_annular_tire_to_stock(aggregate_model, axle_spec)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = Path(entry.replace("\\", "/")).stem
    glb_path = output_dir / f"{axle_spec.axle}__{safe_stem}__native_chain_v2.glb"
    try:
        glb_path.write_bytes(_glb_bytes(final_positions, aggregate_indices))
    except (OSError, TireMorphGeometryError) as exc:
        raise NativeTransformChainV2Error(
            f"could not write native tire derivative {glb_path}: {exc}"
        ) from exc

    return {
        "axle": str(axle_spec.axle),
        "entry": entry.replace("\\", "/"),
        "source_entry": source_entry.replace("\\", "/"),
        "selected_mesh_count": selected_mesh_count,
        "vertex_count": len(final_positions),
        "index_count": len(aggregate_indices),
        "target_width_m": float(axle_spec.tire_width_mm) / 1000.0,
        "target_rim_diameter_m": float(axle_spec.rim_diameter_mm) / 1000.0,
        "target_outer_diameter_m": float(axle_spec.tire_outer_diameter_mm) / 1000.0,
        "rigid_bone_indices": rigid_indices,
        "rigid_bone_names": rigid_names,
        "native_rigid_bone_transform_applied": True,
        "native_origin_preserved": False,
        "aabb_center_used_as_pivot": False,
        "morph_mode": "structural_annular_stock_width_bead_outer",
        "glb_path": str(glb_path),
        **mapping,
    }


def _wheel_side(anchor: Mapping[str, Any]) -> tuple[str, str]:
    named = v1._named_side(str(anchor.get("bone_name") or ""))
    if named is not None:
        return named, "bone_name"
    matrix = v1._finite_matrix(
        anchor.get("carbin_transform_row_major"),
        label=f"{anchor.get('instance_identity', '<wheel>')} carbin transform",
    )
    x = float(matrix[12])
    zero_tolerance = 64.0 * math.ulp(max(1.0, abs(x)))
    if abs(x) <= zero_tolerance:
        return "center", "carbin_lateral_center"
    return ("left", "carbin_lateral_sign") if x < 0.0 else ("right", "carbin_lateral_sign")


def _dynamic_axle_clusters(anchors: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Form physical axle groups by minimum longitudinal left/right pairing."""
    left = [item for item in anchors if item["_side"] == "left"]
    right = [item for item in anchors if item["_side"] == "right"]
    center = [item for item in anchors if item["_side"] == "center"]
    clusters: list[list[dict[str, Any]]] = []

    remaining_left = list(left)
    remaining_right = list(right)
    while remaining_left and remaining_right:
        distance, li, ri = min(
            (
                (abs(float(l["_z"]) - float(r["_z"])), l_index, r_index)
                for l_index, l in enumerate(remaining_left)
                for r_index, r in enumerate(remaining_right)
            ),
            key=lambda item: item[0],
        )
        del distance
        l = remaining_left.pop(li)
        r = remaining_right.pop(ri)
        clusters.append([l, r])
    clusters.extend([[item] for item in remaining_left])
    clusters.extend([[item] for item in remaining_right])
    clusters.extend([[item] for item in center])
    clusters.sort(key=lambda group: -sum(float(item["_z"]) for item in group) / len(group))
    return clusters


def _classify_dynamic_wheel_anchors_v2(
    raw_anchors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_anchors):
        identity = str(raw.get("instance_identity") or "").strip()
        if not identity:
            raise NativeTransformChainV2Error(f"WheelStyle anchor {index} has no instance_identity")
        if identity in seen:
            raise NativeTransformChainV2Error(f"duplicate WheelStyle anchor identity: {identity}")
        seen.add(identity)
        carbin = v1._finite_matrix(raw.get("carbin_transform_row_major"), label=f"{identity} carbin transform")
        effective = v1._finite_matrix(raw.get("effective_transform_row_major"), label=f"{identity} effective transform")
        normalized = {
            **dict(raw),
            "instance_identity": identity,
            "carbin_transform_row_major": list(carbin),
            "effective_transform_row_major": list(effective),
            "_z": float(carbin[14]),
        }
        side, side_inference = _wheel_side(normalized)
        normalized["_side"] = side
        normalized["_side_inference"] = side_inference
        anchors.append(normalized)
    if not anchors:
        raise NativeTransformChainV2Error(
            "KFPS converter returned no resolved WheelStyle anchors; exact rim/tire transform parity cannot be proven"
        )

    clusters = _dynamic_axle_clusters(anchors)
    axle_count = len(clusters)
    if axle_count <= 0:
        raise NativeTransformChainV2Error("dynamic WheelStyle inventory formed no axle groups")
    by_identity: dict[str, tuple[int, int]] = {}
    for axle_index, group in enumerate(clusters):
        for item in group:
            by_identity[str(item["instance_identity"])] = (axle_index, axle_count)

    classified: list[dict[str, Any]] = []
    for item in anchors:
        axle_index, count = by_identity[str(item["instance_identity"])]
        stock_spec_axle = "front" if axle_index == 0 else "rear"
        classified.append(
            {
                **{key: value for key, value in item.items() if not key.startswith("_")},
                "axle": stock_spec_axle,
                "dynamic_axle_index": axle_index,
                "dynamic_axle_count": count,
                "stock_spec_axle": stock_spec_axle,
                "axle_inference": "wheelstyle_longitudinal_left_right_pairing",
                "side": item["_side"],
                "side_inference": item["_side_inference"],
            }
        )
    return classified


def install_native_transform_chain_v2() -> bool:
    """Install v1 integration once, then replace only structural tire/topology rules."""
    if bool(getattr(legacy_integration, _PATCH_MARKER, False)):
        return False
    v1.install_native_transform_chain_patch()
    v1._native_modelbin_geometry = _native_modelbin_geometry_v2
    v1._classify_dynamic_wheel_anchors = _classify_dynamic_wheel_anchors_v2
    v1.NATIVE_TRANSFORM_CHAIN_REVISION = NATIVE_TRANSFORM_CHAIN_V2_REVISION
    legacy_integration.GLOBAL_NATIVE_TIRE_PREVIEW_REVISION = NATIVE_TRANSFORM_CHAIN_V2_REVISION
    legacy_integration.FXX_NATIVE_TIRE_PREVIEW_REVISION = NATIVE_TRANSFORM_CHAIN_V2_REVISION
    setattr(legacy_integration, _PATCH_MARKER, True)
    return True


__all__ = [
    "NATIVE_TRANSFORM_CHAIN_V2_REVISION",
    "NativeTransformChainV2Error",
    "install_native_transform_chain_v2",
]
