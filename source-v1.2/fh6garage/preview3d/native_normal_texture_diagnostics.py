from __future__ import annotations

"""Read-only diagnostics for native FH6 normal-map candidates.

This module deliberately does not enable normal-map rendering. It records only
verified Texture2D selections already resolved by the native material render
plan and identifies the narrow unsigned-BC5 + standard-UV case that can advance
to a later decode/orientation validation stage.

No filename, material-name or vehicle-name inference is used. Signed BC5,
non-BC5 normal textures and ambiguous/unresolved bindings remain deferred.
"""

from dataclasses import asdict, dataclass
import math
from typing import Any

from .native_material_render_plan import NativeMaterialRenderPlan

NATIVE_NORMAL_TEXTURE_DIAGNOSTICS_REVISION = 1
_STANDARD_UV_TRANSFORM_MODE = "kfps_baked_texcoord_transform_vflip_plus_material_tiling"


@dataclass(frozen=True)
class NativeNormalTextureCandidateDiagnostic:
    mesh_index: int
    mesh_name: str
    mesh_role: str
    material_name: str
    parameter_hash: str
    parameter_name: str
    texture_path: str
    dds_path: str
    dds_sha256: str
    width: int
    height: int
    mip_levels: int
    dxgi_format: int
    compression_family: str
    is_srgb: bool
    uv_channel: int
    uv_tiling_u: float
    uv_tiling_v: float
    uv_transform_mode: str
    status: str
    detail: str
    unsigned_bc5_contract: bool
    standard_uv_contract: bool
    rendering_enabled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NativeNormalTextureIssueDiagnostic:
    mesh_index: int | None
    mesh_name: str
    material_name: str
    status: str
    detail: str
    texture_paths: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["texture_paths"] = list(self.texture_paths)
        return data


@dataclass(frozen=True)
class NativeNormalTextureDiagnostics:
    revision: int
    status: str
    candidate_count: int
    unsigned_bc5_candidate_count: int
    unresolved_issue_count: int
    candidates: tuple[NativeNormalTextureCandidateDiagnostic, ...]
    issues: tuple[NativeNormalTextureIssueDiagnostic, ...]
    rendering_enabled: bool = False
    game_data_modified: bool = False

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["candidates"] = [item.as_dict() for item in self.candidates]
        data["issues"] = [item.as_dict() for item in self.issues]
        return data


def _has_standard_uv_contract(selection: Any) -> bool:
    try:
        tiling_u = float(selection.uv_tiling_u)
        tiling_v = float(selection.uv_tiling_v)
    except (TypeError, ValueError):
        return False
    return bool(
        int(selection.uv_channel) == 0
        and str(selection.uv_transform_mode) == _STANDARD_UV_TRANSFORM_MODE
        and math.isfinite(tiling_u)
        and math.isfinite(tiling_v)
        and abs(tiling_u) > 1e-6
        and abs(tiling_v) > 1e-6
    )


def build_native_normal_texture_diagnostics(
    plan: NativeMaterialRenderPlan,
) -> NativeNormalTextureDiagnostics:
    """Classify verified primary-normal candidates without sampling them."""
    candidates: list[NativeNormalTextureCandidateDiagnostic] = []
    for selection in plan.selections:
        if str(selection.semantic) != "normal":
            continue
        unsigned_bc5 = bool(
            int(selection.dxgi_format) == 83
            and str(selection.compression_family).casefold() == "bc5"
            and not bool(selection.is_srgb)
        )
        standard_uv = _has_standard_uv_contract(selection)
        if not unsigned_bc5:
            status = "normal_format_deferred"
            detail = (
                "Primary normal Texture2D is verified, but only unsigned BC5_UNORM is admitted "
                "to the next validation stage. Rendering remains disabled."
            )
        elif not standard_uv:
            status = "normal_uv_contract_deferred"
            detail = (
                "Unsigned BC5 normal candidate does not carry the exact standard UV0/material-tiling "
                "contract. Rendering remains disabled."
            )
        else:
            status = "bc5_decode_orientation_validation_required"
            detail = (
                "Unsigned BC5 + standard UV provenance is complete. Tangent-free derivative TBN is "
                "possible, but BC5 Z reconstruction and Y/handedness must be validated before rendering."
            )
        candidates.append(
            NativeNormalTextureCandidateDiagnostic(
                mesh_index=int(selection.mesh_index),
                mesh_name=str(selection.mesh_name),
                mesh_role=str(selection.mesh_role),
                material_name=str(selection.material_name),
                parameter_hash=str(selection.parameter_hash),
                parameter_name=str(selection.parameter_name),
                texture_path=str(selection.texture_path),
                dds_path=str(selection.dds_path),
                dds_sha256=str(selection.dds_sha256),
                width=int(selection.width),
                height=int(selection.height),
                mip_levels=int(selection.mip_levels),
                dxgi_format=int(selection.dxgi_format),
                compression_family=str(selection.compression_family),
                is_srgb=bool(selection.is_srgb),
                uv_channel=int(selection.uv_channel),
                uv_tiling_u=float(selection.uv_tiling_u),
                uv_tiling_v=float(selection.uv_tiling_v),
                uv_transform_mode=str(selection.uv_transform_mode),
                status=status,
                detail=detail,
                unsigned_bc5_contract=unsigned_bc5,
                standard_uv_contract=standard_uv,
            )
        )

    issues = tuple(
        NativeNormalTextureIssueDiagnostic(
            mesh_index=issue.mesh_index,
            mesh_name=str(issue.mesh_name),
            material_name=str(issue.material_name),
            status=str(issue.status),
            detail=str(issue.detail),
            texture_paths=tuple(str(value) for value in issue.texture_paths),
        )
        for issue in plan.issues
        if str(issue.semantic) == "normal"
    )
    bc5_count = sum(
        1
        for candidate in candidates
        if candidate.unsigned_bc5_contract and candidate.standard_uv_contract
    )
    if candidates:
        status = "normal_candidates_deferred"
    elif issues:
        status = "normal_bindings_unresolved"
    else:
        status = "no_primary_normal_bindings"
    return NativeNormalTextureDiagnostics(
        revision=NATIVE_NORMAL_TEXTURE_DIAGNOSTICS_REVISION,
        status=status,
        candidate_count=len(candidates),
        unsigned_bc5_candidate_count=bc5_count,
        unresolved_issue_count=len(issues),
        candidates=tuple(candidates),
        issues=issues,
    )


__all__ = [
    "NATIVE_NORMAL_TEXTURE_DIAGNOSTICS_REVISION",
    "NativeNormalTextureCandidateDiagnostic",
    "NativeNormalTextureDiagnostics",
    "NativeNormalTextureIssueDiagnostic",
    "build_native_normal_texture_diagnostics",
]
