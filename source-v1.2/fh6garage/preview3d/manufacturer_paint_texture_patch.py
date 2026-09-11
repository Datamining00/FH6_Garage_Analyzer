"""Reference-closed manufacturer paint swatch rendering on native UV4.

External contract (ForzaTechStudio):
* selected manufacturer swatchbin is the diffuse/albedo map for car-paint;
* manufacturer colour remains the diffuse tint over that texture;
* manufacturer paint samples UV channel 4;
* UV order is source V-flip -> MeshBlob channel transform -> material tiling.

Pinned KFPS already exports TEXCOORD_4 after the first two UV operations.  This
stage therefore applies only the exact material-wide tiling multiplier and then
multiplies the established P3B manufacturer tint by the sRGB swatch albedo before
the existing C_livery graphics composite.

Only P3E exact-path candidates on primary ``carpaint`` are enabled.  Secondary
paint is deferred until a separate secondary-tint contract exists.  Durango/Xbox
swatches fail closed in the verified helper because tiled bytes require XG
Detile/Dealign before DDS construction.  No game/save data or GLB is modified.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import numpy as np

from .manufacturer_overlay_texture_diagnostics import (
    diagnose_manufacturer_overlay_texture_payloads,
)
from .native_dds import parse_native_dds
from .native_material_gl import upload_native_dds_2d
from .native_material_textures import (
    NativeTexturePayload,
    _automatic_decoder_helper,
    _decode_resolved_payload,
)

MANUFACTURER_PAINT_TEXTURE_RENDERING_REVISION = 1
_PATCH_MARKER = "_fh6_manufacturer_paint_texture_rendering_patched"
_TEXTURE_UNIT = 8
_VERTEX_LOCATION = 13
_PRIMARY_MATERIAL = "carpaint"
_SRGB_ALBEDO_DXGI = frozenset({29, 72, 75, 78, 99})
_CACHE_NAMESPACE = "manufacturer_paint_uv4_v1"


@dataclass(frozen=True)
class ManufacturerPaintDrawRange:
    first_index: int
    index_count: int
    mesh_index: int
    primitive_index: int
    dds_path: str | None
    uv_tiling_u: float
    uv_tiling_v: float


def _mapping_value(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    folded = {str(key).casefold(): value for key, value in mapping.items()}
    for name in names:
        value = folded.get(name.casefold())
        if value is not None:
            return value
    return None


def _material_tiling(mesh: dict[str, Any]) -> tuple[float, float]:
    extras = mesh.get("extras")
    if not isinstance(extras, dict):
        raise ValueError("manufacturer paint mesh has no material extras")
    appearance = extras.get("kfps_material_appearance")
    if not isinstance(appearance, dict):
        raise ValueError("manufacturer paint mesh has no embedded material appearance")
    raw = _mapping_value(appearance, "uvTiling", "UvTiling")
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise ValueError("manufacturer paint material UV tiling provenance is missing")
    try:
        u = float(raw[0])
        v = float(raw[1])
    except (TypeError, ValueError) as exc:
        raise ValueError("manufacturer paint material UV tiling is non-numeric") from exc
    if not math.isfinite(u) or not math.isfinite(v) or abs(u) <= 1e-6 or abs(v) <= 1e-6:
        raise ValueError(f"manufacturer paint material UV tiling is invalid: {(u, v)!r}")
    return u, v


def build_manufacturer_uv4_stream(glb_path: str | Path, scene_data: Any) -> np.ndarray:
    """Flatten exact exported TEXCOORD_4 in the parser's included primitive order."""
    from .glb_parser import _accessor_array, _read_glb

    document, binary = _read_glb(Path(glb_path).expanduser().resolve())
    meshes = document.get("meshes") or []
    chunks: list[np.ndarray] = []
    for diagnostic in tuple(getattr(scene_data, "primitive_diagnostics", ()) or ()):
        mesh_index = int(diagnostic.get("mesh_index", -1))
        primitive_index = int(diagnostic.get("primitive_index", -1))
        if mesh_index < 0 or mesh_index >= len(meshes):
            raise ValueError("manufacturer UV4 mesh index is outside the GLB")
        primitives = meshes[mesh_index].get("primitives") or []
        if primitive_index < 0 or primitive_index >= len(primitives):
            raise ValueError("manufacturer UV4 primitive index is outside the GLB")
        attrs = primitives[primitive_index].get("attributes") or {}
        if "POSITION" not in attrs:
            raise ValueError("manufacturer UV4 primitive has no POSITION accessor")
        positions = _accessor_array(document, binary, int(attrs["POSITION"]))
        vertex_count = int(len(positions))
        if "TEXCOORD_4" not in attrs:
            chunks.append(np.zeros((vertex_count, 2), dtype=np.float32))
            continue
        uv4 = _accessor_array(document, binary, int(attrs["TEXCOORD_4"])).astype(
            np.float32, copy=False
        )
        if uv4.shape != (vertex_count, 2) or not np.isfinite(uv4).all():
            raise ValueError("manufacturer TEXCOORD_4 is invalid or has a vertex-count mismatch")
        chunks.append(np.ascontiguousarray(uv4, dtype=np.float32))

    stream = (
        np.ascontiguousarray(np.concatenate(chunks), dtype=np.float32)
        if chunks
        else np.empty((0, 2), dtype=np.float32)
    )
    expected = int(len(getattr(scene_data, "positions", ())))
    if stream.shape != (expected, 2):
        raise ValueError(
            f"manufacturer UV4 stream vertex count mismatch: {stream.shape} != ({expected}, 2)"
        )
    return stream


def _decode_exact_p3e_payload(payload_dict: dict[str, Any], cache_root: Path) -> NativeTexturePayload:
    item = NativeTexturePayload(**payload_dict)
    helper, detail = _automatic_decoder_helper()
    if helper is None:
        raise ValueError(detail or "verified native swatchbin decoder is unavailable")
    decoded = _decode_resolved_payload(item, helper, cache_root)
    if decoded.decode_status not in {"decoded_dds", "decoded_dds_cached"} or not decoded.dds_path:
        raise ValueError(decoded.decoder_detail or f"manufacturer swatch decode failed: {decoded.decode_status}")
    texture = parse_native_dds(decoded.dds_path)
    if not texture.is_simple_2d:
        raise ValueError("manufacturer swatch DDS is not an ordinary 2D texture")
    if int(texture.dxgi_format) not in _SRGB_ALBEDO_DXGI or not bool(texture.is_srgb):
        raise ValueError(
            "manufacturer swatch is not an explicitly sRGB albedo-capable DDS; refusing colour-space guessing"
        )
    return decoded


def build_manufacturer_paint_draw_ranges(
    glb_path: str | Path,
    scene_data: Any,
    p3e_report: dict[str, Any],
    cache_root: str | Path,
) -> tuple[tuple[ManufacturerPaintDrawRange, ...], tuple[str, ...]]:
    """Resolve exact P3E primary-paint rows into verified per-primitive DDS ranges."""
    from .material_appearance_patch import _read_glb_document

    document = _read_glb_document(Path(glb_path))
    meshes = document.get("meshes") or []
    rows = p3e_report.get("payloads") if isinstance(p3e_report, dict) else []
    rows = rows if isinstance(rows, list) else []
    exact: dict[tuple[int, int], dict[str, Any]] = {}
    issues: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "manufacturer_overlay_payload_resolved_exact":
            continue
        if row.get("exact_resolution_approved") is not True:
            continue
        if row.get("uv4_status") != "uv4_exact_kfps_accessor":
            continue
        if str(row.get("material_name") or "").strip().casefold() != _PRIMARY_MATERIAL:
            if str(row.get("material_name") or "").strip().casefold() == "carpaint_secondary":
                issues.append(
                    f"mesh {row.get('mesh_index')}: carpaint_secondary UV4 swatch deferred until secondary tint is authoritative"
                )
            continue
        try:
            key = (int(row.get("mesh_index")), int(row.get("primitive_index")))
        except (TypeError, ValueError):
            continue
        if key in exact:
            issues.append(f"mesh {key[0]} primitive {key[1]}: duplicate exact manufacturer overlay rows")
            exact.pop(key, None)
            continue
        exact[key] = row

    cache = Path(cache_root).expanduser().resolve() / _CACHE_NAMESPACE
    cache.mkdir(parents=True, exist_ok=True)
    decoded_by_payload: dict[str, str] = {}
    ranges: list[ManufacturerPaintDrawRange] = []
    first_index = 0
    for diagnostic in tuple(getattr(scene_data, "primitive_diagnostics", ()) or ()):
        index_count = int(diagnostic.get("triangle_count", 0)) * 3
        mesh_index = int(diagnostic.get("mesh_index", -1))
        primitive_index = int(diagnostic.get("primitive_index", -1))
        dds_path: str | None = None
        tiling_u = 1.0
        tiling_v = 1.0
        row = exact.get((mesh_index, primitive_index))
        if row is not None:
            try:
                if mesh_index < 0 or mesh_index >= len(meshes) or not isinstance(meshes[mesh_index], dict):
                    raise ValueError("manufacturer paint mesh is outside the GLB")
                tiling_u, tiling_v = _material_tiling(meshes[mesh_index])
                payload_dict = row.get("payload")
                if not isinstance(payload_dict, dict):
                    raise ValueError("P3E exact manufacturer row has no payload object")
                payload_key = str(payload_dict.get("payload_sha256") or payload_dict.get("cache_path") or "")
                if not payload_key:
                    raise ValueError("P3E exact manufacturer payload has no stable identity")
                dds_path = decoded_by_payload.get(payload_key)
                if dds_path is None:
                    decoded = _decode_exact_p3e_payload(payload_dict, cache)
                    dds_path = str(Path(decoded.dds_path or "").expanduser().resolve())
                    decoded_by_payload[payload_key] = dds_path
            except Exception as exc:
                dds_path = None
                issues.append(
                    f"mesh {mesh_index} primitive {primitive_index}: {type(exc).__name__}: {exc}"
                )
        ranges.append(
            ManufacturerPaintDrawRange(
                first_index=first_index,
                index_count=index_count,
                mesh_index=mesh_index,
                primitive_index=primitive_index,
                dds_path=dds_path,
                uv_tiling_u=tiling_u,
                uv_tiling_v=tiling_v,
            )
        )
        first_index += index_count

    expected = int(len(getattr(scene_data, "indices", ())))
    if first_index != expected:
        raise ValueError(
            f"manufacturer paint draw ranges cover {first_index} indices but scene contains {expected}"
        )
    return tuple(ranges), tuple(issues)


def upgrade_manufacturer_paint_vertex_shader(vertex: str) -> str:
    if "inManufacturerUV4" in vertex:
        return vertex
    attr = "            layout(location=12) in vec2 inMaterialUV;\n"
    out = "            out vec2 vMaterialUV;\n"
    assign = "                vMaterialUV = inMaterialUV;\n"
    if attr not in vertex or out not in vertex or assign not in vertex:
        return vertex
    vertex = vertex.replace(attr, attr + "            layout(location=13) in vec2 inManufacturerUV4;\n", 1)
    vertex = vertex.replace(out, out + "            out vec2 vManufacturerUV4;\n", 1)
    return vertex.replace(assign, assign + "                vManufacturerUV4 = inManufacturerUV4;\n", 1)


def upgrade_manufacturer_paint_fragment_shader(fragment: str) -> str:
    if "uManufacturerPaintEnabled" in fragment:
        return fragment
    input_marker = "            in vec2 vMaterialUV;\n"
    uniform_marker = "            uniform vec2 uNativeEmissiveTiling;\n"
    composite_marker = "                albedo = mix(albedo, decalLinear, decal.a);\n"
    if input_marker not in fragment or uniform_marker not in fragment or composite_marker not in fragment:
        return fragment
    fragment = fragment.replace(
        input_marker,
        input_marker + "            in vec2 vManufacturerUV4;\n",
        1,
    )
    fragment = fragment.replace(
        uniform_marker,
        uniform_marker
        + "            uniform bool uManufacturerPaintEnabled;\n"
        + "            uniform sampler2D uManufacturerPaint;\n"
        + "            uniform vec2 uManufacturerPaintTiling;\n",
        1,
    )
    return fragment.replace(
        composite_marker,
        """                // ForzaTechStudio manufacturer-paint contract: the selected
                // swatch is the UV4 car-paint albedo and the existing P3B colour
                // remains its tint. C_livery graphics stay authoritative above it.
                if (uManufacturerPaintEnabled) {
                    vec3 manufacturerSwatch = texture(
                        uManufacturerPaint,
                        vManufacturerUV4 * uManufacturerPaintTiling).rgb;
                    albedo *= manufacturerSwatch;
                }
                albedo = mix(albedo, decalLinear, decal.a);
""",
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


def install_manufacturer_paint_texture_patch() -> bool:
    """Install exact manufacturer UV4 swatch rendering after emissive, before glass composite."""
    from . import glb_viewer, native_material_texture_patch as texture_patch

    widget_class = glb_viewer.CarOpenGLWidget
    if bool(getattr(widget_class, _PATCH_MARKER, False)):
        return False

    original_vertex_upgrade = texture_patch.upgrade_native_texture_vertex_shader
    original_fragment_upgrade = texture_patch.upgrade_native_texture_fragment_shader

    def _vertex_upgrade_with_manufacturer(vertex: str) -> str:
        return upgrade_manufacturer_paint_vertex_shader(original_vertex_upgrade(vertex))

    def _fragment_upgrade_with_manufacturer(fragment: str) -> str:
        return upgrade_manufacturer_paint_fragment_shader(original_fragment_upgrade(fragment))

    texture_patch.upgrade_native_texture_vertex_shader = _vertex_upgrade_with_manufacturer
    texture_patch.upgrade_native_texture_fragment_shader = _fragment_upgrade_with_manufacturer

    original_widget_init = widget_class.__init__
    original_initialize = widget_class.initializeGL
    original_paint = widget_class.paintGL
    original_close = widget_class.closeEvent

    def _widget_init_with_manufacturer(self, scene_data, *args, **kwargs):
        original_widget_init(self, scene_data, *args, **kwargs)
        self._fh6_manufacturer_paint_texture_ids = {}
        self._fh6_manufacturer_paint_draw_ranges = ()
        self._fh6_manufacturer_paint_uv4 = None
        glb_path = getattr(self, "_fh6_glb_path", None)
        livery = getattr(self, "livery_textures", None)
        paint_source = getattr(livery, "_fh6_paint_source", None)
        vehicle_archive = getattr(livery, "_fh6_vehicle_archive", None)
        cache_root = getattr(livery, "_fh6_manufacturer_cache_root", None)
        if not all((glb_path, paint_source, vehicle_archive, cache_root)):
            self._fh6_manufacturer_paint_status = "provenance_unavailable"
            return
        try:
            p3e = diagnose_manufacturer_overlay_texture_payloads(
                glb_path,
                paint_source,
                vehicle_archive,
                str(Path(cache_root) / _CACHE_NAMESPACE),
            )
            uv4 = build_manufacturer_uv4_stream(glb_path, self.scene_data)
            ranges, issues = build_manufacturer_paint_draw_ranges(
                glb_path,
                self.scene_data,
                p3e,
                cache_root,
            )
        except Exception as exc:
            self._fh6_manufacturer_paint_status = "prepare_failed"
            self._fh6_manufacturer_paint_error = f"{type(exc).__name__}: {exc}"
            return
        self._fh6_manufacturer_paint_p3e = p3e
        self._fh6_manufacturer_paint_uv4 = uv4
        self._fh6_manufacturer_paint_draw_ranges = ranges
        self._fh6_manufacturer_paint_error = "; ".join(issues)
        self._fh6_manufacturer_paint_status = (
            "prepared" if any(item.dds_path for item in ranges) else "no_eligible_primary_swatches"
        )

    def _initialize_with_manufacturer(self) -> None:
        original_initialize(self)
        if not getattr(self, "_program", 0) or not getattr(self, "_vao", 0):
            return
        uv4 = getattr(self, "_fh6_manufacturer_paint_uv4", None)
        if not isinstance(uv4, np.ndarray) or uv4.shape != (len(self.scene_data.positions), 2):
            return
        from OpenGL import GL

        self._fh6_manufacturer_paint_vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self._vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._fh6_manufacturer_paint_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, uv4.nbytes, np.ascontiguousarray(uv4), GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(_VERTEX_LOCATION)
        GL.glVertexAttribPointer(
            _VERTEX_LOCATION, 2, GL.GL_FLOAT, GL.GL_FALSE, 2 * 4, GL.GLvoidp(0)
        )
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)

        paths: list[str] = []
        for item in tuple(getattr(self, "_fh6_manufacturer_paint_draw_ranges", ()) or ()):
            if item.dds_path and item.dds_path not in paths:
                paths.append(item.dds_path)
        textures: dict[str, int] = {}
        errors: list[str] = []
        for dds_path in paths:
            try:
                texture = parse_native_dds(dds_path)
                if int(texture.dxgi_format) not in _SRGB_ALBEDO_DXGI or not bool(texture.is_srgb):
                    raise ValueError("manufacturer swatch DDS changed after validation")
                textures[dds_path] = upload_native_dds_2d(GL, texture)
            except Exception as exc:
                textures[dds_path] = 0
                errors.append(f"{Path(dds_path).name}: {type(exc).__name__}: {exc}")
        self._fh6_manufacturer_paint_texture_ids = textures
        if errors:
            self._fh6_manufacturer_paint_status = "partial_gpu_upload"
            self._fh6_manufacturer_paint_gpu_errors = tuple(errors)
        elif any(textures.values()):
            self._fh6_manufacturer_paint_status = "gpu_ready"
            self._fh6_manufacturer_paint_gpu_errors = ()

    def _paint_with_manufacturer(self) -> None:
        from OpenGL import GL

        ranges = tuple(getattr(self, "_fh6_manufacturer_paint_draw_ranges", ()) or ())
        texture_ids = dict(getattr(self, "_fh6_manufacturer_paint_texture_ids", {}) or {})
        if not ranges or not getattr(self, "_program", 0) or not getattr(self, "_vao", 0):
            original_paint(self)
            return
        expected = int(len(self.scene_data.indices))
        if sum(item.index_count for item in ranges) != expected:
            original_paint(self)
            return

        enabled_loc = GL.glGetUniformLocation(self._program, "uManufacturerPaintEnabled")
        sampler_loc = GL.glGetUniformLocation(self._program, "uManufacturerPaint")
        tiling_loc = GL.glGetUniformLocation(self._program, "uManufacturerPaintTiling")
        if min(int(enabled_loc), int(sampler_loc), int(tiling_loc)) < 0:
            self._fh6_manufacturer_paint_status = "shader_uniforms_unavailable"
            original_paint(self)
            return

        by_draw = {
            (int(item.first_index) * 4, int(item.index_count)): item
            for item in ranges
        }
        real_draw = GL.glDrawElements
        intercepted = False

        def _draw_with_manufacturer(mode, count, index_type, pointer):
            nonlocal intercepted
            offset = _pointer_byte_offset(pointer)
            item = by_draw.get((offset, int(count))) if offset is not None else None
            if item is None or int(mode) != int(GL.GL_TRIANGLES) or int(index_type) != int(GL.GL_UNSIGNED_INT):
                GL.glUniform1i(enabled_loc, 0)
                return real_draw(mode, count, index_type, pointer)
            intercepted = True
            texture_id = int(texture_ids.get(item.dds_path or "", 0) or 0)
            GL.glUniform1i(enabled_loc, 1 if texture_id else 0)
            GL.glUniform2f(tiling_loc, float(item.uv_tiling_u), float(item.uv_tiling_v))
            if texture_id:
                GL.glActiveTexture(GL.GL_TEXTURE0 + _TEXTURE_UNIT)
                GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
                GL.glUniform1i(sampler_loc, _TEXTURE_UNIT)
            return real_draw(mode, count, index_type, pointer)

        GL.glDrawElements = _draw_with_manufacturer
        try:
            original_paint(self)
        finally:
            GL.glDrawElements = real_draw
            try:
                GL.glUniform1i(enabled_loc, 0)
                GL.glActiveTexture(GL.GL_TEXTURE0 + _TEXTURE_UNIT)
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
                GL.glActiveTexture(GL.GL_TEXTURE0)
            except Exception:
                pass
        if intercepted and any(texture_ids.values()):
            self._fh6_manufacturer_paint_status = "rendered_exact_primary_uv4"

    def _close_with_manufacturer(self, event) -> None:
        texture_ids = dict(getattr(self, "_fh6_manufacturer_paint_texture_ids", {}) or {})
        vbo = int(getattr(self, "_fh6_manufacturer_paint_vbo", 0) or 0)
        if texture_ids or vbo:
            try:
                self.makeCurrent()
                from OpenGL import GL
                live = [int(value) for value in texture_ids.values() if int(value)]
                if live:
                    GL.glDeleteTextures(live)
                if vbo:
                    GL.glDeleteBuffers(1, [vbo])
                self.doneCurrent()
            except Exception:
                try:
                    self.doneCurrent()
                except Exception:
                    pass
        self._fh6_manufacturer_paint_texture_ids = {}
        self._fh6_manufacturer_paint_vbo = 0
        original_close(self, event)

    widget_class.__init__ = _widget_init_with_manufacturer
    widget_class.initializeGL = _initialize_with_manufacturer
    widget_class.paintGL = _paint_with_manufacturer
    widget_class.closeEvent = _close_with_manufacturer
    setattr(widget_class, _PATCH_MARKER, True)
    return True
