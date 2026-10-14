from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Sequence
import zipfile

import numpy as np

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
    Aabb,
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
    bake_tire_morph_selectors,
)
from .tire_morph_weights import (
    AxleTireMorphWeights,
    TireMorphWeightError,
    VehicleTireMorphWeights,
    stock_vehicle_tire_morph_weights,
)
from .wheel_spec import AxleWheelSpec, VehicleWheelSpec


GENERIC_TIRE_AUTO_INFERENCE_REVISION = "generic_native_tire_morph_auto_inference_v1"

# The generic path deliberately does not identify or whitelist tire families.
# It measures selector 0/1 from the actual modelbin, keeps selectors 2..4 at zero
# until their physical semantics are independently established, and validates the
# resulting geometry against the stock tire dimensions from the game database.
_MAX_RADIAL_REL_ERROR = 0.05
_MAX_WIDTH_REL_ERROR = 0.05
_MAX_CENTER_DRIFT_REL = 0.05
_MAX_SELECTOR_UNDERSHOOT = -0.15
_MAX_SELECTOR_OVERSHOOT = 1.15
_PRIOR_STRENGTH = 0.02
_CENTER_ROW_WEIGHT = 0.25


class TireMorphAutoInferenceError(RuntimeError):
    """Raised when generic native-tire inference cannot be accepted without guessing."""

    def __init__(
        self,
        message: str,
        *,
        report: dict[str, Any] | None = None,
        report_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.report = report
        self.report_path = report_path


@dataclass(frozen=True)
class ModelbinInferenceValidation:
    entry: str
    raw_span: tuple[float, float, float]
    scaled_span: tuple[float, float, float]
    raw_center: tuple[float, float, float]
    baseline_center: tuple[float, float, float]
    radial_relative_error: float
    width_relative_error: float
    center_drift_relative: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AxleTireMorphAutoInference:
    axle: str
    target_width_m: float
    target_outer_diameter_m: float
    seed_selector_weights: tuple[float, float, float, float, float]
    selector_weights: tuple[float, float, float, float, float]
    scale_x: float
    least_squares_rank: int
    least_squares_residual_norm: float
    modelbins: tuple[ModelbinInferenceValidation, ...]
    maximum_radial_relative_error: float
    maximum_width_relative_error: float
    maximum_center_drift_relative: float
    accepted: bool

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["seed_selector_weights"] = list(self.seed_selector_weights)
        payload["selector_weights"] = list(self.selector_weights)
        payload["modelbins"] = [item.as_dict() for item in self.modelbins]
        return payload


@dataclass(frozen=True)
class VehicleTireMorphAutoInference:
    status: str
    revision: str
    car_id: int
    tire_model_name: str | None
    archive_path: str
    archive_sha256: str
    archive_read_only_unchanged: bool
    modelbin_count: int
    active_selector_indices: tuple[int, ...]
    front: AxleTireMorphAutoInference
    rear: AxleTireMorphAutoInference
    weights: VehicleTireMorphWeights
    persistent_report_path: str | None
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "fh6_generic_native_tire_morph_auto_inference_v1",
            "status": self.status,
            "revision": self.revision,
            "car_id": self.car_id,
            "tire_model_name": self.tire_model_name,
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "archive_read_only_unchanged": self.archive_read_only_unchanged,
            "modelbin_count": self.modelbin_count,
            "active_selector_indices": list(self.active_selector_indices),
            "front": self.front.as_dict(),
            "rear": self.rear.as_dict(),
            "weights": self.weights.as_dict(),
            "persistent_report_path": self.persistent_report_path,
            "limitations": list(self.limitations),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _persistent_report_path(car_id: int) -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base) / "FH6GarageAnalyzer" / "preview3d_runtime"
    else:
        root = Path.home() / ".fh6garageanalyzer" / "preview3d_runtime"
    return (
        root
        / "diagnostics"
        / "generic_tire_auto_inference"
        / f"car_{int(car_id)}"
        / "generic_native_tire_morph_auto_inference.json"
    )


def _write_report_best_effort(path: Path, payload: dict[str, Any]) -> str | None:
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(path)
        return str(path)
    except (OSError, TypeError, ValueError):
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _fail(
    spec: VehicleWheelSpec,
    archive: Path,
    message: str,
    payload: dict[str, Any],
) -> TireMorphAutoInferenceError:
    payload.update(
        {
            "format": "fh6_generic_native_tire_morph_auto_inference_v1",
            "status": "auto_inference_rejected",
            "revision": GENERIC_TIRE_AUTO_INFERENCE_REVISION,
            "car_id": int(spec.car_id),
            "tire_model_name": spec.tire_model_name,
            "archive_path": str(archive),
            "error": message,
        }
    )
    report_path = _write_report_best_effort(_persistent_report_path(spec.car_id), payload)
    suffix = f"; report={report_path}" if report_path else ""
    return TireMorphAutoInferenceError(
        message + suffix,
        report=payload,
        report_path=report_path,
    )


def _triplet(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise TireMorphAutoInferenceError(f"{label} must contain exactly three numeric values")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise TireMorphAutoInferenceError(f"{label} contains non-finite values")
    return result


def _state_aabb(modelbin: Any, state_name: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    states = getattr(modelbin, "states", None)
    if not isinstance(states, dict):
        raise TireMorphAutoInferenceError(f"{getattr(modelbin, 'entry', 'modelbin')}: states are missing")
    state = states.get(state_name)
    if not isinstance(state, dict):
        raise TireMorphAutoInferenceError(
            f"{getattr(modelbin, 'entry', 'modelbin')}: {state_name} is missing"
        )
    aabb = state.get("aabb")
    if not isinstance(aabb, dict):
        raise TireMorphAutoInferenceError(
            f"{getattr(modelbin, 'entry', 'modelbin')}: {state_name} AABB is missing"
        )
    return _triplet(aabb.get("span"), f"{state_name} span"), _triplet(
        aabb.get("center"), f"{state_name} center"
    )


def _read_modelbins(archive: Path) -> tuple[tuple[str, bytes], ...]:
    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            entries = [
                item
                for item in bundle.infolist()
                if not item.is_dir() and item.filename.casefold().endswith(".modelbin")
            ]
            if len(entries) not in (1, 2):
                raise TireMorphAutoInferenceError(
                    f"generic inference requires one or two tire modelbins; found {len(entries)}"
                )
            return tuple(
                (item.filename.replace("\\", "/"), bundle.read(item))
                for item in sorted(entries, key=lambda value: value.filename.casefold())
            )
    except (OSError, zipfile.BadZipFile) as exc:
        raise TireMorphAutoInferenceError(
            f"could not read native tire archive: {type(exc).__name__}: {exc}"
        ) from exc


def _evaluate_modelbin_aabb(
    data: bytes,
    selector_weights: Sequence[float],
) -> Aabb:
    if len(selector_weights) != 5:
        raise TireMorphAutoInferenceError("selector weight vector must contain five values")
    try:
        _major, _minor, blobs = _iter_bundle_blobs(data)
        index_blobs = [blob for blob in blobs if blob.tag == INDEX_BUFFER_TAG]
        if not index_blobs:
            raise TireMorphAutoInferenceError("modelbin has no IndB")
        index_raw, _stride = _parse_global_indices(data, index_blobs[0])
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
        raise TireMorphAutoInferenceError(str(exc)) from exc

    morph_buffers = {item.blob_index: item for item in inventory.morph_buffers}
    morph_resolutions = {item.mesh_blob_index: item for item in inventory.resolutions}
    aggregate_positions: list[tuple[float, float, float]] = []

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
            raise TireMorphAutoInferenceError(
                f"mesh {mesh.blob_index}: {exc}"
            ) from exc

        positions: Sequence[Sequence[float]] = base_positions
        if mesh.morph_target_count > 0 and not mesh.is_morph_damage:
            if mesh.morph_target_count != 5:
                raise TireMorphAutoInferenceError(
                    f"mesh {mesh.blob_index} has {mesh.morph_target_count} weighted morph targets; expected five"
                )
            resolution = morph_resolutions.get(mesh.blob_index)
            if resolution is None or resolution.morph_buffer_blob_index is None:
                raise TireMorphAutoInferenceError(
                    f"mesh {mesh.blob_index} weighted morph buffer cannot be resolved"
                )
            morph_buffer = morph_buffers.get(resolution.morph_buffer_blob_index)
            if morph_buffer is None:
                raise TireMorphAutoInferenceError(
                    f"mesh {mesh.blob_index} resolved morph buffer is missing"
                )
            try:
                positions, _ = apply_weighted_morph(
                    base_positions,
                    morph_buffer,
                    mesh.indexed_vertex_offset,
                    mesh.morph_target_count,
                    selector_weights,
                    min_vertex_index=min_index,
                )
            except ModelbinMorphError as exc:
                raise TireMorphAutoInferenceError(
                    f"mesh {mesh.blob_index} morph evaluation failed: {exc}"
                ) from exc
        try:
            compact_positions, _compact_indices = _compact_geometry(
                positions, source_indices, min_index
            )
        except TireMorphGeometryError as exc:
            raise TireMorphAutoInferenceError(
                f"mesh {mesh.blob_index}: {exc}"
            ) from exc
        aggregate_positions.extend(compact_positions)

    if not aggregate_positions:
        raise TireMorphAutoInferenceError("modelbin has no decodable LOD0 tire geometry")
    try:
        return _aabb(aggregate_positions)
    except TireMorphGeometryError as exc:
        raise TireMorphAutoInferenceError(str(exc)) from exc


def _solve_axle(
    axle_spec: AxleWheelSpec,
    seed: AxleTireMorphWeights,
    bake_modelbins: Sequence[Any],
    modelbins_by_entry: dict[str, bytes],
) -> AxleTireMorphAutoInference:
    target_width = float(axle_spec.tire_width_mm) / 1000.0
    target_outer = float(axle_spec.tire_outer_diameter_mm) / 1000.0
    if not all(math.isfinite(value) and value > 0.0 for value in (target_width, target_outer)):
        raise TireMorphAutoInferenceError(
            f"{axle_spec.axle}: stock target dimensions are not finite positive values"
        )

    rows: list[list[float]] = []
    rhs: list[float] = []
    baseline_centers: dict[str, tuple[float, float, float]] = {}
    baseline_spans: dict[str, tuple[float, float, float]] = {}

    for modelbin in bake_modelbins:
        entry = str(getattr(modelbin, "entry", ""))
        baseline_span, baseline_center = _state_aabb(modelbin, "baseline")
        selector0_span, selector0_center = _state_aabb(modelbin, "selector0")
        selector1_span, selector1_center = _state_aabb(modelbin, "selector1")
        baseline_centers[entry.casefold()] = baseline_center
        baseline_spans[entry.casefold()] = baseline_span

        d0_span = tuple(selector0_span[i] - baseline_span[i] for i in range(3))
        d1_span = tuple(selector1_span[i] - baseline_span[i] for i in range(3))
        d0_center = tuple(selector0_center[i] - baseline_center[i] for i in range(3))
        d1_center = tuple(selector1_center[i] - baseline_center[i] for i in range(3))

        # Radial outer diameter is the primary physical target.  Both Y and Z
        # responses are retained independently so asymmetric or malformed families
        # cannot pass by averaging one good and one bad axis.
        for axis in (1, 2):
            rows.append([d0_span[axis] / target_outer, d1_span[axis] / target_outer])
            rhs.append((target_outer - baseline_span[axis]) / target_outer)

        # Keep the inferred morph centered on the native model.  These lower-weight
        # rows are geometry constraints, not family semantics.
        for axis in (0, 1, 2):
            rows.append(
                [
                    _CENTER_ROW_WEIGHT * d0_center[axis] / target_outer,
                    _CENTER_ROW_WEIGHT * d1_center[axis] / target_outer,
                ]
            )
            rhs.append(0.0)

    seed01 = np.asarray(seed.selector_weights[:2], dtype=float)
    matrix = np.asarray(rows, dtype=float)
    target = np.asarray(rhs, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != 2 or matrix.shape[0] < 2:
        raise TireMorphAutoInferenceError(f"{axle_spec.axle}: selector response matrix is incomplete")
    if not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(target)):
        raise TireMorphAutoInferenceError(f"{axle_spec.axle}: selector response matrix is non-finite")

    prior_scale = math.sqrt(_PRIOR_STRENGTH)
    augmented_matrix = np.vstack((matrix, prior_scale * np.eye(2, dtype=float)))
    augmented_target = np.concatenate((target, prior_scale * seed01))
    solution, residuals, rank, _singular = np.linalg.lstsq(
        augmented_matrix,
        augmented_target,
        rcond=None,
    )
    if not np.all(np.isfinite(solution)):
        raise TireMorphAutoInferenceError(f"{axle_spec.axle}: least-squares solution is non-finite")
    selector0 = float(solution[0])
    selector1 = float(solution[1])
    if (
        selector0 < _MAX_SELECTOR_UNDERSHOOT
        or selector0 > _MAX_SELECTOR_OVERSHOOT
        or selector1 < _MAX_SELECTOR_UNDERSHOOT
        or selector1 > _MAX_SELECTOR_OVERSHOOT
    ):
        raise TireMorphAutoInferenceError(
            f"{axle_spec.axle}: inferred selector weights require extrapolation outside the verified one-hot neighborhood: "
            f"selector0={selector0:.6g}, selector1={selector1:.6g}"
        )

    selector_weights = (selector0, selector1, 0.0, 0.0, 0.0)
    raw_results: list[tuple[str, Aabb]] = []
    for modelbin in bake_modelbins:
        entry = str(getattr(modelbin, "entry", ""))
        data = modelbins_by_entry.get(entry.casefold())
        if data is None:
            raise TireMorphAutoInferenceError(
                f"{axle_spec.axle}: selector report entry is not present in the archive: {entry}"
            )
        raw_results.append((entry, _evaluate_modelbin_aabb(data, selector_weights)))

    raw_widths = [float(bounds.span[0]) for _entry, bounds in raw_results]
    if not raw_widths or any(not math.isfinite(value) or value <= 0.0 for value in raw_widths):
        raise TireMorphAutoInferenceError(f"{axle_spec.axle}: inferred raw tire width is invalid")
    mean_raw_width = sum(raw_widths) / len(raw_widths)
    scale_x = target_width / mean_raw_width
    if not math.isfinite(scale_x) or scale_x <= 0.0:
        raise TireMorphAutoInferenceError(f"{axle_spec.axle}: inferred X scale is invalid")

    validations: list[ModelbinInferenceValidation] = []
    for entry, bounds in raw_results:
        scaled_span = (
            float(bounds.span[0]) * scale_x,
            float(bounds.span[1]),
            float(bounds.span[2]),
        )
        radial_error = max(
            abs(scaled_span[1] - target_outer),
            abs(scaled_span[2] - target_outer),
        ) / target_outer
        width_error = abs(scaled_span[0] - target_width) / target_width
        baseline_center = baseline_centers[entry.casefold()]
        center_delta = (
            float(bounds.center[0]) - baseline_center[0],
            float(bounds.center[1]) - baseline_center[1],
            float(bounds.center[2]) - baseline_center[2],
        )
        center_drift = math.sqrt(sum(value * value for value in center_delta)) / target_outer
        validations.append(
            ModelbinInferenceValidation(
                entry=entry,
                raw_span=tuple(float(value) for value in bounds.span),
                scaled_span=scaled_span,
                raw_center=tuple(float(value) for value in bounds.center),
                baseline_center=baseline_center,
                radial_relative_error=radial_error,
                width_relative_error=width_error,
                center_drift_relative=center_drift,
            )
        )

    max_radial = max(item.radial_relative_error for item in validations)
    max_width = max(item.width_relative_error for item in validations)
    max_center = max(item.center_drift_relative for item in validations)
    if max_radial > _MAX_RADIAL_REL_ERROR:
        raise TireMorphAutoInferenceError(
            f"{axle_spec.axle}: inferred geometry misses stock outer diameter by {max_radial:.2%}; "
            f"limit={_MAX_RADIAL_REL_ERROR:.2%}"
        )
    if max_width > _MAX_WIDTH_REL_ERROR:
        raise TireMorphAutoInferenceError(
            f"{axle_spec.axle}: inferred left/right raw width disagreement produces {max_width:.2%} error; "
            f"limit={_MAX_WIDTH_REL_ERROR:.2%}"
        )
    if max_center > _MAX_CENTER_DRIFT_REL:
        raise TireMorphAutoInferenceError(
            f"{axle_spec.axle}: inferred morph shifts native tire center by {max_center:.2%} of tire diameter; "
            f"limit={_MAX_CENTER_DRIFT_REL:.2%}"
        )

    residual_norm = float(np.linalg.norm(augmented_matrix @ solution - augmented_target))
    return AxleTireMorphAutoInference(
        axle=str(axle_spec.axle),
        target_width_m=target_width,
        target_outer_diameter_m=target_outer,
        seed_selector_weights=tuple(float(value) for value in seed.selector_weights),
        selector_weights=selector_weights,
        scale_x=scale_x,
        least_squares_rank=int(rank),
        least_squares_residual_norm=residual_norm,
        modelbins=tuple(validations),
        maximum_radial_relative_error=max_radial,
        maximum_width_relative_error=max_width,
        maximum_center_drift_relative=max_center,
        accepted=True,
    )


def _as_axle_weights(
    spec: AxleWheelSpec,
    inferred: AxleTireMorphAutoInference,
) -> AxleTireMorphWeights:
    return AxleTireMorphWeights(
        axle=str(spec.axle),
        tire_width_mm=float(spec.tire_width_mm),
        tire_aspect_ratio=float(spec.tire_aspect_ratio),
        original_rim_diameter_in=float(spec.rim_diameter_in),
        rim_diameter_in=float(spec.rim_diameter_in),
        selector_weights=inferred.selector_weights,
        scale_x=float(inferred.scale_x),
        mapping_revision=GENERIC_TIRE_AUTO_INFERENCE_REVISION,
    )


def infer_stock_native_tire_morph(
    spec: VehicleWheelSpec,
    archive_path: str | Path,
) -> VehicleTireMorphAutoInference:
    """Infer stock native-tire morph weights from the actual linked tire modelbin.

    No TireModelName-specific selector role table or geometry-identity whitelist is
    consulted.  The exact tire ZIP linked by the stock database is inspected read-only,
    selector 0/1 responses are measured from its own geometry, a geometry-constrained
    solution is fitted around the historical physical mapping as a weak prior, and the
    resulting full geometry is re-evaluated against stock width/outer-diameter targets.
    """
    archive = Path(archive_path).expanduser().resolve()
    diagnostic: dict[str, Any] = {
        "format": "fh6_generic_native_tire_morph_auto_inference_v1",
        "status": "in_progress",
        "revision": GENERIC_TIRE_AUTO_INFERENCE_REVISION,
        "car_id": int(spec.car_id),
        "tire_model_name": spec.tire_model_name,
        "archive_path": str(archive),
        "active_selector_indices": [0, 1],
        "selector_2_4_forced_zero": True,
    }

    if str(spec.mode).casefold() != "stock":
        raise _fail(spec, archive, f"generic auto inference requires stock mode; got {spec.mode!r}", diagnostic)
    if not archive.is_file():
        raise _fail(spec, archive, f"native tire archive does not exist: {archive}", diagnostic)

    before = _sha256(archive)
    diagnostic["archive_sha256"] = before
    try:
        bake = bake_tire_morph_selectors(archive, None, write_glb=False)
        if not bake.archive_read_only_unchanged:
            raise TireMorphAutoInferenceError("selector bake did not preserve the source archive")
        if bake.archive_sha256.casefold() != before.casefold():
            raise TireMorphAutoInferenceError("archive identity changed during selector bake")
        if len(bake.modelbins) not in (1, 2):
            raise TireMorphAutoInferenceError(
                f"generic inference requires one or two native tire modelbins; found {len(bake.modelbins)}"
            )
        modelbins = _read_modelbins(archive)
        modelbins_by_entry = {entry.casefold(): data for entry, data in modelbins}
        if set(modelbins_by_entry) != {str(item.entry).casefold() for item in bake.modelbins}:
            raise TireMorphAutoInferenceError("selector bake modelbin inventory differs from archive inventory")

        try:
            seed = stock_vehicle_tire_morph_weights(spec)
        except TireMorphWeightError as exc:
            raise TireMorphAutoInferenceError(f"could not build physical seed mapping: {exc}") from exc

        front = _solve_axle(spec.front, seed.front, bake.modelbins, modelbins_by_entry)
        rear = _solve_axle(spec.rear, seed.rear, bake.modelbins, modelbins_by_entry)
    except TireMorphAutoInferenceError as exc:
        diagnostic["cause"] = str(exc)
        raise _fail(spec, archive, str(exc), diagnostic) from exc
    except (OSError, zipfile.BadZipFile, ValueError, np.linalg.LinAlgError) as exc:
        diagnostic["cause"] = f"{type(exc).__name__}: {exc}"
        raise _fail(
            spec,
            archive,
            f"generic auto inference failed: {type(exc).__name__}: {exc}",
            diagnostic,
        ) from exc

    after = _sha256(archive)
    if before != after:
        raise _fail(spec, archive, "read-only generic inference changed the source tire archive", diagnostic)

    weights = VehicleTireMorphWeights(
        car_id=int(spec.car_id),
        wheel_spec_mode=str(spec.mode),
        tire_model_name=spec.tire_model_name,
        front=_as_axle_weights(spec.front, front),
        rear=_as_axle_weights(spec.rear, rear),
        mapping_revision=GENERIC_TIRE_AUTO_INFERENCE_REVISION,
    )
    report = VehicleTireMorphAutoInference(
        status="generic_auto_inference_accepted",
        revision=GENERIC_TIRE_AUTO_INFERENCE_REVISION,
        car_id=int(spec.car_id),
        tire_model_name=spec.tire_model_name,
        archive_path=str(archive),
        archive_sha256=before,
        archive_read_only_unchanged=True,
        modelbin_count=len(bake.modelbins),
        active_selector_indices=(0, 1),
        front=front,
        rear=rear,
        weights=weights,
        persistent_report_path=None,
        limitations=(
            "No TireModelName-specific whitelist or selector-role signature is used.",
            "Selectors 0 and 1 are inferred from the tire file's measured geometry response; selectors 2..4 remain zero in v1.",
            "The historical physical mapping is used only as a weak regularization prior, not as an admission gate.",
            "The inferred full geometry must reproduce stock tire width and outer diameter within global fail-closed tolerances.",
            "No per-car translation, rotation, or arbitrary scale offset is introduced; X scale is solved from the measured raw tire width and stock width.",
        ),
    )
    payload = report.as_dict()
    report_path = _write_report_best_effort(_persistent_report_path(spec.car_id), payload)
    if report_path is None:
        return report
    return VehicleTireMorphAutoInference(
        status=report.status,
        revision=report.revision,
        car_id=report.car_id,
        tire_model_name=report.tire_model_name,
        archive_path=report.archive_path,
        archive_sha256=report.archive_sha256,
        archive_read_only_unchanged=report.archive_read_only_unchanged,
        modelbin_count=report.modelbin_count,
        active_selector_indices=report.active_selector_indices,
        front=report.front,
        rear=report.rear,
        weights=report.weights,
        persistent_report_path=report_path,
        limitations=report.limitations,
    )
