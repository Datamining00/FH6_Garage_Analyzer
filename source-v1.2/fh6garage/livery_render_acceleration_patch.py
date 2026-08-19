from __future__ import annotations

import concurrent.futures
import os
import time
from typing import Any

from .performance_metrics import record_metric


_APPLIED = False


def choose_tile_worker_count(
    scale: int,
    *,
    has_raster: bool,
    cpu_count: int | None = None,
    available_bytes: int | None = None,
) -> int:
    """Choose a conservative worker count for memory-heavy 4096px tiles."""
    if has_raster:
        # The current Decals.zip resolver is treated as single-threaded until its
        # archive access path is explicitly proven thread-safe.
        return 1
    cpu = max(1, int(cpu_count or os.cpu_count() or 1))
    if available_bytes is None:
        try:
            import psutil

            available_bytes = int(psutil.virtual_memory().available)
        except Exception:
            available_bytes = 2 * 1024**3
    available = max(1, int(available_bytes))
    # One projection tile can temporarily hold several RGBA/float32 arrays.
    estimated_per_worker = 900 * 1024**2
    memory_workers = max(1, available // estimated_per_worker)
    scale_cap = 2 if int(scale) >= 16 else 3
    cpu_workers = max(1, cpu // 2)
    return max(1, min(scale_cap, cpu_workers, memory_workers))


def _build_layer_bounds_index(tiled, native_renderer, layers, *, full_width: int, full_height: int):
    """Precompute conservative vector bounds once per 8x/16x render.

    The exact renderer still rasterizes the selected layers itself. The index is
    used only to avoid re-transforming thousands of placements that cannot touch
    a tile; unknown/raster entries remain uncullable and are always preserved.
    """
    world_bounds = (-1024.0, -512.0, 1024.0, 512.0)
    min_x, min_y, max_x, max_y = world_bounds

    def to_global(point):
        return (
            (point[0] - min_x) * full_width / (max_x - min_x),
            (max_y - point[1]) * full_height / (max_y - min_y),
        )

    indexed = []
    for shape in layers:
        bounds = None
        try:
            if not isinstance(shape, dict) or shape.get("is_raster_logo"):
                indexed.append((shape, None))
                continue
            data = list(shape.get("data") or [])
            if len(data) < 4:
                indexed.append((shape, None))
                continue
            type_code = int(shape.get("type", 0))
            resource = native_renderer._resolve_vinyl_resource(type_code, shape)
            alpha_triangles = native_renderer._resource_alpha_triangles(*resource) if resource else None
            if not alpha_triangles:
                indexed.append((shape, None))
                continue
            polygons = []
            for points, _values in alpha_triangles:
                if len(points) < 3:
                    continue
                transformed = native_renderer._transform_resource_polygon(points, data)
                polygons.append([to_global(point) for point in transformed])
            if polygons:
                bounds = tiled._global_polygon_bounds(polygons, full_width, full_height)
        except Exception:
            # Culling is an optimization only. Any uncertainty must fall back to
            # keeping the placement so exactness cannot be degraded.
            bounds = None
        indexed.append((shape, bounds))
    return indexed


def _subset_layers(tiled, indexed_layers, source_region):
    if source_region is None:
        return []
    return [
        shape
        for shape, bounds in indexed_layers
        if bounds is None or tiled._intersect(bounds, source_region) is not None
    ]


def _accelerated_tiled_projection(tiled, prepared_layers, renderer, *, section: str, car_id: int, game_folder, scale: int, raster_resolver=None) -> bytes:
    from PIL import Image

    projection_contract, slot, base_mask, projection, _mask_hash = tiled._projection_record(
        section, int(car_id), game_folder
    )
    base_bounds = projection_contract._projection_pixel_bounds(projection)
    high_bounds = tuple(int(value * scale) for value in base_bounds)
    retained_scale = tiled.RETAINED_SCALE_LIMIT
    ratio = scale // retained_scale
    final_size = (
        (base_bounds[2] - base_bounds[0]) * retained_scale,
        (base_bounds[3] - base_bounds[1]) * retained_scale,
    )
    final = Image.new("RGBA", final_size, (0, 0, 0, 0))

    full_size = (2048 * scale, 1024 * scale)
    _decoder, native_renderer = tiled._load_backend()
    index_started = time.perf_counter()
    indexed_layers = _build_layer_bounds_index(
        tiled,
        native_renderer,
        prepared_layers,
        full_width=full_size[0],
        full_height=full_size[1],
    )
    index_ms = (time.perf_counter() - index_started) * 1000.0

    overlap = max(32, 16 * ratio)
    overlap -= overlap % ratio
    tile_size = tiled.TILE_SIZE - (tiled.TILE_SIZE % ratio)
    hx0, hy0, hx1, hy1 = high_bounds
    affine = projection_contract._atlas_to_local_affine(
        slot,
        full_size[0],
        full_size[1],
        float(projection.get("xorigin", 0.0)) * scale,
        float(projection.get("yorigin", 0.0)) * scale,
    )

    jobs = []
    candidate_total = 0
    for core_y0 in range(hy0, hy1, tile_size):
        core_y1 = min(hy1, core_y0 + tile_size)
        for core_x0 in range(hx0, hx1, tile_size):
            core_x1 = min(hx1, core_x0 + tile_size)
            ex0 = max(hx0, core_x0 - overlap)
            ey0 = max(hy0, core_y0 - overlap)
            ex1 = min(hx1, core_x1 + overlap)
            ey1 = min(hy1, core_y1 + overlap)
            expanded = (ex0, ey0, ex1, ey1)
            source_region = tiled._source_region_for_output(
                affine, expanded, full_size, margin=12
            )
            subset = _subset_layers(tiled, indexed_layers, source_region)
            candidate_total += len(subset)
            jobs.append(
                (
                    expanded,
                    (core_x0, core_y0, core_x1, core_y1),
                    subset,
                )
            )

    has_raster = any(bool(layer.get("is_raster_logo")) for layer in prepared_layers if isinstance(layer, dict))
    workers = choose_tile_worker_count(scale, has_raster=has_raster)

    def render_job(job):
        expanded, core_box, subset = job
        ex0, ey0, ex1, ey1 = expanded
        core_x0, core_y0, core_x1, core_y1 = core_box
        art_hi, mask_hi = tiled._project_tile(
            projection_contract,
            subset,
            slot=slot,
            projection=projection,
            base_mask=base_mask,
            scale=scale,
            output_box=expanded,
            raster_resolver=raster_resolver,
        )
        down_size = ((ex1 - ex0) // ratio, (ey1 - ey0) // ratio)
        art = art_hi.resize(down_size, Image.Resampling.LANCZOS)
        mask = mask_hi.resize(down_size, Image.Resampling.LANCZOS)
        surface = Image.new("RGBA", down_size, (150, 154, 162, 0))
        surface.putalpha(mask.point(lambda value: (int(value) * 72) // 255))
        combined = Image.alpha_composite(surface, art)

        crop_left = (core_x0 - ex0) // ratio
        crop_top = (core_y0 - ey0) // ratio
        crop_right = crop_left + (core_x1 - core_x0) // ratio
        crop_bottom = crop_top + (core_y1 - core_y0) // ratio
        core = combined.crop((crop_left, crop_top, crop_right, crop_bottom))
        dest = ((core_x0 - hx0) // ratio, (core_y0 - hy0) // ratio)
        return dest, core

    tile_started = time.perf_counter()
    if workers <= 1 or len(jobs) <= 1:
        rendered = map(render_job, jobs)
        for dest, core in rendered:
            final.paste(core, dest)
    else:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="fh6-livery-tile",
        ) as pool:
            for dest, core in pool.map(render_job, jobs):
                final.paste(core, dest)
    tile_ms = (time.perf_counter() - tile_started) * 1000.0

    import io

    encode_started = time.perf_counter()
    buffer = io.BytesIO()
    final.save(buffer, format="PNG", compress_level=3)
    encode_ms = (time.perf_counter() - encode_started) * 1000.0

    layer_count = len(prepared_layers)
    average_candidates = (candidate_total / len(jobs)) if jobs else 0.0
    record_metric(
        "render_tiled_geometry_index",
        index_ms,
        scale=int(scale),
        layers=layer_count,
        tiles=len(jobs),
    )
    record_metric(
        "render_tiled_tiles",
        tile_ms,
        scale=int(scale),
        workers=workers,
        tiles=len(jobs),
        layers=layer_count,
        average_tile_candidates=round(average_candidates, 2),
        raster_serialized=bool(has_raster),
    )
    record_metric(
        "render_tiled_png_encode",
        encode_ms,
        scale=int(scale),
        width=final.size[0],
        height=final.size[1],
    )
    return buffer.getvalue()


def apply_livery_render_acceleration_patch() -> None:
    """Enable exact-output CPU acceleration and render-stage profiling."""
    global _APPLIED
    if _APPLIED:
        return

    from . import livery_preview_quality_pipeline as quality
    from . import livery_preview_tiled_quality as tiled

    # Keep stale previews from pre-acceleration/runtime-fix builds out of this
    # path. The image algorithm is intentionally unchanged; this also gives the
    # new timing/culling contract a clean cache namespace.
    tiled.CACHE_VERSION = "v14-tiled-quality-r4-cpu-accel"

    def accelerated_projection(prepared_layers, renderer, **kwargs):
        return _accelerated_tiled_projection(
            tiled,
            prepared_layers,
            renderer,
            **kwargs,
        )

    tiled._tiled_projection = accelerated_projection

    # 1x-4x already process each placement once and KFPS caches native resource
    # meshes. Profile their expensive stages rather than introducing unsafe
    # layer-level parallelism that could change ordered mask composition.
    original_native = quality._render_native_high_precision
    original_projection = quality._projection_high_precision

    def timed_native(*args: Any, **kwargs: Any):
        started = time.perf_counter()
        try:
            return original_native(*args, **kwargs)
        finally:
            config = kwargs.get("config")
            scale = getattr(config, "scale", kwargs.get("scale", 0))
            record_metric(
                "render_native_rasterization",
                (time.perf_counter() - started) * 1000.0,
                scale=int(scale or 0),
                layers=len(args[1]) if len(args) > 1 and hasattr(args[1], "__len__") else None,
            )

    def timed_projection(*args: Any, **kwargs: Any):
        started = time.perf_counter()
        try:
            return original_projection(*args, **kwargs)
        finally:
            record_metric(
                "render_vehicle_projection",
                (time.perf_counter() - started) * 1000.0,
            )

    quality._render_native_high_precision = timed_native
    quality._projection_high_precision = timed_projection
    _APPLIED = True
