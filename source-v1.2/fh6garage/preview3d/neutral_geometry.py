from __future__ import annotations

import json
import os
import struct
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .carbin_structural import parse_fh6_carbin
from .wheel_mesh_diagnostic import MeshStructureRecord, parse_modelbin_mesh_structures

NEUTRAL_GEOMETRY_REVISION = 3

# Draw-group bits documented by the FH6 carbin structural parser.
DRAW_EXTERIOR = 0x01
DRAW_COCKPIT = 0x02
DRAW_SHADOW = 0x04
DRAW_HOOD = 0x08
DRAW_WINDSHIELD_REFLECTION = 0x10
DRAW_DRIVERLESS_COCKPIT = 0x20
DRAW_WINDSHIELD_REFLECTION_DRIVERLESS = 0x40
DRAW_PROXY_LOD = 0x80
PRIMARY_DRAW_GROUPS = DRAW_EXTERIOR | DRAW_COCKPIT | DRAW_HOOD
ALTERNATE_DRAW_GROUPS = (
    DRAW_WINDSHIELD_REFLECTION
    | DRAW_DRIVERLESS_COCKPIT
    | DRAW_WINDSHIELD_REFLECTION_DRIVERLESS
    | DRAW_PROXY_LOD
)

# Format-level/scene-semantic categories, never vehicle/model identifiers.
# These are used only to suppress wheel-position-dependent support geometry from
# the neutral viewer after the user elected not to reconstruct runtime suspension.
SUPPORT_PART_TYPES = frozenset({5, 6, 7})  # SpringDamper, AntiSwayFront, AntiSwayRear
SUPPORT_ASSEMBLY_NAMES = frozenset({"controlarm", "springdamper", "antiswayfront", "antiswayrear"})
BRAKES_PART_TYPE = 4
THIN_PROTECTED_ROLES = frozenset({"paint", "glass"})
THIN_LONG_AXIS_MIN = 0.05
THIN_RATIO_TO_MIDDLE_MAX = 0.015
THIN_RATIO_TO_LONG_MAX = 0.0075


class NeutralGeometryError(RuntimeError):
    pass


@dataclass(frozen=True)
class NeutralGeometryResult:
    status: str
    revision: int
    mesh_count: int
    ab_hidden_meshes: int
    a_presentation_hidden_meshes: int
    b_support_hidden_meshes: int
    c_candidate_meshes: int
    wheelstyle_hidden_meshes: int
    extreme_thin_hidden_meshes: int
    mapped_render_meshes: int
    unmapped_render_meshes: int
    carbin_instances_matched: int
    carbin_instances_unmatched: int

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "revision": self.revision,
            "mesh_count": self.mesh_count,
            "ab_hidden_meshes": self.ab_hidden_meshes,
            "a_presentation_hidden_meshes": self.a_presentation_hidden_meshes,
            "b_support_hidden_meshes": self.b_support_hidden_meshes,
            "c_candidate_meshes": self.c_candidate_meshes,
            "wheelstyle_hidden_meshes": self.wheelstyle_hidden_meshes,
            "extreme_thin_hidden_meshes": self.extreme_thin_hidden_meshes,
            "mapped_render_meshes": self.mapped_render_meshes,
            "unmapped_render_meshes": self.unmapped_render_meshes,
            "carbin_instances_matched": self.carbin_instances_matched,
            "carbin_instances_unmatched": self.carbin_instances_unmatched,
            "policy": {
                "A": "hide structurally presentation-only draw groups and validated shadow-only mesh passes",
                "B": "hide wheel-position-dependent support geometry from semantic converter/carbin structure",
                "thin_geometry": "hide extreme sheet/line-like auxiliary meshes using AABB ratios while preserving paint/glass and brakes",
                "C": "optional aggressive alternate-presentation cleanup candidate; default off",
                "vehicle_specific_rules": False,
                "filename_matching_for_visibility": False,
                "material_name_matching_for_visibility": False,
            },
        }


def _canonical_source(value: object) -> str:
    return str(value or "").replace("\\", "/").casefold()


def _normalize_text(value: object) -> str:
    return str(value or "").casefold().replace(" ", "").replace("-", "").replace("_", "")


def _neutral_support_reasons(model_meta: dict | None) -> tuple[str, ...]:
    """Return only runtime-position-dependent support exclusions.

    WheelStyle is intentionally not excluded here. Its native rim/tire geometry
    is valid in the neutral scene, while wheel_visibility.py independently marks
    only the structurally confirmed motion/blur primitive as hidden.
    """
    if model_meta is None:
        return ()
    reasons: list[str] = []
    if int(model_meta.get("part_type", -1)) in SUPPORT_PART_TYPES:
        reasons.append("wheel_dependent_support_part_type")
    if _normalize_text(model_meta.get("assembly_name")) in SUPPORT_ASSEMBLY_NAMES:
        reasons.append("wheel_dependent_support_assembly")
    return tuple(reasons)


def _float_bits(value: float) -> str:
    return f"{struct.unpack('<I', struct.pack('<f', float(value)))[0]:08X}"


def _carbin_instance_key(model: dict, resolved_part_type: int) -> tuple[str, str, int, int, str]:
    return (
        _canonical_source(model.get("resource_path")),
        str(model.get("bone_name") or "").casefold(),
        int(model.get("bone_id", 0)),
        int(resolved_part_type),
        ",".join(_float_bits(value) for value in model.get("transform_matrix_row_major") or []),
    )


def _glb_instance_key(identity: object) -> tuple[str, str, int, int, str] | None:
    parts = str(identity or "").split("|")
    if len(parts) != 5:
        return None
    source, bone, bone_id, part_type, transform = parts
    try:
        return (
            _canonical_source(source),
            bone.casefold(),
            int(bone_id),
            int(part_type),
            transform.upper(),
        )
    except (TypeError, ValueError):
        return None


def _read_glb(path: Path) -> tuple[dict, list[tuple[int, bytes]]]:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise NeutralGeometryError("cached output is not a GLB file")
    version, total = struct.unpack_from("<II", data, 4)
    if version != 2 or total != len(data):
        raise NeutralGeometryError("cached GLB header is inconsistent")
    chunks: list[tuple[int, bytes]] = []
    cursor = 12
    document = None
    while cursor < total:
        if cursor + 8 > total:
            raise NeutralGeometryError("cached GLB has a truncated chunk header")
        length, chunk_type = struct.unpack_from("<II", data, cursor)
        cursor += 8
        if cursor + length > total:
            raise NeutralGeometryError("cached GLB has a truncated chunk")
        payload = data[cursor:cursor + length]
        cursor += length
        chunks.append((chunk_type, payload))
        if chunk_type == 0x4E4F534A:
            document = json.loads(payload.rstrip(b" \x00").decode("utf-8"))
    if cursor != total or not isinstance(document, dict):
        raise NeutralGeometryError("cached GLB does not have a valid JSON document")
    return document, chunks


def _write_glb(path: Path, document: dict, chunks: list[tuple[int, bytes]]) -> None:
    json_raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_raw += b" " * ((4 - len(json_raw) % 4) % 4)
    rewritten: list[tuple[int, bytes]] = []
    replaced = False
    for chunk_type, payload in chunks:
        if chunk_type == 0x4E4F534A:
            if replaced:
                raise NeutralGeometryError("refusing GLB with multiple JSON chunks")
            rewritten.append((chunk_type, json_raw))
            replaced = True
        else:
            rewritten.append((chunk_type, payload))
    if not replaced:
        raise NeutralGeometryError("refusing GLB without JSON chunk")
    total = 12 + sum(8 + len(payload) for _, payload in rewritten)
    temp = path.with_name(path.name + f".{os.getpid()}.neutral.tmp")
    try:
        with temp.open("wb") as out:
            out.write(b"glTF")
            out.write(struct.pack("<II", 2, total))
            for chunk_type, payload in rewritten:
                out.write(struct.pack("<II", len(payload), chunk_type))
                out.write(payload)
        verify, _ = _read_glb(temp)
        if not isinstance(verify, dict):
            raise NeutralGeometryError("rewritten neutral GLB failed verification")
        temp.replace(path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _index_accessor_count(document: dict, mesh: dict) -> int | None:
    primitives = mesh.get("primitives")
    if not isinstance(primitives, list) or len(primitives) != 1 or not isinstance(primitives[0], dict):
        return None
    accessor_index = primitives[0].get("indices")
    accessors = document.get("accessors")
    if not isinstance(accessor_index, int) or not isinstance(accessors, list):
        return None
    if not (0 <= accessor_index < len(accessors)) or not isinstance(accessors[accessor_index], dict):
        return None
    count = accessors[accessor_index].get("count")
    return int(count) if isinstance(count, int) and count >= 0 else None




def _mesh_local_aabb(document: dict, mesh: dict) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    primitives = mesh.get("primitives")
    if not isinstance(primitives, list) or len(primitives) != 1 or not isinstance(primitives[0], dict):
        return None
    attrs = primitives[0].get("attributes")
    if not isinstance(attrs, dict):
        return None
    accessor_index = attrs.get("POSITION")
    accessors = document.get("accessors")
    if not isinstance(accessor_index, int) or not isinstance(accessors, list):
        return None
    if not (0 <= accessor_index < len(accessors)) or not isinstance(accessors[accessor_index], dict):
        return None
    accessor = accessors[accessor_index]
    minimum = accessor.get("min")
    maximum = accessor.get("max")
    if not (isinstance(minimum, list) and isinstance(maximum, list) and len(minimum) == 3 and len(maximum) == 3):
        return None
    try:
        mn = tuple(float(v) for v in minimum)
        mx = tuple(float(v) for v in maximum)
    except (TypeError, ValueError):
        return None
    if not all(__import__("math").isfinite(v) for v in mn + mx):
        return None
    return mn, mx


def _is_extreme_thin_mesh(document: dict, mesh: dict, extras: dict, model_meta: dict | None) -> bool:
    role = _normalize_text(extras.get("kfps_role"))
    if role in THIN_PROTECTED_ROLES:
        return False
    part_type = int(model_meta.get("part_type", -1)) if model_meta is not None else -1
    if part_type == BRAKES_PART_TYPE or _normalize_text(extras.get("kfps_part_type")) == "brakes":
        return False
    aabb = _mesh_local_aabb(document, mesh)
    if aabb is None:
        return False
    minimum, maximum = aabb
    dims = sorted(abs(maximum[i] - minimum[i]) for i in range(3))
    short, middle, long = dims
    if long < THIN_LONG_AXIS_MIN:
        return False
    if middle <= 1e-7:
        return True
    return (
        short / middle <= THIN_RATIO_TO_MIDDLE_MAX
        and short / long <= THIN_RATIO_TO_LONG_MAX
    )


def _load_carbin_metadata(archive: zipfile.ZipFile, carbin_entry: str) -> dict[tuple[str, str, int, int, str], dict]:
    try:
        graph = parse_fh6_carbin(archive.read(carbin_entry))
    except KeyError as exc:
        raise NeutralGeometryError(f"selected carbin entry is missing from converter archive: {carbin_entry}") from exc
    result: dict[tuple[str, str, int, int, str], dict] = {}

    def add_model(part: dict, model: dict) -> None:
        resolved = int(part.get("resolved_part_type", -1))
        key = _carbin_instance_key(model, resolved)
        result[key] = {
            "part_type": resolved,
            "part_type_name": str(part.get("resolved_part_type_name") or ""),
            "assembly_name": str(model.get("assembly_name") or ""),
            "draw_groups": int(model.get("draw_groups_raw", 0) or 0),
            "is_interior_windshield": bool(model.get("is_interior_windshield", False)),
        }

    for part in graph.get("standard_parts") or []:
        for model in part.get("models") or []:
            add_model(part, model)
    for part in graph.get("upgradable_parts") or []:
        for upgrade in part.get("upgrades") or []:
            for model in upgrade.get("legacy_models") or []:
                add_model(part, model)
        for shared in part.get("shared_models") or []:
            model = shared.get("model") if isinstance(shared, dict) else None
            if isinstance(model, dict):
                add_model(part, model)
    return result


def annotate_neutral_geometry(
    glb_path: str | Path,
    converter_archive: str | Path,
    carbin_entry: str,
) -> NeutralGeometryResult:
    """Annotate A+B default visibility and optional C candidates without deleting geometry.

    The LocalAppData GLB is rewritten only in its JSON extras. Binary geometry is preserved.
    The original game ZIP/save are never opened by this function.
    """
    glb = Path(glb_path)
    archive_path = Path(converter_archive)
    document, chunks = _read_glb(glb)
    meshes = document.get("meshes")
    if not isinstance(meshes, list):
        raise NeutralGeometryError("GLB has no mesh array")

    grouped: dict[tuple[str, str], list[tuple[int, dict]]] = defaultdict(list)
    sources: set[str] = set()
    for mesh_index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            continue
        extras = mesh.get("extras") if isinstance(mesh.get("extras"), dict) else {}
        source = _canonical_source(extras.get("kfps_source_entry"))
        identity = str(extras.get("kfps_instance_identity") or "")
        if source and identity:
            grouped[(source, identity)].append((mesh_index, mesh))
            sources.add(source)

    mapped_render_meshes = 0
    unmapped_render_meshes = 0
    carbin_instances_matched = 0
    carbin_instances_unmatched = 0
    a_hidden = 0
    b_hidden = 0
    c_candidates = 0
    wheelstyle_hidden = 0
    extreme_thin_hidden = 0
    ab_hidden: set[int] = set()

    with zipfile.ZipFile(archive_path, "r") as archive:
        available = {name.replace("\\", "/").casefold(): name for name in archive.namelist()}
        carbin_metadata = _load_carbin_metadata(archive, carbin_entry)
        records_by_source: dict[str, list[MeshStructureRecord]] = {}
        for source in sources:
            actual = available.get(source.removeprefix("game:/media/cars/").split("/", 1)[-1])
            # Converter extras normally carry archive-relative source_entry rather than game:/ paths.
            if actual is None:
                actual = available.get(source)
            if actual is None:
                # Match by suffix against the converter archive only. This is a structural
                # source-path resolution step, not a visibility/classification rule.
                matches = [name for key, name in available.items() if key.endswith("/" + source.strip("/")) or source.endswith("/" + key.strip("/"))]
                actual = matches[0] if len(matches) == 1 else None
            if actual is None:
                continue
            try:
                records_by_source[source] = parse_modelbin_mesh_structures(archive.read(actual))
            except Exception:
                continue

        for (source, identity), glb_group in grouped.items():
            instance_key = _glb_instance_key(identity)
            model_meta = carbin_metadata.get(instance_key) if instance_key is not None else None
            if model_meta is None:
                carbin_instances_unmatched += 1
            else:
                carbin_instances_matched += 1

            primary_records = [record for record in records_by_source.get(source, []) if record.lod_flags & 0x01]
            glb_group = sorted(glb_group, key=lambda item: item[0])
            render_mapping: list[MeshStructureRecord | None] = [None] * len(glb_group)
            if primary_records and len(primary_records) == len(glb_group):
                tentative: list[MeshStructureRecord | None] = []
                valid = True
                for (_mesh_index, mesh), record in zip(glb_group, primary_records):
                    accessor_count = _index_accessor_count(document, mesh)
                    if accessor_count is None or accessor_count != record.index_count:
                        valid = False
                        break
                    tentative.append(record)
                if valid:
                    render_mapping = tentative

            for group_index, (mesh_index, mesh) in enumerate(glb_group):
                extras = mesh.setdefault("extras", {})
                if not isinstance(extras, dict):
                    continue
                draw_groups = int(extras.get("kfps_draw_groups", 0) or 0)
                record = render_mapping[group_index]
                if record is not None:
                    mapped_render_meshes += 1
                    extras["kfps_mesh_bucket_flags"] = int(record.bucket_flags_raw)
                    extras["kfps_mesh_is_opaque"] = bool(record.is_opaque)
                    extras["kfps_mesh_is_decal"] = bool(record.is_decal)
                    extras["kfps_mesh_is_transparent"] = bool(record.is_transparent)
                    extras["kfps_mesh_is_shadow"] = bool(record.is_shadow)
                    extras["kfps_mesh_is_not_shadow"] = bool(record.is_not_shadow)
                else:
                    unmapped_render_meshes += 1

                reasons_a: list[str] = []
                reasons_b: list[str] = []
                reasons_c: list[str] = []

                # Pass A: only use formal draw-group bits and validated mesh render flags.
                if draw_groups and not (draw_groups & PRIMARY_DRAW_GROUPS):
                    reasons_a.append("presentation_only_draw_groups")
                if record is not None and record.is_shadow and not record.is_not_shadow:
                    reasons_a.append("shadow_only_mesh_pass")

                # Pass B: use semantic converter/carbin fields, never vehicle IDs,
                # source filenames, mesh names, or material names. Native
                # WheelStyle remains visible; wheel_visibility.py has already
                # hidden only its structurally confirmed motion/blur primitive.
                if model_meta is not None:
                    extras["kfps_assembly_name"] = str(model_meta.get("assembly_name") or "")
                reasons_b.extend(_neutral_support_reasons(model_meta))

                # Extreme-thin cleanup is geometric rather than name based. Preserve
                # declared paint/glass and Brakes so legitimate body skins, windows,
                # rotors and calipers are not removed by a generic thickness rule.
                if _is_extreme_thin_mesh(document, mesh, extras, model_meta):
                    reasons_b.append("extreme_thin_auxiliary_geometry")
                    extreme_thin_hidden += 1

                # Pass C is intentionally optional and conservative: an instance must
                # participate in an alternate presentation group and the mapped mesh
                # itself must be a non-opaque decal/transparent presentation pass.
                if (
                    draw_groups & ALTERNATE_DRAW_GROUPS
                    and record is not None
                    and not record.is_opaque
                    and (record.is_decal or record.is_transparent)
                ):
                    reasons_c.append("alternate_group_nonopaque_mesh_pass")

                if reasons_a:
                    a_hidden += 1
                if reasons_b:
                    b_hidden += 1
                if reasons_a or reasons_b:
                    ab_hidden.add(mesh_index)
                if reasons_c:
                    c_candidates += 1

                extras["kfps_neutral_ab_hidden"] = bool(reasons_a or reasons_b)
                extras["kfps_neutral_ab_reasons"] = sorted(set(reasons_a + reasons_b))
                extras["kfps_neutral_c_candidate"] = bool(reasons_c)
                extras["kfps_neutral_c_reasons"] = sorted(set(reasons_c))
                extras["kfps_neutral_geometry_revision"] = NEUTRAL_GEOMETRY_REVISION

    _write_glb(glb, document, chunks)
    return NeutralGeometryResult(
        status="annotated",
        revision=NEUTRAL_GEOMETRY_REVISION,
        mesh_count=len(meshes),
        ab_hidden_meshes=len(ab_hidden),
        a_presentation_hidden_meshes=a_hidden,
        b_support_hidden_meshes=b_hidden,
        c_candidate_meshes=c_candidates,
        wheelstyle_hidden_meshes=wheelstyle_hidden,
        extreme_thin_hidden_meshes=extreme_thin_hidden,
        mapped_render_meshes=mapped_render_meshes,
        unmapped_render_meshes=unmapped_render_meshes,
        carbin_instances_matched=carbin_instances_matched,
        carbin_instances_unmatched=carbin_instances_unmatched,
    )
