from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence
import zipfile

from .modelbin_morph import (
    MESH_TAG,
    ModelbinMorphError,
    _iter_bundle_blobs,
    apply_weighted_morph,
    parse_modelbin_morph_inventory,
)
from .tire_morph_auto_inference import GENERIC_TIRE_AUTO_INFERENCE_REVISION
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
from .tire_morph_weights import AxleTireMorphWeights
from .tire_production_policy import (
    TireProductionEligibility,
    evaluate_stock_tire_production_candidate,
)
from .wheel_spec import AxleWheelSpec, VehicleWheelSpec


class TireProductionTrialGeometryError(RuntimeError):
    """Raised when native tire geometry cannot be decoded for FHA assembly."""


@dataclass(frozen=True)
class ModelbinProductionTrialGeometry:
    axle: str
    entry: str
    source_entry: str
    modelbin_sha256: str
    selected_mesh_count: int
    morphed_mesh_count: int
    morph_fallback_mesh_count: int
    static_mesh_count: int
    vertex_count: int
    index_count: int
    selector_weights: tuple[float, float, float, float, float]
    scale_x: float
    normalization_scale_xyz: tuple[float, float, float]
    target_width_m: float
    target_outer_diameter_m: float
    morph_mode: str
    pre_normalization_aabb: dict[str, object]
    aabb: dict[str, object]
    glb_path: str | None

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["selector_weights"] = list(self.selector_weights)
        payload["normalization_scale_xyz"] = list(self.normalization_scale_xyz)
        return payload


@dataclass(frozen=True)
class AxleProductionTrialGeometry:
    axle: str
    selector_weights: tuple[float, float, float, float, float]
    scale_x: float
    target_width_m: float
    target_outer_diameter_m: float
    modelbins: tuple[ModelbinProductionTrialGeometry, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "axle": self.axle,
            "selector_weights": list(self.selector_weights),
            "scale_x": self.scale_x,
            "target_width_m": self.target_width_m,
            "target_outer_diameter_m": self.target_outer_diameter_m,
            "modelbins": [item.as_dict() for item in self.modelbins],
        }


@dataclass(frozen=True)
class TireProductionTrialGeometryReport:
    status: str
    eligibility_status: str
    policy_revision: str
    car_id: int
    tire_model_name: str | None
    archive_path: str
    archive_sha256: str
    archive_read_only_unchanged: bool
    output_dir: str
    manifest_path: str
    front: AxleProductionTrialGeometry
    rear: AxleProductionTrialGeometry
    derived_geometry_only: bool
    trial_renderer_input_ready: bool
    production_renderer_enabled: bool
    spindle_attachment_enabled: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "fh6_native_tire_production_trial_geometry_v1",
            "status": self.status,
            "eligibility_status": self.eligibility_status,
            "policy_revision": self.policy_revision,
            "car_id": self.car_id,
            "tire_model_name": self.tire_model_name,
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "archive_read_only_unchanged": self.archive_read_only_unchanged,
            "output_dir": self.output_dir,
            "manifest_path": self.manifest_path,
            "front": self.front.as_dict(),
            "rear": self.rear.as_dict(),
            "derived_geometry_only": self.derived_geometry_only,
            "trial_renderer_input_ready": self.trial_renderer_input_ready,
            "production_renderer_enabled": self.production_renderer_enabled,
            "spindle_attachment_enabled": self.spindle_attachment_enabled,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_eligible(
    spec: VehicleWheelSpec,
    archive: Path,
) -> TireProductionEligibility:
    eligibility = evaluate_stock_tire_production_candidate(spec, archive)
    if not eligibility.production_trial_eligible or eligibility.weights is None:
        raise TireProductionTrialGeometryError(
            f"native tire production blocked: {eligibility.status}: {eligibility.detail}"
        )
    return eligibility


def _safe_stem(entry: str) -> str:
    return Path(entry.replace("\\", "/")).stem


def _canonical_side_entry(model_name: str, side: str) -> str:
    prefix = "tireL" if side == "left" else "tireR"
    safe_model = model_name or "auto"
    return f"{prefix}_{safe_model}.modelbin"


def _select_native_modelbins(
    bundle: zipfile.ZipFile,
    model_name: str,
) -> tuple[tuple[str, str, bytes], ...]:
    """Select tire modelbins without any family-specific table.

    Exact tireL_/tireR_ names linked to TireModelName are preferred.  Otherwise a
    generic tireL_/tireR_ pair is used.  If the archive exposes no side label, the
    first modelbin becomes the canonical left source and native right-spindle
    transforms reuse it, matching the existing single-left assembly contract.
    """
    entries = sorted(
        (
            item
            for item in bundle.infolist()
            if not item.is_dir() and item.filename.casefold().endswith(".modelbin")
        ),
        key=lambda item: item.filename.casefold(),
    )
    if not entries:
        raise TireProductionTrialGeometryError("native tire archive contains no modelbin")

    wanted_left = f"tirel_{model_name}.modelbin".casefold()
    wanted_right = f"tirer_{model_name}.modelbin".casefold()

    exact_left = [item for item in entries if Path(item.filename).name.casefold() == wanted_left]
    exact_right = [item for item in entries if Path(item.filename).name.casefold() == wanted_right]
    generic_left = [
        item for item in entries if Path(item.filename).stem.casefold().startswith("tirel_")
    ]
    generic_right = [
        item for item in entries if Path(item.filename).stem.casefold().startswith("tirer_")
    ]

    left = exact_left[0] if exact_left else (generic_left[0] if generic_left else None)
    right = exact_right[0] if exact_right else (generic_right[0] if generic_right else None)

    selected: list[tuple[str, str, bytes]] = []
    if left is not None:
        selected.append(
            (
                _canonical_side_entry(model_name, "left"),
                left.filename.replace("\\", "/"),
                bundle.read(left),
            )
        )
    if right is not None:
        selected.append(
            (
                _canonical_side_entry(model_name, "right"),
                right.filename.replace("\\", "/"),
                bundle.read(right),
            )
        )
    if selected:
        return tuple(selected)

    # No explicit side identity: use one native geometry source as canonical left.
    # The existing WheelStyle spindle matrices provide left/right placement.
    first = entries[0]
    return (
        (
            _canonical_side_entry(model_name, "left"),
            first.filename.replace("\\", "/"),
            bundle.read(first),
        ),
    )


def _normalize_positions_to_stock_dimensions(
    positions: Sequence[Sequence[float]],
    axle_spec: AxleWheelSpec,
) -> tuple[
    tuple[tuple[float, float, float], ...],
    tuple[float, float, float],
    dict[str, object],
    dict[str, object],
]:
    try:
        before = _aabb(positions)
    except TireMorphGeometryError as exc:
        raise TireProductionTrialGeometryError(str(exc)) from exc

    target_width = float(axle_spec.tire_width_mm) / 1000.0
    target_outer = float(axle_spec.tire_outer_diameter_mm) / 1000.0
    spans = tuple(float(value) for value in before.span)
    if not all(math.isfinite(value) and value > 1.0e-9 for value in spans):
        raise TireProductionTrialGeometryError(
            f"{axle_spec.axle}: decoded tire geometry has invalid span {spans!r}"
        )
    if not all(math.isfinite(value) and value > 0.0 for value in (target_width, target_outer)):
        raise TireProductionTrialGeometryError(
            f"{axle_spec.axle}: stock tire target dimensions are invalid"
        )

    sx = target_width / spans[0]
    sy = target_outer / spans[1]
    sz = target_outer / spans[2]
    scales = (sx, sy, sz)
    if not all(math.isfinite(value) and value > 0.0 for value in scales):
        raise TireProductionTrialGeometryError(
            f"{axle_spec.axle}: automatic tire normalization produced invalid scale {scales!r}"
        )

    cx, cy, cz = (float(value) for value in before.center)
    normalized = tuple(
        (
            cx + (float(point[0]) - cx) * sx,
            cy + (float(point[1]) - cy) * sy,
            cz + (float(point[2]) - cz) * sz,
        )
        for point in positions
    )
    try:
        after = _aabb(normalized)
    except TireMorphGeometryError as exc:
        raise TireProductionTrialGeometryError(str(exc)) from exc
    return normalized, scales, before.as_dict(), after.as_dict()


def _build_modelbin_geometry(
    data: bytes,
    *,
    entry: str,
    source_entry: str,
    axle_spec: AxleWheelSpec,
    weights: AxleTireMorphWeights,
    output_dir: Path,
    write_glb: bool,
) -> ModelbinProductionTrialGeometry:
    try:
        _bundle_major, _bundle_minor, blobs = _iter_bundle_blobs(data)
        index_blobs = [blob for blob in blobs if blob.tag == INDEX_BUFFER_TAG]
        if not index_blobs:
            raise TireProductionTrialGeometryError(f"{source_entry}: modelbin has no IndB")
        index_raw, _index_stride = _parse_global_indices(data, index_blobs[0])
        layouts = tuple(
            _parse_layout(data, blob)
            for blob in blobs
            if blob.tag in (VERTEX_LAYOUT_TAG, INPUT_LAYOUT_TAG)
        )
        buffers = tuple(
            _parse_vertex_buffer(data, blob)
            for blob in blobs
            if blob.tag == VERTEX_BUFFER_TAG
        )
        by_buffer_blob = {item.blob_index: item for item in buffers}
        meshes = tuple(_parse_mesh(data, blob) for blob in blobs if blob.tag == MESH_TAG)
        inventory = parse_modelbin_morph_inventory(data)
    except (ModelbinMorphError, TireMorphGeometryError) as exc:
        raise TireProductionTrialGeometryError(f"{source_entry}: {exc}") from exc

    morph_buffers = {item.blob_index: item for item in inventory.morph_buffers}
    morph_resolutions = {item.mesh_blob_index: item for item in inventory.resolutions}
    aggregate_positions: list[tuple[float, float, float]] = []
    aggregate_indices: list[int] = []
    selected_mesh_count = 0
    morphed_mesh_count = 0
    morph_fallback_mesh_count = 0
    static_mesh_count = 0

    # Only measured file-driven inference is allowed to deform the source mesh.
    # If inference was unavailable, the native base geometry is retained and the
    # final stock-dimension normalization below supplies the universal fallback.
    use_inferred_morph = str(weights.mapping_revision) == GENERIC_TIRE_AUTO_INFERENCE_REVISION

    for mesh in meshes:
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
        except TireMorphGeometryError as exc:
            raise TireProductionTrialGeometryError(
                f"{source_entry}: mesh {mesh.blob_index}: {exc}"
            ) from exc

        selected_mesh_count += 1
        positions: Sequence[Sequence[float]] = base_positions
        attempted_weighted = mesh.morph_target_count > 0 and not mesh.is_morph_damage
        if attempted_weighted and use_inferred_morph and mesh.morph_target_count == 5:
            resolution = morph_resolutions.get(mesh.blob_index)
            morph_buffer = (
                morph_buffers.get(resolution.morph_buffer_blob_index)
                if resolution is not None and resolution.morph_buffer_blob_index is not None
                else None
            )
            if morph_buffer is not None:
                try:
                    positions, _ = apply_weighted_morph(
                        base_positions,
                        morph_buffer,
                        mesh.indexed_vertex_offset,
                        mesh.morph_target_count,
                        weights.selector_weights,
                        min_vertex_index=min_index,
                    )
                    morphed_mesh_count += 1
                except ModelbinMorphError:
                    positions = base_positions
                    morph_fallback_mesh_count += 1
            else:
                morph_fallback_mesh_count += 1
        elif attempted_weighted:
            morph_fallback_mesh_count += 1
        else:
            static_mesh_count += 1

        try:
            compact_positions, compact_indices = _compact_geometry(
                positions, source_indices, min_index
            )
        except TireMorphGeometryError as exc:
            raise TireProductionTrialGeometryError(
                f"{source_entry}: mesh {mesh.blob_index}: {exc}"
            ) from exc
        vertex_base = len(aggregate_positions)
        aggregate_positions.extend(compact_positions)
        aggregate_indices.extend(vertex_base + index for index in compact_indices)

    if not aggregate_positions or not aggregate_indices or selected_mesh_count <= 0:
        raise TireProductionTrialGeometryError(
            f"{source_entry}: modelbin has no decodable LOD0 tire geometry"
        )

    normalized_positions, scales, before_aabb, after_aabb = _normalize_positions_to_stock_dimensions(
        aggregate_positions,
        axle_spec,
    )

    glb_path: str | None = None
    if write_glb:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{axle_spec.axle}__{_safe_stem(entry)}__stock_auto.glb"
        try:
            path.write_bytes(_glb_bytes(normalized_positions, aggregate_indices))
        except (OSError, TireMorphGeometryError) as exc:
            raise TireProductionTrialGeometryError(
                f"could not write derived {axle_spec.axle} tire GLB for {source_entry}: {exc}"
            ) from exc
        glb_path = str(path)

    morph_mode = (
        "measured_selector_morph_plus_stock_dimension_normalization"
        if morphed_mesh_count > 0
        else "native_base_geometry_plus_stock_dimension_normalization"
    )
    return ModelbinProductionTrialGeometry(
        axle=str(axle_spec.axle),
        entry=entry.replace("\\", "/"),
        source_entry=source_entry.replace("\\", "/"),
        modelbin_sha256=hashlib.sha256(data).hexdigest(),
        selected_mesh_count=selected_mesh_count,
        morphed_mesh_count=morphed_mesh_count,
        morph_fallback_mesh_count=morph_fallback_mesh_count,
        static_mesh_count=static_mesh_count,
        vertex_count=len(normalized_positions),
        index_count=len(aggregate_indices),
        selector_weights=weights.selector_weights,
        scale_x=float(scales[0]),
        normalization_scale_xyz=scales,
        target_width_m=float(axle_spec.tire_width_mm) / 1000.0,
        target_outer_diameter_m=float(axle_spec.tire_outer_diameter_mm) / 1000.0,
        morph_mode=morph_mode,
        pre_normalization_aabb=before_aabb,
        aabb=after_aabb,
        glb_path=glb_path,
    )


def _build_axle(
    modelbins: Sequence[tuple[str, str, bytes]],
    *,
    axle_spec: AxleWheelSpec,
    weights: AxleTireMorphWeights,
    output_dir: Path,
    write_glb: bool,
) -> AxleProductionTrialGeometry:
    reports = tuple(
        _build_modelbin_geometry(
            data,
            entry=logical_entry,
            source_entry=source_entry,
            axle_spec=axle_spec,
            weights=weights,
            output_dir=output_dir,
            write_glb=write_glb,
        )
        for logical_entry, source_entry, data in modelbins
    )
    scale_x = reports[0].scale_x if reports else 1.0
    return AxleProductionTrialGeometry(
        axle=str(axle_spec.axle),
        selector_weights=weights.selector_weights,
        scale_x=float(scale_x),
        target_width_m=float(axle_spec.tire_width_mm) / 1000.0,
        target_outer_diameter_m=float(axle_spec.tire_outer_diameter_mm) / 1000.0,
        modelbins=reports,
    )


def build_stock_tire_production_trial_geometry(
    spec: VehicleWheelSpec,
    archive_path: str | Path,
    output_dir: str | Path,
    *,
    write_glb: bool = True,
) -> TireProductionTrialGeometryReport:
    """Build stock tire geometry for every decodable native tire archive.

    Tire selection is automatic from the stock DB's TireModelName.  The native ZIP
    stays read-only.  Family-specific whitelists are not used.  Measured selector
    inference is used when available; otherwise native base geometry is retained.
    In both cases the final decoded geometry is centered and normalized directly to
    the stock width and outer diameter before attachment to native WheelStyle spindles.
    """
    archive = Path(archive_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    eligibility = _require_eligible(spec, archive)
    weights = eligibility.weights
    assert weights is not None

    before = _sha256(archive)
    if eligibility.archive_sha256 is not None and before != eligibility.archive_sha256:
        raise TireProductionTrialGeometryError(
            "native tire archive changed after automatic recognition"
        )

    model_name = str(spec.tire_model_name or "").strip()
    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            modelbins = _select_native_modelbins(bundle, model_name)
    except (OSError, zipfile.BadZipFile) as exc:
        raise TireProductionTrialGeometryError(
            f"could not read native tire archive: {exc}"
        ) from exc

    destination.mkdir(parents=True, exist_ok=True)
    front = _build_axle(
        modelbins,
        axle_spec=spec.front,
        weights=weights.front,
        output_dir=destination,
        write_glb=write_glb,
    )
    rear = _build_axle(
        modelbins,
        axle_spec=spec.rear,
        weights=weights.rear,
        output_dir=destination,
        write_glb=write_glb,
    )

    after = _sha256(archive)
    if before != after:
        raise TireProductionTrialGeometryError(
            "read-only global tire generation changed the native tire archive"
        )

    manifest_path = destination / "native_tire_production_trial_geometry.json"
    report = TireProductionTrialGeometryReport(
        status="production_trial_geometry_ready",
        eligibility_status=eligibility.status,
        policy_revision=eligibility.policy_revision,
        car_id=int(spec.car_id),
        tire_model_name=spec.tire_model_name,
        archive_path=str(archive),
        archive_sha256=before,
        archive_read_only_unchanged=True,
        output_dir=str(destination),
        manifest_path=str(manifest_path),
        front=front,
        rear=rear,
        derived_geometry_only=True,
        trial_renderer_input_ready=True,
        production_renderer_enabled=False,
        spindle_attachment_enabled=False,
    )
    try:
        manifest_path.write_text(
            json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise TireProductionTrialGeometryError(
            f"could not write production tire manifest: {exc}"
        ) from exc
    return report
