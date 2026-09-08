from __future__ import annotations

"""Third-generation wheel/tire fit rules based on the rendered WheelStyle frame.

The v2 path fixed native tire rigid-bone handling and dynamic wheel counts, but
still sized every tire only from the stock database.  That can leave a tire
misaligned with the *actual* rim geometry produced by KFPS when a WheelStyle
morph or a model-local pivot differs from the database ideal.

v3 therefore derives, for every dynamic axle, the rim centre, rotation plane and
outer rim diameter from KFPS's own post-morph WheelStyle geometry in instance
local space.  Tire derivatives are then mapped to:

* stock tire width;
* the actual rendered rim/bead diameter;
* stock tire outer diameter;
* the actual rendered rim local centre and axis basis.

No Car ID, model code, wheel count, tire family, fixed offset, scale or rotation
is encoded here.  All placement data comes from the active scene, stock wheel
specification and decoded geometry.
"""

from contextvars import ContextVar
import math
from pathlib import Path
from statistics import median
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
import zipfile

from . import native_transform_chain_patch as v1
from . import native_transform_chain_v2 as v2
from . import tire_preview_integration as legacy_integration
from . import tire_production_trial_geometry as legacy_geometry


NATIVE_TRANSFORM_CHAIN_V3_REVISION = "native_transform_chain_rendered_rim_fit_dynamic_axles_v3"
_PATCH_MARKER = "_fh6_native_transform_chain_rendered_rim_fit_installed"
_DIAGNOSTIC_CONTEXT: ContextVar[Mapping[str, Any] | None] = ContextVar(
    "fh6_native_transform_chain_v3_converter_diagnostics", default=None
)
_BASE_TRY_APPLY = v1._try_apply_v5


class NativeTransformChainV3Error(v2.NativeTransformChainV2Error):
    pass


def _finite_vec3(raw: object, *, label: str) -> tuple[float, float, float]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)) or len(raw) != 3:
        raise NativeTransformChainV3Error(f"{label} must contain exactly three values")
    value = tuple(float(item) for item in raw)
    if not all(math.isfinite(item) for item in value):
        raise NativeTransformChainV3Error(f"{label} contains a non-finite value")
    return value


def _bounds_corners(minimum: Sequence[float], maximum: Sequence[float]) -> list[tuple[float, float, float]]:
    low = _finite_vec3(minimum, label="AABB minimum")
    high = _finite_vec3(maximum, label="AABB maximum")
    return [
        (x, y, z)
        for x in (low[0], high[0])
        for y in (low[1], high[1])
        for z in (low[2], high[2])
    ]


def _wheel_rim_fit(
    identity: str,
    converter_diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    rows = converter_diagnostics.get("transform_audit")
    if not isinstance(rows, list):
        raise NativeTransformChainV3Error(
            "converter diagnostics do not contain transform_audit; rendered rim fitting requires the v3 helper"
        )

    selected: list[tuple[tuple[float, float, float], tuple[float, float, float], int]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("instance_identity") or "") != identity:
            continue
        local_min = row.get("local_aabb_min")
        local_max = row.get("local_aabb_max")
        if local_min is None or local_max is None:
            continue
        low = _finite_vec3(local_min, label=f"{identity} local AABB minimum")
        high = _finite_vec3(local_max, label=f"{identity} local AABB maximum")
        if any(high[axis] <= low[axis] for axis in range(3)):
            continue
        count = int(row.get("vertex_count", 0) or 0)
        if count <= 0:
            continue
        selected.append((low, high, count))

    if not selected:
        raise NativeTransformChainV3Error(
            f"WheelStyle {identity} has no usable instance-local geometry audit"
        )

    minimum = tuple(min(item[0][axis] for item in selected) for axis in range(3))
    maximum = tuple(max(item[1][axis] for item in selected) for axis in range(3))
    corners = _bounds_corners(minimum, maximum)
    axial_axis, radial_axes, axis_report = v2._structural_tire_axes(corners)
    span = tuple(maximum[axis] - minimum[axis] for axis in range(3))
    center = tuple((minimum[axis] + maximum[axis]) * 0.5 for axis in range(3))
    radial_diameter = (span[radial_axes[0]] + span[radial_axes[1]]) * 0.5
    if not math.isfinite(radial_diameter) or radial_diameter <= 0.0:
        raise NativeTransformChainV3Error(f"WheelStyle {identity} has invalid rendered rim diameter")

    return {
        "instance_identity": identity,
        "mesh_count": len(selected),
        "vertex_count": sum(item[2] for item in selected),
        "local_aabb_min": list(minimum),
        "local_aabb_max": list(maximum),
        "local_center": list(center),
        "local_span": list(span),
        "axial_axis": axial_axis,
        "radial_axes": list(radial_axes),
        "rendered_rim_outer_diameter_m": radial_diameter,
        "axis_inference": axis_report["axis_inference"],
        "axis_pair_relative_span_error": axis_report["axis_pair_relative_span_error"],
        "fit_source": "kfps_post_morph_instance_local_wheelstyle_geometry",
    }


def _dynamic_rim_fits(
    classified_anchors: Sequence[Mapping[str, Any]],
    converter_diagnostics: Mapping[str, Any],
) -> dict[int, dict[str, Any]]:
    by_axle: dict[int, list[dict[str, Any]]] = {}
    for anchor in classified_anchors:
        axle_index = int(anchor.get("dynamic_axle_index", -1))
        if axle_index < 0:
            raise NativeTransformChainV3Error("classified WheelStyle anchor has no dynamic axle index")
        identity = str(anchor.get("instance_identity") or "")
        by_axle.setdefault(axle_index, []).append(_wheel_rim_fit(identity, converter_diagnostics))

    output: dict[int, dict[str, Any]] = {}
    for axle_index, fits in sorted(by_axle.items()):
        axial_axes = {int(item["axial_axis"]) for item in fits}
        radial_axes = {tuple(int(axis) for axis in item["radial_axes"]) for item in fits}
        if len(axial_axes) != 1 or len(radial_axes) != 1:
            raise NativeTransformChainV3Error(
                f"dynamic axle {axle_index} WheelStyle instances do not share one local wheel axis basis"
            )
        center = [median(float(item["local_center"][axis]) for item in fits) for axis in range(3)]
        diameter = median(float(item["rendered_rim_outer_diameter_m"]) for item in fits)
        if not math.isfinite(diameter) or diameter <= 0.0:
            raise NativeTransformChainV3Error(f"dynamic axle {axle_index} has invalid rendered rim diameter")
        output[axle_index] = {
            "dynamic_axle_index": axle_index,
            "wheel_count": len(fits),
            "axial_axis": next(iter(axial_axes)),
            "radial_axes": list(next(iter(radial_axes))),
            "local_center": center,
            "rendered_rim_outer_diameter_m": diameter,
            "member_wheels": fits,
            "aggregation": "median_across_same_axle_wheelstyle_instances",
        }
    if not output:
        raise NativeTransformChainV3Error("rendered WheelStyle inventory produced no dynamic rim fits")
    return output


def _rewrite_derivative_to_rim_frame(
    path: Path,
    *,
    source_axial_axis: int,
    source_radial_axes: Sequence[int],
    target_axial_axis: int,
    target_radial_axes: Sequence[int],
    target_center: Sequence[float],
) -> dict[str, Any]:
    source_radial = tuple(int(axis) for axis in source_radial_axes)
    target_radial = tuple(int(axis) for axis in target_radial_axes)
    if sorted((int(source_axial_axis), *source_radial)) != [0, 1, 2]:
        raise NativeTransformChainV3Error("source tire axes are not a permutation of XYZ")
    if sorted((int(target_axial_axis), *target_radial)) != [0, 1, 2]:
        raise NativeTransformChainV3Error("target rim axes are not a permutation of XYZ")
    center = _finite_vec3(target_center, label="target rim local center")

    document, binary = v1.legacy_bake._read_glb(path)
    nodes = document.get("nodes") or []
    meshes = document.get("meshes") or []
    if not isinstance(nodes, list) or not isinstance(meshes, list) or len(meshes) != 1:
        raise NativeTransformChainV3Error("native tire derivative is not the expected single-mesh GLB")
    mesh = meshes[0]
    primitives = mesh.get("primitives") if isinstance(mesh, Mapping) else None
    if not isinstance(primitives, list) or len(primitives) != 1 or not isinstance(primitives[0], Mapping):
        raise NativeTransformChainV3Error("native tire derivative has an unsupported primitive layout")
    attrs = primitives[0].get("attributes")
    position_accessor = attrs.get("POSITION") if isinstance(attrs, Mapping) else None
    if not isinstance(position_accessor, int):
        raise NativeTransformChainV3Error("native tire derivative has no POSITION accessor")

    accessor, start, stride, positions = v1.legacy_bake._float_vec3_accessor(
        document, binary, position_accessor
    )
    np = v1.legacy_bake.np
    remapped = np.zeros_like(positions, dtype=np.float64)
    remapped[:, target_axial_axis] = positions[:, source_axial_axis] + center[target_axial_axis]
    remapped[:, target_radial[0]] = positions[:, source_radial[0]] + center[target_radial[0]]
    remapped[:, target_radial[1]] = positions[:, source_radial[1]] + center[target_radial[1]]
    if not np.isfinite(remapped).all():
        raise NativeTransformChainV3Error("rim-frame tire remap produced a non-finite vertex")
    v1.legacy_bake._write_vec3(binary, start, stride, remapped)
    if len(remapped):
        accessor["min"] = [float(value) for value in remapped.min(axis=0)]
        accessor["max"] = [float(value) for value in remapped.max(axis=0)]
    v1.legacy_bake._write_glb(path, document, binary)
    return {
        "source_axial_axis": int(source_axial_axis),
        "source_radial_axes": list(source_radial),
        "target_axial_axis": int(target_axial_axis),
        "target_radial_axes": list(target_radial),
        "target_local_center": list(center),
        "axis_permutation_applied": (
            int(source_axial_axis) != int(target_axial_axis) or source_radial != target_radial
        ),
        "translation_source": "rendered_rim_instance_local_center",
        "vehicle_specific_offset_applied": False,
    }


def _build_native_tire_geometry_report_v3(
    spec: Any,
    tire_archive: Path,
    output_dir: Path,
) -> dict[str, Any]:
    converter_diagnostics = _DIAGNOSTIC_CONTEXT.get()
    if not isinstance(converter_diagnostics, Mapping):
        raise NativeTransformChainV3Error(
            "converter diagnostic context is unavailable during rendered-rim tire fitting"
        )
    raw_anchors = converter_diagnostics.get("wheel_style_anchors")
    if not isinstance(raw_anchors, list) or not raw_anchors:
        raise NativeTransformChainV3Error("converter returned no WheelStyle anchors")
    classified = v2._classify_dynamic_wheel_anchors_v2(
        [item for item in raw_anchors if isinstance(item, Mapping)]
    )
    rim_fits = _dynamic_rim_fits(classified, converter_diagnostics)

    before_sha = v1._sha256(tire_archive)
    model_name = str(spec.tire_model_name or "").strip()
    with zipfile.ZipFile(tire_archive, "r") as bundle:
        selected = legacy_geometry._select_native_modelbins(bundle, model_name)
    if not selected:
        raise NativeTransformChainV3Error("native tire archive yielded no modelbin candidates")

    dynamic_axles: dict[str, Any] = {}
    for axle_index, rim_fit in sorted(rim_fits.items()):
        stock_axle = "front" if axle_index == 0 else "rear"
        stock_spec = spec.front if stock_axle == "front" else spec.rear
        rendered_rim_diameter = float(rim_fit["rendered_rim_outer_diameter_m"])
        stock_outer = float(stock_spec.tire_outer_diameter_mm) / 1000.0
        if rendered_rim_diameter >= stock_outer:
            raise NativeTransformChainV3Error(
                f"dynamic axle {axle_index} rendered rim diameter {rendered_rim_diameter:g} m "
                f"is not smaller than stock tire outer diameter {stock_outer:g} m"
            )
        proxy = SimpleNamespace(
            axle=f"axle_{axle_index}",
            tire_width_mm=float(stock_spec.tire_width_mm),
            rim_diameter_mm=rendered_rim_diameter * 1000.0,
            tire_outer_diameter_mm=float(stock_spec.tire_outer_diameter_mm),
        )
        modelbins: list[dict[str, Any]] = []
        for entry, source_entry, data in selected:
            derivative = v2._native_modelbin_geometry_v2(
                data,
                entry=entry,
                source_entry=source_entry,
                axle_spec=proxy,
                output_dir=output_dir,
            )
            path = Path(str(derivative.get("glb_path") or "")).resolve()
            frame = _rewrite_derivative_to_rim_frame(
                path,
                source_axial_axis=int(derivative["axial_axis"]),
                source_radial_axes=derivative["radial_axes"],
                target_axial_axis=int(rim_fit["axial_axis"]),
                target_radial_axes=rim_fit["radial_axes"],
                target_center=rim_fit["local_center"],
            )
            derivative = {
                **derivative,
                "dynamic_axle_index": axle_index,
                "stock_spec_axle": stock_axle,
                "target_rim_diameter_source": "kfps_rendered_wheelstyle_geometry",
                "target_rim_diameter_m": rendered_rim_diameter,
                "rim_frame": frame,
                "morph_mode": "rendered_rim_fit_stock_width_outer_v3",
            }
            modelbins.append(derivative)
        dynamic_axles[str(axle_index)] = {
            "dynamic_axle_index": axle_index,
            "stock_spec_axle": stock_axle,
            "target_width_m": float(stock_spec.tire_width_mm) / 1000.0,
            "target_rim_diameter_m": rendered_rim_diameter,
            "target_outer_diameter_m": stock_outer,
            "rim_fit": rim_fit,
            "modelbins": modelbins,
        }

    after_sha = v1._sha256(tire_archive)
    if after_sha != before_sha:
        raise NativeTransformChainV3Error("read-only native tire generation changed the source tire archive")
    report = {
        "format": "fh6_native_tire_geometry_rendered_rim_fit_v3",
        "status": "native_tire_geometry_ready",
        "revision": NATIVE_TRANSFORM_CHAIN_V3_REVISION,
        "car_id": int(spec.car_id),
        "tire_model_name": model_name,
        "archive_path": str(tire_archive),
        "archive_sha256": before_sha,
        "archive_read_only_unchanged": True,
        "dynamic_axles": dynamic_axles,
        "dynamic_axle_count": len(dynamic_axles),
        "wheel_count": len(classified),
        "tire_fit_source": "kfps_rendered_wheelstyle_geometry_plus_stock_tire_dimensions",
        "vehicle_specific_offset_applied": False,
        "family_specific_scale_applied": False,
        "four_wheel_assumption": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "native_tire_geometry_rendered_rim_fit_v3.json").write_text(
        __import__("json").dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def _dynamic_axle_derivatives(
    geometry_report: Mapping[str, Any], dynamic_axle_index: int
) -> dict[str, Mapping[str, Any]]:
    all_axles = geometry_report.get("dynamic_axles")
    payload = all_axles.get(str(dynamic_axle_index)) if isinstance(all_axles, Mapping) else None
    if not isinstance(payload, Mapping):
        raise NativeTransformChainV3Error(
            f"native tire geometry report is missing dynamic axle {dynamic_axle_index}"
        )
    result: dict[str, Mapping[str, Any]] = {}
    for item in payload.get("modelbins") or ():
        if not isinstance(item, Mapping):
            continue
        side = v1._entry_side(str(item.get("entry") or ""))
        if side in ("left", "right") and side not in result:
            result[side] = item
    if not result:
        raise NativeTransformChainV3Error(
            f"native tire geometry report has no derivatives for dynamic axle {dynamic_axle_index}"
        )
    return result


def _select_dynamic_derivative(
    geometry_report: Mapping[str, Any], dynamic_axle_index: int, side: str
) -> tuple[Mapping[str, Any], str]:
    candidates = _dynamic_axle_derivatives(geometry_report, dynamic_axle_index)
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
        raise NativeTransformChainV3Error(
            f"dynamic axle {dynamic_axle_index}/left wheel has only a right tire model; refusing an unproven mirror"
        )
    return next(iter(candidates.values())), "only_native_model_reused_by_exact_wheel_anchor"


def _build_dynamic_attachment_contract_v3(
    car_id: int,
    geometry_report: Mapping[str, Any],
    converter_diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    raw_anchors = converter_diagnostics.get("wheel_style_anchors")
    if not isinstance(raw_anchors, list):
        raise NativeTransformChainV3Error("converter diagnostics do not contain wheel_style_anchors")
    anchors = v2._classify_dynamic_wheel_anchors_v2(
        [item for item in raw_anchors if isinstance(item, Mapping)]
    )
    attachments: list[dict[str, Any]] = []
    for index, anchor in enumerate(anchors):
        dynamic_axle_index = int(anchor["dynamic_axle_index"])
        side = str(anchor["side"])
        derivative, source_mode = _select_dynamic_derivative(
            geometry_report, dynamic_axle_index, side
        )
        path = str(derivative.get("glb_path") or "")
        if not path or not Path(path).is_file():
            raise NativeTransformChainV3Error(
                f"WheelStyle anchor {anchor['instance_identity']} has no usable tire derivative"
            )
        effective = v1._finite_matrix(
            anchor.get("effective_transform_row_major"),
            label=f"{anchor['instance_identity']} effective transform",
        )
        carbin = v1._finite_matrix(
            anchor.get("carbin_transform_row_major"),
            label=f"{anchor['instance_identity']} carbin transform",
        )
        bone = str(anchor.get("bone_name") or "").strip() or f"wheel_instance_{index}"
        attachments.append(
            {
                "attachment_id": str(anchor["instance_identity"]),
                "spindle_bone": bone,
                "axle": str(anchor["stock_spec_axle"]),
                "dynamic_axle_index": dynamic_axle_index,
                "dynamic_axle_count": int(anchor["dynamic_axle_count"]),
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
                "derived_tire_source_side": v1._entry_side(str(derivative.get("entry") or "")),
                "side_source_mode": source_mode,
                "rim_frame": derivative.get("rim_frame"),
                "target_rim_diameter_m": derivative.get("target_rim_diameter_m"),
            }
        )
    if not attachments:
        raise NativeTransformChainV3Error("dynamic WheelStyle inventory contains no tire attachments")
    return {
        "format": "fh6_native_tire_dynamic_wheel_attachment_contract_v3",
        "status": "dynamic_wheel_attachment_contract_ready",
        "revision": NATIVE_TRANSFORM_CHAIN_V3_REVISION,
        "car_id": int(car_id),
        "attachment_part_type": v1.WHEEL_STYLE_PART_TYPE,
        "attachment_count": len(attachments),
        "attachments": attachments,
        "wheel_count_source": "resolved_kfps_wheelstyle_instance_inventory",
        "rim_fit_source": "kfps_post_morph_instance_local_wheelstyle_geometry",
        "four_wheel_assumption": False,
        "exact_kfps_effective_instance_transform_used": True,
        "procedural_translation_applied": False,
        "procedural_rotation_applied": False,
        "vehicle_specific_offset_applied": False,
    }


def _try_apply_v6(*args: Any, **kwargs: Any) -> Any:
    diagnostics = kwargs.get("converter_diagnostics")
    token = _DIAGNOSTIC_CONTEXT.set(
        dict(diagnostics) if isinstance(diagnostics, Mapping) else None
    )
    try:
        return _BASE_TRY_APPLY(*args, **kwargs)
    finally:
        _DIAGNOSTIC_CONTEXT.reset(token)


def install_native_transform_chain_v3() -> bool:
    if bool(getattr(legacy_integration, _PATCH_MARKER, False)):
        return False
    v2.install_native_transform_chain_v2()
    v1._build_native_tire_geometry_report = _build_native_tire_geometry_report_v3
    v1._build_dynamic_attachment_contract = _build_dynamic_attachment_contract_v3
    v1._try_apply_v5 = _try_apply_v6
    v1.NATIVE_TRANSFORM_CHAIN_REVISION = NATIVE_TRANSFORM_CHAIN_V3_REVISION
    legacy_integration.try_apply_stock_native_tire_preview = _try_apply_v6
    legacy_integration.try_apply_validated_fxx_native_tire_preview = _try_apply_v6
    legacy_integration.GLOBAL_NATIVE_TIRE_PREVIEW_REVISION = NATIVE_TRANSFORM_CHAIN_V3_REVISION
    legacy_integration.FXX_NATIVE_TIRE_PREVIEW_REVISION = NATIVE_TRANSFORM_CHAIN_V3_REVISION
    setattr(legacy_integration, _PATCH_MARKER, True)
    return True


__all__ = [
    "NATIVE_TRANSFORM_CHAIN_V3_REVISION",
    "NativeTransformChainV3Error",
    "install_native_transform_chain_v3",
]
