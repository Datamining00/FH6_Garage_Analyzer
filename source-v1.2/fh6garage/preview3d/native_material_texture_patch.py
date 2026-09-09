"""Production viewer bridge for verified native FH6 Texture2D maps.

The rendering bridge enables two evidence-closed stages:
* standard non-car-paint base-colour textures;
* standard non-car-paint single-channel roughness/gloss textures.

It preserves the existing livery/paint albedo authority, uses exact TEXCOORD_0
plus material-wide tiling provenance, uploads DDS payloads without CPU
reinterpretation, and fails closed per texture/mesh when evidence is absent.
Packed RoughMetalAO, AO, normal, flake and clear-coat maps remain deferred until
their channel/tangent contracts are explicit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any

import numpy as np

from .native_dds import parse_native_dds
from .native_material_gl import NativeMaterialGlError, upload_native_dds_2d
from .native_material_render_plan import (
    NativeMaterialRenderPlan,
    NativeMaterialRenderPlanError,
    NativeMaterialTextureSelection,
    build_native_material_render_plan,
)

_PATCH_MARKER = "_fh6_native_base_color_texture_rendering_patched"
_BASE_TEXTURE_UNIT = 4
_SURFACE_TEXTURE_UNIT = 5
_VERTEX_LOCATION = 12
_BASE_SEMANTICS = {"base_color", "base_color_alpha"}
_SURFACE_SEMANTICS = {"roughness", "gloss"}
_BASE_COLOR_DXGI = {71, 72, 74, 75, 77, 78, 98, 99, 28, 29, 87}
_SINGLE_CHANNEL_SURFACE_DXGI = {80, 61}  # BC4_UNORM, R8_UNORM


@dataclass(frozen=True)
class NativeBaseColorDrawRange:
    first_index: int
    index_count: int
    mesh_index: int
    dds_path: str | None
    uv_tiling_u: float
    uv_tiling_v: float
    surface_dds_path: str | None = None
    surface_mode: str | None = None


def upgrade_native_texture_vertex_shader(vertex: str) -> str:
    if "inMaterialUV" in vertex:
        return vertex
    attr_marker = "            layout(location=11) in vec4 inMaterialEmission;\n"
    out_marker = "            out vec4 vMaterialEmission;\n"
    assign_marker = "                vMaterialEmission = inMaterialEmission;\n"
    if attr_marker not in vertex or out_marker not in vertex or assign_marker not in vertex:
        return vertex
    upgraded = vertex.replace(
        attr_marker,
        attr_marker + "            layout(location=12) in vec2 inMaterialUV;\n",
        1,
    )
    upgraded = upgraded.replace(
        out_marker,
        out_marker + "            out vec2 vMaterialUV;\n",
        1,
    )
    return upgraded.replace(
        assign_marker,
        assign_marker + "                vMaterialUV = inMaterialUV;\n",
        1,
    )


def upgrade_native_texture_fragment_shader(fragment: str) -> str:
    if "uNativeBaseColorEnabled" in fragment:
        return fragment
    input_marker = "            in vec4 vMaterialEmission;\n"
    uniform_marker = "            uniform vec3 uEye;\n"
    albedo_marker = """                vec3 albedo = vMaterialAux.y >= 0.0
                    ? clamp(vMaterialAux.yzw, 0.0, 1.0)
                    : pow(clamp(vColor, 0.0, 1.0), vec3(2.2));
                albedo = mix(albedo, decalLinear, decal.a);
"""
    pbr_call_marker = """                vec3 shaded = fh6ShadeMaterial(
                    albedo,
                    N,
                    V,
                    vMaterialParams,
"""
    if input_marker not in fragment or uniform_marker not in fragment or albedo_marker not in fragment:
        return fragment
    upgraded = fragment.replace(
        input_marker,
        input_marker + "            in vec2 vMaterialUV;\n",
        1,
    )
    upgraded = upgraded.replace(
        uniform_marker,
        uniform_marker
        + "            uniform bool uNativeBaseColorEnabled;\n"
        + "            uniform sampler2D uNativeBaseColor;\n"
        + "            uniform vec2 uNativeBaseColorTiling;\n"
        + "            uniform bool uNativeSurfaceRoughnessEnabled;\n"
        + "            uniform sampler2D uNativeSurfaceRoughness;\n"
        + "            uniform vec2 uNativeSurfaceRoughnessTiling;\n"
        + "            uniform int uNativeSurfaceRoughnessMode;\n",
        1,
    )
    replacement = """                vec3 albedo = vMaterialAux.y >= 0.0
                    ? clamp(vMaterialAux.yzw, 0.0, 1.0)
                    : pow(clamp(vColor, 0.0, 1.0), vec3(2.2));
                if (uNativeBaseColorEnabled) {
                    albedo = texture(uNativeBaseColor, vMaterialUV * uNativeBaseColorTiling).rgb;
                }
                albedo = mix(albedo, decalLinear, decal.a);
"""
    upgraded = upgraded.replace(albedo_marker, replacement, 1)
    if pbr_call_marker in upgraded:
        surface_replacement = """                vec4 effectiveMaterialParams = vMaterialParams;
                if (uNativeSurfaceRoughnessEnabled) {
                    float nativeSurfaceValue = texture(
                        uNativeSurfaceRoughness,
                        vMaterialUV * uNativeSurfaceRoughnessTiling).r;
                    float nativeRoughness = uNativeSurfaceRoughnessMode == 2
                        ? 1.0 - nativeSurfaceValue
                        : nativeSurfaceValue;
                    effectiveMaterialParams.y = clamp(nativeRoughness, 0.025, 1.0);
                }
                vec3 shaded = fh6ShadeMaterial(
                    albedo,
                    N,
                    V,
                    effectiveMaterialParams,
"""
        upgraded = upgraded.replace(pbr_call_marker, surface_replacement, 1)
    return upgraded


def build_native_material_uv0_stream(glb_path: str | Path, scene_data: Any) -> np.ndarray:
    """Flatten exact exported TEXCOORD_0 in the parser's included primitive order."""
    from .glb_parser import _accessor_array, _read_glb

    document, binary = _read_glb(Path(glb_path).expanduser().resolve())
    meshes = document.get("meshes") or []
    chunks: list[np.ndarray] = []
    for diagnostic in tuple(getattr(scene_data, "primitive_diagnostics", ()) or ()):
        mesh_index = int(diagnostic.get("mesh_index", -1))
        primitive_index = int(diagnostic.get("primitive_index", -1))
        if mesh_index < 0 or mesh_index >= len(meshes):
            raise ValueError("native material UV mesh index is outside the GLB")
        primitives = meshes[mesh_index].get("primitives") or []
        if primitive_index < 0 or primitive_index >= len(primitives):
            raise ValueError("native material UV primitive index is outside the GLB")
        attrs = primitives[primitive_index].get("attributes") or {}
        if "POSITION" not in attrs:
            raise ValueError("native material UV primitive has no POSITION accessor")
        positions = _accessor_array(document, binary, int(attrs["POSITION"]))
        vertex_count = int(len(positions))
        if "TEXCOORD_0" not in attrs:
            chunks.append(np.zeros((vertex_count, 2), dtype=np.float32))
            continue
        uv = _accessor_array(document, binary, int(attrs["TEXCOORD_0"])).astype(
            np.float32, copy=False
        )
        if uv.shape != (vertex_count, 2) or not np.isfinite(uv).all():
            raise ValueError("native material TEXCOORD_0 is invalid or has a vertex-count mismatch")
        chunks.append(np.ascontiguousarray(uv, dtype=np.float32))
    if chunks:
        stream = np.ascontiguousarray(np.concatenate(chunks), dtype=np.float32)
    else:
        stream = np.empty((0, 2), dtype=np.float32)
    expected = int(len(getattr(scene_data, "positions", ())))
    if stream.shape != (expected, 2):
        raise ValueError(
            f"native material UV stream vertex count mismatch: {stream.shape} != ({expected}, 2)"
        )
    return stream


def _base_selection_by_mesh(
    plan: NativeMaterialRenderPlan,
) -> tuple[dict[int, NativeMaterialTextureSelection], dict[int, str]]:
    grouped: dict[int, list[NativeMaterialTextureSelection]] = {}
    for selection in plan.selections:
        if selection.semantic in _BASE_SEMANTICS:
            grouped.setdefault(int(selection.mesh_index), []).append(selection)
    resolved: dict[int, NativeMaterialTextureSelection] = {}
    issues: dict[int, str] = {}
    for mesh_index, values in grouped.items():
        supported = [value for value in values if int(value.dxgi_format) in _BASE_COLOR_DXGI]
        if len(supported) != len(values):
            issues[mesh_index] = "base-color DDS format is not enabled for RGB material sampling"
            continue
        by_path: dict[str, NativeMaterialTextureSelection] = {}
        for value in supported:
            by_path.setdefault(str(Path(value.dds_path).expanduser().resolve()).casefold(), value)
        if len(by_path) == 1:
            resolved[mesh_index] = next(iter(by_path.values()))
        elif len(by_path) > 1:
            issues[mesh_index] = "multiple base-color semantics resolve to different DDS derivatives"
    return resolved, issues


def _surface_selection_by_mesh(
    plan: NativeMaterialRenderPlan,
) -> tuple[dict[int, NativeMaterialTextureSelection], dict[int, str]]:
    grouped: dict[int, list[NativeMaterialTextureSelection]] = {}
    issues: dict[int, str] = {}
    for selection in plan.selections:
        if selection.semantic not in _SURFACE_SEMANTICS:
            continue
        mesh_index = int(selection.mesh_index)
        if str(selection.mesh_role or "").casefold() == "paint":
            issues[mesh_index] = "paint roughness/gloss texture is deferred until the car-paint map contract is explicit"
            continue
        if int(selection.dxgi_format) not in _SINGLE_CHANNEL_SURFACE_DXGI or bool(selection.is_srgb):
            issues[mesh_index] = "roughness/gloss texture is not an unsigned linear single-channel BC4/R8 DDS"
            continue
        grouped.setdefault(mesh_index, []).append(selection)

    resolved: dict[int, NativeMaterialTextureSelection] = {}
    for mesh_index, values in grouped.items():
        # A mesh is all-or-nothing for this first surface-texture stage. If any
        # roughness/gloss binding on the mesh was rejected above, retain the
        # scalar native material value rather than selecting a surviving map.
        if mesh_index in issues:
            continue
        unique: dict[tuple[str, str], NativeMaterialTextureSelection] = {}
        for value in values:
            key = (
                str(value.semantic),
                str(Path(value.dds_path).expanduser().resolve()).casefold(),
            )
            unique.setdefault(key, value)
        if len(unique) == 1:
            resolved[mesh_index] = next(iter(unique.values()))
        elif len(unique) > 1:
            issues[mesh_index] = "multiple roughness/gloss bindings are ambiguous for one mesh"
    return resolved, issues


def build_native_base_color_draw_ranges(
    scene_data: Any,
    plan: NativeMaterialRenderPlan,
) -> tuple[tuple[NativeBaseColorDrawRange, ...], tuple[str, ...]]:
    base_selections, base_issues = _base_selection_by_mesh(plan)
    surface_selections, surface_issues = _surface_selection_by_mesh(plan)
    ranges: list[NativeBaseColorDrawRange] = []
    merged_issues = dict(base_issues)
    for mesh_index, detail in surface_issues.items():
        if mesh_index in merged_issues:
            merged_issues[mesh_index] = merged_issues[mesh_index] + "; " + detail
        else:
            merged_issues[mesh_index] = detail
    issues = [f"mesh {mesh}: {detail}" for mesh, detail in sorted(merged_issues.items())]
    first_index = 0
    for diagnostic in tuple(getattr(scene_data, "primitive_diagnostics", ()) or ()):
        index_count = int(diagnostic.get("triangle_count", 0)) * 3
        if index_count < 0:
            raise ValueError("native material draw range has a negative index count")
        mesh_index = int(diagnostic.get("mesh_index", -1))
        base = base_selections.get(mesh_index)
        surface = surface_selections.get(mesh_index)
        if base is None:
            dds_path = None
            tiling_u = 1.0
            tiling_v = 1.0
        else:
            dds_path = str(Path(base.dds_path).expanduser().resolve())
            tiling_u = float(base.uv_tiling_u)
            tiling_v = float(base.uv_tiling_v)
        surface_path = (
            str(Path(surface.dds_path).expanduser().resolve()) if surface is not None else None
        )
        # FTS applies one material-wide tiling to all standard material maps. If
        # there is no base map, preserve the surface selection's same contract.
        if base is None and surface is not None:
            tiling_u = float(surface.uv_tiling_u)
            tiling_v = float(surface.uv_tiling_v)
        ranges.append(
            NativeBaseColorDrawRange(
                first_index=first_index,
                index_count=index_count,
                mesh_index=mesh_index,
                dds_path=dds_path,
                uv_tiling_u=tiling_u,
                uv_tiling_v=tiling_v,
                surface_dds_path=surface_path,
                surface_mode=str(surface.semantic) if surface is not None else None,
            )
        )
        first_index += index_count
    expected = int(len(getattr(scene_data, "indices", ())))
    if first_index != expected:
        raise ValueError(
            f"native material draw ranges cover {first_index} indices but scene contains {expected}"
        )
    return tuple(ranges), tuple(issues)


def configure_native_material_texture_widget(widget: Any, glb_path: str | Path) -> bool:
    """Prepare render-plan, UV0 stream and primitive draw ranges without touching GL."""
    try:
        plan = build_native_material_render_plan(glb_path)
        uv0 = build_native_material_uv0_stream(glb_path, widget.scene_data)
        ranges, range_issues = build_native_base_color_draw_ranges(widget.scene_data, plan)
    except (OSError, ValueError, NativeMaterialRenderPlanError) as exc:
        widget._fh6_native_texture_plan = None
        widget._fh6_native_material_uv0 = None
        widget._fh6_native_base_draw_ranges = ()
        widget._fh6_native_texture_prepare_error = f"{type(exc).__name__}: {exc}"
        return False
    widget._fh6_native_texture_plan = plan
    widget._fh6_native_material_uv0 = uv0
    widget._fh6_native_base_draw_ranges = ranges
    widget._fh6_native_texture_prepare_error = "; ".join(range_issues)
    return True


def _copy_native_texture_sidecar(source_glb: str | Path, selected_glb: str | Path) -> bool:
    source = Path(source_glb).expanduser().resolve()
    selected = Path(selected_glb).expanduser().resolve()
    if source == selected:
        return True
    source_manifest = source.with_suffix(source.suffix + ".native_textures.json")
    selected_manifest = selected.with_suffix(selected.suffix + ".native_textures.json")
    if not source_manifest.is_file():
        return False
    try:
        payload = json.loads(source_manifest.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("game_data_modified") is not False:
            return False
        selected_manifest.parent.mkdir(parents=True, exist_ok=True)
        temp = selected_manifest.with_suffix(selected_manifest.suffix + ".tmp")
        shutil.copyfile(source_manifest, temp)
        temp.replace(selected_manifest)
        return True
    except (OSError, ValueError, json.JSONDecodeError):
        try:
            temp.unlink(missing_ok=True)  # type: ignore[possibly-undefined]
        except Exception:
            pass
        return False


def install_native_material_texture_patch() -> bool:
    """Install the verified production native Texture2D rendering stages exactly once."""
    from . import glb_viewer, tire_preview_integration
    from .material_appearance_patch import upgrade_fragment_shader, upgrade_vertex_shader

    widget_class = glb_viewer.CarOpenGLWidget
    if bool(getattr(widget_class, _PATCH_MARKER, False)):
        return False

    original_make_program = widget_class._make_program.__func__
    original_widget_init = widget_class.__init__
    original_initialize = widget_class.initializeGL
    original_paint = widget_class.paintGL
    original_close = widget_class.closeEvent
    original_tire_apply = tire_preview_integration.try_apply_stock_native_tire_preview

    def _make_program_with_native_texture(cls, vertex: str, fragment: str) -> int:
        vertex = upgrade_vertex_shader(vertex)
        fragment = upgrade_fragment_shader(fragment)
        vertex = upgrade_native_texture_vertex_shader(vertex)
        fragment = upgrade_native_texture_fragment_shader(fragment)
        return original_make_program(cls, vertex, fragment)

    def _widget_init_with_native_texture(self, scene_data, *args, **kwargs):
        original_widget_init(self, scene_data, *args, **kwargs)
        self._fh6_native_material_uv_vbo = 0
        self._fh6_native_texture_ids = {}
        glb_path = str(getattr(self, "_fh6_glb_path", "") or "").strip()
        if not glb_path:
            self._fh6_native_texture_status = "glb_source_unavailable"
            return
        configured = configure_native_material_texture_widget(self, glb_path)
        self._fh6_native_texture_status = "prepared" if configured else "unavailable"

    def _initialize_with_native_texture(self) -> None:
        original_initialize(self)
        if not getattr(self, "_program", 0) or not getattr(self, "_vao", 0):
            return
        from OpenGL import GL

        uv0 = getattr(self, "_fh6_native_material_uv0", None)
        GL.glBindVertexArray(self._vao)
        GL.glDisableVertexAttribArray(_VERTEX_LOCATION)
        GL.glVertexAttrib2f(_VERTEX_LOCATION, 0.0, 0.0)
        if (
            isinstance(uv0, np.ndarray)
            and uv0.shape == (len(self.scene_data.positions), 2)
            and np.isfinite(uv0).all()
        ):
            uv0 = np.ascontiguousarray(uv0, dtype=np.float32)
            self._fh6_native_material_uv_vbo = GL.glGenBuffers(1)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._fh6_native_material_uv_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, uv0.nbytes, uv0, GL.GL_STATIC_DRAW)
            GL.glEnableVertexAttribArray(_VERTEX_LOCATION)
            GL.glVertexAttribPointer(
                _VERTEX_LOCATION, 2, GL.GL_FLOAT, GL.GL_FALSE, 2 * 4, GL.GLvoidp(0)
            )
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)

        texture_ids: dict[str, int] = {}
        errors: list[str] = []
        paths: list[str] = []
        for draw_range in tuple(getattr(self, "_fh6_native_base_draw_ranges", ()) or ()):
            for candidate in (draw_range.dds_path, draw_range.surface_dds_path):
                if candidate and candidate not in paths:
                    paths.append(candidate)
        for dds_path in paths:
            try:
                texture = parse_native_dds(dds_path)
                texture_ids[dds_path] = upload_native_dds_2d(GL, texture)
            except Exception as exc:
                # Keep geometry/PBR/livery rendering alive if this GPU cannot
                # sample one native compression family.
                texture_ids[dds_path] = 0
                errors.append(f"{Path(dds_path).name}: {type(exc).__name__}: {exc}")
        self._fh6_native_texture_ids = texture_ids
        if errors:
            self._fh6_native_texture_status = "partial_gpu_upload"
            self._fh6_native_texture_gpu_errors = tuple(errors)
        elif any(texture_ids.values()):
            self._fh6_native_texture_status = "gpu_ready"
            self._fh6_native_texture_gpu_errors = ()

    def _paint_with_native_texture(self) -> None:
        from OpenGL import GL

        ranges = tuple(getattr(self, "_fh6_native_base_draw_ranges", ()) or ())
        texture_ids = dict(getattr(self, "_fh6_native_texture_ids", {}) or {})
        if not ranges or not getattr(self, "_program", 0) or not getattr(self, "_vao", 0):
            original_paint(self)
            return
        expected = int(len(self.scene_data.indices))
        if sum(item.index_count for item in ranges) != expected:
            original_paint(self)
            return

        base_enabled_loc = GL.glGetUniformLocation(self._program, "uNativeBaseColorEnabled")
        base_sampler_loc = GL.glGetUniformLocation(self._program, "uNativeBaseColor")
        base_tiling_loc = GL.glGetUniformLocation(self._program, "uNativeBaseColorTiling")
        if min(int(base_enabled_loc), int(base_sampler_loc), int(base_tiling_loc)) < 0:
            original_paint(self)
            return

        surface_enabled_loc = GL.glGetUniformLocation(
            self._program, "uNativeSurfaceRoughnessEnabled"
        )
        surface_sampler_loc = GL.glGetUniformLocation(self._program, "uNativeSurfaceRoughness")
        surface_tiling_loc = GL.glGetUniformLocation(
            self._program, "uNativeSurfaceRoughnessTiling"
        )
        surface_mode_loc = GL.glGetUniformLocation(self._program, "uNativeSurfaceRoughnessMode")
        surface_uniforms_ready = min(
            int(surface_enabled_loc),
            int(surface_sampler_loc),
            int(surface_tiling_loc),
            int(surface_mode_loc),
        ) >= 0

        real_draw = GL.glDrawElements
        intercepted = False

        def _draw_ranges(mode, count, index_type, pointer):
            nonlocal intercepted
            if (
                intercepted
                or int(count) != expected
                or int(mode) != int(GL.GL_TRIANGLES)
                or int(index_type) != int(GL.GL_UNSIGNED_INT)
                or pointer is not None
            ):
                return real_draw(mode, count, index_type, pointer)
            intercepted = True
            for item in ranges:
                base_texture_id = int(texture_ids.get(item.dds_path or "", 0) or 0)
                GL.glUniform1i(base_enabled_loc, 1 if base_texture_id else 0)
                GL.glUniform2f(
                    base_tiling_loc, float(item.uv_tiling_u), float(item.uv_tiling_v)
                )
                if base_texture_id:
                    GL.glActiveTexture(GL.GL_TEXTURE0 + _BASE_TEXTURE_UNIT)
                    GL.glBindTexture(GL.GL_TEXTURE_2D, base_texture_id)
                    GL.glUniform1i(base_sampler_loc, _BASE_TEXTURE_UNIT)

                if surface_uniforms_ready:
                    surface_texture_id = int(
                        texture_ids.get(item.surface_dds_path or "", 0) or 0
                    )
                    surface_mode = 1 if item.surface_mode == "roughness" else 2 if item.surface_mode == "gloss" else 0
                    surface_enabled = bool(surface_texture_id and surface_mode)
                    GL.glUniform1i(surface_enabled_loc, 1 if surface_enabled else 0)
                    GL.glUniform2f(
                        surface_tiling_loc, float(item.uv_tiling_u), float(item.uv_tiling_v)
                    )
                    GL.glUniform1i(surface_mode_loc, surface_mode)
                    if surface_enabled:
                        GL.glActiveTexture(GL.GL_TEXTURE0 + _SURFACE_TEXTURE_UNIT)
                        GL.glBindTexture(GL.GL_TEXTURE_2D, surface_texture_id)
                        GL.glUniform1i(surface_sampler_loc, _SURFACE_TEXTURE_UNIT)

                real_draw(
                    mode,
                    int(item.index_count),
                    index_type,
                    GL.GLvoidp(int(item.first_index) * 4),
                )
            GL.glUniform1i(base_enabled_loc, 0)
            if surface_uniforms_ready:
                GL.glUniform1i(surface_enabled_loc, 0)
            return None

        GL.glDrawElements = _draw_ranges
        try:
            original_paint(self)
        finally:
            GL.glDrawElements = real_draw
            try:
                for unit in (_BASE_TEXTURE_UNIT, _SURFACE_TEXTURE_UNIT):
                    GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
                    GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
                GL.glActiveTexture(GL.GL_TEXTURE0)
            except Exception:
                pass
        if not intercepted:
            self._fh6_native_texture_status = "draw_intercept_not_matched"

    def _close_with_native_texture(self, event) -> None:
        uv_vbo = int(getattr(self, "_fh6_native_material_uv_vbo", 0) or 0)
        texture_ids = [
            int(value)
            for value in dict(getattr(self, "_fh6_native_texture_ids", {}) or {}).values()
            if int(value or 0) > 0
        ]
        if uv_vbo or texture_ids:
            try:
                self.makeCurrent()
                from OpenGL import GL

                if uv_vbo:
                    GL.glDeleteBuffers(1, [uv_vbo])
                    self._fh6_native_material_uv_vbo = 0
                if texture_ids:
                    GL.glDeleteTextures(texture_ids)
                    self._fh6_native_texture_ids = {}
                self.doneCurrent()
            except Exception:
                try:
                    self.doneCurrent()
                except Exception:
                    pass
        original_close(self, event)

    def _tire_apply_with_texture_sidecar(*args, **kwargs):
        result = original_tire_apply(*args, **kwargs)
        if bool(getattr(result, "applied", False)):
            copied = _copy_native_texture_sidecar(
                getattr(result, "source_vehicle_glb", ""),
                getattr(result, "selected_vehicle_glb", ""),
            )
            try:
                result = result.__class__(
                    **{
                        **result.as_dict(),
                        "detail": str(result.detail)
                        + ("; native_texture_sidecar=propagated" if copied else "; native_texture_sidecar=unavailable"),
                    }
                )
            except Exception:
                pass
        return result

    widget_class._make_program = classmethod(_make_program_with_native_texture)
    widget_class.__init__ = _widget_init_with_native_texture
    widget_class.initializeGL = _initialize_with_native_texture
    widget_class.paintGL = _paint_with_native_texture
    widget_class.closeEvent = _close_with_native_texture
    tire_preview_integration.try_apply_stock_native_tire_preview = _tire_apply_with_texture_sidecar
    setattr(widget_class, _PATCH_MARKER, True)
    return True
