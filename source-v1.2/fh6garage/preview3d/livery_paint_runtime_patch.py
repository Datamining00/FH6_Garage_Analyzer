from __future__ import annotations

import json
from functools import wraps
from pathlib import Path

from .livery_paint_provenance import diagnose_livery_paint
from .manufacturer_colors import diagnose_manufacturer_colors_archive


LIVERY_PAINT_RUNTIME_PATCH_REVISION = 5
_PATCH_MARKER = "_fh6_livery_paint_provenance_runtime_patched"
_TEXTURE_PATCH_MARKER = "_fh6_livery_paint_provenance_texture_patched"


def _manufacturer_palette_report(asset) -> dict:
    archive_path = getattr(asset, "archive_path", None)
    if not archive_path:
        return {
            "format": "fh6_manufacturer_colors_v1",
            "status": "manufacturer_colors_archive_unavailable",
            "rendering_applied": False,
            "game_data_modified": False,
            "groups": [],
            "issues": ["Vehicle asset has no archive_path for ManufacturerColors.bin lookup."],
        }
    try:
        return diagnose_manufacturer_colors_archive(archive_path)
    except Exception as exc:
        return {
            "format": "fh6_manufacturer_colors_v1",
            "status": "manufacturer_colors_unresolved",
            "rendering_applied": False,
            "game_data_modified": False,
            "archive_file": str(archive_path),
            "groups": [],
            "issues": [f"{type(exc).__name__}: {exc}"],
            "interpretation_boundary": (
                "Manufacturer color provenance is non-fatal; failure retains the existing paint/livery rendering."
            ),
        }


def install_livery_paint_provenance_runtime_patch() -> bool:
    """Attach read-only paint provenance to the established C_livery render path.

    Paint P1 inventories C_livery descriptors. Paint P2 carries that report into
    DirectLiveryTextures for exact GLB material-hash matching. Paint P3A inventories
    the selected vehicle archive's ManufacturerColors.bin and carries the full
    group/entry structure as transient state. Paint P3B allows the downstream
    material bridge to consume only a resolved manufacturer's FH6 group-trailer
    primary RGB. Paint P3F additionally carries the exact C_livery source, selected
    vehicle archive, and derived cache root so a later manufacturer-overlay stage
    can resolve the P3D/P3E contract without guessing filesystem provenance.

    None of these wrappers modifies game/save files, rendered livery pixels, or
    GLB bytes.
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
                object.__setattr__(result, "_fh6_paint_provenance", report)
                object.__setattr__(result, "_fh6_paint_provenance_path", output_path)
                if callable(log):
                    log(
                        "Paint provenance: "
                        f"{record_count} raw descriptor record(s); "
                        "custom/manufacturer primary resolution available downstream, "
                        "secondary/finish semantics deferred; "
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
                    log(f"Paint provenance unavailable ({exc}); existing 3D rendering retained.")
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
                object.__setattr__(textures, "_fh6_paint_provenance", report)

            object.__setattr__(
                textures,
                "_fh6_paint_source",
                str(Path(render_result.source_path).expanduser().resolve()),
            )
            object.__setattr__(
                textures,
                "_fh6_manufacturer_cache_root",
                str(Path(render_result.output_dir).expanduser().resolve()),
            )

            asset = args[0] if args else kwargs.get("asset")
            archive_path = getattr(asset, "archive_path", None)
            if archive_path:
                object.__setattr__(
                    textures,
                    "_fh6_vehicle_archive",
                    str(Path(archive_path).expanduser().resolve()),
                )
            else:
                object.__setattr__(textures, "_fh6_vehicle_archive", None)

            palette_report = _manufacturer_palette_report(asset)
            object.__setattr__(textures, "_fh6_manufacturer_colors", palette_report)
            return textures

        setattr(wrapped_build_direct_livery_textures, _TEXTURE_PATCH_MARKER, True)
        direct_livery.build_direct_livery_textures = wrapped_build_direct_livery_textures

    return True
