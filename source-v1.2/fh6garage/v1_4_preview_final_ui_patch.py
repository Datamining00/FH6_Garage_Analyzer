from __future__ import annotations

import concurrent.futures
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .exact_livery_preview import ExactLiveryPreviewError, configured_fh6_game_folder, set_fh6_game_folder
from .i18n import get_language, tr
from .livery_analysis import LIVERY_SECTION_NAMES, LiveryAnalysisError, analyze_livery_file
from .livery_preview import LiveryPreviewError, clear_livery_preview_cache
from .livery_preview_tiled_quality import clear_tiled_quality_cache, normalize_scale, render_livery_section_scaled
from .livery_preview_ui_state import load_view_mode, rotate_section_image, save_view_mode
from .models import LiveryRecord
from .ui import APP_STYLE, ZoomableImageView

TEST_VERSION_LABEL = "v1.4 Preview UX Test"
RENDER_MODE_KEY = "livery_preview_render_mode_v14"
QUALITY_SCALE_KEY = "livery_preview_quality_scale_v14"
DEFAULT_RENDER_MODE = "quality"
DEFAULT_QUALITY_SCALE = 4

_SECTION_LABELS_KO = {
    "Front": "전면",
    "Back": "후면",
    "Top": "상단",
    "Left": "왼쪽",
    "Right": "오른쪽",
    "Spoiler": "스포일러",
    "FrontWindshield": "앞유리",
    "BackWindshield": "뒷유리",
    "TopWindow": "상단 유리",
    "LeftWindow": "왼쪽 유리",
    "RightWindow": "오른쪽 유리",
}


def _ko() -> bool:
    return str(get_language() or "").lower().startswith("ko")


def _section_label(name: str) -> str:
    return _SECTION_LABELS_KO.get(name, name) if _ko() else name


def _placeholder(text: str, *, error: bool = False) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setStyleSheet(
        "background:#eff1f6;border:1px solid #dfe1e8;border-radius:10px;"
        + ("color:#a33a45;" if error else "color:#737787;")
        + "padding:24px;font-size:11pt;"
    )
    return label


def _button_style() -> str:
    return """
    QPushButton {
        min-height: 34px;
        padding: 0 14px;
        border-radius: 9px;
        border: 1px solid #40434d;
        background: #f5f5f7;
        color: #202126;
        font-size: 10pt;
    }
    QPushButton:hover { background: #ffffff; border-color: #6b6f7c; }
    QPushButton:checked {
        background: #7357f6;
        color: white;
        border-color: #8b76ff;
    }
    """


def _mode_button_style() -> str:
    return """
    QPushButton {
        min-height: 32px;
        padding: 0 12px;
        border-radius: 8px;
        border: 1px solid #484b57;
        background: #292b33;
        color: #dfe1e7;
        font-size: 9.5pt;
    }
    QPushButton:hover { background: #343741; }
    QPushButton:checked {
        background: #7357f6;
        color: white;
        border-color: #8b76ff;
    }
    """


def _show_livery_image_final(self: Any, record: Any) -> None:
    if not isinstance(record, LiveryRecord) or not record.livery_path:
        return self._fh6_v14_final_ui_original_show_livery_image(record)

    try:
        analysis = analyze_livery_file(record.livery_path)
    except LiveryAnalysisError:
        return self._fh6_v14_final_ui_original_show_livery_image(record)

    thumbnail_image = QImage()
    if record.thumbnail_path and record.thumbnail_path.is_file():
        try:
            thumbnail_image = QImage.fromData(record.thumbnail_path.read_bytes())
        except OSError:
            thumbnail_image = QImage()

    used_sections = [
        section for section in LIVERY_SECTION_NAMES
        if int(analysis.section_counts.get(section, 0)) > 0
    ]
    if thumbnail_image.isNull() and not used_sections:
        return self._fh6_v14_final_ui_original_show_livery_image(record)

    dialog = QDialog(self)
    livery_name = record.header.name or "(unnamed)"
    car_name = self._car_label(record.header.car_id)
    dialog.setWindowTitle(f"{livery_name} — {car_name} — Preview")
    dialog.setModal(True)
    dialog.resize(1480, 980)
    dialog.setMinimumSize(900, 620)
    dialog.setStyleSheet(APP_STYLE)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(8)

    top_bar = QFrame()
    top_bar.setObjectName("liveryPreviewTopBar")
    top_bar.setStyleSheet(
        "QFrame#liveryPreviewTopBar{background:#1b1d24;border:1px solid #30333d;border-radius:12px;}"
    )
    top_layout = QHBoxLayout(top_bar)
    top_layout.setContentsMargins(8, 7, 8, 7)
    top_layout.setSpacing(8)

    tab_scroll = QScrollArea()
    tab_scroll.setWidgetResizable(True)
    tab_scroll.setFrameShape(QFrame.Shape.NoFrame)
    tab_scroll.setStyleSheet("QScrollArea{background:transparent;border:0;} QWidget{background:transparent;}")
    tab_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tab_scroll.setFixedHeight(46)
    tab_host = QWidget()
    tab_row = QHBoxLayout(tab_host)
    tab_row.setContentsMargins(0, 0, 0, 0)
    tab_row.setSpacing(6)
    tab_scroll.setWidget(tab_host)
    top_layout.addWidget(tab_scroll, 1)

    mode_group = QButtonGroup(dialog)
    mode_group.setExclusive(True)
    fast_button = QPushButton("빠르게 보기" if _ko() else "Quick view")
    quality_button = QPushButton("품질 모드" if _ko() else "Quality")
    for button in (fast_button, quality_button):
        button.setCheckable(True)
        button.setStyleSheet(_mode_button_style())
        mode_group.addButton(button)
    top_layout.addWidget(fast_button)
    top_layout.addWidget(quality_button)

    scale_combo = QComboBox()
    scale_combo.setMinimumWidth(88)
    for scale in (2, 4, 8, 16):
        label = f"{scale}×"
        if scale == 4:
            label += " · 기본" if _ko() else " · default"
        scale_combo.addItem(label, scale)
    scale_combo.setToolTip(
        "8×/16×는 타일 방식으로 고배율 렌더 후 4× 미리보기로 결합합니다."
        if _ko() else
        "8×/16× use tiled supersampling and are combined into a retained 4× preview."
    )
    top_layout.addWidget(scale_combo)

    game_folder_button = QPushButton("FH6 폴더" if _ko() else "FH6 folder")
    game_folder_button.setStyleSheet(_mode_button_style())
    top_layout.addWidget(game_folder_button)
    layout.addWidget(top_bar)

    stack = QStackedWidget()
    layout.addWidget(stack, 1)

    status_label = QLabel()
    status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status_label.setStyleSheet("color:#6f7380;font-size:9pt;")

    saved_mode = str(self.settings.value(RENDER_MODE_KEY, DEFAULT_RENDER_MODE, str) or DEFAULT_RENDER_MODE)
    if saved_mode not in {"fast", "quality"}:
        saved_mode = DEFAULT_RENDER_MODE
    saved_scale = normalize_scale(self.settings.value(QUALITY_SCALE_KEY, DEFAULT_QUALITY_SCALE))
    if saved_scale not in {2, 4, 8, 16}:
        saved_scale = DEFAULT_QUALITY_SCALE
    render_state = {"mode": saved_mode, "quality_scale": saved_scale}
    view_mode_state = {"value": load_view_mode(self.settings)}

    index = scale_combo.findData(saved_scale)
    scale_combo.setCurrentIndex(max(0, index))
    fast_button.setChecked(saved_mode == "fast")
    quality_button.setChecked(saved_mode != "fast")
    scale_combo.setEnabled(saved_mode != "fast")

    def effective_scale() -> int:
        return 1 if render_state["mode"] == "fast" else int(render_state["quality_scale"])

    pages: dict[str, QWidget] = {}
    futures: dict[str, tuple[concurrent.futures.Future, int]] = {}
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="fh6-livery-final")
    button_group = QButtonGroup(dialog)
    button_group.setExclusive(True)
    section_buttons: dict[str, QPushButton] = {}

    def current_viewer() -> ZoomableImageView | None:
        current = stack.currentWidget()
        return current if isinstance(current, ZoomableImageView) else None

    def apply_saved_view(viewer: ZoomableImageView) -> None:
        mode = view_mode_state["value"]
        if mode == "actual":
            QTimer.singleShot(0, viewer.actual_size)
        else:
            QTimer.singleShot(0, viewer.fit_image)

    def update_status(key: str) -> None:
        if key == "thumbnail":
            status_label.setText("썸네일" if _ko() else "Thumbnail")
            return
        count = int(analysis.section_counts.get(key, 0))
        scale = effective_scale()
        mode = ("빠르게 보기" if _ko() else "Quick") if render_state["mode"] == "fast" else ("품질" if _ko() else "Quality")
        status_label.setText(f"{_section_label(key)} · {count:,} · {mode} {scale}×")

    def show_page(key: str) -> None:
        page = pages.get(key)
        if page is not None:
            stack.setCurrentWidget(page)
        update_status(key)

    if not thumbnail_image.isNull():
        thumbnail_viewer = ZoomableImageView(QPixmap.fromImage(thumbnail_image))
        pages["thumbnail"] = thumbnail_viewer
        stack.addWidget(thumbnail_viewer)
        thumb_button = QPushButton("썸네일" if _ko() else "Thumbnail")
        thumb_button.setCheckable(True)
        thumb_button.setStyleSheet(_button_style())
        thumb_button.clicked.connect(lambda checked=False: show_page("thumbnail"))
        button_group.addButton(thumb_button)
        tab_row.addWidget(thumb_button)
        thumb_button.setChecked(True)
        update_status("thumbnail")
        apply_saved_view(thumbnail_viewer)
    else:
        missing = _placeholder("저장된 썸네일이 없습니다." if _ko() else "No saved thumbnail is available.")
        pages["thumbnail"] = missing
        stack.addWidget(missing)

    def request_section(section: str) -> None:
        existing = pages.get(section)
        if existing is not None:
            show_page(section)
            return
        scale = effective_scale()
        text = (
            f"{_section_label(section)} 영역을 {scale}×로 재구성하는 중입니다..."
            if _ko() else f"Reconstructing {_section_label(section)} at {scale}×..."
        )
        waiting = _placeholder(text)
        pages[section] = waiting
        stack.addWidget(waiting)
        stack.setCurrentWidget(waiting)
        update_status(section)
        future = executor.submit(render_livery_section_scaled, record.livery_path, section, scale)
        futures[section] = (future, scale)

    for section in used_sections:
        button = QPushButton(f"{_section_label(section)}  {int(analysis.section_counts.get(section, 0)):,}")
        button.setCheckable(True)
        button.setStyleSheet(_button_style())
        button.clicked.connect(lambda checked=False, section_name=section: request_section(section_name))
        button_group.addButton(button)
        section_buttons[section] = button
        tab_row.addWidget(button)
    tab_row.addStretch(1)

    def replace_page(section: str, new_page: QWidget) -> None:
        old_page = pages.get(section)
        was_current = old_page is not None and stack.currentWidget() is old_page
        if old_page is not None:
            index = stack.indexOf(old_page)
            stack.removeWidget(old_page)
            old_page.deleteLater()
            stack.insertWidget(max(0, index), new_page)
        else:
            stack.addWidget(new_page)
        pages[section] = new_page
        if was_current:
            stack.setCurrentWidget(new_page)

    def poll_futures() -> None:
        for section, payload in list(futures.items()):
            future, requested_scale = payload
            if not future.done():
                continue
            futures.pop(section, None)
            if requested_scale != effective_scale():
                continue
            try:
                result = future.result()
                image = QImage.fromData(result.png_bytes)
                if image.isNull():
                    raise LiveryPreviewError("렌더링 결과 PNG를 읽지 못했습니다.")
                image = rotate_section_image(image, section)
                viewer = ZoomableImageView(QPixmap.fromImage(image))
                replace_page(section, viewer)
                if stack.currentWidget() is viewer:
                    update_status(section)
                    apply_saved_view(viewer)
            except Exception as exc:
                failed = _placeholder(
                    (f"{_section_label(section)} 미리보기 생성 실패\n\n{exc}" if _ko() else f"Could not render {_section_label(section)}\n\n{exc}"),
                    error=True,
                )
                replace_page(section, failed)

    poll_timer = QTimer(dialog)
    poll_timer.setInterval(80)
    poll_timer.timeout.connect(poll_futures)
    poll_timer.start()

    if thumbnail_image.isNull() and used_sections:
        first = used_sections[0]
        section_buttons[first].setChecked(True)
        request_section(first)

    def clear_section_pages(*, clear_core_cache: bool = False) -> None:
        for future, _scale in list(futures.values()):
            future.cancel()
        futures.clear()
        for section in used_sections:
            page = pages.pop(section, None)
            if page is not None:
                stack.removeWidget(page)
                page.deleteLater()
        clear_tiled_quality_cache()
        if clear_core_cache:
            clear_livery_preview_cache()

    def selected_section() -> str | None:
        checked = button_group.checkedButton()
        for section, button in section_buttons.items():
            if button is checked:
                return section
        return None

    def rerender_selected() -> None:
        section = selected_section()
        clear_section_pages()
        if section:
            QTimer.singleShot(0, lambda section_name=section: request_section(section_name))
        else:
            show_page("thumbnail")

    def set_render_mode(mode: str) -> None:
        if mode == render_state["mode"]:
            return
        render_state["mode"] = mode
        self.settings.setValue(RENDER_MODE_KEY, mode)
        self.settings.sync()
        scale_combo.setEnabled(mode != "fast")
        rerender_selected()

    fast_button.clicked.connect(lambda checked=False: set_render_mode("fast") if checked else None)
    quality_button.clicked.connect(lambda checked=False: set_render_mode("quality") if checked else None)

    def scale_changed(_index: int) -> None:
        scale = normalize_scale(scale_combo.currentData())
        if scale == render_state["quality_scale"]:
            return
        render_state["quality_scale"] = scale
        self.settings.setValue(QUALITY_SCALE_KEY, scale)
        self.settings.sync()
        if render_state["mode"] == "quality":
            rerender_selected()

    scale_combo.currentIndexChanged.connect(scale_changed)

    def choose_game_folder() -> None:
        current = configured_fh6_game_folder()
        selected = QFileDialog.getExistingDirectory(
            dialog,
            "FH6 게임 또는 Content 폴더 선택" if _ko() else "Choose FH6 game or Content folder",
            str(current or ""),
        )
        if not selected:
            return
        try:
            set_fh6_game_folder(selected)
        except ExactLiveryPreviewError as exc:
            QMessageBox.warning(dialog, "FH6", str(exc))
            return
        section = selected_section()
        clear_section_pages(clear_core_cache=True)
        if section:
            QTimer.singleShot(0, lambda section_name=section: request_section(section_name))

    game_folder_button.clicked.connect(choose_game_folder)

    bottom = QHBoxLayout()
    bottom.setContentsMargins(2, 0, 2, 0)
    bottom.setSpacing(6)
    bottom.addStretch(1)
    bottom.addWidget(status_label)
    bottom.addStretch(1)

    minus_button = QToolButton()
    minus_button.setText("−")
    minus_button.setToolTip(tr("image.zoom_out"))
    minus_button.setFixedSize(38, 34)
    minus_button.clicked.connect(lambda: current_viewer().zoom_by(0.8) if current_viewer() else None)

    actual_button = QPushButton("100%")
    actual_button.setToolTip(tr("image.actual_size"))
    actual_button.setStyleSheet(_button_style())

    def actual_clicked() -> None:
        viewer = current_viewer()
        if viewer is None:
            return
        view_mode_state["value"] = save_view_mode(self.settings, "actual")
        viewer.actual_size()

    actual_button.clicked.connect(actual_clicked)

    fit_button = QPushButton(tr("image.fit"))
    fit_button.setToolTip(tr("image.fit_tip"))
    fit_button.setStyleSheet(_button_style())

    def fit_clicked() -> None:
        viewer = current_viewer()
        if viewer is None:
            return
        view_mode_state["value"] = save_view_mode(self.settings, "fit")
        viewer.fit_image()

    fit_button.clicked.connect(fit_clicked)

    plus_button = QToolButton()
    plus_button.setText("+")
    plus_button.setToolTip(tr("image.zoom_in"))
    plus_button.setFixedSize(38, 34)
    plus_button.clicked.connect(lambda: current_viewer().zoom_by(1.25) if current_viewer() else None)

    bottom.addWidget(minus_button)
    bottom.addWidget(actual_button)
    bottom.addWidget(fit_button)
    bottom.addWidget(plus_button)
    layout.addLayout(bottom)

    if hasattr(self, "_apply_pointing_cursors"):
        self._apply_pointing_cursors(dialog)

    dialog.exec()
    poll_timer.stop()
    executor.shutdown(wait=False, cancel_futures=True)


def apply_v1_4_preview_final_ui_patch(MainWindow) -> None:
    if getattr(MainWindow, "_fh6_v14_preview_final_ui_applied", False):
        return
    original_init = MainWindow.__init__
    original_show = MainWindow._show_livery_image

    def patched_init(self, project_root) -> None:
        original_init(self, project_root)
        self.setWindowTitle(f"FH6 Assistant {TEST_VERSION_LABEL}")
        self._fh6_v14_final_ui_original_show_livery_image = original_show.__get__(self, type(self))

    MainWindow.__init__ = patched_init
    MainWindow._show_livery_image = _show_livery_image_final
    MainWindow._fh6_v14_preview_final_ui_applied = True
