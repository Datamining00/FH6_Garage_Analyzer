from __future__ import annotations


# Thumbnail-like front three-quarter presentation.  Keep these values in one
# place so both initial construction and the Camera Reset button use the same
# framing contract.
HOME_YAW_DEG = 32.0
HOME_PITCH_DEG = 10.0
HOME_DISTANCE_RADIUS = 2.30

# Very light sky-blue background requested for the livery preview.  Values are
# deliberately low-saturation so bright/yellow/white liveries retain contrast.
BACKGROUND_RGBA = (0.78, 0.86, 0.93, 1.0)


def install_preview_presentation_patch() -> bool:
    """Use thumbnail-like camera framing and a light sky-blue GL background."""
    from OpenGL import GL
    from . import glb_viewer

    widget = glb_viewer.CarOpenGLWidget
    if getattr(widget, "_fh6_preview_presentation_patched", False):
        return False

    original_initialize = widget.initializeGL

    def reset_camera(self) -> None:
        self._yaw = HOME_YAW_DEG
        self._pitch = HOME_PITCH_DEG
        self._distance = self._radius * HOME_DISTANCE_RADIUS
        self._target = self._home_target.copy()
        self.update()

    def initialize_gl(self) -> None:
        original_initialize(self)
        # original_initialize establishes the GL context and all renderer state;
        # only replace the clear colour afterwards so material/livery rendering
        # remains untouched.
        GL.glClearColor(*BACKGROUND_RGBA)

    widget.reset_camera = reset_camera
    widget.initializeGL = initialize_gl
    widget._fh6_preview_presentation_patched = True
    return True
