from __future__ import annotations

import time
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

    def __init__(self, car_id: int, livery_path: str, eligibility: str, cleanup_c: bool) -> None:
        super().__init__()
        self.car_id = int(car_id)
        self.livery_path = str(livery_path)
        self.eligibility = str(eligibility or "legacy")
        self.cleanup_c = bool(cleanup_c)

    def _stage(self, text: str) -> float:
        self.progress.emit(text)
        return time.perf_counter()

    @Slot()
    def run(self) -> None:
        try:
            from .converter import convert_vehicle
            from .direct_livery import build_direct_livery_textures
            from .glb_parser import load_kfps_glb
            from .kfps_runtime import render_clivery_sections
            from .vehicle_assets import detect_fh6_installation, find_vehicle_asset, preferred_carbin_entry

            self._stage(_txt("FH6 차량 데이터 확인 중...", "Locating FH6 vehicle data..."))
            game_root = detect_fh6_installation()
            if game_root is None:
                raise RuntimeError(
                    "FH6 installation could not be located. Set FH6_GAME_DIR or "
                    "FORZA_HORIZON_6_DIR if the game is installed in an unusual location."
                )

            asset = find_vehicle_asset(game_root, self.car_id)
            carbin_entry = preferred_carbin_entry(asset)
            if carbin_entry is None:
                raise RuntimeError(
                    f"Car ID {self.car_id} has multiple ambiguous carbin scenes; "
                    "automatic 3D preview was not attempted."
                )

            self._stage(_txt("3D 차량 모델 준비 중...", "Preparing 3D vehicle model..."))
            conversion = convert_vehicle(
                asset,
                progress=self.progress.emit,
                carbin_entry=carbin_entry,
            )

            self._stage(_txt("리버리 레이어 렌더링 중...", "Rendering livery layers..."))
            render_result = render_clivery_sections(
                self.livery_path,
                game_folder=game_root,
                resolution="normal",
                log=self.progress.emit,
            )

            started = self._stage(_txt("3D 텍스처 계약 준비 중...", "Preparing 3D texture contract..."))
            textures = build_direct_livery_textures(render_result, asset)
            self.progress.emit(
                _txt(
                    f"3D 장면 준비 중... (텍스처 {time.perf_counter() - started:.1f}초)",
                    f"Preparing 3D scene... (textures {time.perf_counter() - started:.1f}s)",
                )
            )

            started = time.perf_counter()
            scene = load_kfps_glb(
                conversion.output_path,
                textures,
                livery_uv_channel=3,
                livery_eligibility=self.eligibility,
                neutral_cleanup_c=self.cleanup_c,
            )
            self.progress.emit(
                _txt(
                    f"3D 장면 해석 완료 ({time.perf_counter() - started:.1f}초), 화면 준비 중...",
                    f"3D scene decoded ({time.perf_counter() - started:.1f}s), preparing view...",
                )
            )
            self.finished.emit(
                {
                    "scene": scene,
                    "textures": textures,
                    "glb_path": str(conversion.output_path),
                }
            )
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _SceneReloadWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, glb_path: str, textures: object, eligibility: str, cleanup_c: bool) -> None:
        super().__init__()
        self.glb_path = str(glb_path)
        self.textures = textures
        self.eligibility = str(eligibility or "legacy")
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


class _Preview3DJobLifecycle(QObject):
    """Keep one worker/thread pair alive and release it on the GUI thread."""

    def __init__(self, window: Any, thread: QThread, worker: QObject) -> None:
        super().__init__(window)
        self.window = window
        self.thread_ref = thread
        self.worker_ref = worker

    @Slot()
    def thread_finished(self) -> None:
        jobs = getattr(self.window, "_fh6_preview3d_jobs", None)
        if isinstance(jobs, list):
            try:
                jobs.remove(self)
            except ValueError:
                pass
        self.thread_ref = None
        self.worker_ref = None
        self.deleteLater()


def _start_worker(
    window: Any,
    worker: QObject,
    *,
    finished_slot: Callable[[object], None],
    failed_slot: Callable[[str], None],
    progress_slot: Callable[[str], None] | None = None,
) -> QThread:
    """Use the same QObject-worker/QThread/GUI-slot pattern already proven in v1.4."""

    thread = QThread(window)
    worker.moveToThread(thread)
    lifecycle = _Preview3DJobLifecycle(window, thread, worker)
    jobs = getattr(window, "_fh6_preview3d_jobs", None)
    if not isinstance(jobs, list):
        jobs = []
        window._fh6_preview3d_jobs = jobs
    jobs.append(lifecycle)

    thread.started.connect(worker.run)
    worker.finished.connect(finished_slot)
    worker.failed.connect(failed_slot)
    if progress_slot is not None and hasattr(worker, "progress"):
        worker.progress.connect(progress_slot)

    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(lifecycle.thread_finished)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread


class _Preview3DController(QObject):
    """GUI-thread owner of preview status widgets and OpenGL widgets."""

    def __init__(
        self,
        *,
        window: Any,
        dialog: Any,
        record: Any,
        page: Any,
        layout: Any,
        message: QLabel,
        controls: dict[str, Any],
    ) -> None:
        super().__init__(page)
        self.window = window
        self.dialog = dialog
        self.record = record
        self.page = page
        self.layout = layout
        self.message = message
        self.controls = controls
        self.alive = True
        self.viewer = None
        self.retired_viewers: list[Any] = []
        self.glb_path = ""
        self.textures = None
        self.loading = False
        self.pending_reload = False

        dialog.destroyed.connect(self._dialog_destroyed)
        controls["reset"].clicked.connect(self.reset_camera)
        controls["eligibility"].currentIndexChanged.connect(self.request_reload)
        controls["cleanup_c"].toggled.connect(self.request_reload)

    @Slot()
    def _dialog_destroyed(self) -> None:
        self.alive = False

    def _eligibility(self) -> str:
        return str(self.controls["eligibility"].currentData() or "legacy")

    def _cleanup_c(self) -> bool:
        return bool(self.controls["cleanup_c"].isChecked())

    def _set_options_enabled(self, enabled: bool) -> None:
        if not self.alive:
            return
        self.controls["eligibility"].setEnabled(enabled)
        self.controls["cleanup_c"].setEnabled(enabled)
        self.controls["reset"].setEnabled(enabled and self.viewer is not None)

    def _retire_viewer(self) -> None:
        viewer = self.viewer
        self.viewer = None
        if viewer is None:
            return
        try:
            self.layout.removeWidget(viewer)
            viewer.hide()
            self.retired_viewers.append(viewer)
        except RuntimeError:
            pass

    def _drain_layout(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            child = item.widget()
            if child is None:
                continue
            if child is self.message:
                child.hide()
                continue
            if child in self.retired_viewers:
                child.hide()
                continue
            child.hide()
            child.setParent(None)
            child.deleteLater()

    def _show_message(self, text: str) -> None:
        if not self.alive:
            return
        self._retire_viewer()
        self._drain_layout()
        self.message.setText(text)
        self.layout.addWidget(self.message, 1)
        self.message.show()

    @Slot(str)
    def on_progress(self, text: str) -> None:
        if self.alive:
            self.message.setText(text)

    @Slot(str)
    def on_failed(self, text: str) -> None:
        if not self.alive:
            return
        self.loading = False
        self._show_message(
            _txt("3D 모델을 표시할 수 없습니다.\n", "Unable to display the 3D model.\n")
            + text
        )
        self._set_options_enabled(bool(self.glb_path and self.textures is not None))

    @Slot(str)
    def _viewer_failed(self, text: str) -> None:
        QTimer.singleShot(0, lambda error=text: self.on_failed(error))

    def _install_scene(self, scene: object) -> None:
        if not self.alive:
            return

        from .viewer import CarOpenGLWidget

        self._retire_viewer()
        self._drain_layout()
        self.message.hide()

        viewer = CarOpenGLWidget(scene, self.textures, parent=self.page)
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        viewer.setFormat(fmt)
        viewer.setMinimumSize(320, 240)
        viewer.load_failed.connect(self._viewer_failed)

        self.layout.addWidget(viewer, 1)
        self.viewer = viewer
        self.loading = False
        self._set_options_enabled(True)
        viewer.show()
        viewer.raise_()
        viewer.update()
        QTimer.singleShot(0, viewer.update)

    @Slot(object)
    def initial_completed(self, payload: object) -> None:
        if not self.alive:
            return
        if not isinstance(payload, dict):
            self.on_failed("Invalid 3D worker result")
            return
        glb_path = str(payload.get("glb_path") or "")
        textures = payload.get("textures")
        scene = payload.get("scene")
        if not glb_path or textures is None or scene is None:
            self.on_failed("Incomplete 3D worker result")
            return
        self.glb_path = glb_path
        self.textures = textures
        self._install_scene(scene)
        if self.pending_reload:
            self.pending_reload = False
            self.request_reload()

    @Slot(object)
    def reload_completed(self, scene: object) -> None:
        if not self.alive:
            return
        self._install_scene(scene)
        if self.pending_reload:
            self.pending_reload = False
            self.request_reload()

    @Slot()
    def reset_camera(self) -> None:
        if self.alive and self.viewer is not None:
            self.viewer.reset_camera()

    @Slot()
    def request_reload(self, *_args: object) -> None:
        if not self.alive:
            return
        if self.loading or not self.glb_path or self.textures is None:
            self.pending_reload = True
            return

        self.loading = True
        self.pending_reload = False
        self._set_options_enabled(False)
        self._show_message(_txt("3D 표시 옵션 적용 중...", "Applying 3D display options..."))

        worker = _SceneReloadWorker(
            self.glb_path,
            self.textures,
            self._eligibility(),
            self._cleanup_c(),
        )
        _start_worker(
            self.window,
            worker,
            finished_slot=self.reload_completed,
            failed_slot=self.on_failed,
        )

    def start(self) -> None:
        livery_path = getattr(self.record, "livery_path", None)
        car_id = getattr(self.record, "car_id", None)
        if not livery_path or not Path(livery_path).is_file() or car_id is None:
            self._show_message(
                _txt(
                    "3D에 필요한 C_livery 또는 Car ID가 없습니다.",
                    "C_livery or Car ID required for 3D preview is unavailable.",
                )
            )
            return

        self.loading = True
        self._set_options_enabled(False)
        worker = _InitialPreviewWorker(
            int(car_id),
            str(livery_path),
            self._eligibility(),
            self._cleanup_c(),
        )
        _start_worker(
            self.window,
            worker,
            finished_slot=self.initial_completed,
            failed_slot=self.on_failed,
            progress_slot=self.on_progress,
        )


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
    controller = _Preview3DController(
        window=window,
        dialog=dialog,
        record=record,
        page=page,
        layout=layout,
        message=message,
        controls=controls,
    )
    page._fh6_preview3d_controller = controller
    controller.start()
