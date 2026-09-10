from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Lock


_LOCK = Lock()


def _active_sections(source: str | Path, backend) -> tuple[str, ...] | None:
    """Decode only enough metadata to know which of the 11 sections contain layers.

    We deliberately use the same pinned decoder as the renderer instead of file
    heuristics. This adds one decode pass on a cache miss, but avoids allocating,
    PNG-encoding, writing and verifying huge transparent 4x canvases for empty
    sections. For typical liveries those image operations dominate the extra
    metadata pass.
    """
    try:
        root = backend.ensure_runtime(None)
        decoder, _renderer, _raster = backend._load_backend(root)
        payload = decoder.unwrap_forza_container(Path(source))
        layers, report = decoder.clivery_to_layers(payload)
        standard_layers = layers
        standard_report = report
        warnings = list((report or {}).get("warnings") or [])
        has_count_mismatch = any("stats target" in str(value) for value in warnings)
        has_raster = any(layer.get("is_raster_logo") for layer in layers)
        if has_raster and has_count_mismatch:
            boundary_layers, boundary_report = backend._decode_livery_sections_boundary_aware(decoder, payload)
            if len(boundary_layers) >= len(standard_layers):
                layers, report = boundary_layers, boundary_report
            else:
                layers, report = standard_layers, standard_report
        json_layers, _warnings = decoder.layers_to_kfps_json_layers(layers, game="fh6")
        active = {
            str(layer.get("source_section") or "")
            for layer in json_layers
            if str(layer.get("source_section") or "")
        }
        return tuple(name for name in backend.SECTION_NAMES if name in active)
    except Exception:
        # Optimization must never block a valid render.
        return None


def install_cold_livery_render_fastpath_patch() -> bool:
    """Avoid rendering full-size transparent PNGs for truly empty sections."""
    from . import kfps_render_backend as backend

    if getattr(backend, "_fh6_cold_livery_render_fastpath_patched", False):
        return False
    original = backend.render_clivery_sections
    all_sections = tuple(backend.SECTION_NAMES)

    def wrapped(source, *, game_folder=None, resolution=None, output_root=None, log=None):
        active = _active_sections(source, backend)
        if active is None or not active or len(active) == len(all_sections):
            return original(
                source,
                game_folder=game_folder,
                resolution=resolution,
                output_root=output_root,
                log=log,
            )

        if log:
            skipped = [name for name in all_sections if name not in active]
            log(
                "Cold render fast path: skipping empty livery section(s): "
                + ", ".join(skipped)
            )

        # render_clivery_sections and _section_layers read this module global at
        # call time. Serialize the temporary narrowed list so another preview
        # thread can never observe an incomplete section contract.
        with _LOCK:
            previous_sections = backend.SECTION_NAMES
            previous_section_layers = backend._section_layers

            def filtered_section_layers(layers):
                result = {name: [] for name in active}
                for layer in layers:
                    name = str(layer.get("source_section") or "")
                    if name in result:
                        result[name].append(layer)
                return result

            try:
                backend.SECTION_NAMES = list(active)
                backend._section_layers = filtered_section_layers
                result = original(
                    source,
                    game_folder=game_folder,
                    resolution=resolution,
                    output_root=output_root,
                    log=log,
                )
            finally:
                backend.SECTION_NAMES = previous_sections
                backend._section_layers = previous_section_layers

        counts = {name: 0 for name in all_sections}
        counts.update({str(k): int(v) for k, v in dict(result.section_counts).items()})
        return replace(result, section_counts=counts)

    backend.render_clivery_sections = wrapped
    backend._fh6_cold_livery_render_fastpath_patched = True
    return True
