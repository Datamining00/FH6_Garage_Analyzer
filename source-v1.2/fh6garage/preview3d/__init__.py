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


# Keep the established FinalVerify1 lazy installer contract: importing preview3d
# must not globally replace the conversion/tire APIs used by diagnostics and tests.
# The 3D tab calls install_validated_fxx_native_tire_preview() immediately before
# constructing Preview3DController. Redirect only that installer to the current
# global native transform-chain path, then let the existing global installer wrap
# integration's convert_vehicle exactly once.
def _install_native_transform_chain_preview() -> bool:
    from .material_appearance_patch import install_game_like_material_patch
    from .material_runtime_wiring_patch import install_material_runtime_wiring_patch
    from .native_material_texture_patch import install_native_material_texture_patch
    from .native_normal_texture_patch import install_native_normal_texture_patch
    from .native_transform_chain_v3 import install_native_transform_chain_v3
    from . import tire_preview_integration as tire_preview_integration

    # Viewer patches are installed before integration.py imports its load_kfps_glb
    # / CarOpenGLWidget symbols. Native material scalars/optics are wired first;
    # verified Texture2D sampling then layers onto that PBR shader without taking
    # authority away from dynamic car paint or the livery composite. The narrow
    # BC5 normal stage is installed after native Texture2D so it can reuse the
    # verified render plan and per-primitive draw interception contract.
    install_game_like_material_patch()
    install_material_runtime_wiring_patch()
    install_native_material_texture_patch()
    install_native_normal_texture_patch()
    install_native_transform_chain_v3()
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
