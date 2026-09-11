from __future__ import annotations

import json
import os
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import performance_metrics
from . import subsystem_log


def _rotated_paths(base: Path, rotations: int) -> list[Path]:
    paths = [base]
    for index in range(1, rotations + 1):
        paths.append(base.with_suffix(base.suffix + f".{index}"))
    return paths


def build_manifest(window: Any) -> dict[str, object]:
    result = getattr(window, "result", None)
    state = getattr(window, "_fh6_memory_state", None)
    settings = getattr(window, "settings", None)
    source = ""
    if settings is not None and hasattr(settings, "value"):
        try:
            source = str(settings.value("vehicle_data_source", "", str) or "").strip().casefold()
        except Exception:
            source = ""
    if source not in {"hdr", "user"}:
        source = "hdr"

    scan = {
        "available": result is not None,
        "liveries": len(getattr(result, "liveries", []) or []),
        "tunings": len(getattr(result, "tunings", []) or []),
        "warnings": len(getattr(result, "warnings", []) or []),
    }

    memory = {
        "available": state is not None,
        "scanned_at": getattr(state, "scanned_at", "") if state is not None else "",
        "status": getattr(state, "consensus_status", "") if state is not None else "",
        "usable": bool(getattr(state, "usable", False)) if state is not None else False,
        "active_livery_count": len(getattr(state, "active_livery_names", ()) or ()),
        "soulbound_applied_count": len(getattr(state, "soulbound_applied_names", ()) or ()),
        "soulbound_unapplied_count": len(getattr(state, "soulbound_unapplied_names", ()) or ()),
        "soulbound_review_count": len(getattr(state, "soulbound_review_names", ()) or ()),
        "candidate_regions": int(getattr(state, "candidate_regions", 0) or 0),
        "read_bytes": int(getattr(state, "read_bytes", 0) or 0),
        "read_failures": int(getattr(state, "read_failures", 0) or 0),
        "elapsed_seconds": float(getattr(state, "elapsed_seconds", 0.0) or 0.0),
    }

    return {
        "schema": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "application": {
            "window_title": str(window.windowTitle()) if hasattr(window, "windowTitle") else "FH6 Assistant",
            "python": platform.python_version(),
            "platform": platform.system(),
            "platform_release": platform.release(),
            "executable_kind": "frozen" if getattr(sys, "frozen", False) else "source",
        },
        "vehicle_data_source": source,
        "scan": scan,
        "memory": memory,
    }


def export_diagnostics(window: Any, target: Path) -> Path:
    """Create a privacy-minimized diagnostic ZIP without save data or paths."""
    target = Path(target)
    if target.suffix.casefold() != ".zip":
        target = target.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)

    diagnostic_paths = _rotated_paths(subsystem_log.log_path(), 2)
    performance_base = performance_metrics.log_path()
    performance_paths = _rotated_paths(performance_base, 3)
    latest_performance = performance_metrics.log_dir() / "latest.json"

    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            manifest = json.dumps(build_manifest(window), ensure_ascii=False, indent=2) + "\n"
            archive.writestr("manifest.json", manifest)

            for path in diagnostic_paths:
                if path.is_file():
                    archive.write(path, f"diagnostic/{path.name}")
            for path in performance_paths:
                if path.is_file():
                    archive.write(path, f"performance/{path.name}")
            if latest_performance.is_file():
                archive.write(latest_performance, "performance/latest.json")
        os.replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)
