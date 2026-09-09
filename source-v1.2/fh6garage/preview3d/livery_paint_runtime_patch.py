from __future__ import annotations

import json
from functools import wraps
from pathlib import Path

from .livery_paint_provenance import diagnose_livery_paint


LIVERY_PAINT_RUNTIME_PATCH_REVISION = 2
_PATCH_MARKER = "_fh6_livery_paint_provenance_runtime_patched"
_TEXTURE_PATCH_MARKER = "_fh6_livery_paint_provenance_texture_patched"


def install_livery_paint_provenance_runtime_patch() -> bool:
    """Attach read-only paint provenance to the established C_livery render path.

    Paint P1 still performs only descriptor inventory. Paint P2 additionally
    carries that derived report into DirectLiveryTextures as transient Python
    state so the viewer may exact-match GLB material binding hashes. Neither
    wrapper modifies game/save files, rendered livery pixels, or GLB bytes.
    """
    from . import direct_livery
    from . import kfps_render_backend as backend

    current = backend.render_clivery_sections
    if not bool(getattr(current, _PATCH_MARKER, False)):
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
                        "Paint provenance diagnostics are non-fatal and do not alter existing paint/livery rendering."
                    ),
                }
                object.__setattr__(result, "_fh6_paint_provenance", report)
                object.__setattr__(result, "_fh6_paint_provenance_path", None)
                if callable(log):
                    log(f"Paint P1 provenance unavailable ({exc}); existing 3D rendering retained.")
            return result

        setattr(wrapped_render_clivery_sections, _PATCH_MARKER, True)
        backend.render_clivery_sections = wrapped_render_clivery_sections

    current_textures = direct_livery.build_direct_livery_textures
    if not bool(getattr(current_textures, _TEXTURE_PATCH_MARKER, False)):
        @wraps(current_textures)
        def wrapped_build_direct_livery_textures(render_result, *args, **kwargs):
            textures = current_textures(render_result, *args, **kwargs)
            report = getattr(render_result, "_fh6_paint_provenance", None)
            if isinstance(report, dict):
                # DirectLiveryTextures is frozen but not slotted. This is transient
                # derived state only; no constructor/API change is required and
                # rerendered textures naturally receive the current C_livery report.
                object.__setattr__(textures, "_fh6_paint_provenance", report)
            return textures

        setattr(wrapped_build_direct_livery_textures, _TEXTURE_PATCH_MARKER, True)
        direct_livery.build_direct_livery_textures = wrapped_build_direct_livery_textures

    return True
