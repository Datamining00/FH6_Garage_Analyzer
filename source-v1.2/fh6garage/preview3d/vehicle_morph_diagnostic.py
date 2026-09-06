from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any
import zipfile

from .modelbin_morph import (
    ModelbinMorphError,
    ModelbinMorphInventory,
    parse_modelbin_morph_inventory,
)
from .modelbin_morph_index_profile import profile_modelbin_index_addressing
from .modelbin_morph_profile import profile_weighted_morph_targets
from .near_lod_archive import _referenced_model_paths

DIAGNOSTIC_REVISION = 1


class VehicleMorphDiagnosticError(RuntimeError):
    """Raised when a vehicle archive cannot be inspected safely."""


@dataclass(frozen=True)
class ModelbinMorphDiagnostic:
    archive_entry: str
    game_references: tuple[str, ...]
    category: str
    morph_buffer_count: int
    mesh_binding_count: int
    morph_mesh_count: int
    weighted_morph_meshes: int
    damage_morph_meshes: int
    unresolved_morph_bindings: int
    inventory: dict[str, Any] | None
    parse_error: str | None
    weighted_target_profiles: tuple[dict[str, Any], ...] = ()
    index_addressing_profiles: tuple[dict[str, Any], ...] = ()
    index_addressing_error: str | None = None


@dataclass(frozen=True)
class VehicleMorphDiagnosticReport:
    revision: int
    source_archive: str
    carbin_entry: str
    model_code: str
    discovered_modelbin_references: int
    resolved_modelbin_references: int
    unresolved_modelbin_references: tuple[str, ...]
    referenced_modelbins: int
    parsed_modelbins: int
    modelbins_with_morph: int
    morph_buffers: int
    morph_meshes: int
    weighted_morph_meshes: int
    damage_morph_meshes: int
    unresolved_morph_bindings: int
    category_counts: dict[str, int]
    modelbins: tuple[ModelbinMorphDiagnostic, ...]
    game_data_modified: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["format"] = "fh6_vehicle_morph_diagnostic_v1"
        return payload


def classify_modelbin_path(archive_entry: str, game_references: tuple[str, ...] = ()) -> str:
    """Classify a modelbin for diagnostics only; never use this as geometry truth."""
    text = " ".join((archive_entry, *game_references)).replace("\\", "/").casefold()
    if any(token in text for token in ("/tire", "_tire", "/tyre", "_tyre")):
        return "tire"
    if any(token in text for token in ("/brake", "_brake", "/rotor", "_rotor", "/disc", "_disc")):
        return "brake"
    if any(token in text for token in ("/wheel", "_wheel", "/rim", "_rim", "wheelstyle", "wheel_style")):
        return "wheel"
    return "other"


def _weighted_target_profiles(inventory: ModelbinMorphInventory) -> tuple[dict[str, Any], ...]:
    """Build diagnostic-only selector profiles for resolved non-damage morph bindings."""
    resolutions = {item.mesh_blob_index: item for item in inventory.resolutions}
    buffers = {item.blob_index: item for item in inventory.morph_buffers}
    groups: dict[tuple[int | None, int, int | None, str], list[int]] = defaultdict(list)

    for mesh in inventory.mesh_bindings:
        buffer_index = mesh.morph_data_buffer_index
        if (
            mesh.morph_target_count <= 0
            or mesh.is_morph_damage
            or buffer_index is None
            or buffer_index < 0
        ):
            continue
        resolution = resolutions.get(mesh.blob_index)
        resolved_blob = resolution.morph_buffer_blob_index if resolution is not None else None
        resolved_by = resolution.resolved_by if resolution is not None else "unresolved"
        groups[(resolved_blob, mesh.morph_target_count, buffer_index, resolved_by)].append(mesh.blob_index)

    profiles: list[dict[str, Any]] = []
    for (resolved_blob, target_count, buffer_index, resolved_by), mesh_blob_indices in sorted(
        groups.items(),
        key=lambda item: (
            item[0][0] is None,
            -1 if item[0][0] is None else item[0][0],
            item[0][1],
            item[0][2] if item[0][2] is not None else -1,
            item[0][3],
        ),
    ):
        profile_payload: dict[str, Any] | None = None
        profile_error: str | None = None
        if resolved_blob is None:
            profile_error = "morph buffer binding unresolved"
        else:
            morph_buffer = buffers.get(resolved_blob)
            if morph_buffer is None:
                profile_error = f"resolved morph buffer blob {resolved_blob} missing from inventory"
            else:
                try:
                    profile_payload = profile_weighted_morph_targets(
                        morph_buffer,
                        target_count,
                    ).as_dict()
                except ModelbinMorphError as exc:
                    profile_error = str(exc)

        profiles.append(
            {
                "mesh_blob_indices": tuple(sorted(mesh_blob_indices)),
                "morph_target_count": target_count,
                "morph_data_buffer_index": buffer_index,
                "morph_buffer_blob_index": resolved_blob,
                "resolved_by": resolved_by,
                "profile": profile_payload,
                "profile_error": profile_error,
            }
        )

    return tuple(profiles)


def _weighted_index_addressing_profiles(
    data: bytes,
    inventory: ModelbinMorphInventory,
) -> tuple[tuple[dict[str, Any], ...], str | None]:
    """Return FTS-compatible index/base-vertex diagnostics for weighted morph meshes only."""
    weighted_mesh_blob_indices = {
        mesh.blob_index
        for mesh in inventory.mesh_bindings
        if (
            mesh.morph_target_count > 0
            and not mesh.is_morph_damage
            and mesh.morph_data_buffer_index is not None
            and mesh.morph_data_buffer_index >= 0
        )
    }
    if not weighted_mesh_blob_indices:
        return (), None

    try:
        profiles = profile_modelbin_index_addressing(data)
    except ModelbinMorphError as exc:
        return (), str(exc)

    filtered = tuple(
        profile.as_dict()
        for profile in profiles
        if profile.mesh_blob_index in weighted_mesh_blob_indices
    )
    missing = weighted_mesh_blob_indices.difference(
        profile["mesh_blob_index"] for profile in filtered
    )
    if missing:
        return filtered, f"index addressing profile missing mesh blobs: {sorted(missing)}"
    return filtered, None


def _summarize_modelbin(
    archive_entry: str,
    game_references: tuple[str, ...],
    data: bytes,
) -> ModelbinMorphDiagnostic:
    category = classify_modelbin_path(archive_entry, game_references)
    try:
        inventory = parse_modelbin_morph_inventory(data)
    except ModelbinMorphError as exc:
        return ModelbinMorphDiagnostic(
            archive_entry=archive_entry,
            game_references=game_references,
            category=category,
            morph_buffer_count=0,
            mesh_binding_count=0,
            morph_mesh_count=0,
            weighted_morph_meshes=0,
            damage_morph_meshes=0,
            unresolved_morph_bindings=0,
            inventory=None,
            parse_error=str(exc),
        )

    resolutions = {item.mesh_blob_index: item for item in inventory.resolutions}
    morph_meshes = 0
    weighted = 0
    damage = 0
    unresolved = 0
    for mesh in inventory.mesh_bindings:
        buffer_index = mesh.morph_data_buffer_index
        if mesh.morph_target_count <= 0 or buffer_index is None or buffer_index < 0:
            continue
        morph_meshes += 1
        if mesh.is_morph_damage:
            damage += 1
        else:
            weighted += 1
        resolution = resolutions.get(mesh.blob_index)
        if resolution is None or resolution.morph_buffer_blob_index is None:
            unresolved += 1

    index_profiles, index_error = _weighted_index_addressing_profiles(data, inventory)
    return ModelbinMorphDiagnostic(
        archive_entry=archive_entry,
        game_references=game_references,
        category=category,
        morph_buffer_count=len(inventory.morph_buffers),
        mesh_binding_count=len(inventory.mesh_bindings),
        morph_mesh_count=morph_meshes,
        weighted_morph_meshes=weighted,
        damage_morph_meshes=damage,
        unresolved_morph_bindings=unresolved,
        inventory=inventory.as_dict(),
        parse_error=None,
        weighted_target_profiles=_weighted_target_profiles(inventory),
        index_addressing_profiles=index_profiles,
        index_addressing_error=index_error,
    )


def inspect_vehicle_morph_archive(
    source_archive: str | Path,
    carbin_entry: str,
    model_code: str,
) -> VehicleMorphDiagnosticReport:
    """Inspect referenced modelbins without modifying the source vehicle archive."""
    source = Path(source_archive).expanduser().resolve()
    if not source.is_file():
        raise VehicleMorphDiagnosticError(f"Vehicle archive does not exist: {source}")

    try:
        with zipfile.ZipFile(source, "r") as bundle:
            names = tuple(bundle.namelist())
            names_cf = {name.replace("\\", "/").casefold(): name for name in names}
            carbin_exact = names_cf.get(carbin_entry.replace("\\", "/").casefold())
            if carbin_exact is None:
                raise VehicleMorphDiagnosticError(f"carbin entry not found in archive: {carbin_entry}")

            carbin = bundle.read(carbin_exact)
            resolved, discovered, unresolved_refs = _referenced_model_paths(
                carbin,
                names_cf,
                model_code,
            )
            if not discovered:
                raise VehicleMorphDiagnosticError("carbin contained no modelbin references")

            references_by_entry: dict[str, list[str]] = defaultdict(list)
            for game_reference, archive_entry in resolved.items():
                references_by_entry[archive_entry].append(game_reference)

            diagnostics: list[ModelbinMorphDiagnostic] = []
            for archive_entry in sorted(references_by_entry, key=str.casefold):
                if not archive_entry.casefold().endswith(".modelbin"):
                    continue
                refs = tuple(sorted(set(references_by_entry[archive_entry]), key=str.casefold))
                try:
                    modelbin_data = bundle.read(archive_entry)
                except KeyError as exc:
                    raise VehicleMorphDiagnosticError(
                        f"Resolved modelbin disappeared from archive: {archive_entry}"
                    ) from exc
                diagnostics.append(_summarize_modelbin(archive_entry, refs, modelbin_data))
    except zipfile.BadZipFile as exc:
        raise VehicleMorphDiagnosticError(f"Vehicle archive is not a readable ZIP: {source.name}") from exc
    except OSError as exc:
        raise VehicleMorphDiagnosticError(f"Vehicle archive could not be read: {source.name}: {exc}") from exc

    category_counts = Counter(item.category for item in diagnostics)
    parsed = [item for item in diagnostics if item.parse_error is None]
    return VehicleMorphDiagnosticReport(
        revision=DIAGNOSTIC_REVISION,
        source_archive=str(source),
        carbin_entry=carbin_exact,
        model_code=model_code,
        discovered_modelbin_references=len(discovered),
        resolved_modelbin_references=len(resolved),
        unresolved_modelbin_references=tuple(sorted(unresolved_refs, key=str.casefold)),
        referenced_modelbins=len(diagnostics),
        parsed_modelbins=len(parsed),
        modelbins_with_morph=sum(1 for item in parsed if item.morph_mesh_count > 0),
        morph_buffers=sum(item.morph_buffer_count for item in parsed),
        morph_meshes=sum(item.morph_mesh_count for item in parsed),
        weighted_morph_meshes=sum(item.weighted_morph_meshes for item in parsed),
        damage_morph_meshes=sum(item.damage_morph_meshes for item in parsed),
        unresolved_morph_bindings=sum(item.unresolved_morph_bindings for item in parsed),
        category_counts=dict(sorted(category_counts.items())),
        modelbins=tuple(diagnostics),
        game_data_modified=False,
    )


def report_json(report: VehicleMorphDiagnosticReport) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2)


def write_vehicle_morph_report(
    report: VehicleMorphDiagnosticReport,
    output: str | Path,
) -> Path:
    """Write diagnostics outside the source vehicle archive directory only."""
    target = Path(output).expanduser().resolve()
    source = Path(report.source_archive).resolve()
    try:
        if target == source or target.is_relative_to(source.parent):
            raise VehicleMorphDiagnosticError(
                "Refusing to write diagnostics inside the source vehicle archive directory"
            )
    except AttributeError:
        source_parent = str(source.parent).casefold().rstrip("\\/") + "/"
        target_text = str(target).replace("\\", "/").casefold()
        if target == source or target_text.startswith(source_parent.replace("\\", "/")):
            raise VehicleMorphDiagnosticError(
                "Refusing to write diagnostics inside the source vehicle archive directory"
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(report_json(report), encoding="utf-8")
    temp.replace(target)
    return target
