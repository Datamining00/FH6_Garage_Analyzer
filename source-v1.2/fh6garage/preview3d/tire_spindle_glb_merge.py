from __future__ import annotations

from dataclasses import asdict, dataclass
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any, Mapping, Sequence


TIRE_SPINDLE_GLB_MERGE_REVISION = "wheelstyle_native_matrix_tire_glb_merge_v1"
_EXPECTED_SPINDLES = ("spindleLF", "spindleRF", "spindleLR", "spindleRR")
_JSON_CHUNK = 0x4E4F534A
_BIN_CHUNK = 0x004E4942


class TireSpindleGlbMergeError(RuntimeError):
    """Raised when a derived tire cannot be merged without guessing."""


@dataclass(frozen=True)
class MergedTireNode:
    spindle_bone: str
    axle: str
    side: str
    source_tire_glb: str
    source_tire_glb_sha256: str
    node_index: int
    mesh_index: int
    matrix: tuple[float, ...]

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["matrix"] = list(self.matrix)
        return payload


@dataclass(frozen=True)
class TireSpindleGlbMergeReport:
    status: str
    revision: str
    car_id: int
    source_vehicle_glb: str
    source_vehicle_glb_sha256: str
    source_vehicle_glb_unchanged: bool
    output_vehicle_glb: str
    output_vehicle_glb_sha256: str
    merged_tire_nodes: tuple[MergedTireNode, ...]
    native_carbin_transform_only: bool
    procedural_translation_applied: bool
    procedural_rotation_applied: bool
    procedural_scale_applied: bool
    spindle_attachment_applied: bool
    trial_vehicle_glb_ready: bool
    production_renderer_enabled: bool
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fh6_native_tire_spindle_glb_merge_v1",
            "status": self.status,
            "revision": self.revision,
            "car_id": self.car_id,
            "source_vehicle_glb": self.source_vehicle_glb,
            "source_vehicle_glb_sha256": self.source_vehicle_glb_sha256,
            "source_vehicle_glb_unchanged": self.source_vehicle_glb_unchanged,
            "output_vehicle_glb": self.output_vehicle_glb,
            "output_vehicle_glb_sha256": self.output_vehicle_glb_sha256,
            "merged_tire_nodes": [item.as_dict() for item in self.merged_tire_nodes],
            "native_carbin_transform_only": self.native_carbin_transform_only,
            "procedural_translation_applied": self.procedural_translation_applied,
            "procedural_rotation_applied": self.procedural_rotation_applied,
            "procedural_scale_applied": self.procedural_scale_applied,
            "spindle_attachment_applied": self.spindle_attachment_applied,
            "trial_vehicle_glb_ready": self.trial_vehicle_glb_ready,
            "production_renderer_enabled": self.production_renderer_enabled,
            "limitations": list(self.limitations),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pad4(raw: bytes, padding: bytes = b"\x00") -> bytes:
    return raw + padding * ((-len(raw)) % 4)


def _read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TireSpindleGlbMergeError(f"could not read GLB {path}: {exc}") from exc
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise TireSpindleGlbMergeError(f"not a GLB file: {path}")
    version, total = struct.unpack_from("<II", raw, 4)
    if version != 2 or total != len(raw):
        raise TireSpindleGlbMergeError(
            f"unsupported or truncated GLB {path}: version={version}, declared={total}, actual={len(raw)}"
        )

    document: dict[str, Any] | None = None
    binary: bytes | None = None
    offset = 12
    while offset + 8 <= total:
        length, chunk_type = struct.unpack_from("<II", raw, offset)
        offset += 8
        if offset + length > total:
            raise TireSpindleGlbMergeError(f"GLB chunk extends past EOF: {path}")
        chunk = raw[offset:offset + length]
        offset += length
        if chunk_type == _JSON_CHUNK:
            if document is not None:
                raise TireSpindleGlbMergeError(f"GLB has more than one JSON chunk: {path}")
            try:
                parsed = json.loads(chunk.rstrip(b" \x00").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TireSpindleGlbMergeError(f"invalid GLB JSON in {path}: {exc}") from exc
            if not isinstance(parsed, dict):
                raise TireSpindleGlbMergeError(f"GLB JSON root is not an object: {path}")
            document = parsed
        elif chunk_type == _BIN_CHUNK:
            if binary is not None:
                raise TireSpindleGlbMergeError(f"GLB has more than one BIN chunk: {path}")
            binary = bytes(chunk)
        else:
            raise TireSpindleGlbMergeError(
                f"GLB contains unsupported chunk type 0x{chunk_type:08X}; merge refuses to drop it: {path}"
            )
    if offset != total or document is None or binary is None:
        raise TireSpindleGlbMergeError(f"GLB has incomplete JSON/BIN structure: {path}")
    return document, binary


def _write_glb(path: Path, document: Mapping[str, Any], binary: bytes) -> None:
    doc = copy.deepcopy(dict(document))
    buffers = doc.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or not isinstance(buffers[0], dict):
        raise TireSpindleGlbMergeError("merged GLB must contain exactly one embedded buffer")
    buffers[0].pop("uri", None)
    buffers[0]["byteLength"] = len(binary)
    json_raw = _pad4(json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), b" ")
    bin_raw = _pad4(binary)
    total = 12 + 8 + len(json_raw) + 8 + len(bin_raw)
    payload = (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(json_raw), b"JSON")
        + json_raw
        + struct.pack("<I4s", len(bin_raw), b"BIN\x00")
        + bin_raw
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    except OSError as exc:
        raise TireSpindleGlbMergeError(f"could not write merged GLB {path}: {exc}") from exc


def _finite_affine_matrix(raw: object, *, bone: str) -> tuple[float, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)) or len(raw) != 16:
        raise TireSpindleGlbMergeError(f"{bone}: attachment matrix must contain exactly 16 values")
    matrix = tuple(float(value) for value in raw)
    if not all(math.isfinite(value) for value in matrix):
        raise TireSpindleGlbMergeError(f"{bone}: attachment matrix contains non-finite values")
    # ForzaTech/System.Numerics stores translation in M41/M42/M43.  The first
    # production trial accepts affine matrices only.  Feeding the same flattened
    # 16 values to glTF represents the transposed column-vector transform because
    # glTF serializes matrices column-major; no extra procedural transform is added.
    if any(abs(matrix[index]) > 1.0e-6 for index in (3, 7, 11)) or abs(matrix[15] - 1.0) > 1.0e-6:
        raise TireSpindleGlbMergeError(f"{bone}: native matrix is not an affine ForzaTech transform")
    return matrix


def _validate_contract(contract: Mapping[str, Any]) -> tuple[int, tuple[Mapping[str, Any], ...]]:
    if str(contract.get("format") or "") != "fh6_native_tire_spindle_attachment_contract_v2":
        raise TireSpindleGlbMergeError("unsupported spindle attachment contract format")
    if str(contract.get("status") or "") != "spindle_attachment_contract_ready":
        raise TireSpindleGlbMergeError("spindle attachment contract is not ready")
    if not bool(contract.get("spindle_attachment_contract_ready")):
        raise TireSpindleGlbMergeError("spindle attachment contract readiness flag is false")
    if bool(contract.get("spindle_attachment_applied")) or bool(contract.get("production_renderer_enabled")):
        raise TireSpindleGlbMergeError("spindle contract was unexpectedly already applied/enabled")
    if not bool(contract.get("native_carbin_transform_only")):
        raise TireSpindleGlbMergeError("spindle contract is not native-transform-only")
    if any(bool(contract.get(key)) for key in (
        "procedural_translation_applied",
        "procedural_rotation_applied",
        "procedural_scale_applied",
    )):
        raise TireSpindleGlbMergeError("spindle contract contains a procedural placement transform")
    if int(contract.get("attachment_part_type", -1)) != 44:
        raise TireSpindleGlbMergeError("spindle contract is not based on CCarParts_WheelStyle (44)")
    car_id = int(contract.get("car_id", 0))
    if car_id <= 0:
        raise TireSpindleGlbMergeError("spindle contract has no valid Car ID")
    attachments = contract.get("attachments")
    if not isinstance(attachments, list) or len(attachments) != 4:
        raise TireSpindleGlbMergeError("spindle contract must contain exactly four attachments")
    by_bone: dict[str, Mapping[str, Any]] = {}
    for item in attachments:
        if not isinstance(item, Mapping):
            raise TireSpindleGlbMergeError("spindle attachment entry is not an object")
        bone = str(item.get("spindle_bone") or "")
        if bone not in _EXPECTED_SPINDLES:
            raise TireSpindleGlbMergeError(f"unexpected spindle bone in contract: {bone!r}")
        if bone in by_bone:
            raise TireSpindleGlbMergeError(f"duplicate spindle attachment: {bone}")
        _finite_affine_matrix(item.get("carbin_transform_matrix_row_major"), bone=bone)
        tire_path = Path(str(item.get("derived_tire_glb_path") or "")).expanduser()
        if not str(tire_path):
            raise TireSpindleGlbMergeError(f"{bone}: derivative tire GLB path is empty")
        by_bone[bone] = item
    missing = [bone for bone in _EXPECTED_SPINDLES if bone not in by_bone]
    if missing:
        raise TireSpindleGlbMergeError("spindle contract is missing: " + ", ".join(missing))
    return car_id, tuple(by_bone[bone] for bone in _EXPECTED_SPINDLES)


def _validate_vehicle_document(document: Mapping[str, Any]) -> int:
    buffers = document.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or not isinstance(buffers[0], Mapping):
        raise TireSpindleGlbMergeError("vehicle GLB must use exactly one embedded buffer")
    if buffers[0].get("uri"):
        raise TireSpindleGlbMergeError("vehicle GLB uses an external buffer")
    scenes = document.get("scenes")
    scene_index = int(document.get("scene", 0))
    if not isinstance(scenes, list) or scene_index < 0 or scene_index >= len(scenes):
        raise TireSpindleGlbMergeError("vehicle GLB has no valid default scene")
    scene = scenes[scene_index]
    if not isinstance(scene, Mapping):
        raise TireSpindleGlbMergeError("vehicle GLB default scene is invalid")
    return scene_index


def _validate_derivative_document(document: Mapping[str, Any], *, path: Path) -> None:
    buffers = document.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or not isinstance(buffers[0], Mapping):
        raise TireSpindleGlbMergeError(f"derivative tire GLB must use one embedded buffer: {path}")
    if buffers[0].get("uri"):
        raise TireSpindleGlbMergeError(f"derivative tire GLB uses an external buffer: {path}")
    for unsupported in ("animations", "skins", "cameras", "images", "textures", "samplers", "materials"):
        if document.get(unsupported):
            raise TireSpindleGlbMergeError(
                f"derivative tire GLB contains unsupported {unsupported}; first merge refuses to guess: {path}"
            )
    meshes = document.get("meshes")
    nodes = document.get("nodes")
    scenes = document.get("scenes")
    scene_index = int(document.get("scene", 0))
    if not isinstance(meshes, list) or len(meshes) != 1:
        raise TireSpindleGlbMergeError(f"derivative tire GLB must contain exactly one mesh: {path}")
    if not isinstance(nodes, list) or len(nodes) != 1 or not isinstance(nodes[0], Mapping):
        raise TireSpindleGlbMergeError(f"derivative tire GLB must contain exactly one node: {path}")
    if int(nodes[0].get("mesh", -1)) != 0:
        raise TireSpindleGlbMergeError(f"derivative tire node does not reference mesh 0: {path}")
    if any(key in nodes[0] for key in ("matrix", "translation", "rotation", "scale", "children", "skin", "camera")):
        raise TireSpindleGlbMergeError(f"derivative tire node contains an unexpected transform/graph link: {path}")
    if not isinstance(scenes, list) or scene_index < 0 or scene_index >= len(scenes):
        raise TireSpindleGlbMergeError(f"derivative tire GLB has no valid scene: {path}")
    scene = scenes[scene_index]
    if not isinstance(scene, Mapping) or list(scene.get("nodes") or ()) != [0]:
        raise TireSpindleGlbMergeError(f"derivative tire scene is not a single root node: {path}")


def _append_derivative(
    vehicle_document: dict[str, Any],
    vehicle_binary: bytes,
    derivative_document: Mapping[str, Any],
    derivative_binary: bytes,
    attachment: Mapping[str, Any],
) -> tuple[bytes, int, int]:
    # The generated tire derivative contains POSITION+indices only and one mesh.
    # Remap its accessor graph into the vehicle's single BIN chunk without touching
    # existing vehicle indices, materials, textures, nodes, or meshes.
    vehicle_binary = _pad4(vehicle_binary)
    binary_base = len(vehicle_binary)
    merged_binary = vehicle_binary + derivative_binary

    target_views = vehicle_document.setdefault("bufferViews", [])
    target_accessors = vehicle_document.setdefault("accessors", [])
    target_meshes = vehicle_document.setdefault("meshes", [])
    target_nodes = vehicle_document.setdefault("nodes", [])
    if not all(isinstance(value, list) for value in (target_views, target_accessors, target_meshes, target_nodes)):
        raise TireSpindleGlbMergeError("vehicle GLB has malformed bufferViews/accessors/meshes/nodes")

    view_base = len(target_views)
    for raw_view in derivative_document.get("bufferViews") or ():
        if not isinstance(raw_view, Mapping) or int(raw_view.get("buffer", 0)) != 0:
            raise TireSpindleGlbMergeError("derivative tire bufferView does not reference embedded buffer 0")
        view = copy.deepcopy(dict(raw_view))
        view["buffer"] = 0
        view["byteOffset"] = binary_base + int(view.get("byteOffset", 0))
        target_views.append(view)

    accessor_base = len(target_accessors)
    derivative_accessors = derivative_document.get("accessors") or ()
    for raw_accessor in derivative_accessors:
        if not isinstance(raw_accessor, Mapping):
            raise TireSpindleGlbMergeError("derivative tire accessor is invalid")
        if raw_accessor.get("sparse") is not None:
            raise TireSpindleGlbMergeError("sparse derivative tire accessors are not supported")
        accessor = copy.deepcopy(dict(raw_accessor))
        if "bufferView" not in accessor:
            raise TireSpindleGlbMergeError("derivative tire accessor has no bufferView")
        accessor["bufferView"] = view_base + int(accessor["bufferView"])
        target_accessors.append(accessor)

    raw_mesh = derivative_document["meshes"][0]
    if not isinstance(raw_mesh, Mapping):
        raise TireSpindleGlbMergeError("derivative tire mesh is invalid")
    mesh = copy.deepcopy(dict(raw_mesh))
    primitives = mesh.get("primitives")
    if not isinstance(primitives, list) or not primitives:
        raise TireSpindleGlbMergeError("derivative tire mesh has no primitives")
    for primitive in primitives:
        if not isinstance(primitive, dict):
            raise TireSpindleGlbMergeError("derivative tire primitive is invalid")
        attrs = primitive.get("attributes")
        if not isinstance(attrs, dict) or "POSITION" not in attrs:
            raise TireSpindleGlbMergeError("derivative tire primitive has no POSITION accessor")
        for semantic, value in tuple(attrs.items()):
            attrs[semantic] = accessor_base + int(value)
        if "indices" in primitive:
            primitive["indices"] = accessor_base + int(primitive["indices"])
        if "material" in primitive or "targets" in primitive:
            raise TireSpindleGlbMergeError("first tire merge refuses derivative material/morph targets")
    mesh_index = len(target_meshes)
    target_meshes.append(mesh)

    bone = str(attachment.get("spindle_bone") or "")
    matrix = _finite_affine_matrix(
        attachment.get("carbin_transform_matrix_row_major"), bone=bone
    )
    node_index = len(target_nodes)
    target_nodes.append(
        {
            "name": f"FH6 Native Tire {bone}",
            "mesh": mesh_index,
            "matrix": list(matrix),
            "extras": {
                "fh6_native_tire_trial": True,
                "spindle_bone": bone,
                "axle": str(attachment.get("axle") or ""),
                "side": str(attachment.get("side") or ""),
                "source_tire_entry": str(attachment.get("derived_tire_entry") or ""),
                "placement_revision": TIRE_SPINDLE_GLB_MERGE_REVISION,
            },
        }
    )
    return merged_binary, node_index, mesh_index


def merge_tire_spindle_trial_glb(
    vehicle_glb_path: str | Path,
    attachment_contract: Mapping[str, Any],
    output_path: str | Path,
) -> TireSpindleGlbMergeReport:
    """Merge four gated tire derivative GLBs into a separate vehicle GLB.

    The existing vehicle GLB and all FH6 source archives remain read-only.  The
    exact WheelStyle matrices serialized in the v2 spindle contract are attached
    to four new root nodes.  No track, spacer, rotation, scale, or car-specific
    offset formula is evaluated in this stage.
    """
    source = Path(vehicle_glb_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    if not source.is_file():
        raise TireSpindleGlbMergeError(f"source vehicle GLB does not exist: {source}")
    if source == output:
        raise TireSpindleGlbMergeError("merged tire trial must not overwrite the source vehicle GLB")

    car_id, attachments = _validate_contract(attachment_contract)
    source_sha_before = _sha256(source)
    vehicle_document, vehicle_binary = _read_glb(source)
    scene_index = _validate_vehicle_document(vehicle_document)
    document = copy.deepcopy(vehicle_document)
    binary = bytes(vehicle_binary)
    scene = document["scenes"][scene_index]
    if "nodes" not in scene:
        scene["nodes"] = []
    if not isinstance(scene["nodes"], list):
        raise TireSpindleGlbMergeError("vehicle default scene nodes field is invalid")

    merged_nodes: list[MergedTireNode] = []
    for attachment in attachments:
        bone = str(attachment.get("spindle_bone") or "")
        derivative_path = Path(str(attachment.get("derived_tire_glb_path") or "")).expanduser().resolve()
        if not derivative_path.is_file():
            raise TireSpindleGlbMergeError(f"{bone}: derivative tire GLB does not exist: {derivative_path}")
        derivative_sha = _sha256(derivative_path)
        derivative_document, derivative_binary = _read_glb(derivative_path)
        _validate_derivative_document(derivative_document, path=derivative_path)
        binary, node_index, mesh_index = _append_derivative(
            document,
            binary,
            derivative_document,
            derivative_binary,
            attachment,
        )
        scene["nodes"].append(node_index)
        merged_nodes.append(
            MergedTireNode(
                spindle_bone=bone,
                axle=str(attachment.get("axle") or ""),
                side=str(attachment.get("side") or ""),
                source_tire_glb=str(derivative_path),
                source_tire_glb_sha256=derivative_sha,
                node_index=node_index,
                mesh_index=mesh_index,
                matrix=_finite_affine_matrix(
                    attachment.get("carbin_transform_matrix_row_major"), bone=bone
                ),
            )
        )

    _write_glb(output, document, binary)
    # Re-open the result so a malformed write cannot be reported as ready.
    merged_document, _merged_binary = _read_glb(output)
    if len(merged_document.get("nodes") or ()) < len(vehicle_document.get("nodes") or ()) + 4:
        output.unlink(missing_ok=True)
        raise TireSpindleGlbMergeError("merged GLB did not retain all four new tire nodes")

    source_sha_after = _sha256(source)
    if source_sha_after != source_sha_before:
        output.unlink(missing_ok=True)
        raise TireSpindleGlbMergeError("read-only tire merge changed the source vehicle GLB")

    return TireSpindleGlbMergeReport(
        status="spindle_tire_trial_glb_ready",
        revision=TIRE_SPINDLE_GLB_MERGE_REVISION,
        car_id=car_id,
        source_vehicle_glb=str(source),
        source_vehicle_glb_sha256=source_sha_before,
        source_vehicle_glb_unchanged=True,
        output_vehicle_glb=str(output),
        output_vehicle_glb_sha256=_sha256(output),
        merged_tire_nodes=tuple(merged_nodes),
        native_carbin_transform_only=True,
        procedural_translation_applied=False,
        procedural_rotation_applied=False,
        procedural_scale_applied=False,
        spindle_attachment_applied=True,
        trial_vehicle_glb_ready=True,
        production_renderer_enabled=False,
        limitations=(
            "This is a derived visual trial GLB; the main viewer production path is not enabled yet.",
            "Existing wheel/rim/brake geometry is preserved. This stage adds native tire geometry only.",
            "Visual wheel-arch fit and left/right orientation must be checked on the real converted FXX before promotion beyond the trial gate.",
        ),
    )
