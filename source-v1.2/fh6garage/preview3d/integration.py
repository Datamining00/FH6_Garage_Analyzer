from __future__ import annotations

import re
import shutil
import tempfile
import traceback
from pathlib import Path
from threading import Lock
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QMessageBox

from .chassis_converter import ChassisConverterError, convert_vehicle
from .direct_livery import DirectLiveryError, build_direct_livery_textures
from .glb_parser import GlbViewerError, load_kfps_glb
from .glb_viewer import CarOpenGLWidget
from .kfps_render_backend import KfpsRenderError, SECTION_NAMES, render_clivery_sections
from .livery_resolution import resolve_livery_resolution
from .vehicle_index import (
    VehicleAsset,
    VehicleIndexError,
    detect_fh6_installation,
    preferred_carbin_entry,
    scan_vehicle_assets,
)


_INDEX_LOCK = Lock()
_INDEX_CACHE: dict[str, dict[int, VehicleAsset]] = {}


def _vehicle_index(game_root: Path) -> dict[int, VehicleAsset]:
    key = str(game_root.resolve()).casefold()
    with _INDEX_LOCK:
        cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    index = scan_vehicle_assets(game_root)
    with _INDEX_LOCK:
        _INDEX_CACHE[key] = index
    return index


def _select_asset(game_root: Path, car_id: int) -> tuple[VehicleAsset, str]:
    index = _vehicle_index(game_root)
    asset = index.get(int(car_id))
    if asset is None:
        raise VehicleIndexError(f"Car ID {car_id} was not found in the installed FH6 vehicle archives.")
    carbin_entry = preferred_carbin_entry(asset)
    if carbin_entry is None:
        if len(asset.carbin_entries) == 1:
            carbin_entry = asset.carbin_entries[0]
        else:
            raise VehicleIndexError(
                f"Car ID {car_id} has multiple ambiguous carbin scenes; "
                "the FinalVerify1 automatic scene selection could not choose one."
            )
    return asset, carbin_entry


class _InitialPipelineWorker(QThread):
    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        car_id: int,
        livery_path: str,
        work_root: str,
        resolution: str,
        uv_channel: int,
        eligibility: str,
        cleanup_ab: bool,
        cleanup_c: bool,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.car_id = int(car_id)
        self.livery_path = str(livery_path)
        self.work_root = Path(work_root)
        self.resolution = str(resolution)
        self.uv_channel = int(uv_channel)
        self.eligibility = str(eligibility)
        self.cleanup_ab = bool(cleanup_ab)
        self.cleanup_c = bool(cleanup_c)

    def run(self) -> None:
        try:
            self.progress.emit("FH6 차량 3D 데이터를 찾는 중...")
            game_root = detect_fh6_installation()
            if game_root is None:
                raise VehicleIndexError(
                    "FH6 설치 경로를 찾을 수 없습니다. 비표준 설치 경로라면 "
                    "FH6_GAME_DIR 또는 FORZA_HORIZON_6_DIR 환경 변수를 지정하십시오."
                )
            game_root = Path(game_root)
            asset, carbin_entry = _select_asset(game_root, self.car_id)

            self.progress.emit("FinalVerify1 차량 형상을 준비하는 중...")
            geometry_root = self.work_root / "geometry"
            conversion = convert_vehicle(
                asset,
                progress=self.progress.emit,
                carbin_entry=carbin_entry,
                work_root=geometry_root,
            )

            self.progress.emit("선택한 리버리를 렌더링하는 중...")
            render_root = self.work_root / "render"
            result = render_clivery_sections(
                self.livery_path,
                game_folder=game_root,
                resolution=self.resolution,
                output_root=render_root,
                log=self.progress.emit,
            )
            if int(result.car_id) != self.car_id:
                raise KfpsRenderError(
                    f"C_livery Car ID {result.car_id} does not match selected card Car ID {self.car_id}."
                )

            self.progress.emit("3D 리버리 텍스처를 준비하는 중...")
            textures = build_direct_livery_textures(result, asset)

            self.progress.emit(
                f"TEXCOORD_{self.uv_channel} / {self.eligibility} 장면을 준비하는 중..."
            )
            scene = load_kfps_glb(
                conversion.output_path,
                textures,
                diagnostic_all_uv=False,
                livery_uv_channel=self.uv_channel,
                livery_eligibility=self.eligibility,
                neutral_cleanup_ab=self.cleanup_ab,
                neutral_cleanup_c=self.cleanup_c,
            )

            # Section PNGs are only an intermediate transport into DirectLiveryTextures.
            # Remove them immediately; the dialog retains the in-memory texture arrays.
            try:
                shutil.rmtree(render_root, ignore_errors=True)
            except OSError:
                pass

            self.completed.emit(
                {
                    "game_root": str(game_root),
                    "asset": asset,
                    "glb_path": str(conversion.output_path),
                    "textures": textures,
                    "scene": scene,
                    "resolution": self.resolution,
                }
            )
        except Exception as exc:
            if isinstance(
                exc,
                (
                    ChassisConverterError,
                    DirectLiveryError,
                    GlbViewerError,
                    KfpsRenderError,
                    VehicleIndexError,
                    OSError,
                    ValueError,
                ),
            ):
                self.failed.emit(f"{type(exc).__name__}: {exc}")
            else:
                self.failed.emit(f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")


class _RerenderWorker(QThread):
    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        asset: VehicleAsset,
        game_root: str,
        livery_path: str,
        glb_path: str,
        work_root: str,
        resolution: str,
        uv_channel: int,
        eligibility: str,
        cleanup_ab: bool,
        cleanup_c: bool,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.asset = asset
        self.game_root = Path(game_root)
        self.livery_path = str(livery_path)
        self.glb_path = str(glb_path)
        self.work_root = Path(work_root)
        self.resolution = str(resolution)
        self.uv_channel = int(uv_channel)
        self.eligibility = str(eligibility)
        self.cleanup_ab = bool(cleanup_ab)
        self.cleanup_c = bool(cleanup_c)

    def run(self) -> None:
        try:
            render_root = self.work_root / "render"
            try:
                shutil.rmtree(render_root, ignore_errors=True)
            except OSError:
                pass
            self.progress.emit("선택한 배율로 리버리를 다시 렌더링하는 중...")
            result = render_clivery_sections(
                self.livery_path,
                game_folder=self.game_root,
                resolution=self.resolution,
                output_root=render_root,
                log=self.progress.emit,
            )
            if int(result.car_id) != int(self.asset.car_id):
                raise KfpsRenderError(
                    f"C_livery Car ID {result.car_id} does not match selected card Car ID {self.asset.car_id}."
                )
            textures = build_direct_livery_textures(result, self.asset)
            scene = load_kfps_glb(
                self.glb_path,
                textures,
                diagnostic_all_uv=False,
                livery_uv_channel=self.uv_channel,
                livery_eligibility=self.eligibility,
                neutral_cleanup_ab=self.cleanup_ab,
                neutral_cleanup_c=self.cleanup_c,
            )
            try:
                shutil.rmtree(render_root, ignore_errors=True)
            except OSError:
                pass
            self.completed.emit(
                {
                    "textures": textures,
                    "scene": scene,
                    "resolution": self.resolution,
                }
            )
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _SceneReloadWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        glb_path: str,
        textures: object,
        uv_channel: int,
        eligibility: str,
        cleanup_ab: bool,
        cleanup_c: bool,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.glb_path = str(glb_path)
        self.textures = textures
        self.uv_channel = int(uv_channel)
        self.eligibility = str(eligibility)
        self.cleanup_ab = bool(cleanup_ab)
        self.cleanup_c = bool(cleanup_c)

    def run(self) -> None:
        try:
            scene = load_kfps_glb(
                self.glb_path,
                self.textures,
                diagnostic_all_uv=False,
                livery_uv_channel=self.uv_channel,
                livery_eligibility=self.eligibility,
                neutral_cleanup_ab=self.cleanup_ab,
                neutral_cleanup_c=self.cleanup_c,
            )
            self.completed.emit(scene)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class Preview3DController(QObject):
    """GUI-thread controller for one livery-card magnifier dialog."""

    def __init__(
        self,
        *,
        window: Any,
        dialog: Any,
        record: Any,
        viewer_layout: Any,
        status_label: Any,
        controls: dict[str, Any],
    ) -> None:
        super().__init__(window)
        self.window = window
        self.dialog = dialog
        self.record = record
        self.viewer_layout = viewer_layout
        self.status_label = status_label
        self.controls = controls
        self.progress_bar = controls.get("progress")
        self.progress_title = controls.get("progress_title")
        self._progress_resolution = "ultra4x"
        self._progress_section_index = -1
        self.alive = True
        self.loading = False
        self.viewer: CarOpenGLWidget | None = None
        self.worker: QThread | None = None
        self.asset: VehicleAsset | None = None
        self.game_root = ""
        self.glb_path = ""
        self.textures = None
        self.rendered_resolution = ""
        self._temp = tempfile.TemporaryDirectory(prefix="fh6_assistant_3d_")
        self.work_root = Path(self._temp.name)

        dialog.destroyed.connect(self._dialog_destroyed)
        controls["apply"].clicked.connect(self.apply_current_options)
        controls["reset"].clicked.connect(self.reset_camera)

    def _selected(self) -> tuple[str, int, str, bool, bool]:
        return (
            str(self.controls["resolution"].currentData() or "ultra4x"),
            int(self.controls["uv"].currentData()),
            str(self.controls["eligibility"].currentData() or "legacy"),
            bool(self.controls["cleanup_ab"].isChecked()),
            bool(self.controls["cleanup_c"].isChecked()),
        )

    def _set_controls_enabled(self, enabled: bool) -> None:
        for key in ("resolution", "uv", "eligibility", "cleanup_ab", "cleanup_c", "apply"):
            self.controls[key].setEnabled(bool(enabled))
        self.controls["reset"].setEnabled(bool(enabled and self.viewer is not None))

    def _set_progress(self, value: int, title: str | None = None, detail: str | None = None) -> None:
        if not self.alive:
            return
        value = max(0, min(100, int(value)))
        if self.progress_bar is not None:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)
            self.progress_bar.setFormat(f"{value}%")
        if title is not None and self.progress_title is not None:
            self.progress_title.setText(str(title))
        if detail is not None:
            self.status_label.setText(str(detail))

    def _render_progress_from_message(self, text: str) -> bool:
        message = str(text).strip()
        spec = resolve_livery_resolution(self._progress_resolution)
        canvas_h = int(spec.canvas_size[1])
        section_count = max(1, len(SECTION_NAMES))

        if message.startswith("M6.23 stage 1/4"):
            self._set_progress(22, "리버리 렌더링 준비 중", "렌더러를 준비하고 있습니다.")
            return True
        if message.startswith("M6.23 stage 2/4"):
            self._set_progress(24, "리버리 렌더링 준비 중", "렌더링 백엔드를 불러오고 있습니다.")
            return True
        if message.startswith("M6.23 stage 3/4"):
            self._set_progress(27, "리버리 디코딩 중", "C_livery 레이어를 읽고 있습니다.")
            return True
        if "stage 4/4: rendering 11 sections" in message:
            self._set_progress(30, "3D 리버리 렌더링 중", f"전체 {section_count}개 영역 렌더링을 시작합니다.")
            return True

        rendering = re.match(r"Rendering ([^:]+):", message)
        if rendering:
            section = rendering.group(1)
            try:
                self._progress_section_index = SECTION_NAMES.index(section)
            except ValueError:
                self._progress_section_index = -1
            if self._progress_section_index >= 0:
                base_fraction = self._progress_section_index / section_count
                value = 30 + round(62 * base_fraction)
                self._set_progress(
                    value,
                    "3D 리버리 렌더링 중",
                    f"{section} · {self._progress_section_index + 1} / {section_count} 영역",
                )
                return True

        strip = re.match(r"strip (\d+):(\d+)", message)
        if strip and self._progress_section_index >= 0 and canvas_h > 0:
            y0, y1 = (int(strip.group(1)), int(strip.group(2)))
            section_fraction = max(0.0, min(1.0, y1 / canvas_h))
            total_fraction = (self._progress_section_index + section_fraction) / section_count
            value = 30 + round(62 * total_fraction)
            strips_per_section = max(1, (canvas_h + 1023) // 1024)
            strip_number = min(strips_per_section, (max(0, y0) // 1024) + 1)
            section = SECTION_NAMES[self._progress_section_index]
            self._set_progress(
                value,
                "3D 리버리 렌더링 중",
                f"{section} · {strip_number} / {strips_per_section} strip · "
                f"영역 {self._progress_section_index + 1} / {section_count}",
            )
            return True

        rendered = re.match(r"Rendered ([^ ]+) in ", message)
        if rendered:
            section = rendered.group(1)
            try:
                index = SECTION_NAMES.index(section)
            except ValueError:
                index = -1
            if index >= 0:
                total_fraction = (index + 1) / section_count
                value = 30 + round(62 * total_fraction)
                self._set_progress(
                    value,
                    "3D 리버리 렌더링 중",
                    f"{section} 완료 · {index + 1} / {section_count} 영역",
                )
                return True
        return False

    def _set_status(self, text: str) -> None:
        if not self.alive:
            return
        message = str(text)
        if self._render_progress_from_message(message):
            return
        if message.startswith("FH6 차량 3D 데이터를 찾는 중"):
            self._set_progress(4, "3D 모델 준비 중", "FH6 차량 데이터를 찾고 있습니다.")
        elif message.startswith("FinalVerify1 차량 형상을 준비하는 중"):
            self._set_progress(10, "3D 모델 준비 중", "FinalVerify1 차량 형상을 준비하고 있습니다.")
        elif message.startswith("선택한 리버리를 렌더링하는 중") or message.startswith("선택한 배율로 리버리를 다시 렌더링하는 중"):
            self._set_progress(20, "리버리 렌더링 준비 중", "선택한 리버리의 렌더링 작업을 시작합니다.")
        elif message.startswith("3D 리버리 텍스처를 준비하는 중"):
            self._set_progress(94, "3D 텍스처 준비 중", "렌더링된 영역을 3D 텍스처로 결합하고 있습니다.")
        elif message.startswith("TEXCOORD_"):
            self._set_progress(98, "3D 장면 구성 중", message.replace("장면을 준비하는 중...", "장면을 구성하고 있습니다."))
        else:
            self.status_label.setText(message)

    def _confirm_high_resolution(self, resolution_key: str) -> bool:
        spec = resolve_livery_resolution(resolution_key)
        if spec.scale < 8:
            return True
        approx_mib = spec.raw_rgba_bytes / (1024 * 1024)
        answer = QMessageBox.question(
            self.dialog,
            f"{spec.scale}x 리버리 렌더링",
            f"{spec.label}은 고메모리 모드입니다.\n\n"
            f"단일 비압축 RGBA 섹션만 약 {approx_mib:,.0f} MiB이며 렌더링 중 여러 버퍼가 필요할 수 있습니다.\n"
            "선택한 배율을 자동으로 낮추지 않습니다. 계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    @Slot()
    def start(self) -> None:
        if self.loading or self.glb_path:
            return
        self.apply_current_options()

    @Slot()
    def apply_current_options(self) -> None:
        if not self.alive or self.loading:
            return
        livery_path = getattr(self.record, "livery_path", None)
        car_id = getattr(self.record, "car_id", None)
        if not livery_path or not Path(livery_path).is_file() or car_id is None:
            self._set_status("이 리버리 카드에는 3D 렌더링에 필요한 C_livery 또는 Car ID가 없습니다.")
            return

        resolution, uv_channel, eligibility, cleanup_ab, cleanup_c = self._selected()
        if resolution != self.rendered_resolution and not self._confirm_high_resolution(resolution):
            self._set_status("고해상도 렌더링이 취소되었습니다.")
            return

        self.loading = True
        self._progress_resolution = resolution
        self._progress_section_index = -1
        self._set_controls_enabled(False)
        if not self.glb_path:
            self._set_progress(2, "3D 모델 준비 중", "차량 형상과 선택한 리버리를 준비합니다.")
            worker: QThread = _InitialPipelineWorker(
                car_id=int(car_id),
                livery_path=str(livery_path),
                work_root=str(self.work_root),
                resolution=resolution,
                uv_channel=uv_channel,
                eligibility=eligibility,
                cleanup_ab=cleanup_ab,
                cleanup_c=cleanup_c,
                parent=self.window,
            )
            worker.progress.connect(self._set_status)
            worker.completed.connect(self._initial_completed)
        elif resolution != self.rendered_resolution:
            self._set_progress(20, "리버리 다시 렌더링 중", "선택한 배율로 전체 리버리를 다시 렌더링합니다.")
            worker = _RerenderWorker(
                asset=self.asset,
                game_root=self.game_root,
                livery_path=str(livery_path),
                glb_path=self.glb_path,
                work_root=str(self.work_root),
                resolution=resolution,
                uv_channel=uv_channel,
                eligibility=eligibility,
                cleanup_ab=cleanup_ab,
                cleanup_c=cleanup_c,
                parent=self.window,
            )
            worker.progress.connect(self._set_status)
            worker.completed.connect(self._rerender_completed)
        else:
            self._set_progress(65, "3D 옵션 적용 중", "UV / 정책 / cleanup 옵션을 장면에 적용하고 있습니다.")
            worker = _SceneReloadWorker(
                glb_path=self.glb_path,
                textures=self.textures,
                uv_channel=uv_channel,
                eligibility=eligibility,
                cleanup_ab=cleanup_ab,
                cleanup_c=cleanup_c,
                parent=self.window,
            )
            worker.completed.connect(self._reload_completed)

        worker.failed.connect(self._failed)
        worker.finished.connect(self._worker_finished)
        worker.finished.connect(worker.deleteLater)
        self.worker = worker
        worker.start()

    @Slot(str)
    def _failed(self, message: str) -> None:
        self.loading = False
        self._set_controls_enabled(True)
        self._set_progress(0, "3D 렌더링 실패", "3D 리버리를 표시할 수 없습니다.\n" + str(message))

    @Slot(object)
    def _initial_completed(self, payload: object) -> None:
        if not self.alive or not isinstance(payload, dict):
            return
        self.asset = payload.get("asset")
        self.game_root = str(payload.get("game_root") or "")
        self.glb_path = str(payload.get("glb_path") or "")
        self.textures = payload.get("textures")
        self.rendered_resolution = str(payload.get("resolution") or "")
        self._install_scene(payload.get("scene"))

    @Slot(object)
    def _rerender_completed(self, payload: object) -> None:
        if not self.alive or not isinstance(payload, dict):
            return
        self.textures = payload.get("textures")
        self.rendered_resolution = str(payload.get("resolution") or "")
        self._install_scene(payload.get("scene"))

    @Slot(object)
    def _reload_completed(self, scene: object) -> None:
        if not self.alive:
            return
        self._install_scene(scene)

    def _install_scene(self, scene: object) -> None:
        if not self.alive or scene is None:
            return
        placeholder = self.controls.get("placeholder")
        if placeholder is not None:
            try:
                self.viewer_layout.removeWidget(placeholder)
                placeholder.hide()
                placeholder.deleteLater()
            except RuntimeError:
                pass
            self.controls["placeholder"] = None

        old = self.viewer
        if old is not None:
            try:
                self.viewer_layout.removeWidget(old)
                old.hide()
                old.deleteLater()
            except RuntimeError:
                pass

        viewer = CarOpenGLWidget(scene, self.textures, parent=self.dialog)
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        viewer.setFormat(fmt)
        viewer.setMinimumSize(520, 360)
        viewer.load_failed.connect(self._viewer_failed)
        self.viewer_layout.addWidget(viewer, 1)
        self.viewer = viewer
        self.loading = False
        self._set_controls_enabled(True)

        resolution, uv_channel, eligibility, cleanup_ab, cleanup_c = self._selected()
        spec = resolve_livery_resolution(resolution)
        self._set_progress(
            100,
            "3D 렌더링 완료",
            f"{spec.scale}x · TEXCOORD_{uv_channel} · {eligibility} · "
            f"A+B {'ON' if cleanup_ab else 'OFF'} · C {'ON' if cleanup_c else 'OFF'}",
        )
        viewer.show()
        viewer.raise_()
        viewer.update()
        QTimer.singleShot(0, viewer.update)

    @Slot(str)
    def _viewer_failed(self, message: str) -> None:
        self._set_progress(0, "OpenGL 초기화 실패", str(message))

    @Slot()
    def reset_camera(self) -> None:
        if self.viewer is not None:
            try:
                self.viewer.reset_camera()
            except RuntimeError:
                pass

    @Slot()
    def _worker_finished(self) -> None:
        self.worker = None
        if not self.alive:
            self._cleanup()

    @Slot()
    def _dialog_destroyed(self) -> None:
        self.alive = False
        if self.worker is None or not self.worker.isRunning():
            self._cleanup()

    def _cleanup(self) -> None:
        try:
            self._temp.cleanup()
        except Exception:
            pass
        self.deleteLater()
