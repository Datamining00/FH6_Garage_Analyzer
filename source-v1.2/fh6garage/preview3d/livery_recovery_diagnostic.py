from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


_DIAGNOSTIC_RISK_TOKENS = (
    "headlight",
    "taillight",
    "headlamp",
    "taillamp",
    "lamp",
    "bulb",
    "intake",
    "grille",
    "grill",
    "vent",
    "exhaust",
    "brake",
    "wheel",
    "tire",
    "tyre",
)


def classify_strict_recovery_candidate(diagnostic: dict[str, Any]) -> dict[str, Any]:
    """Classify a Strict false-negative candidate without changing rendering.

    This is deliberately diagnostic-only. KFPS's published livery contract keeps
    converter-declared paint/glass authoritative and rejects unclassified geometry
    rather than guessing it into the livery route. We therefore collect evidence
    from Strict-missed exterior CarBody primitives first and only enable a future
    Hybrid policy after real-vehicle validation.
    """
    final_allowed = int(diagnostic.get("final_allowed_sides") or 0)
    structural = str(diagnostic.get("structural_livery_exclusion") or "").strip()
    role = str(diagnostic.get("declared_role") or "").strip().casefold()
    part_type = str(diagnostic.get("part_type") or "").strip().casefold()
    source = str(diagnostic.get("source_entry") or "").replace("\\", "/").casefold()
    canonical_source = f"/{source.lstrip('/')}"
    evidence_mask = int(
        diagnostic.get("selected_uv_evidence_sides")
        or diagnostic.get("uv3_evidence_sides")
        or diagnostic.get("inferred_mask_sides")
        or 0
    )

    if final_allowed:
        candidate = False
        reason = "already_eligible"
    elif structural:
        candidate = False
        reason = f"structural_exclusion:{structural}"
    elif part_type != "carbody":
        candidate = False
        reason = "not_carbody"
    elif "/scene/exterior/" not in canonical_source:
        candidate = False
        reason = "not_scene_exterior"
    elif not evidence_mask:
        candidate = False
        reason = "no_livery_mask_evidence"
    else:
        candidate = True
        reason = "strict_missed_exterior_carbody_with_mask_evidence"

    searchable = " ".join(
        (
            str(diagnostic.get("mesh_name") or ""),
            str(diagnostic.get("material_name") or ""),
            str(diagnostic.get("source_entry") or ""),
        )
    ).casefold()
    risk_tokens = tuple(token for token in _DIAGNOSTIC_RISK_TOKENS if token in searchable)

    return {
        "candidate": bool(candidate),
        "reason": reason,
        "declared_role": role,
        "evidence_mask": evidence_mask,
        "risk_tokens": risk_tokens,
        "safe_candidate_for_review": bool(candidate and not risk_tokens),
    }


def annotate_scene_recovery_diagnostics(scene: Any) -> dict[str, Any]:
    rows = []
    for item in tuple(getattr(scene, "primitive_diagnostics", ()) or ()):
        if not isinstance(item, dict):
            continue
        result = classify_strict_recovery_candidate(item)
        item["livery_recovery_candidate"] = result["candidate"]
        item["livery_recovery_reason"] = result["reason"]
        item["livery_recovery_evidence_mask"] = result["evidence_mask"]
        item["livery_recovery_risk_tokens"] = list(result["risk_tokens"])
        item["livery_recovery_safe_candidate_for_review"] = result["safe_candidate_for_review"]
        if result["candidate"]:
            rows.append({
                "mesh_index": item.get("mesh_index"),
                "mesh_name": item.get("mesh_name"),
                "primitive_index": item.get("primitive_index"),
                "material_name": item.get("material_name"),
                "source_entry": item.get("source_entry"),
                "part_type": item.get("part_type"),
                "declared_role": item.get("declared_role"),
                "declared_allowed_sides": item.get("declared_allowed_sides"),
                "uv3_evidence_sides": item.get("uv3_evidence_sides"),
                "selected_uv_evidence_sides": item.get("selected_uv_evidence_sides"),
                "inferred_mask_sides": item.get("inferred_mask_sides"),
                "final_allowed_sides": item.get("final_allowed_sides"),
                "risk_tokens": list(result["risk_tokens"]),
                "safe_candidate_for_review": result["safe_candidate_for_review"],
            })
    return {
        "format": "fh6_livery_strict_recovery_diagnostic_v1",
        "policy": str(getattr(scene, "livery_eligibility_policy", "")),
        "candidate_count": len(rows),
        "safe_candidate_count": sum(bool(row["safe_candidate_for_review"]) for row in rows),
        "candidates": rows,
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
    """Annotate/report Strict recovery evidence without changing render policy."""
    from . import glb_parser

    if getattr(glb_parser, "_fh6_livery_recovery_diagnostic_patched", False):
        return False

    original = glb_parser.load_kfps_glb

    def wrapped(path, *args, **kwargs):
        scene = original(path, *args, **kwargs)
        report = annotate_scene_recovery_diagnostics(scene)
        report_path = _write_report_for_glb(path, report)
        if report_path is not None:
            for item in tuple(getattr(scene, "primitive_diagnostics", ()) or ()):
                if isinstance(item, dict):
                    item["livery_recovery_report_path"] = str(report_path)
        return scene

    glb_parser.load_kfps_glb = wrapped
    glb_parser._fh6_livery_recovery_diagnostic_patched = True

    # If integration was imported before this late diagnostic installer, update
    # only the exact alias that still points at the original function. Do not
    # import integration here; avoiding that import keeps this patch cycle-free.
    integration = sys.modules.get(f"{__package__}.integration")
    if integration is not None and getattr(integration, "load_kfps_glb", None) is original:
        integration.load_kfps_glb = wrapped
    return True
