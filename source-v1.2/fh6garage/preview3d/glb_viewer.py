from __future__ import annotations

import math
from pathlib import Path

import numpy as np
try:
    from OpenGL import GL
except ImportError:  # Parser tests can run before the launcher installs PyOpenGL.
    GL = None
from PySide6.QtCore import QPoint, QThread, Qt, Signal
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


from .glb_parser import GlbSceneData, GlbViewerError, load_kfps_glb
from .wheel_assembly import native_wheel_scene_info
from .direct_livery import DirectLiveryTextures


def _perspective(fovy_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    out = np.zeros((4, 4), dtype=np.float32)
    out[0, 0] = f / max(aspect, 1e-6)
    out[1, 1] = f
    out[2, 2] = (far + near) / (near - far)
    out[2, 3] = (2.0 * far * near) / (near - far)
    out[3, 2] = -1.0
    return out


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    f = target - eye
    f /= max(float(np.linalg.norm(f)), 1e-8)
    s = np.cross(f, up)
    if np.linalg.norm(s) < 1e-8:
        up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        s = np.cross(f, up)
    s /= max(float(np.linalg.norm(s)), 1e-8)
    u = np.cross(s, f)
    out = np.eye(4, dtype=np.float32)
    out[0, :3] = s
    out[1, :3] = u
    out[2, :3] = -f
    out[0, 3] = -np.dot(s, eye)
    out[1, 3] = -np.dot(u, eye)
    out[2, 3] = np.dot(f, eye)
    return out


_SLOT_GEOMETRY_SIDES = (0, 1, 2, 4, 3, 5, 6, 7, 8, 10, 9)

def _projection_bounds(scene_data: GlbSceneData, livery: DirectLiveryTextures | None):
    if livery is None:
        return (
            np.zeros((11, 2), dtype=np.float32),
            np.ones((11, 2), dtype=np.float32),
            np.zeros(11, dtype=np.float32),
        )
    # M6.16: parser and shader must use the same vehicle-wide projection frame.
    # Recomputing bounds from only the selected fallback primitives changes the
    # normalization after inference and moves the mask projection.
    return (
        np.ascontiguousarray(scene_data.projection_minimum, dtype=np.float32),
        np.ascontiguousarray(scene_data.projection_maximum, dtype=np.float32),
        np.ascontiguousarray(scene_data.projection_valid, dtype=np.float32),
    )


class CarOpenGLWidget(QOpenGLWidget):
    load_failed = Signal(str)

    def __init__(self, scene_data: GlbSceneData, livery_textures: DirectLiveryTextures | None = None, parent=None) -> None:
        super().__init__(parent)
        self.scene_data = scene_data
        self.livery_textures = livery_textures
        self._livery_enabled = livery_textures is not None
        self._debug_sections = False
        self._livery_texture = 0
        self._livery_mask_textures = [0, 0, 0]
        self._projection_minimum, self._projection_maximum, self._projection_valid = _projection_bounds(scene_data, livery_textures)
        self._two_sided = False
        self.setMinimumSize(800, 520)
        self.setFocusPolicy(Qt.StrongFocus)
        self._program = 0
        self._vao = 0
        self._vbo = 0
        self._ebo = 0
        self._last_pos = QPoint()
        self._yaw = 35.0
        self._pitch = 18.0
        self._distance = 1.0
        self._home_target = (scene_data.bounds_min + scene_data.bounds_max) * 0.5
        self._target = self._home_target.copy()
        size = scene_data.bounds_max - scene_data.bounds_min
        self._radius = max(float(np.linalg.norm(size)) * 0.55, 0.5)
        self.reset_camera()

    def set_two_sided(self, enabled: bool) -> None:
        """Diagnostic rendering toggle for materials whose game cull state is unknown."""
        self._two_sided = bool(enabled)
        try:
            self.makeCurrent()
            if self._two_sided:
                GL.glDisable(GL.GL_CULL_FACE)
            else:
                GL.glEnable(GL.GL_CULL_FACE)
                GL.glCullFace(GL.GL_BACK)
            self.doneCurrent()
        except Exception:
            try:
                self.doneCurrent()
            except Exception:
                pass
        self.update()

    def reset_camera(self) -> None:
        self._yaw = 35.0
        self._pitch = 18.0
        self._distance = self._radius * 2.2
        self._target = self._home_target.copy()
        self.update()

    def initializeGL(self) -> None:
        try:
            if GL is None:
                raise GlbViewerError("PyOpenGL is not installed. Re-run run.bat so M3 dependencies are installed.")
            GL.glEnable(GL.GL_DEPTH_TEST)
            if self._two_sided:
                GL.glDisable(GL.GL_CULL_FACE)
            else:
                GL.glEnable(GL.GL_CULL_FACE)
                GL.glCullFace(GL.GL_BACK)
            GL.glClearColor(0.2901961, 0.3137255, 0.3450980, 1.0)
            vertex = """
            #version 330 core
            layout(location=0) in vec3 inPosition;
            layout(location=1) in vec3 inNormal;
            layout(location=2) in vec3 inColor;
            layout(location=3) in vec2 inUV3;
            layout(location=4) in float inAllowed;
            layout(location=5) in float inProjection;
            layout(location=6) in float inDirectUv;
            uniform mat4 uMVP;
            uniform mat4 uModel;
            out vec3 vNormal;
            out vec3 vColor;
            out vec3 vWorld;
            out vec2 vUV3;
            flat out int vAllowed;
            flat out int vProjection;
            flat out int vDirectUv;
            void main() {
                vec4 world = uModel * vec4(inPosition, 1.0);
                vWorld = world.xyz;
                vNormal = normalize(mat3(uModel) * inNormal);
                vColor = inColor;
                vUV3 = inUV3;
                vAllowed = int(floor(inAllowed + 0.5));
                vProjection = int(floor(inProjection + 0.5));
                vDirectUv = int(floor(inDirectUv + 0.5));
                gl_Position = uMVP * vec4(inPosition, 1.0);
            }
            """
            fragment = """
            #version 330 core
            in vec3 vNormal;
            in vec3 vColor;
            in vec3 vWorld;
            in vec2 vUV3;
            flat in int vAllowed;
            flat in int vProjection;
            flat in int vDirectUv;
            uniform vec3 uEye;
            uniform bool uLiveryEnabled;
            uniform bool uDebugSections;
            uniform int uValidMask;
            uniform sampler2D uLivery;
            uniform sampler2D uMask0;
            uniform sampler2D uMask1;
            uniform sampler2D uMask2;
            uniform vec4 uSourceRegions[11];
            uniform vec4 uPaintRegions[11];
            uniform vec4 uProjectionAxes[11];
            uniform vec4 uProjectionMaskRegions[11];
            uniform vec2 uProjectionMinimum[11];
            uniform vec2 uProjectionMaximum[11];
            uniform float uProjectionValid[11];
            out vec4 fragColor;

            vec3 facing(int slot) {
                if (slot == 0 || slot == 6) return vec3(0,0,1);
                if (slot == 1 || slot == 7) return vec3(0,0,-1);
                if (slot == 2 || slot == 5 || slot == 8) return vec3(0,1,0);
                if (slot == 3 || slot == 9) return vec3(1,0,0);
                return vec3(-1,0,0);
            }
            float coverageForSlot(int slot, vec4 p0, vec4 p1, vec4 p2) {
                if (slot == 0) return p0.r;
                if (slot == 1) return p0.g;
                if (slot == 2) return p0.b;
                if (slot == 3) return p0.a;
                if (slot == 4) return p1.r;
                if (slot == 5) return p1.g;
                if (slot == 6) return p1.b;
                if (slot == 7) return p1.a;
                if (slot == 8) return p2.r;
                if (slot == 9) return p2.g;
                return p2.b;
            }
            int geometrySide(int slot) {
                if (slot == 3) return 4;
                if (slot == 4) return 3;
                if (slot == 9) return 10;
                if (slot == 10) return 9;
                return slot;
            }
            float axisComponent(vec3 value, float axis) {
                if (axis < 0.5) return value.x;
                if (axis < 1.5) return value.y;
                return value.z;
            }
            vec3 debugColor(int slot) {
                vec3 colors[11] = vec3[11](
                    vec3(1,0.2,0.2), vec3(0.8,0.1,0.8), vec3(0.2,0.7,1),
                    vec3(0.2,1,0.3), vec3(1,0.7,0.1), vec3(0.7,0.7,0.7),
                    vec3(0.2,1,1), vec3(1,0.3,0.7), vec3(0.5,0.4,1),
                    vec3(0.4,1,0.7), vec3(1,0.5,0.2));
                return colors[slot];
            }
            void main() {
                vec3 N = normalize(vNormal);
                vec3 L = normalize(vec3(0.45, 0.85, 0.55));
                float d = max(dot(N, L), 0.0);
                vec3 V = normalize(uEye - vWorld);
                float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0);
                vec3 base = vColor * (0.34 + 0.66 * d) + vec3(0.08, 0.11, 0.14) * rim;

                vec2 atlasUv = vec2(vUV3.x * 0.5, vUV3.y);
                vec2 bestAtlasUv = atlasUv;
                float bestCoverage = 0.0;
                int bestSlot = -1;
                if (uLiveryEnabled && vAllowed != 0) {
                    for (int slot = 0; slot < 11; ++slot) {
                        int bit = 1 << slot;
                        if ((vAllowed & bit) == 0 || (uValidMask & bit) == 0) continue;
                        if (dot(N, facing(slot)) <= 0.0) continue;
                        vec2 candidateUv = atlasUv;
                        if (vDirectUv == 0) {
                            int geometryBit = 1 << geometrySide(slot);
                            if ((vProjection & geometryBit) == 0 || uProjectionValid[slot] < 0.5) continue;
                            vec4 axis = uProjectionAxes[slot];
                            vec2 minimum = uProjectionMinimum[slot];
                            vec2 range = uProjectionMaximum[slot] - minimum;
                            if (range.x <= 0.000001 || range.y <= 0.000001) continue;
                            vec2 axisValue = vec2(
                                axisComponent(vWorld, axis.x) * axis.z,
                                axisComponent(vWorld, axis.y) * axis.w
                            );
                            vec2 normalized = (axisValue - minimum) / range;
                            vec4 maskRegion = uProjectionMaskRegions[slot];
                            candidateUv = vec2(
                                mix(maskRegion.x, maskRegion.y, normalized.x),
                                mix(maskRegion.z, maskRegion.w, normalized.y)
                            );
                        }
                        if (candidateUv.x < 0.0 || candidateUv.x > 1.0 || candidateUv.y < 0.0 || candidateUv.y > 1.0) continue;
                        vec4 page0 = texture(uMask0, candidateUv);
                        vec4 page1 = texture(uMask1, candidateUv);
                        vec4 page2 = texture(uMask2, candidateUv);
                        float candidate = coverageForSlot(slot, page0, page1, page2);
                        if (candidate > bestCoverage) {
                            bestCoverage = candidate;
                            bestSlot = slot;
                            bestAtlasUv = candidateUv;
                        }
                    }
                }

                vec4 decal = vec4(0.0);
                if (bestSlot >= 0 && bestCoverage > 0.0) {
                    vec4 source = uSourceRegions[bestSlot];
                    vec2 sourceSize = source.zw - source.xy;
                    if (sourceSize.x > 0.000001 && sourceSize.y > 0.000001) {
                        vec2 sectionUv = clamp((bestAtlasUv - source.xy) / sourceSize, 0.0, 1.0);
                        vec4 paint = uPaintRegions[bestSlot];
                        vec2 paintUv = mix(paint.xy, paint.zw, sectionUv);
                        decal = texture(uLivery, paintUv);
                        decal.a *= bestCoverage;
                    }
                }

                if (uDebugSections && bestSlot >= 0) {
                    fragColor = vec4(mix(base, debugColor(bestSlot), max(bestCoverage, 0.55)), 1.0);
                } else {
                    fragColor = vec4(mix(base, decal.rgb, decal.a), 1.0);
                }
            }
            """
            self._program = self._make_program(vertex, fragment)
            packed = np.ascontiguousarray(
                np.concatenate((
                    self.scene_data.positions, self.scene_data.normals, self.scene_data.colors,
                    self.scene_data.uv3, self.scene_data.allowed_sides,
                    self.scene_data.projection_sides, self.scene_data.direct_uv
                ), axis=1),
                dtype=np.float32,
            )
            self._vao = GL.glGenVertexArrays(1)
            self._vbo = GL.glGenBuffers(1)
            self._ebo = GL.glGenBuffers(1)
            GL.glBindVertexArray(self._vao)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, packed.nbytes, packed, GL.GL_STATIC_DRAW)
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self._ebo)
            GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, self.scene_data.indices.nbytes, self.scene_data.indices, GL.GL_STATIC_DRAW)
            stride = 14 * 4
            for location, size, offset in ((0, 3, 0), (1, 3, 12), (2, 3, 24), (3, 2, 36), (4, 1, 44), (5, 1, 48), (6, 1, 52)):
                GL.glEnableVertexAttribArray(location)
                GL.glVertexAttribPointer(location, size, GL.GL_FLOAT, GL.GL_FALSE, stride, GL.GLvoidp(offset))
            GL.glBindVertexArray(0)
            if self.livery_textures is not None:
                paint = self.livery_textures.paint
                expected_paint_width = int(self.livery_textures.canvas_size[0])
                if (
                    paint.ndim != 3
                    or paint.shape[0] <= 0
                    or paint.shape[1] != expected_paint_width
                    or paint.shape[2] != 4
                    or paint.dtype != np.uint8
                ):
                    raise GlbViewerError(
                        "M6.23B paint atlas has an invalid shape or format: "
                        f"{getattr(paint, 'shape', None)}, expected width {expected_paint_width} RGBA8."
                    )
                max_texture_size = int(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_SIZE))
                if (
                    int(paint.shape[1]) > max_texture_size
                    or int(paint.shape[0]) > max_texture_size
                ):
                    raise GlbViewerError(
                        "Selected livery resolution produced a paint atlas of "
                        f"{paint.shape[1]}x{paint.shape[0]}, but this GPU reports "
                        f"GL_MAX_TEXTURE_SIZE={max_texture_size}. "
                        "Choose a lower livery resolution under Tools."
                    )
                self._livery_texture = GL.glGenTextures(1)
                GL.glBindTexture(GL.GL_TEXTURE_2D, self._livery_texture)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
                GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, int(paint.shape[1]), int(paint.shape[0]), 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, paint)
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

                pages = self.livery_textures.mask_pages
                if pages.shape != (3, 1024, 2048, 4) or pages.dtype != np.uint8:
                    raise GlbViewerError("M6.23B native mask pages have an invalid shape or format.")
                self._livery_mask_textures = list(GL.glGenTextures(3))
                for page_index, texture_id in enumerate(self._livery_mask_textures):
                    GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
                    GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
                    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, 2048, 1024, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, pages[page_index])
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        except Exception as exc:
            self.load_failed.emit(str(exc))

    @staticmethod
    def _compile_shader(source: str, shader_type: int) -> int:
        shader = GL.glCreateShader(shader_type)
        GL.glShaderSource(shader, source)
        GL.glCompileShader(shader)
        if GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS) != GL.GL_TRUE:
            log = GL.glGetShaderInfoLog(shader).decode("utf-8", "replace")
            GL.glDeleteShader(shader)
            raise GlbViewerError("OpenGL shader compile failed: " + log)
        return shader

    @classmethod
    def _make_program(cls, vertex: str, fragment: str) -> int:
        vs = cls._compile_shader(vertex, GL.GL_VERTEX_SHADER)
        fs = cls._compile_shader(fragment, GL.GL_FRAGMENT_SHADER)
        program = GL.glCreateProgram()
        GL.glAttachShader(program, vs)
        GL.glAttachShader(program, fs)
        GL.glLinkProgram(program)
        GL.glDeleteShader(vs)
        GL.glDeleteShader(fs)
        if GL.glGetProgramiv(program, GL.GL_LINK_STATUS) != GL.GL_TRUE:
            log = GL.glGetProgramInfoLog(program).decode("utf-8", "replace")
            GL.glDeleteProgram(program)
            raise GlbViewerError("OpenGL shader link failed: " + log)
        return program

    def _eye(self) -> np.ndarray:
        yaw = math.radians(self._yaw)
        pitch = math.radians(self._pitch)
        cp = math.cos(pitch)
        direction = np.array([math.sin(yaw) * cp, math.sin(pitch), math.cos(yaw) * cp], dtype=np.float32)
        return self._target + direction * self._distance

    def paintGL(self) -> None:
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        if not self._program or not self._vao:
            return
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        eye = self._eye()
        view = _look_at(eye, self._target.astype(np.float32), np.array([0.0, 1.0, 0.0], dtype=np.float32))
        proj = _perspective(36.0, width / height, max(self._radius / 200.0, 0.01), self._radius * 50.0)
        model = np.eye(4, dtype=np.float32)
        mvp = proj @ view @ model
        GL.glUseProgram(self._program)
        loc = GL.glGetUniformLocation(self._program, "uMVP")
        GL.glUniformMatrix4fv(loc, 1, GL.GL_TRUE, mvp)
        loc = GL.glGetUniformLocation(self._program, "uModel")
        GL.glUniformMatrix4fv(loc, 1, GL.GL_TRUE, model)
        loc = GL.glGetUniformLocation(self._program, "uEye")
        GL.glUniform3f(loc, float(eye[0]), float(eye[1]), float(eye[2]))
        GL.glUniform1i(GL.glGetUniformLocation(self._program, "uLiveryEnabled"), int(self._livery_enabled and self._livery_texture != 0 and all(self._livery_mask_textures)))
        GL.glUniform1i(GL.glGetUniformLocation(self._program, "uDebugSections"), int(self._debug_sections))
        valid_mask = 0
        if self.livery_textures is not None:
            for i, value in enumerate(self.livery_textures.valid_slots):
                if value: valid_mask |= 1 << i
            source_loc = GL.glGetUniformLocation(self._program, "uSourceRegions[0]")
            paint_loc = GL.glGetUniformLocation(self._program, "uPaintRegions[0]")
            GL.glUniform4fv(source_loc, 11, self.livery_textures.source_regions)
            GL.glUniform4fv(paint_loc, 11, self.livery_textures.paint_regions)
            GL.glUniform4fv(GL.glGetUniformLocation(self._program, "uProjectionAxes[0]"), 11, self.livery_textures.projection_axes)
            GL.glUniform4fv(GL.glGetUniformLocation(self._program, "uProjectionMaskRegions[0]"), 11, self.livery_textures.projection_mask_regions)
            GL.glUniform2fv(GL.glGetUniformLocation(self._program, "uProjectionMinimum[0]"), 11, self._projection_minimum)
            GL.glUniform2fv(GL.glGetUniformLocation(self._program, "uProjectionMaximum[0]"), 11, self._projection_maximum)
            GL.glUniform1fv(GL.glGetUniformLocation(self._program, "uProjectionValid[0]"), 11, self._projection_valid)
        GL.glUniform1i(GL.glGetUniformLocation(self._program, "uValidMask"), valid_mask)
        if self._livery_texture:
            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._livery_texture)
            GL.glUniform1i(GL.glGetUniformLocation(self._program, "uLivery"), 0)
        for page_index, texture_id in enumerate(self._livery_mask_textures):
            if texture_id:
                GL.glActiveTexture(GL.GL_TEXTURE1 + page_index)
                GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
                GL.glUniform1i(GL.glGetUniformLocation(self._program, f"uMask{page_index}"), 1 + page_index)
        GL.glBindVertexArray(self._vao)
        GL.glDrawElements(GL.GL_TRIANGLES, int(len(self.scene_data.indices)), GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)
        if self._livery_texture or any(self._livery_mask_textures):
            for unit in (3, 2, 1, 0):
                GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glUseProgram(0)

    def set_livery_enabled(self, enabled: bool) -> None:
        self._livery_enabled = bool(enabled) and self.livery_textures is not None
        self.update()

    def toggle_section_debug(self) -> bool:
        self._debug_sections = not self._debug_sections
        self.update()
        return self._debug_sections

    def resizeGL(self, width: int, height: int) -> None:
        GL.glViewport(0, 0, max(width, 1), max(height, 1))

    def mousePressEvent(self, event) -> None:
        self._last_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        delta = pos - self._last_pos
        self._last_pos = pos
        pan_mode = bool(event.buttons() & Qt.RightButton) or (
            bool(event.buttons() & Qt.LeftButton) and bool(event.modifiers() & Qt.ShiftModifier)
        )
        if pan_mode:
            eye = self._eye()
            forward = self._target - eye
            forward /= max(float(np.linalg.norm(forward)), 1e-8)
            world_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            right = np.cross(forward, world_up)
            right /= max(float(np.linalg.norm(right)), 1e-8)
            up = np.cross(right, forward)
            up /= max(float(np.linalg.norm(up)), 1e-8)
            scale = self._distance * 0.0018
            self._target += right * (-delta.x() * scale) + up * (delta.y() * scale)
            self.update()
        elif event.buttons() & Qt.LeftButton:
            # M3.1: horizontal orbit direction intentionally reversed from M3.
            self._yaw -= delta.x() * 0.45
            self._pitch = max(-85.0, min(85.0, self._pitch + delta.y() * 0.35))
            self.update()
        super().mouseMoveEvent(event)

    def wheelEvent(self, event) -> None:
        steps = event.angleDelta().y() / 120.0
        self._distance *= math.pow(0.88, steps)
        self._distance = max(self._radius * 0.35, min(self._radius * 8.0, self._distance))
        self.update()
        event.accept()

    def closeEvent(self, event) -> None:
        try:
            self.makeCurrent()
            if self._ebo:
                GL.glDeleteBuffers(1, [self._ebo])
            if self._vbo:
                GL.glDeleteBuffers(1, [self._vbo])
            if self._vao:
                GL.glDeleteVertexArrays(1, [self._vao])
            if self._livery_texture:
                GL.glDeleteTextures([self._livery_texture])
                self._livery_texture = 0
            for texture_id in self._livery_mask_textures:
                if texture_id:
                    GL.glDeleteTextures([texture_id])
            self._livery_mask_textures = [0, 0, 0]
            if self._program:
                GL.glDeleteProgram(self._program)
            self.doneCurrent()
        finally:
            super().closeEvent(event)


class CarViewerDialog(QDialog):
    def __init__(self, glb_path: Path | str, archive_path: Path | str | None = None, livery_textures: DirectLiveryTextures | None = None, parent=None, *, scene_data: GlbSceneData | None = None, wheel_info: dict | None = None) -> None:
        app = QApplication.instance()
        if app is not None and QThread.currentThread() is not app.thread():
            raise GlbViewerError(
                "OpenGL viewer creation was requested outside QApplication's GUI thread. "
                "Refusing unsafe QOpenGLWidget construction instead of opening a blank window."
            )
        super().__init__(parent)
        self.glb_path = Path(glb_path)
        self.setWindowTitle(f"FH6 Livery 3D Viewer PoC - M6.24B FinalVerify1 ErrorFix1 - {self.glb_path.name}")
        self.resize(1100, 760)
        root = QVBoxLayout(self)
        if scene_data is None:
            base_scene = load_kfps_glb(self.glb_path, livery_textures)
            resolved_wheel_info = native_wheel_scene_info(base_scene)
            self.scene_data = base_scene
            self.wheel_info = resolved_wheel_info
        else:
            self.scene_data = scene_data
            self.wheel_info = dict(wheel_info or {"wheel_mode": "none", "wheel_locator_count": 0})
        # Final verification policy deliberately hides WheelStyle and does not
        # synthesize tires. Keep this label policy-oriented instead of implying
        # that a zero post-filter wheel count means the source had no wheels.
        wheel_label = "WheelStyle hidden · tire reconstruction disabled"
        info = QLabel(
            f"Meshes {self.scene_data.mesh_count:,} · Triangles {self.scene_data.triangle_count:,} · "
            f"TEXCOORD_{self.scene_data.livery_uv_channel} direct meshes {self.scene_data.uv3_meshes:,} · "
            f"Projected fallback {self.scene_data.projected_meshes:,} · "
            f"Excluded declared livery meshes {self.scene_data.excluded_livery_meshes:,} · Roles {self.scene_data.role_counts}\n"
            f"Eligibility {self.scene_data.livery_eligibility_policy} · "
            f"UV3/mask eligibility evidence {self.scene_data.inferred_uv3_meshes:,} · "
            f"Selected-UV/mask evidence {self.scene_data.selected_uv_mask_evidence_meshes:,} · "
            f"Promoted {self.scene_data.promoted_livery_meshes:,} · "
            f"Expanded {self.scene_data.expanded_allowed_meshes:,} · "
            f"Selected-UV/no-mask-overlap {self.scene_data.uv3_without_mask_overlap:,} · "
            f"Projection-inferred {self.scene_data.inferred_projection_meshes:,} · "
            f"Projection/no-overlap {self.scene_data.projection_no_overlap_meshes:,}\n"
            f"Neutral A+B {'ON' if self.scene_data.neutral_cleanup_ab_enabled else 'OFF'} "
            f"(excluded {self.scene_data.neutral_ab_excluded_meshes:,}) · "
            f"C {'ON' if self.scene_data.neutral_cleanup_c_enabled else 'OFF'} "
            f"(additional excluded {self.scene_data.neutral_c_excluded_meshes:,})\n"
            f"M6.24B {'livery diagnostic/render' if livery_textures is not None else 'neutral geometry'} · {wheel_label}. "
            "Left-drag: rotate · Right-drag / Shift+Left: pan · Mouse wheel: zoom"
        )
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(info)
        self.viewer = CarOpenGLWidget(self.scene_data, livery_textures, self)
        self.opengl_error = QLabel("")
        self.opengl_error.setWordWrap(True)
        self.opengl_error.setStyleSheet("color: #b00020; font-weight: 600;")
        self.opengl_error.hide()
        self.viewer.load_failed.connect(self._on_viewer_load_failed)
        root.addWidget(self.opengl_error)
        root.addWidget(self.viewer, 1)
        controls = QHBoxLayout()
        reset = QPushButton("Reset camera")
        reset.clicked.connect(self.viewer.reset_camera)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        controls.addWidget(reset)
        if livery_textures is not None:
            clear = QPushButton("Clear livery")
            clear.setCheckable(True)
            clear.toggled.connect(lambda checked: self.viewer.set_livery_enabled(not checked))
            debug = QPushButton("Section debug")
            debug.setCheckable(True)
            debug.toggled.connect(lambda _checked: self.viewer.toggle_section_debug())
            controls.addWidget(clear)
            controls.addWidget(debug)
        two_sided = QPushButton("Two-sided inspection")
        two_sided.setCheckable(True)
        two_sided.setChecked(False)
        two_sided.setToolTip("Disable back-face culling for diagnosis. Off by default to match the M6.21 neutral rendering baseline; does not modify GLB/game data.")
        two_sided.toggled.connect(self.viewer.set_two_sided)
        controls.addWidget(two_sided)
        controls.addStretch(1)
        controls.addWidget(close)
        root.addLayout(controls)

    def _on_viewer_load_failed(self, message: str) -> None:
        self.opengl_error.setText("OpenGL viewer initialization failed: " + message)
        self.opengl_error.show()


def configure_default_opengl_format() -> None:
    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)
