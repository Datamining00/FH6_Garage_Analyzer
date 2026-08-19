from __future__ import annotations


_APPLIED = False


def _has_native_renderer_contract(candidate) -> bool:
    return all(
        callable(getattr(candidate, name, None))
        for name in (
            "_shape_mask_flag",
            "_resolve_vinyl_resource",
            "_resource_alpha_triangles",
            "_transform_resource_polygon",
        )
    )


def apply_livery_tiled_runtime_patch() -> None:
    """Keep vehicle projection contract and native shape renderer roles separate.

    The tiled projection code intentionally passes the vehicle render_contract
    into _project_tile because it owns _atlas_to_local_affine. That same object
    was then forwarded to _render_native_region, which instead needs the KFPS
    JSON/native renderer. This runtime patch selects the actual native renderer
    only for the source-tile artwork stage while leaving projection math intact.
    """
    global _APPLIED
    if _APPLIED:
        return

    from . import livery_preview_tiled_quality as tiled

    original_native_region = tiled._render_native_region

    def native_region_with_correct_backend(candidate, shapes, **kwargs):
        native_renderer = candidate
        if not _has_native_renderer_contract(native_renderer):
            _decoder, native_renderer = tiled._load_backend()
        return original_native_region(native_renderer, shapes, **kwargs)

    tiled._render_native_region = native_region_with_correct_backend
    _APPLIED = True
