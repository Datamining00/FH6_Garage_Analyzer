"""FinalVerify1 ErrorFix1 3D livery rendering backend for FH6 Assistant."""

from .geometry_integrity_patch import install_geometry_integrity_patch

install_geometry_integrity_patch()

# Keep the established FinalVerify1 lazy installer contract: importing preview3d
# must not globally replace the conversion/tire APIs used by diagnostics and tests.
# The 3D tab calls install_validated_fxx_native_tire_preview() immediately before
# constructing Preview3DController. Redirect only that installer to the new native
# transform-chain path, then let the existing global installer wrap integration's
# convert_vehicle exactly once.
from . import tire_preview_integration as _tire_preview_integration


def _install_native_transform_chain_preview() -> bool:
    from .native_transform_chain_patch import install_native_transform_chain_patch

    install_native_transform_chain_patch()
    return _tire_preview_integration.install_global_stock_native_tire_preview()


_tire_preview_integration.install_validated_fxx_native_tire_preview = (
    _install_native_transform_chain_preview
)
