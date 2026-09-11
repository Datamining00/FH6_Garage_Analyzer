"""Lazy section PNG viewer; never prepares vehicle geometry or native materials."""
from pathlib import Path
import tempfile

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QComboBox, QGraphicsPixmapItem, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .app_options import options_snapshot
from .ui import ZoomableImageView


SECTION_LABELS = {
    'Front': '앞', 'Back': '뒤', 'Top': '위', 'Left': '왼쪽', 'Right': '오른쪽',
    'Spoiler': '스포일러', 'FrontWindshield': '앞유리', 'BackWindshield': '뒷유리',
    'TopWindow': '지붕 유리', 'LeftWindow': '왼쪽 유리', 'RightWindow': '오른쪽 유리',
}


class _SectionWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, source, root, resolution, parent):
        super().__init__(parent)
        self.source, self.root, self.resolution = source, root, resolution

    def run(self):
        try:
            from .preview3d.kfps_render_backend import render_clivery_sections
            from .preview3d.vehicle_index import detect_fh6_installation
            from .preview3d.pipeline_diagnostics import preview_trace
            with options_snapshot(), preview_trace('livery_2d'):
                result = render_clivery_sections(self.source, game_folder=detect_fh6_installation(),
                    resolution=self.resolution, output_root=self.root, log=self.progress.emit)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')


class Livery2DController(QObject):
    def __init__(self, window, dialog, record):
        # Parent to the main window so closing the dialog cannot destroy an active worker.
        super().__init__(window)
        self.window, self.dialog, self.record = window, dialog, record
        self.alive, self.started = True, False
        self.worker = None
        self.temp = tempfile.TemporaryDirectory(prefix='fh6_livery_2d_')
        self.result = None
        self.page = QWidget()
        layout = QVBoxLayout(self.page)
        toolbar = QHBoxLayout()
        self.section = QComboBox()
        for key, label in SECTION_LABELS.items():
            self.section.addItem(label, key)
        self.section.currentIndexChanged.connect(self.show_section)
        self.resolution = QComboBox()
        for label, key in (('1x', 'normal'), ('2x', 'high'), ('4x', 'ultra4x')):
            self.resolution.addItem(label, key)
        self.resolution.setCurrentIndex(2)
        self.render = QPushButton('렌더링')
        self.render.clicked.connect(self.start)
        fit = QPushButton('화면에 맞춤')
        actual = QPushButton('100%')
        toolbar.addWidget(self.section)
        toolbar.addWidget(self.resolution)
        toolbar.addWidget(self.render)
        toolbar.addStretch()
        toolbar.addWidget(fit)
        toolbar.addWidget(actual)
        layout.addLayout(toolbar)
        self.status = QLabel('2D 탭을 선택하면 부위별 리버리 PNG를 준비합니다.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.viewer = ZoomableImageView(QPixmap())
        # Fit the entire PNG canvas, including its transparent margins.
        self.viewer._pixmap_item.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        fit.clicked.connect(self.viewer.fit_image)
        actual.clicked.connect(self.viewer.actual_size)
        layout.addWidget(self.viewer, 1)
        dialog.finished.connect(self.closed)

    @Slot()
    def start(self):
        if not self.alive or self.worker is not None:
            return
        source = getattr(self.record, 'livery_path', None)
        if source is None or not Path(source).is_file():
            self.status.setText('C_livery 파일을 찾을 수 없습니다.')
            return
        from .preview3d.cold_livery_render_fastpath_patch import install_cold_livery_render_fastpath_patch
        from .preview3d.livery_render_cache_patch import install_livery_render_cache_patch
        install_cold_livery_render_fastpath_patch()
        install_livery_render_cache_patch()
        self.started = True
        self.render.setEnabled(False)
        worker = _SectionWorker(source, self.temp.name, self.resolution.currentData(), self.window)
        worker.completed.connect(self.completed)
        worker.failed.connect(self.failed)
        worker.progress.connect(self.progress)
        worker.finished.connect(self.finished)
        self.worker = worker
        worker.start()

    @Slot(str)
    def progress(self, message):
        if self.alive:
            self.status.setText(message)

    @Slot(object)
    def completed(self, result):
        if not self.alive:
            return
        self.result = result
        self.show_section()

    @Slot(str)
    def failed(self, message):
        self.progress('2D 렌더링 실패: ' + message)

    @Slot()
    def show_section(self, *_):
        if self.result is None or not self.alive:
            return
        section = self.section.currentData()
        path = self.result.png_paths.get(section)
        pixmap = QPixmap(str(path)) if path else QPixmap()
        self.viewer._pixmap_item.setPixmap(pixmap)
        self.viewer.scene().setSceneRect(self.viewer._pixmap_item.boundingRect())
        self.viewer.fit_image()
        self.status.setText(f'{self.section.currentText()} · {self.result.section_counts.get(section, 0)} 레이어'
                            if path else f'{self.section.currentText()} · 이 부위에는 리버리가 없습니다.')

    @Slot()
    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        if self.alive:
            self.render.setEnabled(True)
        else:
            self.temp.cleanup()
            self.deleteLater()

    @Slot()
    def closed(self, *_):
        self.alive = False
        if self.worker is None:
            self.temp.cleanup()
            self.deleteLater()
