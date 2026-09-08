"""FinalVerify1 ErrorFix1 3D livery rendering backend for FH6 Assistant."""

from .geometry_integrity_patch import install_geometry_integrity_patch
from .native_transform_chain_patch import install_native_transform_chain_patch

install_geometry_integrity_patch()
install_native_transform_chain_patch()
