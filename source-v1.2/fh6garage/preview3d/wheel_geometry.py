from __future__ import annotations

import json
import math
import os
import struct
from dataclasses import dataclass
from pathlib import Path

WHEEL_GEOMETRY_REVISION = 1


class WheelGeometryError(RuntimeError):
    pass


@dataclass(frozen=True)
class WheelGeometryResult:
    status: str
    revision: int
    wheel_instances: int
    repaired_primitives: int
    repaired_vertices: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _normal(value: object) -> str:
    return str(value or "").casefold().replace(" ", "").replace("-", "").replace("_", "")


def _read_glb(path: Path) -> tuple[dict, list[tuple[int, bytes]]]:
    raw = path.read_bytes()
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise WheelGeometryError("output is not a GLB file")
    version, total = struct.unpack_from("<II", raw, 4)
    if version != 2 or total != len(raw):
        raise WheelGeometryError("GLB header is inconsistent")
    chunks, document, cursor = [], None, 12
    while cursor < total:
        if cursor + 8 > total:
            raise WheelGeometryError("GLB chunk header is truncated")
        length, kind = struct.unpack_from("<II", raw, cursor)
        cursor += 8
        if cursor + length > total:
            raise WheelGeometryError("GLB chunk is truncated")
        payload = raw[cursor:cursor + length]
        cursor += length
        chunks.append((kind, payload))
        if kind == 0x4E4F534A:
            if document is not None:
                raise WheelGeometryError("GLB has multiple JSON chunks")
            document = json.loads(payload.rstrip(b" \x00").decode("utf-8"))
    if cursor != total or not isinstance(document, dict):
        raise WheelGeometryError("GLB JSON chunk is invalid")
    return document, chunks


def _write_glb(path: Path, document: dict, chunks: list[tuple[int, bytes]]) -> None:
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    rewritten = [(kind, encoded if kind == 0x4E4F534A else data) for kind, data in chunks]
    total = 12 + sum(8 + len(data) for _, data in rewritten)
    temp = path.with_name(path.name + f".{os.getpid()}.wheelgeo.tmp")
    try:
        with temp.open("wb") as out:
            out.write(b"glTF" + struct.pack("<II", 2, total))
            for kind, data in rewritten:
                out.write(struct.pack("<II", len(data), kind) + data)
        _read_glb(temp)
        temp.replace(path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _layout(document: dict, number: int, kind: str) -> tuple[int, int, int, dict]:
    try:
        accessor = document["accessors"][number]
        view = document["bufferViews"][accessor["bufferView"]]
    except (KeyError, IndexError, TypeError) as exc:
        raise WheelGeometryError("WheelStyle accessor is invalid") from exc
    if accessor.get("type") != kind or accessor.get("sparse") is not None or view.get("buffer", 0) != 0:
        raise WheelGeometryError("unsupported WheelStyle accessor layout")
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    return start, int(accessor["count"]), int(view.get("byteStride", 0)), accessor


def _vertices(document: dict, binary: bytearray, primitive: dict):
    try:
        position_number = primitive["attributes"]["POSITION"]
        index_number = primitive["indices"]
    except (KeyError, TypeError) as exc:
        raise WheelGeometryError("WheelStyle primitive is not indexed") from exc
    p_start, p_count, p_stride, p_accessor = _layout(document, position_number, "VEC3")
    if p_accessor.get("componentType") != 5126:
        raise WheelGeometryError("WheelStyle POSITION is not float32")
    p_stride = p_stride or 12
    i_start, i_count, i_stride, i_accessor = _layout(document, index_number, "SCALAR")
    formats = {5121: ("<B", 1), 5123: ("<H", 2), 5125: ("<I", 4)}
    try:
        fmt, size = formats[i_accessor["componentType"]]
    except (KeyError, TypeError) as exc:
        raise WheelGeometryError("WheelStyle index type is unsupported") from exc
    i_stride = i_stride or size
    indices = sorted({struct.unpack_from(fmt, binary, i_start + n * i_stride)[0] for n in range(i_count)})
    if not indices or indices[-1] >= p_count or p_stride < 12:
        raise WheelGeometryError("WheelStyle vertex layout is invalid")
    positions = [list(struct.unpack_from("<fff", binary, p_start + n * p_stride)) for n in indices]
    return position_number, p_start, p_stride, indices, positions


def _bounds(points: list[list[float]]) -> tuple[list[float], list[float]]:
    return [min(p[a] for p in points) for a in range(3)], [max(p[a] for p in points) for a in range(3)]


def _median(values: list[float]) -> float:
    values = sorted(values)
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def repair_wheelstyle_lateral_translation(glb_path: str | Path) -> WheelGeometryResult:
    """Repair mixed local/world lateral coordinates without name heuristics."""
    path = Path(glb_path)
    document, chunks = _read_glb(path)
    bins = [n for n, (kind, _) in enumerate(chunks) if kind == 0x004E4942]
    if len(bins) != 1:
        raise WheelGeometryError("GLB must have exactly one BIN chunk")
    bin_number = bins[0]
    binary = bytearray(chunks[bin_number][1])
    groups: dict[str, list[tuple[dict, dict, tuple]]] = {}
    for mesh in document.get("meshes") or []:
        if not isinstance(mesh, dict):
            continue
        extras = mesh.get("extras") if isinstance(mesh.get("extras"), dict) else {}
        if _normal(extras.get("kfps_part_type")) != "wheelstyle":
            continue
        identity, primitives = str(extras.get("kfps_instance_identity") or ""), mesh.get("primitives")
        if not identity or not isinstance(primitives, list) or len(primitives) != 1:
            raise WheelGeometryError("WheelStyle structural metadata is incomplete")
        groups.setdefault(identity, []).append((mesh, primitives[0], _vertices(document, binary, primitives[0])))

    repaired_primitives = repaired_vertices = 0
    for items in groups.values():
        measured, compact = [], []
        for mesh, primitive, layout in items:
            low, high = _bounds(layout[4])
            span = [high[a] - low[a] for a in range(3)]
            centre = (low[0] + high[0]) / 2
            measured.append((mesh, primitive, layout, span))
            if span[0] <= 0.15 and max(span[1:]) >= 0.15:
                compact.append(centre)
        if len(compact) < 2:
            continue
        target = _median(compact)
        if abs(target) < 0.35 or max(abs(value - target) for value in compact) > 0.12:
            continue
        for mesh, primitive, layout, span in measured:
            extras = mesh.get("extras") if isinstance(mesh.get("extras"), dict) else {}
            if str(extras.get("kfps_role") or "").casefold() == "hidden":
                continue
            if span[0] < 0.50 or span[0] < max(span[1:]) * 2:
                continue
            accessor_number, start, stride, indices, points = layout
            selected = [n for n, point in enumerate(points) if abs(point[0]) < abs(point[0] - target)]
            if not selected or len(selected) == len(points):
                continue
            shifted = [point[:] for point in points]
            for n in selected:
                shifted[n][0] += target
            low, high = _bounds(shifted)
            if high[0] - low[0] > 0.20 or not all(math.isfinite(v) for point in shifted for v in point):
                continue
            for n in selected:
                struct.pack_into("<f", binary, start + indices[n] * stride, shifted[n][0])
            document["accessors"][accessor_number]["min"] = low
            document["accessors"][accessor_number]["max"] = high
            mesh.setdefault("extras", {})["kfps_wheel_geometry_repair"] = "lateral_translation_v1"
            repaired_primitives += 1
            repaired_vertices += len(selected)
    if repaired_primitives:
        chunks[bin_number] = chunks[bin_number][0], bytes(binary)
        _write_glb(path, document, chunks)
        status = "applied"
    else:
        status = "no_confirmed_candidates"
    return WheelGeometryResult(status, WHEEL_GEOMETRY_REVISION, len(groups), repaired_primitives, repaired_vertices)
