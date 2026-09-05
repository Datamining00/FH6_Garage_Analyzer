from __future__ import annotations

import json
import os
import struct
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .wheel_mesh_diagnostic import MeshStructureRecord, parse_modelbin_mesh_structures

WHEEL_VISIBILITY_REVISION = 1
WHEEL_MOTION_SIGNATURE = "wheelstyle_transparent_shadow_notshadow_noatoc_v1"


class WheelVisibilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class WheelVisibilityResult:
    status: str
    revision: int
    wheel_sources: int
    wheel_instances: int
    mapped_primitives: int
    motion_primitives_hidden: int
    already_hidden_primitives: int
    signature: str

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "revision": self.revision,
            "wheel_sources": self.wheel_sources,
            "wheel_instances": self.wheel_instances,
            "mapped_primitives": self.mapped_primitives,
            "motion_primitives_hidden": self.motion_primitives_hidden,
            "already_hidden_primitives": self.already_hidden_primitives,
            "signature": self.signature,
        }


def _normalize_part_type(value: object) -> str:
    return str(value or "").casefold().replace(" ", "").replace("-", "").replace("_", "")


def _canonical_source(value: object) -> str:
    return str(value or "").replace("\\", "/").casefold()


def _read_glb(path: Path) -> tuple[dict, list[tuple[int, bytes]]]:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise WheelVisibilityError("cached output is not a GLB file")
    version, total = struct.unpack_from("<II", data, 4)
    if version != 2 or total != len(data):
        raise WheelVisibilityError("cached GLB header is inconsistent")

    chunks: list[tuple[int, bytes]] = []
    cursor = 12
    document: dict | None = None
    json_chunks = 0
    while cursor < total:
        if cursor + 8 > total:
            raise WheelVisibilityError("cached GLB has a truncated chunk header")
        length, chunk_type = struct.unpack_from("<II", data, cursor)
        cursor += 8
        if length < 0 or cursor + length > total:
            raise WheelVisibilityError("cached GLB has a truncated chunk")
        payload = data[cursor:cursor + length]
        cursor += length
        chunks.append((chunk_type, payload))
        if chunk_type == 0x4E4F534A:
            json_chunks += 1
            value = json.loads(payload.rstrip(b" \x00").decode("utf-8"))
            if not isinstance(value, dict):
                raise WheelVisibilityError("GLB JSON root is not an object")
            document = value
    if cursor != total or document is None or json_chunks != 1:
        raise WheelVisibilityError("cached GLB does not have exactly one valid JSON chunk")
    return document, chunks


def _write_glb(path: Path, document: dict, chunks: list[tuple[int, bytes]]) -> None:
    json_raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_raw += b" " * ((4 - (len(json_raw) % 4)) % 4)

    rewritten: list[tuple[int, bytes]] = []
    replaced = False
    for chunk_type, payload in chunks:
        if chunk_type == 0x4E4F534A:
            if replaced:
                raise WheelVisibilityError("refusing to rewrite a GLB with multiple JSON chunks")
            rewritten.append((chunk_type, json_raw))
            replaced = True
        else:
            rewritten.append((chunk_type, payload))
    if not replaced:
        raise WheelVisibilityError("refusing to rewrite a GLB without a JSON chunk")

    total = 12 + sum(8 + len(payload) for _, payload in rewritten)
    temp = path.with_name(path.name + f".{os.getpid()}.wheelvis.tmp")
    try:
        with temp.open("wb") as out:
            out.write(b"glTF")
            out.write(struct.pack("<II", 2, total))
            for chunk_type, payload in rewritten:
                out.write(struct.pack("<II", len(payload), chunk_type))
                out.write(payload)
        # Reopen before replacing the established cached GLB.
        verify_doc, _ = _read_glb(temp)
        if not isinstance(verify_doc, dict):
            raise WheelVisibilityError("rewritten GLB failed JSON verification")
        temp.replace(path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _motion_blur_signature(record: MeshStructureRecord) -> bool:
    """Structure-only neutral-view exclusion rule confirmed on MINI and FXX WheelStyle.

    No vehicle/model/mesh/material string participates in this decision.
    The complete signature is intentionally conservative to avoid treating every
    shadow-capable wheel primitive as motion geometry.
    """
    return (
        record.bucket_flags_raw == 28
        and not record.is_opaque
        and not record.is_decal
        and record.is_transparent
        and record.is_shadow
        and record.is_not_shadow
        and not record.is_alpha_to_coverage
        and record.morph_target_count == 1
        and record.vertex_layout_index == 0
        and record.morph_data_buffer_index == 0
    )


def _index_accessor_count(document: dict, mesh: dict) -> int:
    primitives = mesh.get("primitives")
    if not isinstance(primitives, list) or len(primitives) != 1 or not isinstance(primitives[0], dict):
        raise WheelVisibilityError("WheelStyle mapping requires exactly one GLB primitive per mesh")
    accessor_index = primitives[0].get("indices")
    accessors = document.get("accessors")
    if not isinstance(accessor_index, int) or not isinstance(accessors, list):
        raise WheelVisibilityError("WheelStyle mesh has no indexed accessor")
    if accessor_index < 0 or accessor_index >= len(accessors) or not isinstance(accessors[accessor_index], dict):
        raise WheelVisibilityError("WheelStyle mesh index accessor is invalid")
    count = accessors[accessor_index].get("count")
    if not isinstance(count, int) or count < 0:
        raise WheelVisibilityError("WheelStyle mesh index accessor count is invalid")
    return count


def _apply_document_visibility(
    document: dict,
    records_by_source: dict[str, list[MeshStructureRecord]],
) -> WheelVisibilityResult:
    meshes = document.get("meshes")
    if not isinstance(meshes, list):
        raise WheelVisibilityError("GLB has no mesh array")

    grouped: dict[tuple[str, str], list[tuple[int, dict]]] = defaultdict(list)
    sources: set[str] = set()
    for mesh_index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            continue
        extras = mesh.get("extras") if isinstance(mesh.get("extras"), dict) else {}
        if _normalize_part_type(extras.get("kfps_part_type")) != "wheelstyle":
            continue
        source = _canonical_source(extras.get("kfps_source_entry"))
        identity = str(extras.get("kfps_instance_identity") or "")
        if not source or not identity:
            raise WheelVisibilityError("WheelStyle mesh is missing structured source/instance metadata")
        sources.add(source)
        grouped[(source, identity)].append((mesh_index, mesh))

    if not grouped:
        return WheelVisibilityResult(
            "no_wheelstyle_geometry", WHEEL_VISIBILITY_REVISION, 0, 0, 0, 0, 0, WHEEL_MOTION_SIGNATURE
        )

    if sources != set(records_by_source):
        missing = sorted(sources - set(records_by_source))
        extra = sorted(set(records_by_source) - sources)
        raise WheelVisibilityError(
            f"WheelStyle source map mismatch (missing={len(missing)}, extra={len(extra)})"
        )

    mapped = 0
    hidden_motion = 0
    already_hidden = 0
    # Validate every source/instance mapping before mutating the JSON document.
    planned: list[tuple[dict, MeshStructureRecord]] = []
    for (source, _identity), glb_group in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        primary = [record for record in records_by_source[source] if record.lod_flags & 0x01]
        glb_group = sorted(glb_group, key=lambda item: item[0])
        if not primary:
            raise WheelVisibilityError("WheelStyle modelbin has no primary LODS mesh records")
        if len(glb_group) != len(primary):
            raise WheelVisibilityError(
                f"WheelStyle primitive count mismatch: GLB={len(glb_group)} modelbin={len(primary)}"
            )
        for (_mesh_index, mesh), record in zip(glb_group, primary):
            # Structural join: converter preserves MeshBlob order, and the index count
            # is required to match exactly. Names/materials are not used to join or filter.
            if _index_accessor_count(document, mesh) != record.index_count:
                raise WheelVisibilityError("WheelStyle ordered mapping failed index-count validation")
            planned.append((mesh, record))
            mapped += 1

    for mesh, record in planned:
        extras = mesh.setdefault("extras", {})
        if not isinstance(extras, dict):
            raise WheelVisibilityError("WheelStyle mesh extras are not an object")
        if _motion_blur_signature(record):
            previous = str(extras.get("kfps_role") or "trim").casefold()
            if previous == "hidden":
                already_hidden += 1
            else:
                extras["kfps_role"] = "hidden"
                hidden_motion += 1
            extras["kfps_neutral_visibility_basis"] = WHEEL_MOTION_SIGNATURE

    status = "applied" if hidden_motion else "already_applied_or_no_motion_candidates"
    return WheelVisibilityResult(
        status,
        WHEEL_VISIBILITY_REVISION,
        len(sources),
        len(grouped),
        mapped,
        hidden_motion,
        already_hidden,
        WHEEL_MOTION_SIGNATURE,
    )


def apply_neutral_wheel_visibility(glb_path: str | Path, converter_archive: str | Path) -> WheelVisibilityResult:
    """Hide only structurally confirmed WheelStyle motion/blur draw geometry.

    Both inputs are LocalAppData-derived artifacts. The original FH6 ZIP and save
    data are never opened for writing. The GLB is rewritten atomically only after
    all WheelStyle source/instance mappings validate.
    """
    glb = Path(glb_path)
    archive_path = Path(converter_archive)
    document, chunks = _read_glb(glb)

    wheel_sources: set[str] = set()
    original_source_by_key: dict[str, str] = {}
    for mesh in document.get("meshes") or []:
        if not isinstance(mesh, dict):
            continue
        extras = mesh.get("extras") if isinstance(mesh.get("extras"), dict) else {}
        if _normalize_part_type(extras.get("kfps_part_type")) != "wheelstyle":
            continue
        raw_source = str(extras.get("kfps_source_entry") or "").replace("\\", "/")
        key = _canonical_source(raw_source)
        if key:
            wheel_sources.add(key)
            original_source_by_key.setdefault(key, raw_source)

    if not wheel_sources:
        return _apply_document_visibility(document, {})

    records_by_source: dict[str, list[MeshStructureRecord]] = {}
    with zipfile.ZipFile(archive_path, "r") as archive:
        available = {name.replace("\\", "/").casefold(): name for name in archive.namelist()}
        for source in wheel_sources:
            actual = available.get(source)
            if actual is None:
                shown = original_source_by_key.get(source, source)
                raise WheelVisibilityError(f"WheelStyle source is missing from converter archive: {shown}")
            records_by_source[source] = parse_modelbin_mesh_structures(archive.read(actual))

    result = _apply_document_visibility(document, records_by_source)
    if result.motion_primitives_hidden > 0:
        _write_glb(glb, document, chunks)
    return result
