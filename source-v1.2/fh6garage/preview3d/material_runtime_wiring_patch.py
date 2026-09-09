"""Wire native material provenance into the production direct-widget 3D path.

The PBR patch historically populated material vertex streams from
CarViewerDialog.__init__.  FinalVerify1's production 3D tab constructs
CarOpenGLWidget directly, so this bridge records the GLB source when
load_kfps_glb() returns and configures the widget from the same scene object.
No geometry, livery, game file, or save data is modified.
"""

from __future__ import annotations

from pathlib import Path
import weakref
from typing import Any

_PATCH_MARKER = "_fh6_native_material_direct_widget_wiring_patched"
_SCENE_PATHS: dict[int, tuple[weakref.ReferenceType[Any], str]] = {}


def remember_scene_glb_path(scene_data: Any, glb_path: str | Path) -> None:
    key = id(scene_data)
    resolved = str(Path(glb_path).expanduser().resolve())

    def _discard(_reference: weakref.ReferenceType[Any], *, scene_key: int = key) -> None:
        _SCENE_PATHS.pop(scene_key, None)

    try:
        reference = weakref.ref(scene_data, _discard)
    except TypeError:
        # GlbSceneData is weak-referenceable in production. Fail closed for an
        # unexpected replacement type instead of retaining an unbounded map.
        return
    _SCENE_PATHS[key] = (reference, resolved)


def scene_glb_path(scene_data: Any) -> str | None:
    entry = _SCENE_PATHS.get(id(scene_data))
    if entry is None:
        return None
    reference, path = entry
    if reference() is not scene_data:
        _SCENE_PATHS.pop(id(scene_data), None)
        return None
    return path


def configure_game_like_material_widget(widget: Any, glb_path: str | Path) -> bool:
    """Populate native surface/optical vertex streams on one production widget."""
    from .material_appearance_patch import _build_material_vertex_streams_all

    widget._fh6_glb_path = str(Path(glb_path).expanduser().resolve())
    try:
        (
            params,
            aux,
            f0,
            coat_f0,
            emission,
            native_count,
            native_optical_count,
        ) = _build_material_vertex_streams_all(widget._fh6_glb_path, widget.scene_data)
    except Exception as exc:
        widget._fh6_material_params = None
        widget._fh6_material_aux = None
        widget._fh6_material_f0 = None
        widget._fh6_material_coat_f0 = None
        widget._fh6_material_emission = None
        widget._fh6_material_stream_error = f"{type(exc).__name__}: {exc}"
        widget._fh6_native_material_primitives = 0
        widget._fh6_native_optical_primitives = 0
        return False

    widget._fh6_material_params = params
    widget._fh6_material_aux = aux
    widget._fh6_material_f0 = f0
    widget._fh6_material_coat_f0 = coat_f0
    widget._fh6_material_emission = emission
    widget._fh6_material_stream_error = ""
    widget._fh6_native_material_primitives = int(native_count)
    widget._fh6_native_optical_primitives = int(native_optical_count)
    return True


def install_material_runtime_wiring_patch() -> bool:
    """Install GLB-source tracking and direct CarOpenGLWidget material wiring."""
    from . import glb_parser, glb_viewer

    widget_class = glb_viewer.CarOpenGLWidget
    if bool(getattr(widget_class, _PATCH_MARKER, False)):
        return False

    original_load = glb_parser.load_kfps_glb
    original_widget_init = widget_class.__init__

    def _load_with_source_path(glb_path, *args, **kwargs):
        scene = original_load(glb_path, *args, **kwargs)
        remember_scene_glb_path(scene, glb_path)
        return scene

    def _widget_init_with_material_streams(self, scene_data, *args, **kwargs):
        original_widget_init(self, scene_data, *args, **kwargs)
        glb_path = scene_glb_path(scene_data)
        if glb_path is None:
            # CarViewerDialog remains covered by material_appearance_patch's
            # established dialog path. Direct widgets fail closed to defaults if
            # source provenance is unavailable.
            self._fh6_material_direct_wiring_status = "glb_source_unavailable"
            return
        configured = configure_game_like_material_widget(self, glb_path)
        self._fh6_material_direct_wiring_status = (
            "native_material_streams_ready" if configured else "native_material_streams_unavailable"
        )

    glb_parser.load_kfps_glb = _load_with_source_path
    widget_class.__init__ = _widget_init_with_material_streams
    setattr(widget_class, _PATCH_MARKER, True)
    return True
