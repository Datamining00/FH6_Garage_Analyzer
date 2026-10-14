"""Evidence-closed native emissive Texture2D rendering for the FH6 preview.

External reference contract:
* ForzaTechStudio classifies explicit emissive Texture2D parameters as EmissiveMap
  and keeps texture processing enabled for car-paint materials.
* glTF 2.0 defines emissive RGB textures as sRGB inputs multiplied by a linear
  emissive factor.

This bridge therefore enables only exact render-plan selections with
semantic="emissive", exact UV0/material-tiling provenance, and DDS formats that
are explicitly sRGB-capable in native_material_gl. The sampled RGB modulates the
native emissive color/intensity when present. When the native emissive color is
absent, the established ForzaTechStudio fallback is mirrored by using the
already-composited linear albedo as the emissive factor. Texture alpha is never
used. Unsupported or ambiguous bindings fail closed per mesh.

No FH6 game/save data is modified.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from .native_dds import parse_native_dds
from .native_material_gl import upload_native_dds_2d
from .native_material_render_plan import (
    NativeMaterialRenderPlan,
    NativeMaterialTextureSelection,
)

NATIVE_EMISSIVE_RENDERING_REVISION = 1
_PATCH_MARKER = "_fh6_native_emissive_texture_rendering_patched"
_EMISSIVE_TEXTURE_UNIT = 7
_STANDARD_UV_TRANSFORM_MODE = "kfps_baked_texcoord_transform_vflip_plus_material_tiling"

# Only native GL mappings whose internal format performs sRGB decode are enabled.
# glTF's emissive contract requires sRGB RGB texels to be converted to linear
# before material computations. Linear/unknown color-space payloads remain
# diagnostic-only rather than being guessed.
_SRGB_EMISSIVE_DXGI = frozenset({29, 72, 75, 78, 99})


@dataclass(frozen=True)
class NativeEmissiveDrawRange:
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
        str(selection.semantic) == "emissive"
        and int(selection.dxgi_format) in _SRGB_EMISSIVE_DXGI
        and bool(selection.is_srgb)
        and int(selection.uv_channel) == 0
        and str(selection.uv_transform_mode) == _STANDARD_UV_TRANSFORM_MODE
        and math.isfinite(tiling_u)
        and math.isfinite(tiling_v)
        and abs(tiling_u) > 1e-6
        and abs(tiling_v) > 1e-6
    )


def _emissive_selection_by_mesh(
    plan: NativeMaterialRenderPlan,
) -> tuple[dict[int, NativeMaterialTextureSelection], dict[int, str]]:
    grouped: dict[int, list[NativeMaterialTextureSelection]] = {}
    for selection in plan.selections:
        if str(selection.semantic) == "emissive":
            grouped.setdefault(int(selection.mesh_index), []).append(selection)

    resolved: dict[int, NativeMaterialTextureSelection] = {}
    issues: dict[int, str] = {}
    for mesh_index, values in grouped.items():
        if not values or any(not _selection_has_reference_contract(value) for value in values):
            issues[mesh_index] = (
                "emissive binding is not an sRGB Texture2D with the exact "
                "UV0/material-tiling contract"
            )
            continue
        unique: dict[str, NativeMaterialTextureSelection] = {}
        for value in values:
            key = str(Path(value.dds_path).expanduser().resolve()).casefold()
            unique.setdefault(key, value)
        if len(unique) == 1:
            resolved[mesh_index] = next(iter(unique.values()))
        else:
            issues[mesh_index] = (
                "multiple emissive bindings resolve to different DDS derivatives"
            )
    return resolved, issues


def build_native_emissive_draw_ranges(
    scene_data: Any,
    plan: NativeMaterialRenderPlan,
) -> tuple[tuple[NativeEmissiveDrawRange, ...], tuple[str, ...]]:
    """Build exact per-primitive ranges in the parser's flattened index order."""
    selections, issue_map = _emissive_selection_by_mesh(plan)
    ranges: list[NativeEmissiveDrawRange] = []
    first_index = 0
    for diagnostic in tuple(getattr(scene_data, "primitive_diagnostics", ()) or ()):
        index_count = int(diagnostic.get("triangle_count", 0)) * 3
        if index_count < 0:
            raise ValueError("native emissive draw range has a negative index count")
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
            NativeEmissiveDrawRange(
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
            f"native emissive draw ranges cover {first_index} indices "
            f"but scene contains {expected}"
        )
    issues = tuple(f"mesh {mesh}: {detail}" for mesh, detail in sorted(issue_map.items()))
    return tuple(ranges), issues


def upgrade_native_emissive_fragment_shader(fragment: str) -> str:
    """Layer exact emissive-map sampling onto the established native PBR shader."""
    if "uNativeEmissiveEnabled" in fragment:
        return fragment
    if "in vec2 vMaterialUV;" not in fragment:
        return fragment

    uniform_marker = "            uniform int uNativeSurfaceRoughnessMode;\n"
    pbr_call_marker = "                vec3 shaded = fh6ShadeMaterial(\n"
    emission_arg_marker = "                    vMaterialEmission);\n"
    if (
        uniform_marker not in fragment
        or pbr_call_marker not in fragment
        or emission_arg_marker not in fragment
    ):
        return fragment

    upgraded = fragment.replace(
        uniform_marker,
        uniform_marker
        + "            uniform bool uNativeEmissiveEnabled;\n"
        + "            uniform sampler2D uNativeEmissive;\n"
        + "            uniform vec2 uNativeEmissiveTiling;\n",
        1,
    )

    emissive_block = """                vec4 effectiveEmission = vMaterialEmission;
                if (uNativeEmissiveEnabled) {
                    vec3 nativeEmissiveTexel = texture(
                        uNativeEmissive,
                        vMaterialUV * uNativeEmissiveTiling).rgb;
                    if (effectiveEmission.w > 0.5) {
                        effectiveEmission.rgb *= nativeEmissiveTexel;
                    } else {
                        effectiveEmission.rgb = albedo * nativeEmissiveTexel;
                        effectiveEmission.w = 1.0;
                    }
                }
"""
    upgraded = upgraded.replace(
        pbr_call_marker,
        emissive_block + pbr_call_marker,
        1,
    )
    return upgraded.replace(
        emission_arg_marker,
        "                    effectiveEmission);\n",
        1,
    )


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


def install_native_emissive_texture_patch() -> bool:
    """Install the narrow emissive Texture2D stage after normal-map wiring."""
    from . import glb_viewer, native_material_texture_patch as texture_patch

    widget_class = glb_viewer.CarOpenGLWidget
    if bool(getattr(widget_class, _PATCH_MARKER, False)):
        return False

    # native_material_texture_patch resolves this global at shader-build time.
    # At this point the normal stage has already wrapped it, so this wrapper
    # preserves base/surface/normal shader upgrades and adds emissive last.
    original_fragment_upgrade = texture_patch.upgrade_native_texture_fragment_shader

    def _fragment_upgrade_with_emissive(fragment: str) -> str:
        return upgrade_native_emissive_fragment_shader(original_fragment_upgrade(fragment))

    texture_patch.upgrade_native_texture_fragment_shader = _fragment_upgrade_with_emissive

    original_widget_init = widget_class.__init__
    original_initialize = widget_class.initializeGL
    original_paint = widget_class.paintGL
    original_close = widget_class.closeEvent

    def _widget_init_with_emissive(self, scene_data, *args, **kwargs):
        original_widget_init(self, scene_data, *args, **kwargs)
        self._fh6_native_emissive_texture_ids = {}
        self._fh6_native_emissive_draw_ranges = ()
        plan = getattr(self, "_fh6_native_texture_plan", None)
        if plan is None:
            self._fh6_native_emissive_status = "render_plan_unavailable"
            return
        try:
            ranges, issues = build_native_emissive_draw_ranges(self.scene_data, plan)
        except (OSError, ValueError) as exc:
            self._fh6_native_emissive_status = "draw_range_unavailable"
            self._fh6_native_emissive_error = f"{type(exc).__name__}: {exc}"
            return
        self._fh6_native_emissive_draw_ranges = ranges
        self._fh6_native_emissive_error = "; ".join(issues)
        self._fh6_native_emissive_status = "prepared"

    def _initialize_with_emissive(self) -> None:
        original_initialize(self)
        if not getattr(self, "_program", 0) or not getattr(self, "_vao", 0):
            return

        paths: list[str] = []
        for item in tuple(getattr(self, "_fh6_native_emissive_draw_ranges", ()) or ()):
            if item.dds_path and item.dds_path not in paths:
                paths.append(item.dds_path)
        if not paths:
            self._fh6_native_emissive_status = "no_eligible_emissive_maps"
            return

        from OpenGL import GL

        texture_ids: dict[str, int] = {}
        errors: list[str] = []
        for dds_path in paths:
            try:
                texture = parse_native_dds(dds_path)
                if (
                    int(texture.dxgi_format) not in _SRGB_EMISSIVE_DXGI
                    or not bool(texture.is_srgb)
                ):
                    raise ValueError(
                        "emissive DDS changed after render-plan validation"
                    )
                texture_ids[dds_path] = upload_native_dds_2d(GL, texture)
            except Exception as exc:
                texture_ids[dds_path] = 0
                errors.append(f"{Path(dds_path).name}: {type(exc).__name__}: {exc}")
        self._fh6_native_emissive_texture_ids = texture_ids
        if errors:
            self._fh6_native_emissive_status = "partial_gpu_upload"
            self._fh6_native_emissive_gpu_errors = tuple(errors)
        elif any(texture_ids.values()):
            self._fh6_native_emissive_status = "gpu_ready"
            self._fh6_native_emissive_gpu_errors = ()

    def _paint_with_emissive(self) -> None:
        from OpenGL import GL

        ranges = tuple(getattr(self, "_fh6_native_emissive_draw_ranges", ()) or ())
        texture_ids = dict(
            getattr(self, "_fh6_native_emissive_texture_ids", {}) or {}
        )
        if (
            not ranges
            or not getattr(self, "_program", 0)
            or not getattr(self, "_vao", 0)
        ):
            original_paint(self)
            return

        expected = int(len(self.scene_data.indices))
        if sum(item.index_count for item in ranges) != expected:
            original_paint(self)
            return

        enabled_loc = GL.glGetUniformLocation(self._program, "uNativeEmissiveEnabled")
        sampler_loc = GL.glGetUniformLocation(self._program, "uNativeEmissive")
        tiling_loc = GL.glGetUniformLocation(self._program, "uNativeEmissiveTiling")
        if min(int(enabled_loc), int(sampler_loc), int(tiling_loc)) < 0:
            self._fh6_native_emissive_status = "shader_uniforms_unavailable"
            original_paint(self)
            return

        by_draw = {
            (int(item.first_index) * 4, int(item.index_count)): item
            for item in ranges
        }
        real_draw = GL.glDrawElements
        intercepted = False

        def _draw_with_emissive(mode, count, index_type, pointer):
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
            GL.glUniform2f(
                tiling_loc,
                float(item.uv_tiling_u),
                float(item.uv_tiling_v),
            )
            if texture_id:
                GL.glActiveTexture(GL.GL_TEXTURE0 + _EMISSIVE_TEXTURE_UNIT)
                GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
                GL.glUniform1i(sampler_loc, _EMISSIVE_TEXTURE_UNIT)
            return real_draw(mode, count, index_type, pointer)

        GL.glDrawElements = _draw_with_emissive
        try:
            original_paint(self)
        finally:
            GL.glDrawElements = real_draw
            try:
                GL.glUniform1i(enabled_loc, 0)
                GL.glActiveTexture(GL.GL_TEXTURE0 + _EMISSIVE_TEXTURE_UNIT)
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
                GL.glActiveTexture(GL.GL_TEXTURE0)
            except Exception:
                pass

        if intercepted and any(texture_ids.values()):
            self._fh6_native_emissive_status = "rendering_reference_emissive"
        elif not intercepted:
            self._fh6_native_emissive_status = "draw_intercept_not_matched"

    def _close_with_emissive(self, event) -> None:
        texture_ids = [
            int(value)
            for value in dict(
                getattr(self, "_fh6_native_emissive_texture_ids", {}) or {}
            ).values()
            if int(value or 0) > 0
        ]
        if texture_ids:
            try:
                self.makeCurrent()
                from OpenGL import GL

                GL.glDeleteTextures(texture_ids)
                self._fh6_native_emissive_texture_ids = {}
                self.doneCurrent()
            except Exception:
                try:
                    self.doneCurrent()
                except Exception:
                    pass
        original_close(self, event)

    widget_class.__init__ = _widget_init_with_emissive
    widget_class.initializeGL = _initialize_with_emissive
    widget_class.paintGL = _paint_with_emissive
    widget_class.closeEvent = _close_with_emissive
    setattr(widget_class, _PATCH_MARKER, True)
    return True


__all__ = [
    "NATIVE_EMISSIVE_RENDERING_REVISION",
    "NativeEmissiveDrawRange",
    "build_native_emissive_draw_ranges",
    "install_native_emissive_texture_patch",
    "upgrade_native_emissive_fragment_shader",
]
