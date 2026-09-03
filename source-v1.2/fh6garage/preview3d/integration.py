from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QLabel

from ..i18n import get_language


def _txt(ko: str, en: str) -> str:
    return ko if get_language().casefold().startswith("ko") else en


class _InitialPreviewWorker(QObject):
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, car_id: int, livery_path: str, eligibility: str, cleanup_c: bool):
        super().__init__()
        self.car_id = int(car_id)
        self.livery_path = str(livery_path)
        self.eligibility = str(eligibility)
        self.cleanup_c = bool(cleanup_c)

    @Slot()
    def run(self) -> None:
        try:
            from .converter import convert_vehicle
            from .direct_livery import build_direct_livery_textures
            from .glb_parser import load_kfps_glb
            from .kfps_runtime import render_clivery_sections
            from .vehicle_assets import (
                detect_fh6_installation,
                find_vehicle_asset,
                preferred_carbin_entry,
            )

            game_root = detect_fh6_installation()
            if game_root is None:
                raise RuntimeError(
                    "FH6 installation could not be located. Set FH6_GAME_DIR or "
                    "FORZA_HORIZON_6_DIR if the game is installed in an unusual location."
                )
            self.progress.emit(
                _txt("FH6 차량 데이터 확인 중...", "Locating FH6 vehicle data...")
            )
            asset = find_vehicle_asset(game_root, self.car_id)
            carbin_entry = preferred_carbin_entry(asset)
            if carbin_entry is None:
                raise RuntimeError(
                    f"Car ID {self.car_id} has multiple ambiguous carbin scenes; "
                    "automatic 3D preview was not attempted."
                )
            conversion = convert_vehicle(
                asset,
                progress=self.progress.emit,
                carbin_entry=carbin_entry,
            )
            self.progress.emit(
                _txt("리버리 레이어 렌더링 중...", "Rendering livery layers...")
            )
            render_result = render_clivery_sections(
                self.livery_path,
                game_folder=game_root,
                resolution="normal",
                log=self.progress.emit,
            )
            textures = build_direct_livery_textures(render_result, asset)
            self.progress.emit(_txt("3D 장면 준비 중...", "Preparing 3D scene..."))
            scene = load_kfps_glb(
                conversion.output_path,
                textures,
                livery_uv_channel=3,
                livery_eligibility=self.eligibility,
                neutral_cleanup_c=self.cleanup_c,
            )
            self.finished.emit(
                {
                    "scene": scene,
                    "textures": textures,
                    "glb_path": conversion.output_path,
                }
            )
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _SceneReloadWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        glb_path: str,
        textures: object,
        eligibility: str,
        cleanup_c: bool,
    ) -> None:
        super().__init__()
        self.glb_path = str(glb_path)
        self.textures = textures
        self.eligibility = str(eligibility)
        self.cleanup_c = bool(cleanup_c)

    @Slot()
    def run(self) -> None:
        try:
            from .glb_parser import load_kfps_glb

            scene = load_kfps_glb(
                self.glb_path,
                self.textures,
                livery_uv_channel=3,
                livery_eligibility=self.eligibility,
                neutral_cleanup_c=self.cleanup_c,
            )
            self.finished.emit(scene)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def _job_store(window: Any) -> list[tuple[QThread, QObject]]:
    jobs = getattr(window, "_fh6_preview3d_jobs", None)
    if not isinstance(jobs, list):
        jobs = []
        window._fh6_preview3d_jobs = jobs
    return jobs


def _start_job(
    window: Any,
    worker: QObject,
    *,
    finished: Callable[[object], None],
    failed: Callable[[str], None],
    progress: Callable[[str], None] | None = None,
) -> None:
    """Run one preview worker without allowing QThread/worker premature deletion."""
    thread = QThread(window)
    worker.moveToThread(thread)
    jobs = _job_store(window)
    jobs.append((thread, worker))

    def release_refs() -> None:
        try:
            jobs.remove((thread, worker))
        except ValueError:
            pass
        thread.deleteLater()

    thread.started.connect(worker.run)
    if progress is not None and hasattr(worker, "progress"):
        worker.progress.connect(progress)
    worker.finished.connect(finished)
    worker.failed.connect(failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    # Schedule worker deletion while its owning event loop still exists.
    worker.finished.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(release_refs)
    thread.start()


def _prepare_preview_3d(
    window: Any,
    *,
    dialog: Any,
    record: Any,
    page: Any,
    layout: Any,
    message: QLabel,
    controls: dict[str, Any],
) -> None:
    livery_path = getattr(record, "livery_path", None)
    car_id = getattr(record, "car_id", None)
    if not livery_path or not Path(livery_path).is_file() or car_id is None:
        message.setText(
            _txt(
                "3D에 필요한 C_livery 또는 Car ID가 없습니다.",
                "C_livery or Car ID required for 3D preview is unavailable.",
            )
        )
        return

    state: dict[str, Any] = {
        "alive": True,
        "viewer": None,
        "retired_viewers": [],
        "glb_path": "",
        "textures": None,
        "loading": True,
        "pending_reload": False,
    }
    page._fh6_preview3d_state = state
    dialog.destroyed.connect(lambda *_args: state.__setitem__("alive", False))

    eligibility = controls["eligibility"]
    cleanup_c = controls["cleanup_c"]
    reset = controls["reset"]

    def is_alive() -> bool:
        return bool(state.get("alive"))

    def set_options_enabled(enabled: bool) -> None:
        if not is_alive():
            return
        eligibility.setEnabled(enabled)
        cleanup_c.setEnabled(enabled)
        reset.setEnabled(enabled and state.get("viewer") is not None)

    def retire_viewer() -> None:
        """Hide the current GL widget without destroying its native context mid-switch.

        Destroying a visible QOpenGLWidget while a mode-change reload is in flight can
        terminate the Windows process inside Qt/driver teardown. Retired widgets remain
        children of the preview page and are reclaimed with the dialog.
        """
        viewer = state.get("viewer")
        state["viewer"] = None
        if viewer is None:
            return
        try:
            layout.removeWidget(viewer)
            viewer.hide()
            state["retired_viewers"].append(viewer)
        except RuntimeError:
            pass

    def rebuild_layout_with(widget: Any) -> None:
        """Drop stretch/items while preserving the reusable status QLabel."""
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            if child is not None and child is not message and child is not widget:
                child.hide()
                if child not in state["retired_viewers"]:
                    child.setParent(None)
                    child.deleteLater()
        if widget is not None:
            layout.addWidget(widget, 1)

    def show_message(text: str) -> None:
        if not is_alive():
            return
        retire_viewer()
        rebuild_layout_with(message)
        message.setText(text)
        message.show()

    def show_error(text: str) -> None:
        if not is_alive():
            return
        state["loading"] = False
        show_message(
            _txt(
                "3D 모델을 표시할 수 없습니다.\n",
                "Unable to display the 3D model.\n",
            )
            + text
        )
        # Allow another option change to retry an already-built GLB.
        can_retry = bool(state.get("glb_path") and state.get("textures") is not None)
        set_options_enabled(can_retry)

    def install_scene(scene: object) -> None:
        if not is_alive():
            return
        from .viewer import CarOpenGLWidget

        # Never close/delete a live GL widget during an eligibility switch. Keep it
        # hidden until the dialog is destroyed, then install and explicitly show the
        # new widget. This avoids native context teardown crashes on Windows.
        retire_viewer()
        message.hide()
        viewer = CarOpenGLWidget(scene, state["textures"], parent=page)
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        # QApplication already exists when lazy 3D mode is imported. Request the
        # context on this widget instead of mutating the process-wide default format.
        viewer.setFormat(fmt)
        viewer.setMinimumSize(320, 240)
        # Defer teardown until initializeGL has returned if context creation fails.
        viewer.load_failed.connect(
            lambda text: QTimer.singleShot(0, lambda error=text: show_error(error))
        )
        rebuild_layout_with(viewer)
        state["viewer"] = viewer
        state["loading"] = False
        set_options_enabled(True)
        # The page is already visible when the lazy widget is created. Explicitly show
        # the new child so QOpenGLWidget creates its context and initializeGL runs.
        viewer.show()
        viewer.raise_()
        viewer.update()
        QTimer.singleShot(0, viewer.update)

    set_options_enabled(False)

    def initial_finished(payload: object) -> None:
        if not is_alive():
            return
        if not isinstance(payload, dict):
            show_error("Invalid 3D worker result")
            return
        state["glb_path"] = str(payload.get("glb_path") or "")
        state["textures"] = payload.get("textures")
        scene = payload.get("scene")
        if not state["glb_path"] or state["textures"] is None or scene is None:
            show_error("Incomplete 3D worker result")
            return
        install_scene(scene)

    initial = _InitialPreviewWorker(
        int(car_id),
        str(livery_path),
        str(eligibility.currentData() or "legacy"),
        bool(cleanup_c.isChecked()),
    )
    _start_job(
        window,
        initial,
        finished=initial_finished,
        failed=show_error,
        progress=message.setText,
    )

    def reset_camera() -> None:
        if not is_alive():
            return
        viewer = state.get("viewer")
        if viewer is not None:
            viewer.reset_camera()

    reset.clicked.connect(reset_camera)

    def reload_scene() -> None:
        if not is_alive():
            return
        if state.get("loading") or not state.get("glb_path") or state.get("textures") is None:
            state["pending_reload"] = True
            return
        state["loading"] = True
        state["pending_reload"] = False
        set_options_enabled(False)
        show_message(_txt("3D 표시 옵션 적용 중...", "Applying 3D display options..."))

        def reloaded(scene: object) -> None:
            if not is_alive():
                return
            install_scene(scene)
            if state.pop("pending_reload", False):
                reload_scene()

        worker = _SceneReloadWorker(
            str(state["glb_path"]),
            state["textures"],
            str(eligibility.currentData() or "legacy"),
            bool(cleanup_c.isChecked()),
        )
        _start_job(window, worker, finished=reloaded, failed=show_error)

    eligibility.currentIndexChanged.connect(lambda _index: reload_scene())
    cleanup_c.toggled.connect(lambda _checked: reload_scene())
