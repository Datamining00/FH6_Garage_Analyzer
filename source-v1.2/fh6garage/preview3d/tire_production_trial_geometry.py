from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
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
from .wheel_spec import VehicleWheelSpec


class TireProductionTrialGeometryError(RuntimeError):
    """Raised when the gated native tire production-trial geometry cannot be built."""


@dataclass(frozen=True)
class ModelbinProductionTrialGeometry:
    axle: str
    entry: str
    modelbin_sha256: str
    selected_mesh_count: int
    morphed_mesh_count: int
    static_mesh_count: int
    vertex_count: int
    index_count: int
    selector_weights: tuple[float, float, float, float, float]
    scale_x: float
    aabb: dict[str, object]
    glb_path: str | None

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["selector_weights"] = list(self.selector_weights)
        return payload


@dataclass(frozen=True)
class AxleProductionTrialGeometry:
    axle: str
    selector_weights: tuple[float, float, float, float, float]
    scale_x: float
    modelbins: tuple[ModelbinProductionTrialGeometry, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "axle": self.axle,
            "selector_weights": list(self.selector_weights),
            "scale_x": self.scale_x,
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
            f"native tire production trial blocked: {eligibility.status}: {eligibility.detail}"
        )
    if eligibility.production_renderer_enabled:
        raise TireProductionTrialGeometryError(
            "production policy unexpectedly enabled the renderer before spindle integration review"
        )
    return eligibility


def _safe_stem(entry: str) -> str:
    return Path(entry.replace("\\", "/")).stem


def _build_modelbin_geometry(
    data: bytes,
    *,
    entry: str,
    axle: str,
    weights: AxleTireMorphWeights,
    output_dir: Path,
    write_glb: bool,
) -> ModelbinProductionTrialGeometry:
    if weights.selector_weights[2:] != (0.0, 0.0, 0.0):
        raise TireProductionTrialGeometryError(
            f"{axle}: selector 2..4 must stay zero in the first production trial"
        )

    try:
        _bundle_major, _bundle_minor, blobs = _iter_bundle_blobs(data)
        index_blobs = [blob for blob in blobs if blob.tag == INDEX_BUFFER_TAG]
        if not index_blobs:
            raise TireProductionTrialGeometryError(f"{entry}: modelbin has no IndB")
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
        raise TireProductionTrialGeometryError(f"{entry}: {exc}") from exc

    morph_buffers = {item.blob_index: item for item in inventory.morph_buffers}
    morph_resolutions = {item.mesh_blob_index: item for item in inventory.resolutions}
    aggregate_positions: list[tuple[float, float, float]] = []
    aggregate_indices: list[int] = []
    selected_mesh_count = 0
    morphed_mesh_count = 0
    static_mesh_count = 0

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
                f"{entry}: mesh {mesh.blob_index}: {exc}"
            ) from exc

        selected_mesh_count += 1
        positions: Sequence[Sequence[float]] = base_positions
        if mesh.morph_target_count > 0 and not mesh.is_morph_damage:
            if mesh.morph_target_count != 5:
                raise TireProductionTrialGeometryError(
                    f"{entry}: mesh {mesh.blob_index} has {mesh.morph_target_count} "
                    "weighted targets; production trial refuses to guess"
                )
            resolution = morph_resolutions.get(mesh.blob_index)
            if resolution is None or resolution.morph_buffer_blob_index is None:
                raise TireProductionTrialGeometryError(
                    f"{entry}: mesh {mesh.blob_index} weighted morph buffer cannot be resolved"
                )
            morph_buffer = morph_buffers.get(resolution.morph_buffer_blob_index)
            if morph_buffer is None:
                raise TireProductionTrialGeometryError(
                    f"{entry}: mesh {mesh.blob_index} resolved morph buffer is missing"
                )
            try:
                positions, _ = apply_weighted_morph(
                    base_positions,
                    morph_buffer,
                    mesh.indexed_vertex_offset,
                    mesh.morph_target_count,
                    weights.selector_weights,
                    min_vertex_index=min_index,
                )
            except ModelbinMorphError as exc:
                raise TireProductionTrialGeometryError(
                    f"{entry}: mesh {mesh.blob_index} stock morph failed: {exc}"
                ) from exc
            morphed_mesh_count += 1
        else:
            static_mesh_count += 1

        scaled_positions = tuple(
            (float(point[0]) * weights.scale_x, float(point[1]), float(point[2]))
            for point in positions
        )
        try:
            compact_positions, compact_indices = _compact_geometry(
                scaled_positions, source_indices, min_index
            )
        except TireMorphGeometryError as exc:
            raise TireProductionTrialGeometryError(
                f"{entry}: mesh {mesh.blob_index}: {exc}"
            ) from exc
        vertex_base = len(aggregate_positions)
        aggregate_positions.extend(compact_positions)
        aggregate_indices.extend(vertex_base + index for index in compact_indices)

    if not aggregate_positions or not aggregate_indices or selected_mesh_count <= 0:
        raise TireProductionTrialGeometryError(
            f"{entry}: modelbin has no decodable LOD0 tire geometry"
        )

    try:
        bounds = _aabb(aggregate_positions)
    except TireMorphGeometryError as exc:
        raise TireProductionTrialGeometryError(f"{entry}: {exc}") from exc

    glb_path: str | None = None
    if write_glb:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{axle}__{_safe_stem(entry)}__stock_trial.glb"
        try:
            path.write_bytes(_glb_bytes(aggregate_positions, aggregate_indices))
        except (OSError, TireMorphGeometryError) as exc:
            raise TireProductionTrialGeometryError(
                f"could not write derived {axle} tire GLB for {entry}: {exc}"
            ) from exc
        glb_path = str(path)

    return ModelbinProductionTrialGeometry(
        axle=axle,
        entry=entry.replace("\\", "/"),
        modelbin_sha256=hashlib.sha256(data).hexdigest(),
        selected_mesh_count=selected_mesh_count,
        morphed_mesh_count=morphed_mesh_count,
        static_mesh_count=static_mesh_count,
        vertex_count=len(aggregate_positions),
        index_count=len(aggregate_indices),
        selector_weights=weights.selector_weights,
        scale_x=float(weights.scale_x),
        aabb=bounds.as_dict(),
        glb_path=glb_path,
    )


def _build_axle(
    modelbins: Sequence[tuple[str, bytes]],
    *,
    axle: str,
    weights: AxleTireMorphWeights,
    output_dir: Path,
    write_glb: bool,
) -> AxleProductionTrialGeometry:
    reports = tuple(
        _build_modelbin_geometry(
            data,
            entry=entry,
            axle=axle,
            weights=weights,
            output_dir=output_dir,
            write_glb=write_glb,
        )
        for entry, data in modelbins
    )
    return AxleProductionTrialGeometry(
        axle=axle,
        selector_weights=weights.selector_weights,
        scale_x=float(weights.scale_x),
        modelbins=reports,
    )


def build_stock_tire_production_trial_geometry(
    spec: VehicleWheelSpec,
    archive_path: str | Path,
    output_dir: str | Path,
    *,
    write_glb: bool = True,
) -> TireProductionTrialGeometryReport:
    """Build derived native tire GLBs only after the evidence-backed production gate.

    The source ZIP remains read-only. The output geometry is intentionally detached
    from vehicle spindles: this stage validates that the exact approved stock FXX/Slick
    mapping can create renderer-ready front/rear geometry without enabling assembly.
    """
    archive = Path(archive_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    eligibility = _require_eligible(spec, archive)
    weights = eligibility.weights
    assert weights is not None

    before = _sha256(archive)
    if eligibility.archive_sha256 is not None and before != eligibility.archive_sha256:
        raise TireProductionTrialGeometryError(
            "native tire archive changed after production eligibility validation"
        )

    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            entries = [
                item
                for item in bundle.infolist()
                if not item.is_dir() and item.filename.casefold().endswith(".modelbin")
            ]
            if not entries:
                raise TireProductionTrialGeometryError(
                    "native tire archive contains no modelbin"
                )
            modelbins = tuple(
                (item.filename.replace("\\", "/"), bundle.read(item))
                for item in sorted(entries, key=lambda item: item.filename.casefold())
            )
    except (OSError, zipfile.BadZipFile) as exc:
        raise TireProductionTrialGeometryError(
            f"could not read native tire archive: {exc}"
        ) from exc

    destination.mkdir(parents=True, exist_ok=True)
    front = _build_axle(
        modelbins,
        axle="front",
        weights=weights.front,
        output_dir=destination,
        write_glb=write_glb,
    )
    rear = _build_axle(
        modelbins,
        axle="rear",
        weights=weights.rear,
        output_dir=destination,
        write_glb=write_glb,
    )

    after = _sha256(archive)
    if before != after:
        raise TireProductionTrialGeometryError(
            "read-only production trial changed the native tire archive"
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
            f"could not write production-trial manifest: {exc}"
        ) from exc
    return report
