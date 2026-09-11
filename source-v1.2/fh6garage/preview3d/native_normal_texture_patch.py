"""Reference-based BC5 native normal-map rendering for the FH6 preview.

This stage deliberately stays narrow:
* only exact render-plan selections with semantic="normal";
* only unsigned linear BC5_UNORM (DXGI 83);
* only the established KFPS TEXCOORD_0 + material-wide tiling contract;
* exactly one resolved normal DDS per mesh.

The current reference interpretation is R->X, G->Y, no green-channel inversion,
and +Z reconstruction via sqrt(max(0, 1-X^2-Y^2)). Tangent space is rebuilt
per fragment from world-position/UV derivatives, matching the previously
identified auto-tangent rendering approach. Any unsupported or ambiguous mesh
falls back to the existing vertex normal. Game/save data is never modified.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from .native_dds import parse_native_dds
from .native_material_gl import upload_native_dds_2d
from .native_material_render_plan import NativeMaterialRenderPlan, NativeMaterialTextureSelection

NATIVE_NORMAL_RENDERING_REVISION = 1
NATIVE_NORMAL_Y_SIGN = 1.0
_PATCH_MARKER = "_fh6_native_bc5_normal_rendering_patched"
_NORMAL_TEXTURE_UNIT = 6
_STANDARD_UV_TRANSFORM_MODE = "kfps_baked_texcoord_transform_vflip_plus_material_tiling"


@dataclass(frozen=True)
class NativeNormalDrawRange:
    first_index: int
    index_count: int
    mesh_index: int
    dds_path: str | None
    uv_tiling_u: float
    uv_tiling_v: float


def _selection_has_reference_contract(selection: NativeMaterialTextureSelection) -> bool:
    try:
        tiling_u = float(selection.uv_tiling_u)
        tiling_v = float(selection.uv_tiling_v)
    except (TypeError, ValueError):
        return False
    return bool(
        str(selection.semantic) == "normal"
        and int(selection.dxgi_format) == 83
        and str(selection.compression_family).casefold() == "bc5"
        and not bool(selection.is_srgb)
        and int(selection.uv_channel) == 0
        and str(selection.uv_transform_mode) == _STANDARD_UV_TRANSFORM_MODE
        and math.isfinite(tiling_u)
        and math.isfinite(tiling_v)
        and abs(tiling_u) > 1e-6
        and abs(tiling_v) > 1e-6
    )


def _normal_selection_by_mesh(
    plan: NativeMaterialRenderPlan,
) -> tuple[dict[int, NativeMaterialTextureSelection], dict[int, str]]:
    grouped: dict[int, list[NativeMaterialTextureSelection]] = {}
    for selection in plan.selections:
        if str(selection.semantic) == "normal":
            grouped.setdefault(int(selection.mesh_index), []).append(selection)

    resolved: dict[int, NativeMaterialTextureSelection] = {}
    issues: dict[int, str] = {}
    for mesh_index, values in grouped.items():
        if not values or any(not _selection_has_reference_contract(value) for value in values):
            issues[mesh_index] = (
                "normal binding is not a linear BC5_UNORM Texture2D with the exact UV0/material-tiling contract"
            )
            continue
        unique: dict[str, NativeMaterialTextureSelection] = {}
        for value in values:
            key = str(Path(value.dds_path).expanduser().resolve()).casefold()
            unique.setdefault(key, value)
        if len(unique) == 1:
            resolved[mesh_index] = next(iter(unique.values()))
        else:
            issues[mesh_index] = "multiple primary normal bindings resolve to different DDS derivatives"
    return resolved, issues


def build_native_normal_draw_ranges(
    scene_data: Any,
    plan: NativeMaterialRenderPlan,
) -> tuple[tuple[NativeNormalDrawRange, ...], tuple[str, ...]]:
    selections, issue_map = _normal_selection_by_mesh(plan)
    ranges: list[NativeNormalDrawRange] = []
    first_index = 0
    for diagnostic in tuple(getattr(scene_data, "primitive_diagnostics", ()) or ()):
        index_count = int(diagnostic.get("triangle_count", 0)) * 3
        if index_count < 0:
            raise ValueError("native normal draw range has a negative index count")
        mesh_index = int(diagnostic.get("mesh_index", -1))
        selection = selections.get(mesh_index)
        if selection is None:
            path = None
            tiling_u = 1.0
            tiling_v = 1.0
        else:
            path = str(Path(selection.dds_path).expanduser().resolve())
            tiling_u = float(selection.uv_tiling_u)
            tiling_v = float(selection.uv_tiling_v)
        ranges.append(
            NativeNormalDrawRange(
                first_index=first_index,
                index_count=index_count,
                mesh_index=mesh_index,
                dds_path=path,
                uv_tiling_u=tiling_u,
                uv_tiling_v=tiling_v,
            )
        )
        first_index += index_count

    expected = int(len(getattr(scene_data, "indices", ())))
    if first_index != expected:
        raise ValueError(
            f"native normal draw ranges cover {first_index} indices but scene contains {expected}"
        )
    issues = tuple(f"mesh {mesh}: {detail}" for mesh, detail in sorted(issue_map.items()))
    return tuple(ranges), issues


def upgrade_native_normal_fragment_shader(fragment: str) -> str:
    """Layer reference-based BC5 normal sampling onto the native material shader."""
    if "uNativeNormalEnabled" in fragment:
        return fragment
    if "in vec2 vMaterialUV;" not in fragment:
        return fragment
    uniform_marker = "            uniform int uNativeSurfaceRoughnessMode;\n"
    pbr_start = """                vec3 N = normalize(vNormal);
                vec3 V = normalize(uEye - vWorld);
"""
    if uniform_marker not in fragment or pbr_start not in fragment:
        return fragment
    uniforms = (
        uniform_marker
        + "            uniform bool uNativeNormalEnabled;\n"
        + "            uniform sampler2D uNativeNormal;\n"
        + "            uniform vec2 uNativeNormalTiling;\n"
        + "            uniform float uNativeNormalYSign;\n"
    )
    upgraded = fragment.replace(uniform_marker, uniforms, 1)
    normal_block = """                vec3 N = normalize(vNormal);
                vec3 V = normalize(uEye - vWorld);
                if (uNativeNormalEnabled) {
                    vec2 nativeNormalUV = vMaterialUV * uNativeNormalTiling;
                    vec2 nativeXY = texture(uNativeNormal, nativeNormalUV).rg * 2.0 - 1.0;
                    nativeXY.y *= uNativeNormalYSign;
                    float nativeZ = sqrt(max(0.0, 1.0 - dot(nativeXY, nativeXY)));
                    vec3 tangentNormal = normalize(vec3(nativeXY, nativeZ));

                    vec3 dp1 = dFdx(vWorld);
                    vec3 dp2 = dFdy(vWorld);
                    vec2 duv1 = dFdx(nativeNormalUV);
                    vec2 duv2 = dFdy(nativeNormalUV);
                    vec3 dp2perp = cross(dp2, N);
                    vec3 dp1perp = cross(N, dp1);
                    vec3 T = dp2perp * duv1.x + dp1perp * duv2.x;
                    vec3 B = dp2perp * duv1.y + dp1perp * duv2.y;
                    float tangentScale2 = max(dot(T, T), dot(B, B));
                    if (tangentScale2 > 1e-12) {
                        float invScale = inversesqrt(tangentScale2);
                        mat3 TBN = mat3(T * invScale, B * invScale, N);
                        vec3 mappedNormal = TBN * tangentNormal;
                        if (dot(mappedNormal, mappedNormal) > 1e-12) {
                            N = normalize(mappedNormal);
                        }
                    }
                }
"""
    return upgraded.replace(pbr_start, normal_block, 1)


def _pointer_byte_offset(pointer: Any) -> int | None:
    if pointer is None:
        return None
    if hasattr(pointer, "value"):
        value = getattr(pointer, "value")
        return 0 if value is None else int(value)
    try:
        return int(pointer)
    except (TypeError, ValueError):
        return None


def install_native_normal_texture_patch() -> bool:
    """Install the narrow BC5 normal stage after native material Texture2D wiring."""
    from . import glb_viewer, native_material_texture_patch as texture_patch

    widget_class = glb_viewer.CarOpenGLWidget
    if bool(getattr(widget_class, _PATCH_MARKER, False)):
        return False

    # The already-installed native Texture2D _make_program wrapper resolves this
    # module global at shader-build time. Wrapping it here layers normal GLSL
    # without replacing the established base/surface texture pipeline.
    original_fragment_upgrade = texture_patch.upgrade_native_texture_fragment_shader

    def _fragment_upgrade_with_normal(fragment: str) -> str:
        return upgrade_native_normal_fragment_shader(original_fragment_upgrade(fragment))

    texture_patch.upgrade_native_texture_fragment_shader = _fragment_upgrade_with_normal

    original_widget_init = widget_class.__init__
    original_initialize = widget_class.initializeGL
    original_paint = widget_class.paintGL
    original_close = widget_class.closeEvent

    def _widget_init_with_normal(self, scene_data, *args, **kwargs):
        original_widget_init(self, scene_data, *args, **kwargs)
        self._fh6_native_normal_texture_ids = {}
        self._fh6_native_normal_draw_ranges = ()
        plan = getattr(self, "_fh6_native_texture_plan", None)
        if plan is None:
            self._fh6_native_normal_status = "render_plan_unavailable"
            return
        try:
            ranges, issues = build_native_normal_draw_ranges(self.scene_data, plan)
        except (OSError, ValueError) as exc:
            self._fh6_native_normal_status = "draw_range_unavailable"
            self._fh6_native_normal_error = f"{type(exc).__name__}: {exc}"
            return
        self._fh6_native_normal_draw_ranges = ranges
        self._fh6_native_normal_error = "; ".join(issues)
        self._fh6_native_normal_status = "prepared"

    def _initialize_with_normal(self) -> None:
        original_initialize(self)
        if not getattr(self, "_program", 0) or not getattr(self, "_vao", 0):
            return
        paths: list[str] = []
        for item in tuple(getattr(self, "_fh6_native_normal_draw_ranges", ()) or ()):
            if item.dds_path and item.dds_path not in paths:
                paths.append(item.dds_path)
        if not paths:
            self._fh6_native_normal_status = "no_eligible_normal_maps"
            return

        from OpenGL import GL

        texture_ids: dict[str, int] = {}
        errors: list[str] = []
        for dds_path in paths:
            try:
                texture = parse_native_dds(dds_path)
                if int(texture.dxgi_format) != 83 or bool(texture.is_srgb):
                    raise ValueError("normal DDS changed after render-plan validation")
                texture_ids[dds_path] = upload_native_dds_2d(GL, texture)
            except Exception as exc:
                texture_ids[dds_path] = 0
                errors.append(f"{Path(dds_path).name}: {type(exc).__name__}: {exc}")
        self._fh6_native_normal_texture_ids = texture_ids
        if errors:
            self._fh6_native_normal_status = "partial_gpu_upload"
            self._fh6_native_normal_gpu_errors = tuple(errors)
        elif any(texture_ids.values()):
            self._fh6_native_normal_status = "gpu_ready"
            self._fh6_native_normal_gpu_errors = ()

    def _paint_with_normal(self) -> None:
        from OpenGL import GL

        ranges = tuple(getattr(self, "_fh6_native_normal_draw_ranges", ()) or ())
        texture_ids = dict(getattr(self, "_fh6_native_normal_texture_ids", {}) or {})
        if not ranges or not getattr(self, "_program", 0) or not getattr(self, "_vao", 0):
            original_paint(self)
            return
        expected = int(len(self.scene_data.indices))
        if sum(item.index_count for item in ranges) != expected:
            original_paint(self)
            return

        enabled_loc = GL.glGetUniformLocation(self._program, "uNativeNormalEnabled")
        sampler_loc = GL.glGetUniformLocation(self._program, "uNativeNormal")
        tiling_loc = GL.glGetUniformLocation(self._program, "uNativeNormalTiling")
        y_sign_loc = GL.glGetUniformLocation(self._program, "uNativeNormalYSign")
        if min(int(enabled_loc), int(sampler_loc), int(tiling_loc), int(y_sign_loc)) < 0:
            self._fh6_native_normal_status = "shader_uniforms_unavailable"
            original_paint(self)
            return

        by_draw = {
            (int(item.first_index) * 4, int(item.index_count)): item
            for item in ranges
        }
        real_draw = GL.glDrawElements
        intercepted = False

        def _draw_with_normal(mode, count, index_type, pointer):
            nonlocal intercepted
            offset = _pointer_byte_offset(pointer)
            item = by_draw.get((offset, int(count))) if offset is not None else None
            if (
                item is None
                or int(mode) != int(GL.GL_TRIANGLES)
                or int(index_type) != int(GL.GL_UNSIGNED_INT)
            ):
                GL.glUniform1i(enabled_loc, 0)
                return real_draw(mode, count, index_type, pointer)

            intercepted = True
            texture_id = int(texture_ids.get(item.dds_path or "", 0) or 0)
            GL.glUniform1i(enabled_loc, 1 if texture_id else 0)
            GL.glUniform2f(tiling_loc, float(item.uv_tiling_u), float(item.uv_tiling_v))
            GL.glUniform1f(y_sign_loc, float(NATIVE_NORMAL_Y_SIGN))
            if texture_id:
                GL.glActiveTexture(GL.GL_TEXTURE0 + _NORMAL_TEXTURE_UNIT)
                GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
                GL.glUniform1i(sampler_loc, _NORMAL_TEXTURE_UNIT)
            return real_draw(mode, count, index_type, pointer)

        GL.glDrawElements = _draw_with_normal
        try:
            original_paint(self)
        finally:
            GL.glDrawElements = real_draw
            try:
                GL.glUniform1i(enabled_loc, 0)
                GL.glActiveTexture(GL.GL_TEXTURE0 + _NORMAL_TEXTURE_UNIT)
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
                GL.glActiveTexture(GL.GL_TEXTURE0)
            except Exception:
                pass
        if intercepted and any(texture_ids.values()):
            self._fh6_native_normal_status = "rendering_reference_bc5"
        elif not intercepted:
            self._fh6_native_normal_status = "draw_intercept_not_matched"

    def _close_with_normal(self, event) -> None:
        texture_ids = [
            int(value)
            for value in dict(getattr(self, "_fh6_native_normal_texture_ids", {}) or {}).values()
            if int(value or 0) > 0
        ]
        if texture_ids:
            try:
                self.makeCurrent()
                from OpenGL import GL

                GL.glDeleteTextures(texture_ids)
                self._fh6_native_normal_texture_ids = {}
                self.doneCurrent()
            except Exception:
                try:
                    self.doneCurrent()
                except Exception:
                    pass
        original_close(self, event)

    widget_class.__init__ = _widget_init_with_normal
    widget_class.initializeGL = _initialize_with_normal
    widget_class.paintGL = _paint_with_normal
    widget_class.closeEvent = _close_with_normal
    setattr(widget_class, _PATCH_MARKER, True)
    return True


__all__ = [
    "NATIVE_NORMAL_RENDERING_REVISION",
    "NATIVE_NORMAL_Y_SIGN",
    "NativeNormalDrawRange",
    "build_native_normal_draw_ranges",
    "install_native_normal_texture_patch",
    "upgrade_native_normal_fragment_shader",
]
