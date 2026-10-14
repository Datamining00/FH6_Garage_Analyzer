from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


_ACCESSORY_OR_NON_LIVERY_TOKENS = (
    "headlight",
    "taillight",
    "headlamp",
    "taillamp",
    "light",
    "lamp",
    "bulb",
    "reflector",
    "intake",
    "grille",
    "grill",
    "vent",
    "exhaust",
    "brake",
    "wheel",
    "tire",
    "tyre",
    "doorhandle",
    "door_handle",
    "handle",
    "antenna",
    "badge",
    "emblem",
    "logo",
)

# These are the body part families for which pinned KFPS explicitly provides
# livery-side semantics in ProjectionLiverySides(), plus CarBody which owns the
# authored exterior shell.  Unknown part types are not promoted; v4 diagnostics
# inventories them so real-vehicle evidence can expand this set safely.
_PAINTABLE_LIVERY_PART_TYPES = frozenset(
    {
        "carbody",
        "hood",
        "frontbumper",
        "rearbumper",
        "sideskirts",
        "rearwing",
    }
)

_EXTERIOR_SHELL_PATHS = (
    "/scene/exterior/doors/",
    "/scene/exterior/fenders/",
    "/scene/exterior/platform/",
    "/scene/exterior/hood/",
    "/scene/exterior/roof/",
    "/scene/exterior/trunk/",
    "/scene/exterior/bumper/",
    "/scene/exterior/bumpers/",
    "/scene/exterior/body/",
    "/scene/exterior/sideskirts/",
    "/scene/exterior/rearwing/",
    "/scene/exterior/wing/",
)

_HARD_NON_LIVERY_PATHS = (
    "/scene/exterior/primarylights/",
    "/scene/exterior/secondarylights/",
    "/scene/exterior/lights/",
    "/scene/exterior/brakes/",
    "/scene/exterior/wheels/",
    "/scene/interior/",
)

_PROVENANCE_KEYS = {
    "kfps_material_binding_hash": "material_binding_hash",
    "kfps_instance_identity": "instance_identity",
    "kfps_stock_part": "stock_part",
    "kfps_part_option_ids": "part_option_ids",
    "kfps_draw_groups": "draw_groups",
    "kfps_allowed_sides": "converter_allowed_sides",
    "kfps_projection_sides": "converter_projection_sides",
}


def _canonical_source(diagnostic: dict[str, Any]) -> str:
    source = str(diagnostic.get("source_entry") or "").replace("\\", "/").casefold()
    return f"/{source.lstrip('/')}"


def _searchable_identity(diagnostic: dict[str, Any]) -> str:
    return " ".join(
        (
            str(diagnostic.get("mesh_name") or ""),
            str(diagnostic.get("material_name") or ""),
            str(diagnostic.get("source_entry") or ""),
        )
    ).casefold()


def mesh_provenance_from_document(document: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Extract converter-authored GLB provenance without touching geometry bytes."""
    output: dict[int, dict[str, Any]] = {}
    meshes = document.get("meshes") if isinstance(document, dict) else None
    if not isinstance(meshes, list):
        return output
    for mesh_index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            continue
        extras = mesh.get("extras")
        if not isinstance(extras, dict):
            continue
        row = {
            target: extras.get(source)
            for source, target in _PROVENANCE_KEYS.items()
            if source in extras
        }
        if row:
            output[mesh_index] = row
    return output


def _load_mesh_provenance(path: Path | str) -> dict[int, dict[str, Any]]:
    try:
        from . import glb_parser

        document, binary = glb_parser._read_glb(Path(path))
        try:
            return mesh_provenance_from_document(document)
        finally:
            try:
                binary.release()
            except (AttributeError, BufferError, ValueError):
                pass
    except (OSError, TypeError, ValueError, RuntimeError):
        return {}


def _apply_provenance(item: dict[str, Any], provenance: dict[str, Any] | None) -> None:
    if not provenance:
        return
    for key, value in provenance.items():
        if key not in item or item.get(key) in (None, "", [], ()):  # parser data stays authoritative
            item[key] = value


def _evidence_mask(diagnostic: dict[str, Any]) -> int:
    return int(
        diagnostic.get("selected_uv_evidence_sides")
        or diagnostic.get("uv3_evidence_sides")
        or diagnostic.get("inferred_mask_sides")
        or 0
    )


def classify_strict_recovery_candidate(diagnostic: dict[str, Any]) -> dict[str, Any]:
    """Classify a Strict false negative without weakening non-livery exclusions."""
    final_allowed = int(diagnostic.get("final_allowed_sides") or 0)
    structural = str(diagnostic.get("structural_livery_exclusion") or "").strip()
    role = str(diagnostic.get("declared_role") or "").strip().casefold()
    part_type = str(diagnostic.get("part_type") or "").strip().casefold()
    canonical_source = _canonical_source(diagnostic)
    searchable = _searchable_identity(diagnostic)
    evidence_mask = _evidence_mask(diagnostic)

    if final_allowed:
        candidate = False
        reason = "already_eligible"
    elif structural:
        candidate = False
        reason = f"structural_exclusion:{structural}"
    elif part_type not in _PAINTABLE_LIVERY_PART_TYPES:
        candidate = False
        reason = "not_paintable_livery_part_type"
    elif "/scene/exterior/" not in canonical_source:
        candidate = False
        reason = "not_scene_exterior"
    elif not evidence_mask:
        candidate = False
        reason = "no_livery_mask_evidence"
    else:
        candidate = True
        reason = "strict_missed_paintable_exterior_with_mask_evidence"

    risk_tokens = tuple(
        token for token in _ACCESSORY_OR_NON_LIVERY_TOKENS if token in searchable
    )
    hard_non_livery_path = next(
        (path for path in _HARD_NON_LIVERY_PATHS if path in canonical_source),
        "",
    )
    shell_path = next(
        (path for path in _EXTERIOR_SHELL_PATHS if path in canonical_source),
        "",
    )

    if not candidate:
        recovery_class = "not_candidate"
        review_reason = reason
    elif hard_non_livery_path:
        recovery_class = "non_livery_structure"
        review_reason = f"hard_non_livery_path:{hard_non_livery_path.strip('/')}"
    elif risk_tokens:
        recovery_class = "accessory_or_non_livery"
        review_reason = "accessory_or_non_livery_identity"
    elif not shell_path:
        recovery_class = "unclassified_exterior"
        review_reason = "outside_verified_exterior_shell_families"
    else:
        recovery_class = "exterior_shell"
        review_reason = "high_confidence_paintable_exterior_with_mask_evidence"

    safe = bool(candidate and recovery_class == "exterior_shell")

    return {
        "candidate": bool(candidate),
        "reason": reason,
        "declared_role": role,
        "part_type": part_type,
        "evidence_mask": evidence_mask,
        "risk_tokens": risk_tokens,
        "hard_non_livery_path": hard_non_livery_path,
        "shell_path": shell_path,
        "recovery_class": recovery_class,
        "review_reason": review_reason,
        "safe_candidate_for_review": safe,
    }


def _report_row(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "mesh_index": item.get("mesh_index"),
        "mesh_name": item.get("mesh_name"),
        "primitive_index": item.get("primitive_index"),
        "material_name": item.get("material_name"),
        "source_entry": item.get("source_entry"),
        "part_type": item.get("part_type"),
        "declared_role": item.get("declared_role"),
        "material_binding_hash": item.get("material_binding_hash"),
        "instance_identity": item.get("instance_identity"),
        "stock_part": item.get("stock_part"),
        "part_option_ids": item.get("part_option_ids"),
        "draw_groups": item.get("draw_groups"),
        "converter_allowed_sides": item.get("converter_allowed_sides"),
        "converter_projection_sides": item.get("converter_projection_sides"),
        "declared_allowed_sides": item.get("declared_allowed_sides"),
        "uv3_evidence_sides": item.get("uv3_evidence_sides"),
        "selected_uv_evidence_sides": item.get("selected_uv_evidence_sides"),
        "inferred_mask_sides": item.get("inferred_mask_sides"),
        "final_allowed_sides": item.get("final_allowed_sides"),
        "risk_tokens": list(result["risk_tokens"]),
        "hard_non_livery_path": result["hard_non_livery_path"],
        "shell_path": result["shell_path"],
        "recovery_class": result["recovery_class"],
        "reason": result["reason"],
        "review_reason": result["review_reason"],
        "safe_candidate_for_review": result["safe_candidate_for_review"],
    }


def annotate_scene_recovery_diagnostics(
    scene: Any,
    provenance_by_mesh: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    missed_exterior: list[dict[str, Any]] = []
    provenance_by_mesh = provenance_by_mesh or {}

    for item in tuple(getattr(scene, "primitive_diagnostics", ()) or ()):
        if not isinstance(item, dict):
            continue
        mesh_index = item.get("mesh_index")
        if isinstance(mesh_index, int):
            _apply_provenance(item, provenance_by_mesh.get(mesh_index))

        result = classify_strict_recovery_candidate(item)
        item["livery_recovery_candidate"] = result["candidate"]
        item["livery_recovery_reason"] = result["reason"]
        item["livery_recovery_evidence_mask"] = result["evidence_mask"]
        item["livery_recovery_risk_tokens"] = list(result["risk_tokens"])
        item["livery_recovery_class"] = result["recovery_class"]
        item["livery_recovery_review_reason"] = result["review_reason"]
        item["livery_recovery_safe_candidate_for_review"] = result["safe_candidate_for_review"]

        row = _report_row(item, result)
        if result["candidate"]:
            candidates.append(row)

        # This broader inventory is intentionally diagnostic-only.  It captures
        # every Strict-missed Scene/Exterior primitive with real livery-mask
        # evidence, including unknown part types.  FXX-like exotic body layouts
        # can therefore be studied without relaxing Hybrid eligibility first.
        if (
            not int(item.get("final_allowed_sides") or 0)
            and "/scene/exterior/" in _canonical_source(item)
            and result["evidence_mask"]
        ):
            missed_exterior.append(row)

    class_counts: dict[str, int] = {}
    for row in candidates:
        key = str(row["recovery_class"])
        class_counts[key] = class_counts.get(key, 0) + 1

    missed_by_part_type: dict[str, int] = {}
    for row in missed_exterior:
        key = str(row.get("part_type") or "<unknown>")
        missed_by_part_type[key] = missed_by_part_type.get(key, 0) + 1

    return {
        "format": "fh6_livery_strict_recovery_diagnostic_v4",
        "policy": str(getattr(scene, "livery_eligibility_policy", "")),
        "candidate_count": len(candidates),
        "safe_candidate_count": sum(bool(row["safe_candidate_for_review"]) for row in candidates),
        "class_counts": class_counts,
        "candidates": candidates,
        "missed_exterior_count": len(missed_exterior),
        "missed_exterior_by_part_type": dict(sorted(missed_by_part_type.items())),
        "missed_exterior_inventory": missed_exterior,
    }


def _write_report_for_glb(path: Path | str, report: dict[str, Any]) -> Path | None:
    try:
        glb_path = Path(path)
        output = glb_path.with_suffix(glb_path.suffix + ".livery-recovery.json")
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return output
    except (OSError, TypeError, ValueError):
        return None


def install_livery_recovery_diagnostic_patch() -> bool:
    """Annotate/report Strict recovery evidence without changing base parser policy."""
    from . import glb_parser

    if getattr(glb_parser, "_fh6_livery_recovery_diagnostic_patched", False):
        return False

    original = glb_parser.load_kfps_glb

    def wrapped(path, *args, **kwargs):
        scene = original(path, *args, **kwargs)
        provenance = _load_mesh_provenance(path)
        report = annotate_scene_recovery_diagnostics(scene, provenance)
        report_path = _write_report_for_glb(path, report)
        if report_path is not None:
            for item in tuple(getattr(scene, "primitive_diagnostics", ()) or ()):
                if isinstance(item, dict):
                    item["livery_recovery_report_path"] = str(report_path)
        return scene

    glb_parser.load_kfps_glb = wrapped
    glb_parser._fh6_livery_recovery_diagnostic_patched = True

    integration = sys.modules.get(f"{__package__}.integration")
    if integration is not None and getattr(integration, "load_kfps_glb", None) is original:
        integration.load_kfps_glb = wrapped
    return True
