"""Game-like preview material shading without changing FH6 geometry/livery mapping.

The geometry/livery pipeline stays authoritative.  When the KFPS converter has
exported embedded MaterialBlob shader provenance, this bridge derives per-vertex
PBR parameters from those native values.  Missing or unresolved material data
falls back to the existing role defaults without vehicle-specific tuning.
"""

from __future__ import annotations

from pathlib import Path
import struct
from typing import Any

import numpy as np

_PATCH_MARKER = "_fh6_game_like_material_shading_patched"

_FLAT_LIGHTING = """                vec3 N = normalize(vNormal);
                vec3 L = normalize(vec3(0.45, 0.85, 0.55));
                float d = max(dot(N, L), 0.0);
                vec3 V = normalize(uEye - vWorld);
                float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0);
                vec3 base = vColor * (0.34 + 0.66 * d) + vec3(0.08, 0.11, 0.14) * rim;
"""

_PBR_MAIN_START = """                vec3 N = normalize(vNormal);
                vec3 V = normalize(uEye - vWorld);
"""

_FLAT_OUTPUT = """                if (uDebugSections && bestSlot >= 0) {
                    fragColor = vec4(mix(base, debugColor(bestSlot), max(bestCoverage, 0.55)), 1.0);
                } else {
                    fragColor = vec4(mix(base, decal.rgb, decal.a), 1.0);
                }
"""

_PBR_OUTPUT = """                vec3 decalLinear = pow(max(decal.rgb, vec3(0.0)), vec3(2.2));
                vec3 albedo = vMaterialAux.y >= 0.0
                    ? clamp(vMaterialAux.yzw, 0.0, 1.0)
                    : pow(clamp(vColor, 0.0, 1.0), vec3(2.2));
                albedo = mix(albedo, decalLinear, decal.a);
                vec3 shaded = fh6ShadeMaterial(
                    albedo, N, V, vMaterialParams, clamp(vMaterialAux.x, 0.0, 1.0));

                if (uDebugSections && bestSlot >= 0) {
                    fragColor = vec4(mix(shaded, debugColor(bestSlot), max(bestCoverage, 0.55)), 1.0);
                } else {
                    fragColor = vec4(shaded, 1.0);
                }
"""

_VERTEX_ATTR_MARKER = """            layout(location=6) in float inDirectUv;
"""
_VERTEX_ATTR_REPLACEMENT = """            layout(location=6) in float inDirectUv;
            layout(location=7) in vec4 inMaterialParams;
            layout(location=8) in vec4 inMaterialAux;
"""
_VERTEX_OUT_MARKER = """            flat out int vDirectUv;
"""
_VERTEX_OUT_REPLACEMENT = """            flat out int vDirectUv;
            out vec4 vMaterialParams;
            out vec4 vMaterialAux;
"""
_VERTEX_ASSIGN_MARKER = """                vDirectUv = int(floor(inDirectUv + 0.5));
"""
_VERTEX_ASSIGN_REPLACEMENT = """                vDirectUv = int(floor(inDirectUv + 0.5));
                vMaterialParams = inMaterialParams;
                vMaterialAux = inMaterialAux;
"""
_FRAGMENT_IN_MARKER = """            flat in int vDirectUv;
"""
_FRAGMENT_IN_REPLACEMENT = """            flat in int vDirectUv;
            in vec4 vMaterialParams;
            in vec4 vMaterialAux;
"""

_PBR_HELPERS = r"""
            const float FH6_PI = 3.14159265359;

            float fh6DistributionGGX(vec3 N, vec3 H, float roughness) {
                float a = max(roughness * roughness, 0.0025);
                float a2 = a * a;
                float ndh = max(dot(N, H), 0.0);
                float ndh2 = ndh * ndh;
                float denom = ndh2 * (a2 - 1.0) + 1.0;
                return a2 / max(FH6_PI * denom * denom, 0.000001);
            }

            float fh6GeometrySchlickGGX(float ndv, float roughness) {
                float r = roughness + 1.0;
                float k = (r * r) * 0.125;
                return ndv / max(ndv * (1.0 - k) + k, 0.000001);
            }

            float fh6GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
                return fh6GeometrySchlickGGX(max(dot(N, V), 0.0), roughness)
                     * fh6GeometrySchlickGGX(max(dot(N, L), 0.0), roughness);
            }

            vec3 fh6FresnelSchlick(float cosTheta, vec3 F0) {
                return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
            }

            vec3 fh6Environment(vec3 direction) {
                float sky = clamp(direction.y * 0.5 + 0.5, 0.0, 1.0);
                vec3 ground = vec3(0.055, 0.060, 0.070);
                vec3 horizon = vec3(0.24, 0.27, 0.31);
                vec3 zenith = vec3(0.52, 0.61, 0.72);
                vec3 upper = mix(horizon, zenith, smoothstep(0.15, 1.0, sky));
                return mix(ground, upper, smoothstep(0.0, 0.55, sky));
            }

            vec3 fh6ShadeMaterial(
                vec3 albedo, vec3 N, vec3 V, vec4 materialParams, float transmission) {
                float metallic = clamp(materialParams.x, 0.0, 1.0);
                float roughness = clamp(materialParams.y, 0.025, 1.0);
                float clearcoat = clamp(materialParams.z, 0.0, 1.0);
                float coatRoughness = clamp(materialParams.w, 0.025, 1.0);

                vec3 L = normalize(vec3(0.42, 0.82, 0.38));
                vec3 H = normalize(V + L);
                float ndl = max(dot(N, L), 0.0);
                float ndv = max(dot(N, V), 0.0);
                float ndh = max(dot(N, H), 0.0);
                float vdh = max(dot(V, H), 0.0);

                vec3 F0 = mix(vec3(0.04), albedo, metallic);
                vec3 F = fh6FresnelSchlick(vdh, F0);
                float D = fh6DistributionGGX(N, H, roughness);
                float G = fh6GeometrySmith(N, V, L, roughness);
                vec3 specular = (D * G * F) / max(4.0 * ndv * ndl, 0.001);
                vec3 kd = (vec3(1.0) - F) * (1.0 - metallic);
                vec3 direct = (kd * albedo / FH6_PI + specular)
                            * vec3(3.8, 3.6, 3.35) * ndl;

                vec3 R = reflect(-V, N);
                vec3 environment = fh6Environment(R);
                vec3 envF = fh6FresnelSchlick(ndv, F0);
                float hemi = clamp(N.y * 0.5 + 0.5, 0.0, 1.0);
                vec3 ambient = albedo * mix(0.045, 0.14, hemi) * (1.0 - metallic)
                             + environment * envF * mix(0.55, 0.16, roughness);

                float coatPower = mix(256.0, 28.0, coatRoughness);
                float coatHighlight = pow(ndh, coatPower) * clearcoat;
                vec3 coatF = fh6FresnelSchlick(ndv, vec3(0.04));
                vec3 color = direct + ambient + coatF * coatHighlight * 2.1;

                if (transmission > 0.0) {
                    vec3 glassEnvironment = fh6Environment(R) * (vec3(0.72) + 0.28 * envF);
                    color = mix(color, glassEnvironment + albedo * 0.12, transmission);
                }

                color = max(color, vec3(0.0));
                color = color / (color + vec3(1.0));
                return pow(color, vec3(1.0 / 2.2));
            }
"""

_ROLE_DEFAULTS: dict[str, tuple[tuple[float, float, float, float], float]] = {
    "paint": ((0.08, 0.25, 0.95, 0.08), 0.0),
    "glass": ((0.00, 0.08, 0.35, 0.05), 0.72),
    "dark": ((0.00, 0.70, 0.02, 0.35), 0.0),
    "trim": ((0.28, 0.40, 0.18, 0.18), 0.0),
}


def _finite_scalar(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def material_values_for_primitive(
    role: str,
    appearance: dict[str, Any] | None,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Return (PBR params, aux, native-used) for one GLB primitive.

    params = metallic, roughness, clearcoat, clearcoat roughness.
    aux    = transmission, native-linear-base-R/G/B.  A negative base-R means
             the shader should keep the existing role/display color.
    """
    key = str(role or "trim").casefold()
    defaults, transmission = _ROLE_DEFAULTS.get(key, _ROLE_DEFAULTS["trim"])
    params = np.asarray(defaults, dtype=np.float32).copy()
    aux = np.asarray([transmission, -1.0, -1.0, -1.0], dtype=np.float32)
    if not isinstance(appearance, dict):
        return params, aux, False
    if appearance.get("resolutionMode") != "embedded_material_shader_parameters":
        return params, aux, False

    used = False
    metalness = _finite_scalar(appearance.get("metalness"))
    if metalness is not None:
        params[0] = _clamp01(metalness)
        used = True

    roughness = _finite_scalar(appearance.get("roughness"))
    if roughness is not None:
        params[1] = max(0.025, _clamp01(roughness))
        used = True
    else:
        gloss = _finite_scalar(appearance.get("gloss"))
        if gloss is not None:
            params[1] = max(0.025, 1.0 - _clamp01(gloss))
            used = True

    clearcoat_gloss = _finite_scalar(appearance.get("clearCoatGloss"))
    if clearcoat_gloss is not None:
        params[2] = 1.0
        params[3] = max(0.025, 1.0 - _clamp01(clearcoat_gloss))
        used = True

    # Embedded shader colors are GPU parameter values and therefore treated as
    # linear values.  Car-paint base color is deliberately not consumed here:
    # its final game color is user/manufacturer paint state, not a static material
    # default.  Livery pixels still become the paint albedo before PBR lighting.
    base = appearance.get("baseColor")
    if key != "paint" and isinstance(base, (list, tuple)) and len(base) >= 3:
        values = [_finite_scalar(base[index]) for index in range(3)]
        if all(value is not None for value in values):
            aux[1:4] = np.asarray([_clamp01(float(value)) for value in values], dtype=np.float32)
            used = True

    return params, aux, used


def _read_glb_document(path: Path) -> dict[str, Any]:
    with path.open("rb") as source:
        header = source.read(12)
        if len(header) != 12 or header[:4] != b"glTF":
            raise ValueError("not a GLB 2.0 file")
        version, total = struct.unpack_from("<II", header, 4)
        if version != 2:
            raise ValueError(f"unsupported GLB version {version}")
        consumed = 12
        while consumed + 8 <= total:
            chunk_header = source.read(8)
            if len(chunk_header) != 8:
                break
            length, chunk_type = struct.unpack("<II", chunk_header)
            consumed += 8
            if chunk_type == 0x4E4F534A:
                payload = source.read(length)
                if len(payload) != length:
                    raise ValueError("truncated GLB JSON chunk")
                import json

                parsed = json.loads(payload.rstrip(b" \x00").decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise ValueError("GLB JSON root is not an object")
                return parsed
            source.seek(length, 1)
            consumed += length
    raise ValueError("GLB has no JSON chunk")


def build_material_vertex_streams(
    glb_path: Path | str,
    scene_data: Any,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Map exported mesh material extras onto the parser's flattened vertex order."""
    document = _read_glb_document(Path(glb_path))
    meshes = document.get("meshes") or []
    accessors = document.get("accessors") or []
    node_extras_by_mesh: dict[int, dict[str, Any]] = {}
    for node in document.get("nodes") or []:
        if not isinstance(node, dict) or "mesh" not in node:
            continue
        try:
            index = int(node["mesh"])
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(meshes):
            node_extras_by_mesh[index] = dict(node.get("extras") or {})

    all_params: list[np.ndarray] = []
    all_aux: list[np.ndarray] = []
    native_primitives = 0
    for diagnostic in tuple(getattr(scene_data, "primitive_diagnostics", ()) or ()):
        mesh_index = int(diagnostic.get("mesh_index", -1))
        primitive_index = int(diagnostic.get("primitive_index", -1))
        if mesh_index < 0 or mesh_index >= len(meshes):
            raise ValueError("material stream mesh index is outside the GLB")
        mesh = meshes[mesh_index]
        primitives = mesh.get("primitives") or []
        if primitive_index < 0 or primitive_index >= len(primitives):
            raise ValueError("material stream primitive index is outside the GLB")
        attrs = primitives[primitive_index].get("attributes") or {}
        accessor_index = int(attrs["POSITION"])
        if accessor_index < 0 or accessor_index >= len(accessors):
            raise ValueError("material stream POSITION accessor is outside the GLB")
        vertex_count = int(accessors[accessor_index].get("count", 0))
        if vertex_count <= 0:
            raise ValueError("material stream primitive has no vertices")

        extras = dict(node_extras_by_mesh.get(mesh_index) or {})
        extras.update(mesh.get("extras") or {})
        appearance = extras.get("kfps_material_appearance")
        params, aux, used = material_values_for_primitive(
            str(diagnostic.get("declared_role") or extras.get("kfps_role") or "trim"),
            appearance if isinstance(appearance, dict) else None,
        )
        if used:
            native_primitives += 1
        all_params.append(np.repeat(params[None, :], vertex_count, axis=0))
        all_aux.append(np.repeat(aux[None, :], vertex_count, axis=0))

    params_stream = np.ascontiguousarray(np.concatenate(all_params), dtype=np.float32)
    aux_stream = np.ascontiguousarray(np.concatenate(all_aux), dtype=np.float32)
    expected = int(len(getattr(scene_data, "positions")))
    if len(params_stream) != expected or len(aux_stream) != expected:
        raise ValueError(
            f"material stream vertex count mismatch: {len(params_stream)} / {len(aux_stream)} != {expected}"
        )
    return params_stream, aux_stream, native_primitives


def upgrade_vertex_shader(vertex: str) -> str:
    if "inMaterialParams" in vertex:
        return vertex
    if _VERTEX_ATTR_MARKER not in vertex:
        return vertex
    upgraded = vertex.replace(_VERTEX_ATTR_MARKER, _VERTEX_ATTR_REPLACEMENT, 1)
    upgraded = upgraded.replace(_VERTEX_OUT_MARKER, _VERTEX_OUT_REPLACEMENT, 1)
    return upgraded.replace(_VERTEX_ASSIGN_MARKER, _VERTEX_ASSIGN_REPLACEMENT, 1)


def upgrade_fragment_shader(fragment: str) -> str:
    """Upgrade the current FHA flat shader while preserving livery UV/mask logic."""
    if "fh6ShadeMaterial(" in fragment:
        return fragment
    if _FLAT_LIGHTING not in fragment or _FLAT_OUTPUT not in fragment:
        return fragment
    upgraded = fragment
    if _FRAGMENT_IN_MARKER in upgraded:
        upgraded = upgraded.replace(_FRAGMENT_IN_MARKER, _FRAGMENT_IN_REPLACEMENT, 1)
    upgraded = upgraded.replace(
        "            void main() {\n",
        _PBR_HELPERS + "\n            void main() {\n",
        1,
    )
    upgraded = upgraded.replace(_FLAT_LIGHTING, _PBR_MAIN_START, 1)
    return upgraded.replace(_FLAT_OUTPUT, _PBR_OUTPUT, 1)


def install_game_like_material_patch() -> bool:
    """Install the native-material/PBR bridge exactly once on the production viewer."""
    from . import glb_viewer

    widget = glb_viewer.CarOpenGLWidget
    if bool(getattr(widget, _PATCH_MARKER, False)):
        return False

    original_make_program = widget._make_program.__func__
    original_initialize = widget.initializeGL
    original_close = widget.closeEvent
    dialog = glb_viewer.CarViewerDialog
    original_dialog_init = dialog.__init__

    def _make_program_with_materials(cls, vertex: str, fragment: str) -> int:
        return original_make_program(
            cls,
            upgrade_vertex_shader(vertex),
            upgrade_fragment_shader(fragment),
        )

    def _dialog_init_with_materials(self, glb_path, *args, **kwargs):
        original_dialog_init(self, glb_path, *args, **kwargs)
        try:
            params, aux, native_count = build_material_vertex_streams(glb_path, self.scene_data)
        except Exception as exc:
            self.viewer._fh6_material_params = None
            self.viewer._fh6_material_aux = None
            self.viewer._fh6_material_stream_error = f"{type(exc).__name__}: {exc}"
            self.viewer._fh6_native_material_primitives = 0
        else:
            self.viewer._fh6_material_params = params
            self.viewer._fh6_material_aux = aux
            self.viewer._fh6_material_stream_error = ""
            self.viewer._fh6_native_material_primitives = int(native_count)

    def _initialize_with_materials(self) -> None:
        original_initialize(self)
        if not getattr(self, "_program", 0) or not getattr(self, "_vao", 0):
            return
        from OpenGL import GL

        params = getattr(self, "_fh6_material_params", None)
        aux = getattr(self, "_fh6_material_aux", None)
        self._fh6_material_vbo = 0
        GL.glBindVertexArray(self._vao)
        # Safe generic defaults when loading a legacy GLB without provenance.
        GL.glDisableVertexAttribArray(7)
        GL.glVertexAttrib4f(7, 0.28, 0.40, 0.18, 0.18)
        GL.glDisableVertexAttribArray(8)
        GL.glVertexAttrib4f(8, 0.0, -1.0, -1.0, -1.0)
        if (
            isinstance(params, np.ndarray)
            and isinstance(aux, np.ndarray)
            and params.shape == aux.shape
            and params.ndim == 2
            and params.shape[1] == 4
            and params.shape[0] == len(self.scene_data.positions)
        ):
            packed = np.ascontiguousarray(np.concatenate((params, aux), axis=1), dtype=np.float32)
            self._fh6_material_vbo = GL.glGenBuffers(1)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._fh6_material_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, packed.nbytes, packed, GL.GL_STATIC_DRAW)
            stride = 8 * 4
            GL.glEnableVertexAttribArray(7)
            GL.glVertexAttribPointer(7, 4, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.GLvoidp(0))
            GL.glEnableVertexAttribArray(8)
            GL.glVertexAttribPointer(8, 4, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.GLvoidp(16))
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)

    def _close_with_materials(self, event) -> None:
        material_vbo = int(getattr(self, "_fh6_material_vbo", 0) or 0)
        if material_vbo:
            try:
                self.makeCurrent()
                from OpenGL import GL

                GL.glDeleteBuffers(1, [material_vbo])
                self._fh6_material_vbo = 0
                self.doneCurrent()
            except Exception:
                try:
                    self.doneCurrent()
                except Exception:
                    pass
        original_close(self, event)

    widget._make_program = classmethod(_make_program_with_materials)
    widget.initializeGL = _initialize_with_materials
    widget.closeEvent = _close_with_materials
    dialog.__init__ = _dialog_init_with_materials
    setattr(widget, _PATCH_MARKER, True)
    return True
