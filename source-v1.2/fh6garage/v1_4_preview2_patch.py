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

from .exact_livery_preview import (
    ExactLiveryPreviewError,
    configured_fh6_game_folder,
    set_fh6_game_folder,
)
from .i18n import get_language, tr
from .livery_analysis import LIVERY_SECTION_NAMES, LiveryAnalysisError, analyze_livery_file
from .livery_preview import LiveryPreviewError, clear_livery_preview_cache
from .livery_preview_preview2 import (
    DEFAULT_QUALITY,
    clear_preview2_memory_cache,
    normalize_quality,
    render_livery_section_preview2,
)
from .models import LiveryRecord
from .ui import APP_STYLE, ZoomableImageView


PREVIEW2_VERSION_LABEL = "v1.4 Preview 2"
QUALITY_SETTING_KEY = "livery_preview_quality_preview2"

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


def _text(key: str, **values) -> str:
    ko = {
        "thumbnail": "썸네일",
        "loading": "{section} 영역을 {quality} 품질로 재구성하는 중입니다...",
        "failed": "{section} 미리보기 생성 실패\n\n{error}",
        "no_thumbnail": "저장된 썸네일이 없습니다.",
        "status_thumbnail": "저장된 bigThumb.webp 썸네일",
        "status_section": "{section} · {count:,}개 배치 · {quality}",
        "note": "영역별 이미지는 실제 FH6 차량 projection mask를 사용하는 2D 재구성입니다. 고해상도 모드는 supersampling 후 정확한 2048×1024 projection 좌표계로 축소합니다.",
        "warning": "native 리소스가 없으면 대체 도형을 쓰지 않고 실패 처리합니다. 한 번 완성된 면은 디스크 캐시에서 재사용합니다.",
        "controls": "마우스 휠: 확대/축소 · 드래그: 이동 · 더블클릭: 100%",
        "game_folder": "FH6 설치 폴더 지정",
        "game_folder_title": "FH6 게임 또는 Content 폴더 선택",
        "game_folder_set": "FH6 설치 폴더: {path}",
        "game_folder_auto": "면 재구성을 처음 요청할 때 FH6 설치 폴더를 확인합니다.",
        "game_folder_error": "FH6 설치 폴더를 사용할 수 없습니다.\n\n{error}",
        "quality": "렌더 품질",
        "quality_fast": "빠름",
        "quality_balanced": "균형",
        "quality_high": "고품질",
        "quality_tip": "빠름=1×, 균형=1.5×, 고품질=2× supersampling. 품질별 결과는 별도로 캐시됩니다.",
    }
    en = {
        "thumbnail": "Thumbnail",
        "loading": "Reconstructing {section} at {quality} quality...",
        "failed": "Could not render {section}\n\n{error}",
        "no_thumbnail": "No saved thumbnail is available.",
        "status_thumbnail": "Saved bigThumb.webp thumbnail",
        "status_section": "{section} · {count:,} placements · {quality}",
        "note": "Section images use the exact local FH6 vehicle projection mask. Higher modes supersample before returning to the exact 2048×1024 projection coordinate system.",
        "warning": "Missing native assets fail closed instead of using substitute geometry. Completed sections are reused from a persistent disk cache.",
        "controls": "Mouse wheel: zoom · Drag: pan · Double-click: 100%",
        "game_folder": "Set FH6 game folder",
        "game_folder_title": "Choose the FH6 game or Content folder",
        "game_folder_set": "FH6 game folder: {path}",
        "game_folder_auto": "The FH6 install is resolved only when a section render is first requested.",
        "game_folder_error": "The FH6 game folder cannot be used.\n\n{error}",
        "quality": "Render quality",
        "quality_fast": "Fast",
        "quality_balanced": "Balanced",
        "quality_high": "High quality",
        "quality_tip": "Fast=1×, Balanced=1.5×, High=2× supersampling. Each quality level has its own cache.",
    }
    return (ko if _ko() else en)[key].format(**values)


def _quality_label(quality: str) -> str:
    quality = normalize_quality(quality)
    return _text(
        {
            "fast": "quality_fast",
            "balanced": "quality_balanced",
            "high": "quality_high",
        }[quality]
    )


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


def _show_livery_image_preview2(self: Any, record: Any) -> None:
    # Keep thumbnail-only use light: exact FH6 install discovery and vehicle archive
    # indexing are deferred until a section button is actually pressed.
    if not isinstance(record, LiveryRecord) or not record.livery_path:
        return self._fh6_v14_preview2_original_show_livery_image(record)

    try:
        analysis = analyze_livery_file(record.livery_path)
    except LiveryAnalysisError:
        return self._fh6_v14_preview2_original_show_livery_image(record)

    thumbnail_image = QImage()
    if record.thumbnail_path and record.thumbnail_path.is_file():
        try:
            thumbnail_image = QImage.fromData(record.thumbnail_path.read_bytes())
        except OSError:
            thumbnail_image = QImage()

    used_sections = [
        section
        for section in LIVERY_SECTION_NAMES
        if int(analysis.section_counts.get(section, 0)) > 0
    ]
    if thumbnail_image.isNull() and not used_sections:
        return self._fh6_v14_preview2_original_show_livery_image(record)

    dialog = QDialog(self)
    livery_name = record.header.name or "(unnamed)"
    car_name = self._car_label(record.header.car_id)
    dialog.setWindowTitle(f"{livery_name} — {car_name} — Preview 2")
    dialog.setModal(True)
    dialog.resize(1480, 980)
    dialog.setMinimumSize(900, 620)
    dialog.setStyleSheet(APP_STYLE)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 12, 12, 10)
    layout.setSpacing(8)

    tab_scroll = QScrollArea()
    tab_scroll.setWidgetResizable(True)
    tab_scroll.setFrameShape(QFrame.Shape.NoFrame)
    tab_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tab_scroll.setFixedHeight(52)
    tab_host = QWidget()
    tab_row = QHBoxLayout(tab_host)
    tab_row.setContentsMargins(0, 0, 0, 4)
    tab_row.setSpacing(6)
    tab_scroll.setWidget(tab_host)
    layout.addWidget(tab_scroll)

    stack = QStackedWidget()
    layout.addWidget(stack, 1)

    status_label = QLabel()
    status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status_label.setObjectName("muted")
    status_label.setStyleSheet("color:#737787;font-size:9pt;")

    warning_label = QLabel(_text("note") + " " + _text("warning"))
    warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    warning_label.setWordWrap(True)
    warning_label.setStyleSheet("color:#777b88;font-size:8.8pt;")

    saved_quality = normalize_quality(
        self.settings.value(QUALITY_SETTING_KEY, DEFAULT_QUALITY, str)
    )
    quality_state = {"value": saved_quality}
    pages: dict[str, QWidget] = {}
    futures: dict[str, tuple[concurrent.futures.Future, str]] = {}
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="fh6-livery-preview2",
    )
    button_group = QButtonGroup(dialog)
    button_group.setExclusive(True)
    section_buttons: dict[str, QPushButton] = {}

    def current_viewer() -> ZoomableImageView | None:
        current = stack.currentWidget()
        return current if isinstance(current, ZoomableImageView) else None

    def show_page(key: str) -> None:
        page = pages.get(key)
        if page is not None:
            stack.setCurrentWidget(page)
        if key == "thumbnail":
            status_label.setText(_text("status_thumbnail"))
        elif key in analysis.section_counts:
            status_label.setText(
                _text(
                    "status_section",
                    section=_section_label(key),
                    count=int(analysis.section_counts.get(key, 0)),
                    quality=_quality_label(quality_state["value"]),
                )
            )

    if not thumbnail_image.isNull():
        thumbnail_viewer = ZoomableImageView(QPixmap.fromImage(thumbnail_image))
        pages["thumbnail"] = thumbnail_viewer
        stack.addWidget(thumbnail_viewer)
        thumbnail_button = QPushButton(_text("thumbnail"))
        thumbnail_button.setObjectName("secondary")
        thumbnail_button.setCheckable(True)
        thumbnail_button.clicked.connect(lambda checked=False: show_page("thumbnail"))
        button_group.addButton(thumbnail_button)
        tab_row.addWidget(thumbnail_button)
        thumbnail_button.setChecked(True)
        status_label.setText(_text("status_thumbnail"))
    else:
        missing = _placeholder(_text("no_thumbnail"))
        pages["thumbnail"] = missing
        stack.addWidget(missing)

    def request_section(section: str) -> None:
        existing = pages.get(section)
        if existing is not None:
            show_page(section)
            return

        quality = quality_state["value"]
        waiting = _placeholder(
            _text(
                "loading",
                section=_section_label(section),
                quality=_quality_label(quality),
            )
        )
        pages[section] = waiting
        stack.addWidget(waiting)
        stack.setCurrentWidget(waiting)
        status_label.setText(
            _text(
                "status_section",
                section=_section_label(section),
                count=int(analysis.section_counts.get(section, 0)),
                quality=_quality_label(quality),
            )
        )
        future = executor.submit(
            render_livery_section_preview2,
            record.livery_path,
            section,
            quality,
        )
        futures[section] = (future, quality)

    for section in used_sections:
        button = QPushButton(
            f"{_section_label(section)}  {int(analysis.section_counts.get(section, 0)):,}"
        )
        button.setObjectName("secondary")
        button.setCheckable(True)
        button.clicked.connect(
            lambda checked=False, section_name=section: request_section(section_name)
        )
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
            if index < 0:
                stack.addWidget(new_page)
            else:
                stack.insertWidget(index, new_page)
        else:
            stack.addWidget(new_page)
        pages[section] = new_page
        if was_current:
            stack.setCurrentWidget(new_page)

    def poll_futures() -> None:
        for section, payload in list(futures.items()):
            future, requested_quality = payload
            if not future.done():
                continue
            futures.pop(section, None)
            # Ignore stale work completed after the quality selection changed.
            if requested_quality != quality_state["value"]:
                continue
            try:
                result = future.result()
                image = QImage.fromData(result.png_bytes)
                if image.isNull():
                    raise LiveryPreviewError("렌더링 결과 PNG를 읽지 못했습니다.")
                viewer = ZoomableImageView(QPixmap.fromImage(image))
                replace_page(section, viewer)
                if stack.currentWidget() is viewer:
                    status_label.setText(
                        _text(
                            "status_section",
                            section=_section_label(section),
                            count=result.placement_count,
                            quality=_quality_label(requested_quality),
                        )
                    )
                    QTimer.singleShot(0, viewer.fit_image)
            except Exception as exc:
                failed = _placeholder(
                    _text(
                        "failed",
                        section=_section_label(section),
                        error=str(exc),
                    ),
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

    controls = QHBoxLayout()
    controls.setContentsMargins(0, 0, 0, 0)
    controls.setSpacing(6)

    quality_label = QLabel(_text("quality"))
    controls.addWidget(quality_label)
    quality_combo = QComboBox()
    quality_combo.setToolTip(_text("quality_tip"))
    quality_combo.addItem(_text("quality_fast"), "fast")
    quality_combo.addItem(_text("quality_balanced"), "balanced")
    quality_combo.addItem(_text("quality_high"), "high")
    selected_index = max(0, quality_combo.findData(saved_quality))
    quality_combo.setCurrentIndex(selected_index)
    controls.addWidget(quality_combo)

    def clear_section_pages(*, clear_core_cache: bool = False) -> None:
        for future, _quality in list(futures.values()):
            future.cancel()
        futures.clear()
        for section in used_sections:
            page = pages.pop(section, None)
            if page is not None:
                stack.removeWidget(page)
                page.deleteLater()
        clear_preview2_memory_cache()
        if clear_core_cache:
            clear_livery_preview_cache()

    def selected_section() -> str | None:
        checked = button_group.checkedButton()
        for section, button in section_buttons.items():
            if button is checked:
                return section
        return None

    def quality_changed(_index: int) -> None:
        new_quality = normalize_quality(quality_combo.currentData())
        if new_quality == quality_state["value"]:
            return
        quality_state["value"] = new_quality
        self.settings.setValue(QUALITY_SETTING_KEY, new_quality)
        self.settings.sync()
        section = selected_section()
        clear_section_pages()
        if section:
            QTimer.singleShot(0, lambda section_name=section: request_section(section_name))
        else:
            show_page("thumbnail")

    quality_combo.currentIndexChanged.connect(quality_changed)

    game_folder_button = QPushButton(_text("game_folder"))
    game_folder_button.setObjectName("secondary")

    def choose_game_folder() -> None:
        current = configured_fh6_game_folder()
        selected = QFileDialog.getExistingDirectory(
            dialog,
            _text("game_folder_title"),
            str(current or ""),
        )
        if not selected:
            return
        try:
            normalized = set_fh6_game_folder(selected)
        except ExactLiveryPreviewError as exc:
            QMessageBox.warning(
                dialog,
                _text("game_folder"),
                _text("game_folder_error", error=str(exc)),
            )
            return
        section = selected_section()
        clear_section_pages(clear_core_cache=True)
        game_folder_status.setText(_text("game_folder_set", path=str(normalized)))
        if section:
            QTimer.singleShot(0, lambda section_name=section: request_section(section_name))

    game_folder_button.clicked.connect(choose_game_folder)
    controls.addWidget(game_folder_button)

    detected_game_folder = configured_fh6_game_folder()
    game_folder_status = QLabel(
        _text("game_folder_set", path=str(detected_game_folder))
        if detected_game_folder
        else _text("game_folder_auto")
    )
    game_folder_status.setObjectName("muted")
    game_folder_status.setStyleSheet("color:#737787;font-size:8.6pt;")
    controls.addWidget(game_folder_status)
    controls.addStretch(1)

    minus_button = QToolButton()
    minus_button.setText("−")
    minus_button.setToolTip(tr("image.zoom_out"))
    minus_button.setAccessibleName(tr("image.zoom_out_accessible"))
    minus_button.setFixedSize(38, 34)
    minus_button.clicked.connect(
        lambda: current_viewer().zoom_by(0.8) if current_viewer() else None
    )

    actual_button = QPushButton("100%")
    actual_button.setObjectName("secondary")
    actual_button.setToolTip(tr("image.actual_size"))
    actual_button.clicked.connect(
        lambda: current_viewer().actual_size() if current_viewer() else None
    )

    fit_button = QPushButton(tr("image.fit"))
    fit_button.setObjectName("secondary")
    fit_button.setToolTip(tr("image.fit_tip"))
    fit_button.clicked.connect(
        lambda: current_viewer().fit_image() if current_viewer() else None
    )

    plus_button = QToolButton()
    plus_button.setText("+")
    plus_button.setToolTip(tr("image.zoom_in"))
    plus_button.setAccessibleName(tr("image.zoom_in_accessible"))
    plus_button.setFixedSize(38, 34)
    plus_button.clicked.connect(
        lambda: current_viewer().zoom_by(1.25) if current_viewer() else None
    )

    controls.addWidget(minus_button)
    controls.addWidget(actual_button)
    controls.addWidget(fit_button)
    controls.addWidget(plus_button)
    layout.addLayout(controls)
    layout.addWidget(status_label)
    layout.addWidget(warning_label)

    help_label = QLabel(_text("controls"))
    help_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    help_label.setStyleSheet("color:#8a8e9d;font-size:8.5pt;")
    layout.addWidget(help_label)

    if hasattr(self, "_apply_pointing_cursors"):
        self._apply_pointing_cursors(dialog)

    QTimer.singleShot(
        0,
        lambda: current_viewer().fit_image() if current_viewer() else None,
    )
    dialog.exec()
    poll_timer.stop()
    executor.shutdown(wait=False, cancel_futures=True)


def apply_v1_4_preview2_patch(MainWindow) -> None:
    if getattr(MainWindow, "_fh6_v14_preview2_patched", False):
        return

    original_init = MainWindow.__init__
    original_show_livery_image = MainWindow._show_livery_image

    def patched_init(self, project_root) -> None:
        original_init(self, project_root)
        self.setWindowTitle(f"FH6 Assistant {PREVIEW2_VERSION_LABEL}")
        for label in self.findChildren(QLabel):
            text = label.text()
            if text.startswith("v1.4\n") or text.startswith("v1.3.1\n"):
                suffix = text.split("\n", 1)[1] if "\n" in text else "LIVERY & TUNING"
                label.setText(f"{PREVIEW2_VERSION_LABEL}\n{suffix}")
                break
        self._fh6_v14_preview2_original_show_livery_image = original_show_livery_image.__get__(self, type(self))

    MainWindow.__init__ = patched_init
    MainWindow._show_livery_image = _show_livery_image_preview2
    MainWindow._fh6_v14_preview2_patched = True
