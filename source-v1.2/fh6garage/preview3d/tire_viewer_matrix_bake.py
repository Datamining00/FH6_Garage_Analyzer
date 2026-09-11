from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import struct
from typing import Any, Mapping, Sequence

import numpy as np


TIRE_VIEWER_MATRIX_BAKE_REVISION = "native_tire_kfps_render_space_bake_v2"
_EXPECTED_SPINDLES = ("spindleLF", "spindleRF", "spindleLR", "spindleRR")
_JSON_CHUNK = 0x4E4F534A
_BIN_CHUNK = 0x004E4942
_KFPS_RENDER_SPACE_RULE = "(-x,y,z)"


class TireViewerMatrixBakeError(RuntimeError):
    """Raised when native tire geometry cannot be baked into KFPS render space exactly."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pad4(raw: bytes, padding: bytes = b"\x00") -> bytes:
    return raw + padding * ((-len(raw)) % 4)


def _read_glb(path: Path) -> tuple[dict[str, Any], bytearray]:
    raw = path.read_bytes()
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise TireViewerMatrixBakeError(f"not a GLB file: {path}")
    version, total = struct.unpack_from("<II", raw, 4)
    if version != 2 or total != len(raw):
        raise TireViewerMatrixBakeError(
            f"unsupported or truncated GLB {path}: version={version}, declared={total}, actual={len(raw)}"
        )

    document: dict[str, Any] | None = None
    binary: bytearray | None = None
    offset = 12
    while offset + 8 <= total:
        length, chunk_type = struct.unpack_from("<II", raw, offset)
        offset += 8
        if offset + length > total:
            raise TireViewerMatrixBakeError(f"GLB chunk extends past EOF: {path}")
        chunk = raw[offset:offset + length]
        offset += length
        if chunk_type == _JSON_CHUNK:
            if document is not None:
                raise TireViewerMatrixBakeError(f"GLB has more than one JSON chunk: {path}")
            parsed = json.loads(chunk.rstrip(b" \x00").decode("utf-8"))
            if not isinstance(parsed, dict):
                raise TireViewerMatrixBakeError(f"GLB JSON root is not an object: {path}")
            document = parsed
        elif chunk_type == _BIN_CHUNK:
            if binary is not None:
                raise TireViewerMatrixBakeError(f"GLB has more than one BIN chunk: {path}")
            binary = bytearray(chunk)
        else:
            raise TireViewerMatrixBakeError(
                f"GLB contains unsupported chunk type 0x{chunk_type:08X}: {path}"
            )
    if offset != total or document is None or binary is None:
        raise TireViewerMatrixBakeError(f"GLB has incomplete JSON/BIN structure: {path}")
    return document, binary


def _write_glb(path: Path, document: Mapping[str, Any], binary: bytearray) -> None:
    doc = dict(document)
    buffers = doc.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or not isinstance(buffers[0], dict):
        raise TireViewerMatrixBakeError("viewer-compatible GLB must use exactly one embedded buffer")
    buffers[0].pop("uri", None)
    buffers[0]["byteLength"] = len(binary)

    json_raw = _pad4(
        json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        b" ",
    )
    bin_raw = _pad4(bytes(binary))
    total = 12 + 8 + len(json_raw) + 8 + len(bin_raw)
    payload = (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(json_raw), b"JSON")
        + json_raw
        + struct.pack("<I4s", len(bin_raw), b"BIN\x00")
        + bin_raw
    )
    temporary = path.with_suffix(path.suffix + ".matrix-bake.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _glTF_matrix(raw: object, *, bone: str) -> np.ndarray:
    if (
        not isinstance(raw, Sequence)
        or isinstance(raw, (str, bytes, bytearray))
        or len(raw) != 16
    ):
        raise TireViewerMatrixBakeError(f"{bone}: native node matrix must contain exactly 16 values")
    values = np.asarray([float(value) for value in raw], dtype=np.float64)
    if not np.isfinite(values).all():
        raise TireViewerMatrixBakeError(f"{bone}: native node matrix contains non-finite values")
    # glTF serializes matrices column-major. The merge stage deliberately writes
    # the flattened ForzaTech/System.Numerics row-major values unchanged, which is
    # the correct transpose for glTF's column-vector convention.
    matrix = values.reshape((4, 4), order="F")
    if not np.allclose(matrix[3], np.array([0.0, 0.0, 0.0, 1.0]), atol=1.0e-6):
        raise TireViewerMatrixBakeError(f"{bone}: native node matrix is not affine")
    return matrix


def _float_vec3_accessor(
    document: Mapping[str, Any],
    binary: bytearray,
    accessor_index: int,
) -> tuple[dict[str, Any], int, int, np.ndarray]:
    try:
        accessor = document["accessors"][accessor_index]
        view = document["bufferViews"][int(accessor["bufferView"])]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise TireViewerMatrixBakeError(f"invalid accessor {accessor_index}") from exc
    if not isinstance(accessor, dict) or not isinstance(view, Mapping):
        raise TireViewerMatrixBakeError(f"invalid accessor graph for {accessor_index}")
    if (
        int(accessor.get("componentType", 0)) != 5126
        or str(accessor.get("type") or "") != "VEC3"
        or accessor.get("sparse") is not None
    ):
        raise TireViewerMatrixBakeError(
            f"accessor {accessor_index}: expected a non-sparse FLOAT VEC3 accessor"
        )
    if int(view.get("buffer", 0)) != 0:
        raise TireViewerMatrixBakeError(f"accessor {accessor_index}: external buffers are not supported")

    count = int(accessor.get("count", 0))
    stride = int(view.get("byteStride", 12))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    if count < 0 or stride < 12:
        raise TireViewerMatrixBakeError(f"accessor {accessor_index}: invalid count/stride")
    end = start + (count - 1) * stride + 12 if count else start
    if start < 0 or end > len(binary):
        raise TireViewerMatrixBakeError(f"accessor {accessor_index}: data range is outside the BIN chunk")

    values = np.empty((count, 3), dtype=np.float64)
    for index in range(count):
        values[index] = struct.unpack_from("<fff", binary, start + index * stride)
    return accessor, start, stride, values


def _index_accessor(
    document: Mapping[str, Any],
    binary: bytearray,
    accessor_index: int,
) -> tuple[int, int, int, str, int]:
    try:
        accessor = document["accessors"][accessor_index]
        view = document["bufferViews"][int(accessor["bufferView"])]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise TireViewerMatrixBakeError(f"invalid index accessor {accessor_index}") from exc
    if not isinstance(accessor, Mapping) or not isinstance(view, Mapping):
        raise TireViewerMatrixBakeError(f"invalid index accessor graph for {accessor_index}")
    if str(accessor.get("type") or "") != "SCALAR" or accessor.get("sparse") is not None:
        raise TireViewerMatrixBakeError(
            f"accessor {accessor_index}: expected a non-sparse SCALAR index accessor"
        )
    if int(view.get("buffer", 0)) != 0:
        raise TireViewerMatrixBakeError(f"accessor {accessor_index}: external buffers are not supported")
    formats = {
        5121: ("<B", 1),
        5123: ("<H", 2),
        5125: ("<I", 4),
    }
    try:
        fmt, size = formats[int(accessor.get("componentType", 0))]
    except (KeyError, TypeError, ValueError) as exc:
        raise TireViewerMatrixBakeError(
            f"accessor {accessor_index}: unsupported index component type"
        ) from exc
    count = int(accessor.get("count", 0))
    stride = int(view.get("byteStride", size))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    if count <= 0 or count % 3 != 0 or stride < size:
        raise TireViewerMatrixBakeError(
            f"accessor {accessor_index}: tire indices must be a non-empty triangle list"
        )
    end = start + (count - 1) * stride + size
    if start < 0 or end > len(binary):
        raise TireViewerMatrixBakeError(f"accessor {accessor_index}: data range is outside the BIN chunk")
    return start, stride, count, fmt, size


def _write_vec3(binary: bytearray, start: int, stride: int, values: np.ndarray) -> None:
    for index, (x_value, y_value, z_value) in enumerate(
        np.asarray(values, dtype=np.float32)
    ):
        struct.pack_into(
            "<fff",
            binary,
            start + index * stride,
            float(x_value),
            float(y_value),
            float(z_value),
        )


def _reverse_triangle_winding(
    document: Mapping[str, Any],
    binary: bytearray,
    accessor_index: int,
) -> int:
    start, stride, count, fmt, _size = _index_accessor(
        document,
        binary,
        accessor_index,
    )
    for index in range(0, count, 3):
        second = struct.unpack_from(fmt, binary, start + (index + 1) * stride)[0]
        third = struct.unpack_from(fmt, binary, start + (index + 2) * stride)[0]
        struct.pack_into(fmt, binary, start + (index + 1) * stride, third)
        struct.pack_into(fmt, binary, start + (index + 2) * stride, second)
    return count // 3


def bake_native_tire_trial_node_matrices(glb_path: str | Path) -> dict[str, object]:
    """Bake native tire matrices into the same render space as KFPS chassis meshes.

    KFPS ChassisConverter applies the carbin/bone transform and then emits
    ``(-X, Y, Z)`` positions, reflects normal X, and reverses triangle winding.
    FinalVerify1 consumes those converter meshes as already-world-positioned geometry
    and does not traverse the glTF node transform graph. The native tire preview must
    therefore reproduce that exact converter coordinate convention after baking the
    four validated WheelStyle matrices. This is a format-space conversion, not a
    per-car placement correction.
    """
    path = Path(glb_path).expanduser().resolve()
    if not path.is_file():
        raise TireViewerMatrixBakeError(f"GLB does not exist: {path}")
    sha_before = _sha256(path)
    document, binary = _read_glb(path)
    nodes = document.get("nodes") or []
    meshes = document.get("meshes") or []
    if not isinstance(nodes, list) or not isinstance(meshes, list):
        raise TireViewerMatrixBakeError("GLB has malformed nodes/meshes")

    targets: list[tuple[int, dict[str, Any]]] = []
    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        extras = node.get("extras") or {}
        if isinstance(extras, Mapping) and extras.get("fh6_native_tire_trial") is True:
            targets.append((node_index, node))
    if len(targets) != 4:
        raise TireViewerMatrixBakeError(
            f"expected exactly four native tire trial nodes, found {len(targets)}"
        )

    bones: list[str] = []
    mesh_indices: list[int] = []
    for _node_index, node in targets:
        extras = node.get("extras") or {}
        bone = str(extras.get("spindle_bone") or "")
        bones.append(bone)
        mesh_indices.append(int(node.get("mesh", -1)))
    if set(bones) != set(_EXPECTED_SPINDLES) or len(set(bones)) != 4:
        raise TireViewerMatrixBakeError(f"unexpected native tire spindle set: {bones}")
    if (
        len(set(mesh_indices)) != 4
        or any(index < 0 or index >= len(meshes) for index in mesh_indices)
    ):
        raise TireViewerMatrixBakeError("native tire nodes must reference four unique valid meshes")

    for mesh_index in mesh_indices:
        references = sum(
            1
            for node in nodes
            if isinstance(node, Mapping) and int(node.get("mesh", -999999)) == mesh_index
        )
        if references != 1:
            raise TireViewerMatrixBakeError(
                f"native tire mesh {mesh_index} must have exactly one node reference; found {references}"
            )

    transformed_vertices = 0
    reversed_triangles = 0
    original_matrices: dict[str, list[float]] = {}
    for _node_index, node in targets:
        extras = dict(node.get("extras") or {})
        bone = str(extras.get("spindle_bone") or "")
        original_matrix = [float(value) for value in node.get("matrix") or ()]
        matrix = _glTF_matrix(original_matrix, bone=bone)
        original_matrices[bone] = original_matrix
        mesh = meshes[int(node["mesh"])]
        if not isinstance(mesh, Mapping):
            raise TireViewerMatrixBakeError(f"{bone}: referenced mesh is invalid")

        primitives = mesh.get("primitives") or ()
        if not isinstance(primitives, Sequence) or not primitives:
            raise TireViewerMatrixBakeError(f"{bone}: referenced mesh has no primitives")
        for primitive in primitives:
            if not isinstance(primitive, Mapping):
                raise TireViewerMatrixBakeError(f"{bone}: primitive is invalid")
            if int(primitive.get("mode", 4)) != 4:
                raise TireViewerMatrixBakeError(f"{bone}: native tire primitive is not a triangle list")
            attributes = primitive.get("attributes") or {}
            if "POSITION" not in attributes:
                raise TireViewerMatrixBakeError(f"{bone}: native tire primitive has no POSITION")
            if "indices" not in primitive:
                raise TireViewerMatrixBakeError(f"{bone}: native tire primitive is not indexed")

            accessor, start, stride, positions = _float_vec3_accessor(
                document,
                binary,
                int(attributes["POSITION"]),
            )
            homogeneous = np.concatenate(
                (positions, np.ones((len(positions), 1), dtype=np.float64)),
                axis=1,
            )
            render_positions = (matrix @ homogeneous.T).T[:, :3]
            # Exact KFPS ChassisConverter render-coordinate conversion.
            render_positions[:, 0] *= -1.0
            if not np.isfinite(render_positions).all():
                raise TireViewerMatrixBakeError(f"{bone}: transformed POSITION contains non-finite values")
            _write_vec3(binary, start, stride, render_positions)
            if len(render_positions):
                accessor["min"] = [float(value) for value in render_positions.min(axis=0)]
                accessor["max"] = [float(value) for value in render_positions.max(axis=0)]
            transformed_vertices += len(render_positions)

            if "NORMAL" in attributes:
                _normal_accessor, normal_start, normal_stride, normals = _float_vec3_accessor(
                    document,
                    binary,
                    int(attributes["NORMAL"]),
                )
                try:
                    normal_matrix = np.linalg.inv(matrix[:3, :3]).T
                except np.linalg.LinAlgError as exc:
                    raise TireViewerMatrixBakeError(f"{bone}: native normal matrix is singular") from exc
                render_normals = (normal_matrix @ normals.T).T
                render_normals[:, 0] *= -1.0
                lengths = np.linalg.norm(render_normals, axis=1)
                valid = lengths > 0.0
                render_normals[valid] /= lengths[valid, None]
                if not np.isfinite(render_normals).all():
                    raise TireViewerMatrixBakeError(f"{bone}: transformed NORMAL contains non-finite values")
                _write_vec3(binary, normal_start, normal_stride, render_normals)

            # Reflecting one axis changes handedness. KFPS ChassisConverter performs
            # the equivalent B/C swap in CleanTriangleIndices(), so mirror that exact
            # triangle-winding rule for the derived tire primitive.
            reversed_triangles += _reverse_triangle_winding(
                document,
                binary,
                int(primitive["indices"]),
            )

        node.pop("matrix", None)
        extras["fh6_viewer_matrix_baked"] = True
        extras["fh6_viewer_matrix_bake_revision"] = TIRE_VIEWER_MATRIX_BAKE_REVISION
        extras["fh6_kfps_render_space_reflection_applied"] = True
        extras["fh6_kfps_render_space_rule"] = _KFPS_RENDER_SPACE_RULE
        node["extras"] = extras

    _write_glb(path, document, binary)
    sha_after = _sha256(path)
    return {
        "format": "fh6_native_tire_viewer_matrix_bake_v2",
        "status": "native_tire_trial_node_matrices_baked",
        "revision": TIRE_VIEWER_MATRIX_BAKE_REVISION,
        "glb_path": str(path),
        "sha256_before": sha_before,
        "sha256_after": sha_after,
        "node_count": 4,
        "vertex_count": int(transformed_vertices),
        "triangle_winding_reversed_count": int(reversed_triangles),
        "spindles": list(bones),
        "original_native_matrices": original_matrices,
        "native_matrix_only": False,
        "native_matrix_and_kfps_render_space_only": True,
        "kfps_render_space_reflection_applied": True,
        "kfps_render_space_rule": _KFPS_RENDER_SPACE_RULE,
        "procedural_translation_applied": False,
        "procedural_rotation_applied": False,
        "procedural_scale_applied": False,
    }
