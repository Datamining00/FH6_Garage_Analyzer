"""FinalVerify1 ErrorFix1 3D livery rendering backend for FH6 Assistant."""

from __future__ import annotations

import sys


def _allow_missing_source_subset(exc: ModuleNotFoundError, module: str) -> bool:
    """Allow intentionally minimal source diagnostics, but never a frozen app gap."""
    return (
        exc.name == f"{__name__}.{module}"
        and not bool(getattr(sys, "frozen", False))
    )


try:
    from .geometry_integrity_patch import install_geometry_integrity_patch
except ModuleNotFoundError as exc:
    if not _allow_missing_source_subset(exc, "geometry_integrity_patch"):
        raise
else:
    install_geometry_integrity_patch()


def _install_native_transform_chain_preview() -> bool:
    from .material_appearance_patch import install_game_like_material_patch
    from .material_runtime_wiring_patch import install_material_runtime_wiring_patch
    from .native_material_texture_patch import install_native_material_texture_patch
    from .native_normal_texture_patch import install_native_normal_texture_patch
    from .native_emissive_texture_patch import install_native_emissive_texture_patch
    from .manufacturer_paint_texture_patch import install_manufacturer_paint_texture_patch
    from .glass_livery_composite_patch import install_glass_livery_composite_patch
    from .livery_paint_runtime_patch import install_livery_paint_provenance_runtime_patch
    from .native_transform_chain_v3 import install_native_transform_chain_v3
    from .geometry_cache_patch import install_geometry_cache_patch
    from .cold_livery_render_fastpath_patch import install_cold_livery_render_fastpath_patch
    from .livery_render_cache_patch import install_livery_render_cache_patch
    from .tire_preview_cache_patch import install_native_tire_preview_cache_patch
    from .native_tire_visibility_provenance_patch import install_native_tire_visibility_provenance_patch
    from .hybrid_livery_recovery_patch import install_hybrid_livery_recovery_patch
    from .strict_livery_default_patch import install_strict_livery_default_patch
    from .part_visibility_patch import install_part_visibility_patch
    from .preview_presentation_patch import install_preview_presentation_patch
    from . import tire_preview_integration as tire_preview_integration

    # Normal production preview keeps game/save data read-only. Persistent caches
    # store only derived GLBs, fully merged stock-tire previews, and rendered livery
    # sections under LocalAppData. Cold renders first narrow the pinned KFPS section
    # list to sections that actually contain decoded layers; the livery cache wraps
    # that production-visible fast path so subsequent opens skip decode/render too.
    # Repeated stock-tire opens reuse the already merged/baked derived GLB and the
    # pinned wheel DB is cryptographically hashed only once per unchanged process
    # file identity. Hybrid remains opt-in. Mechanical visibility filtering alters
    # only the in-memory scene index list; it never rewrites cached GLBs. Native tire
    # provenance is recovered from derived GLB node extras so the wheel/tire
    # checkbox can hide the separately merged rubber geometry reliably. Release
    # specs explicitly bundle the lazy tire cache patch and CI guards that contract.
    install_game_like_material_patch()
    install_material_runtime_wiring_patch()
    install_native_material_texture_patch()
    install_native_normal_texture_patch()
    install_native_emissive_texture_patch()
    install_manufacturer_paint_texture_patch()
    install_glass_livery_composite_patch()
    install_livery_paint_provenance_runtime_patch()
    install_native_transform_chain_v3()
    install_geometry_cache_patch()
    install_cold_livery_render_fastpath_patch()
    install_livery_render_cache_patch()
    install_native_tire_preview_cache_patch()
    install_native_tire_visibility_provenance_patch()
    install_hybrid_livery_recovery_patch()
    install_strict_livery_default_patch()
    install_part_visibility_patch()
    install_preview_presentation_patch()
    return tire_preview_integration.install_global_stock_native_tire_preview()


def _wire_native_tire_lazy_installer() -> bool:
    try:
        from . import tire_preview_integration as tire_preview_integration
    except ModuleNotFoundError as exc:
        if _allow_missing_source_subset(exc, "tire_preview_integration"):
            return False
        raise

    tire_preview_integration.install_validated_fxx_native_tire_preview = (
        _install_native_transform_chain_preview
    )
    return True


_wire_native_tire_lazy_installer()
