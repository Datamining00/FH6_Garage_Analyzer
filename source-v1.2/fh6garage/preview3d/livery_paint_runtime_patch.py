from __future__ import annotations

import json
from functools import wraps
from pathlib import Path

from .livery_paint_provenance import diagnose_livery_paint


LIVERY_PAINT_RUNTIME_PATCH_REVISION = 1
_PATCH_MARKER = "_fh6_livery_paint_provenance_runtime_patched"


def install_livery_paint_provenance_runtime_patch() -> bool:
    """Attach Paint P1 diagnostics to the established C_livery render path.

    This is deliberately non-authoritative for rendering. It does not alter the
    paint albedo, livery composite, material parameters, or game/save data. A
    diagnostic failure therefore cannot invalidate an otherwise valid 3D render.
    """
    from . import kfps_render_backend as backend

    current = backend.render_clivery_sections
    if bool(getattr(current, _PATCH_MARKER, False)):
        return True

    @wraps(current)
    def wrapped_render_clivery_sections(*args, **kwargs):
        result = current(*args, **kwargs)
        log = kwargs.get("log")
        report: dict
        try:
            report = diagnose_livery_paint(result.source_path)
            record_count = len(report.get("records") or [])
            output_path = Path(result.output_dir) / "paint_provenance.json"
            output_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            # RenderResult is a frozen dataclass for normal caller behavior, but
            # it is not slotted. Preserve the diagnostic as private derived state
            # without changing its public constructor or existing call sites.
            object.__setattr__(result, "_fh6_paint_provenance", report)
            object.__setattr__(result, "_fh6_paint_provenance_path", output_path)
            if callable(log):
                log(
                    "Paint P1 provenance: "
                    f"{record_count} raw descriptor record(s), "
                    "manufacturer selector/finish semantics unresolved; "
                    f"diagnostic -> {output_path.name}"
                )
        except Exception as exc:
            report = {
                "format": "fh6_livery_paint_provenance_v1",
                "status": "paint_provenance_unresolved",
                "rendering_applied": False,
                "game_data_modified": False,
                "error": str(exc),
                "interpretation_boundary": (
                    "Paint P1 diagnostics are non-fatal and do not alter existing paint/livery rendering."
                ),
            }
            object.__setattr__(result, "_fh6_paint_provenance", report)
            object.__setattr__(result, "_fh6_paint_provenance_path", None)
            if callable(log):
                log(f"Paint P1 provenance unavailable ({exc}); existing 3D rendering retained.")
        return result

    setattr(wrapped_render_clivery_sections, _PATCH_MARKER, True)
    backend.render_clivery_sections = wrapped_render_clivery_sections
    return True
