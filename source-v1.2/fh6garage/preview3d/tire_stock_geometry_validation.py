from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
from typing import Sequence
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
    _mesh_indices,
    _parse_global_indices,
    _parse_layout,
    _parse_mesh,
    _parse_vertex_buffer,
    _resolve_layout,
)
from .tire_morph_weights import AxleTireMorphWeights, stock_axle_tire_morph_weights
from .wheel_spec import AxleWheelSpec, VehicleWheelSpec


class TireStockGeometryValidationError(RuntimeError):
    """Raised when stock tire geometry cannot be reconstructed without guessing."""


@dataclass(frozen=True)
class ModelbinStockGeometryEvidence:
    entry: str
    modelbin_sha256: str
    vertex_count: int
    index_count: int
    reconstructed_width_mm: float
    reconstructed_outer_diameter_y_mm: float
    reconstructed_outer_diameter_z_mm: float
    nominal_width_mm: float
    nominal_outer_diameter_mm: float
    width_error_percent: float
    outer_diameter_y_error_percent: float
    outer_diameter_z_error_percent: float
    radial_circularity_percent: float
    corroborated: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AxleStockGeometryEvidence:
    axle: str
    weights: AxleTireMorphWeights
    nominal_width_mm: float
    nominal_outer_diameter_mm: float
    modelbins: tuple[ModelbinStockGeometryEvidence, ...]
    tolerance_percent: float
    corroborated: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "axle": self.axle,
            "weights": self.weights.as_dict(),
            "nominal_width_mm": self.nominal_width_mm,
            "nominal_outer_diameter_mm": self.nominal_outer_diameter_mm,
            "modelbins": [item.as_dict() for item in self.modelbins],
            "tolerance_percent": self.tolerance_percent,
            "corroborated": self.corroborated,
        }


@dataclass(frozen=True)
class TireStockGeometryValidationReport:
    archive_path: str
    archive_sha256: str
    archive_read_only_unchanged: bool
    car_id: int
    tire_model_name: str | None
    front: AxleStockGeometryEvidence
    rear: AxleStockGeometryEvidence
    production_mapping_enabled: bool
    complete_mapping_status: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fh6_native_tire_stock_geometry_validation_v1",
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "archive_read_only_unchanged": self.archive_read_only_unchanged,
            "car_id": self.car_id,
            "tire_model_name": self.tire_model_name,
            "front": self.front.as_dict(),
            "rear": self.rear.as_dict(),
            "production_mapping_enabled": self.production_mapping_enabled,
            "complete_mapping_status": self.complete_mapping_status,
            "limitations": list(self.limitations),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_error_percent(actual: float, expected: float) -> float:
    if not math.isfinite(actual) or not math.isfinite(expected) or expected <= 0.0:
        raise TireStockGeometryValidationError(
            "dimension comparison requires finite positive values"
        )
    return (actual - expected) / expected * 100.0


def _validate_tolerance(value: float) -> float:
    tolerance = float(value)
    if not math.isfinite(tolerance) or tolerance <= 0.0 or tolerance > 100.0:
        raise TireStockGeometryValidationError(
            f"tolerance_percent must be finite and in (0, 100]: {value!r}"
        )
    return tolerance


def _reconstruct_modelbin(
    data: bytes,
    *,
    entry: str,
    axle_spec: AxleWheelSpec,
    weights: AxleTireMorphWeights,
    tolerance_percent: float,
) -> ModelbinStockGeometryEvidence:
    try:
        _bundle_major, _bundle_minor, blobs = _iter_bundle_blobs(data)
        index_blobs = [blob for blob in blobs if blob.tag == INDEX_BUFFER_TAG]
        if not index_blobs:
            raise TireStockGeometryValidationError(f"{entry}: modelbin has no IndB")
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
        raise TireStockGeometryValidationError(f"{entry}: {exc}") from exc

    morph_buffers = {item.blob_index: item for item in inventory.morph_buffers}
    morph_resolutions = {item.mesh_blob_index: item for item in inventory.resolutions}
    aggregate_positions: list[tuple[float, float, float]] = []
    aggregate_indices: list[int] = []

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
            raise TireStockGeometryValidationError(
                f"{entry}: mesh {mesh.blob_index}: {exc}"
            ) from exc

        positions: Sequence[Sequence[float]] = base_positions
        if mesh.morph_target_count > 0 and not mesh.is_morph_damage:
            if mesh.morph_target_count != 5:
                raise TireStockGeometryValidationError(
                    f"{entry}: mesh {mesh.blob_index} has "
                    f"{mesh.morph_target_count} weighted targets; "
                    "stock tire reconstruction refuses to guess"
                )
            resolution = morph_resolutions.get(mesh.blob_index)
            if resolution is None or resolution.morph_buffer_blob_index is None:
                raise TireStockGeometryValidationError(
                    f"{entry}: mesh {mesh.blob_index} weighted morph buffer "
                    "cannot be resolved"
                )
            morph_buffer = morph_buffers.get(resolution.morph_buffer_blob_index)
            if morph_buffer is None:
                raise TireStockGeometryValidationError(
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
                raise TireStockGeometryValidationError(
                    f"{entry}: mesh {mesh.blob_index} stock morph failed: {exc}"
                ) from exc

        scaled_positions = tuple(
            (float(point[0]) * weights.scale_x, float(point[1]), float(point[2]))
            for point in positions
        )
        try:
            compact_positions, compact_indices = _compact_geometry(
                scaled_positions, source_indices, min_index
            )
        except TireMorphGeometryError as exc:
            raise TireStockGeometryValidationError(
                f"{entry}: mesh {mesh.blob_index}: {exc}"
            ) from exc
        vertex_base = len(aggregate_positions)
        aggregate_positions.extend(compact_positions)
        aggregate_indices.extend(vertex_base + index for index in compact_indices)

    if not aggregate_positions or not aggregate_indices:
        raise TireStockGeometryValidationError(
            f"{entry}: modelbin has no decodable LOD0 tire geometry"
        )

    try:
        bounds = _aabb(aggregate_positions)
    except TireMorphGeometryError as exc:
        raise TireStockGeometryValidationError(f"{entry}: {exc}") from exc

    width_mm = float(bounds.span[0]) * 1000.0
    diameter_y_mm = float(bounds.span[1]) * 1000.0
    diameter_z_mm = float(bounds.span[2]) * 1000.0
    nominal_width = float(axle_spec.tire_width_mm)
    nominal_diameter = float(axle_spec.tire_outer_diameter_mm)
    width_error = _relative_error_percent(width_mm, nominal_width)
    y_error = _relative_error_percent(diameter_y_mm, nominal_diameter)
    z_error = _relative_error_percent(diameter_z_mm, nominal_diameter)
    circularity = abs(diameter_y_mm - diameter_z_mm) / nominal_diameter * 100.0
    corroborated = (
        max(abs(width_error), abs(y_error), abs(z_error)) <= tolerance_percent
    )

    return ModelbinStockGeometryEvidence(
        entry=entry.replace("\\", "/"),
        modelbin_sha256=hashlib.sha256(data).hexdigest(),
        vertex_count=len(aggregate_positions),
        index_count=len(aggregate_indices),
        reconstructed_width_mm=width_mm,
        reconstructed_outer_diameter_y_mm=diameter_y_mm,
        reconstructed_outer_diameter_z_mm=diameter_z_mm,
        nominal_width_mm=nominal_width,
        nominal_outer_diameter_mm=nominal_diameter,
        width_error_percent=width_error,
        outer_diameter_y_error_percent=y_error,
        outer_diameter_z_error_percent=z_error,
        radial_circularity_percent=circularity,
        corroborated=corroborated,
    )


def _validate_axle(
    modelbins: Sequence[tuple[str, bytes]],
    spec: AxleWheelSpec,
    *,
    tolerance_percent: float,
) -> AxleStockGeometryEvidence:
    weights = stock_axle_tire_morph_weights(spec)
    reports = tuple(
        _reconstruct_modelbin(
            data,
            entry=entry,
            axle_spec=spec,
            weights=weights,
            tolerance_percent=tolerance_percent,
        )
        for entry, data in modelbins
    )
    return AxleStockGeometryEvidence(
        axle=str(spec.axle),
        weights=weights,
        nominal_width_mm=float(spec.tire_width_mm),
        nominal_outer_diameter_mm=float(spec.tire_outer_diameter_mm),
        modelbins=reports,
        tolerance_percent=tolerance_percent,
        corroborated=bool(reports) and all(item.corroborated for item in reports),
    )


def validate_stock_tire_geometry(
    archive_path: str | Path,
    spec: VehicleWheelSpec,
    *,
    tolerance_percent: float = 2.0,
) -> TireStockGeometryValidationReport:
    """Reconstruct stock tire dimensions from native morph data, diagnostic-only.

    Historical selector0/selector1 weights and the post-morph X scale are applied
    to every decodable LOD0 tire mesh. The resulting X/Y/Z AABB spans are compared
    with DB tire width and nominal outer diameter. Passing this diagnostic never
    enables production tire assembly.
    """
    if str(spec.mode).casefold() != "stock":
        raise TireStockGeometryValidationError(
            f"stock tire geometry validation requires mode='stock'; got {spec.mode!r}"
        )
    tolerance = _validate_tolerance(tolerance_percent)
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file():
        raise TireStockGeometryValidationError(
            f"native tire archive does not exist: {archive}"
        )
    before = _sha256(archive)
    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            entries = [
                item
                for item in bundle.infolist()
                if not item.is_dir() and item.filename.casefold().endswith(".modelbin")
            ]
            if not entries:
                raise TireStockGeometryValidationError(
                    "native tire archive contains no modelbin"
                )
            modelbins = tuple(
                (item.filename.replace("\\", "/"), bundle.read(item))
                for item in sorted(entries, key=lambda item: item.filename.casefold())
            )
    except (OSError, zipfile.BadZipFile) as exc:
        raise TireStockGeometryValidationError(
            f"could not read native tire archive: {exc}"
        ) from exc

    front = _validate_axle(modelbins, spec.front, tolerance_percent=tolerance)
    rear = _validate_axle(modelbins, spec.rear, tolerance_percent=tolerance)
    after = _sha256(archive)
    if before != after:
        raise TireStockGeometryValidationError(
            "read-only stock tire validation changed the source archive"
        )

    corroborated = front.corroborated and rear.corroborated
    return TireStockGeometryValidationReport(
        archive_path=str(archive),
        archive_sha256=before,
        archive_read_only_unchanged=True,
        car_id=int(spec.car_id),
        tire_model_name=spec.tire_model_name,
        front=front,
        rear=rear,
        production_mapping_enabled=False,
        complete_mapping_status=(
            "diagnostic_stock_dimensions_corroborated"
            if corroborated
            else "diagnostic_stock_dimensions_not_corroborated"
        ),
        limitations=(
            "This validates one resolved tire archive and one stock vehicle specification only; it does not establish a global ForzaTech tire formula.",
            "The historical Doliman mapping remains diagnostic-only until corroborated across additional TireModelName families and independently sourced dimensions.",
            "Production spindle tire assembly is intentionally not enabled by this report.",
        ),
    )
