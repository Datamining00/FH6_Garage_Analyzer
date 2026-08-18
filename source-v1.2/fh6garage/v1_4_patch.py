from __future__ import annotations

import concurrent.futures
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import get_language, tr
from .livery_analysis import (
    LIVERY_SECTION_NAMES,
    LiveryAnalysisError,
    analyze_livery_file,
)
from .livery_preview import LiveryPreviewError, render_livery_section
from .models import LiveryRecord
from .ui import APP_STYLE, ZoomableImageView


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

_ORIGINAL_SHOW_LIVERY_IMAGE = None


def _ko() -> bool:
    return str(get_language() or "").lower().startswith("ko")


def _section_label(name: str) -> str:
    return _SECTION_LABELS_KO.get(name, name) if _ko() else name


def _analysis_text(key: str, **values) -> str:
    ko = {
        "section_title": "리버리 내부 정보",
        "total": "총 배치 수: {count:,}",
        "used": "사용 영역: {used} / {total}",
        "header_count": "헤더 기록 데칼 수: {count:,}",
        "area": "영역",
        "placements": "배치 수",
        "empty": "사용 안 함",
        "used_state": "사용",
        "state": "상태",
        "missing": "C_livery 파일이 없어 내부 정보를 분석할 수 없습니다.",
        "failed": "C_livery 분석 실패: {error}",
        "mismatch": "참고: 헤더의 데칼 수({header:,})와 C_livery 영역 합계({internal:,})가 다릅니다.",
        "readonly": "읽기 전용 분석 · 원본 C_livery는 변경하지 않습니다.",
    }
    en = {
        "section_title": "Internal livery information",
        "total": "Total placements: {count:,}",
        "used": "Used sections: {used} / {total}",
        "header_count": "Header decal count: {count:,}",
        "area": "Section",
        "placements": "Placements",
        "empty": "Unused",
        "used_state": "Used",
        "state": "State",
        "missing": "C_livery is missing, so internal information cannot be analyzed.",
        "failed": "C_livery analysis failed: {error}",
        "mismatch": "Note: header decal count ({header:,}) differs from the C_livery section total ({internal:,}).",
        "readonly": "Read-only analysis · the original C_livery is not modified.",
    }
    template = (ko if _ko() else en)[key]
    return template.format(**values)


def _preview_text(key: str, **values) -> str:
    ko = {
        "thumbnail": "썸네일",
        "loading": "{section} 영역을 재구성하는 중입니다...",
        "failed": "{section} 미리보기 생성 실패\n\n{error}",
        "no_thumbnail": "저장된 썸네일이 없습니다.",
        "status_thumbnail": "저장된 bigThumb.webp 썸네일",
        "status_section": "{section} · {count:,}개 배치",
        "status_raster": " · 내장 래스터 로고 {count:,}개 생략",
        "note": "영역별 이미지는 C_livery의 placement를 2D 평면에 재구성한 결과이며 차량의 3D 표면 렌더링은 아닙니다.",
        "warning": "일부 요소가 완전히 재구성되지 않았을 수 있습니다.",
        "controls": "마우스 휠: 확대/축소 · 드래그: 이동 · 더블클릭: 100%",
    }
    en = {
        "thumbnail": "Thumbnail",
        "loading": "Reconstructing the {section} section...",
        "failed": "Could not render {section}\n\n{error}",
        "no_thumbnail": "No saved thumbnail is available.",
        "status_thumbnail": "Saved bigThumb.webp thumbnail",
        "status_section": "{section} · {count:,} placements",
        "status_raster": " · {count:,} built-in raster logos omitted",
        "note": "Section images reconstruct C_livery placements on a 2D plane; they are not a 3D vehicle-surface render.",
        "warning": "Some elements may not be fully reconstructed.",
        "controls": "Mouse wheel: zoom · Drag: pan · Double-click: 100%",
    }
    return (ko if _ko() else en)[key].format(**values)


def _build_analysis_panel(record: Any) -> QFrame:
    panel = QFrame()
    panel.setObjectName("panel")
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(12, 10, 12, 10)
    panel_layout.setSpacing(7)

    heading = QLabel(_analysis_text("section_title"))
    heading.setStyleSheet("font-size:10.5pt;font-weight:700;")
    panel_layout.addWidget(heading)

    source = getattr(record, "livery_path", None)
    if source is None:
        message = QLabel(_analysis_text("missing"))
        message.setWordWrap(True)
        message.setObjectName("muted")
        panel_layout.addWidget(message)
        return panel

    try:
        analysis = analyze_livery_file(source)
    except LiveryAnalysisError as exc:
        message = QLabel(_analysis_text("failed", error=str(exc)))
        message.setWordWrap(True)
        message.setStyleSheet("color:#a33a45;")
        panel_layout.addWidget(message)
        return panel

    summary = QGridLayout()
    summary.setContentsMargins(0, 0, 0, 0)
    summary.setHorizontalSpacing(22)
    summary.setVerticalSpacing(3)
    total_label = QLabel(_analysis_text("total", count=analysis.total_placements))
    total_label.setStyleSheet("font-weight:700;")
    used_label = QLabel(
        _analysis_text(
            "used",
            used=analysis.populated_sections,
            total=len(LIVERY_SECTION_NAMES),
        )
    )
    used_label.setStyleSheet("font-weight:700;")
    summary.addWidget(total_label, 0, 0)
    summary.addWidget(used_label, 0, 1)

    header_count = getattr(getattr(record, "header", None), "decal_count", None)
    if isinstance(header_count, int):
        header_label = QLabel(_analysis_text("header_count", count=header_count))
        header_label.setObjectName("muted")
        summary.addWidget(header_label, 1, 0, 1, 2)
    panel_layout.addLayout(summary)

    table = QTableWidget(len(LIVERY_SECTION_NAMES), 3)
    table.setHorizontalHeaderLabels(
        (
            _analysis_text("area"),
            _analysis_text("placements"),
            _analysis_text("state"),
        )
    )
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setShowGrid(False)
    table.setMinimumHeight(278)
    header = table.horizontalHeader()
    header.setStretchLastSection(True)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

    for row, section in enumerate(LIVERY_SECTION_NAMES):
        count = int(analysis.section_counts.get(section, 0))
        values = (
            _section_label(section),
            f"{count:,}",
            _analysis_text("used_state") if count else _analysis_text("empty"),
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(
                (Qt.AlignmentFlag.AlignRight if column == 1 else Qt.AlignmentFlag.AlignLeft)
                | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, column, item)
        table.setRowHeight(row, 22)

    panel_layout.addWidget(table)

    if isinstance(header_count, int) and header_count != analysis.total_placements:
        mismatch = QLabel(
            _analysis_text(
                "mismatch",
                header=header_count,
                internal=analysis.total_placements,
            )
        )
        mismatch.setWordWrap(True)
        mismatch.setStyleSheet("color:#8a5b16;")
        panel_layout.addWidget(mismatch)

    readonly = QLabel(_analysis_text("readonly"))
    readonly.setObjectName("muted")
    readonly.setStyleSheet("color:#737787;font-size:9pt;")
    panel_layout.addWidget(readonly)
    return panel


def _show_livery_metadata(self: Any, record: Any) -> None:
    dialog = QDialog(self)
    dialog.setWindowTitle(tr("detail.livery_info_title"))
    dialog.setModal(True)
    dialog.resize(660, 760)
    dialog.setMinimumSize(580, 650)
    dialog.setStyleSheet(APP_STYLE)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)

    vehicle = QLabel(self._car_label(record.header.car_id))
    vehicle.setStyleSheet("font-size:13pt;font-weight:700;")
    layout.addWidget(vehicle)

    title = QLabel(
        tr(
            "detail.livery_prefix",
            name=record.header.name or tr("detail.no_title"),
        )
    )
    title.setObjectName("muted")
    layout.addWidget(title)

    layout.addWidget(QLabel(tr("detail.description")))
    description = QPlainTextEdit()
    description.setReadOnly(True)
    description.setMaximumHeight(150)
    description.setPlainText(
        (record.header.description or "").strip()
        or tr("detail.no_description")
    )
    layout.addWidget(description)

    uploaded = record.header.created or tr("common.unavailable")
    layout.addWidget(QLabel(tr("detail.uploaded", date=uploaded)))
    layout.addWidget(_build_analysis_panel(record), 1)

    close_button = QPushButton(tr("common.close"))
    close_button.setObjectName("primary")
    close_button.clicked.connect(dialog.accept)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(close_button)
    layout.addLayout(row)

    if hasattr(self, "_apply_pointing_cursors"):
        self._apply_pointing_cursors(dialog)
    dialog.exec()


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


def _show_livery_image(self: Any, record: Any) -> None:
    global _ORIGINAL_SHOW_LIVERY_IMAGE

    if not isinstance(record, LiveryRecord) or not record.livery_path:
        if _ORIGINAL_SHOW_LIVERY_IMAGE is not None:
            return _ORIGINAL_SHOW_LIVERY_IMAGE(self, record)
        return None

    try:
        analysis = analyze_livery_file(record.livery_path)
    except LiveryAnalysisError:
        if _ORIGINAL_SHOW_LIVERY_IMAGE is not None:
            return _ORIGINAL_SHOW_LIVERY_IMAGE(self, record)
        return None

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
        if _ORIGINAL_SHOW_LIVERY_IMAGE is not None:
            return _ORIGINAL_SHOW_LIVERY_IMAGE(self, record)
        return None

    dialog = QDialog(self)
    livery_name = record.header.name or "(unnamed)"
    car_name = self._car_label(record.header.car_id)
    dialog.setWindowTitle(f"{livery_name} — {car_name}")
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

    warning_label = QLabel(_preview_text("note"))
    warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    warning_label.setWordWrap(True)
    warning_label.setStyleSheet("color:#777b88;font-size:8.8pt;")

    pages: dict[str, QWidget] = {}
    futures: dict[str, concurrent.futures.Future] = {}
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="fh6-livery-preview",
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
            status_label.setText(_preview_text("status_thumbnail"))
        elif key in analysis.section_counts:
            status_label.setText(
                _preview_text(
                    "status_section",
                    section=_section_label(key),
                    count=int(analysis.section_counts.get(key, 0)),
                )
            )

    if not thumbnail_image.isNull():
        thumbnail_viewer = ZoomableImageView(QPixmap.fromImage(thumbnail_image))
        pages["thumbnail"] = thumbnail_viewer
        stack.addWidget(thumbnail_viewer)
        thumbnail_button = QPushButton(_preview_text("thumbnail"))
        thumbnail_button.setObjectName("secondary")
        thumbnail_button.setCheckable(True)
        thumbnail_button.clicked.connect(lambda checked=False: show_page("thumbnail"))
        button_group.addButton(thumbnail_button)
        tab_row.addWidget(thumbnail_button)
        thumbnail_button.setChecked(True)
        status_label.setText(_preview_text("status_thumbnail"))
    else:
        missing = _placeholder(_preview_text("no_thumbnail"))
        pages["thumbnail"] = missing
        stack.addWidget(missing)

    def request_section(section: str) -> None:
        existing = pages.get(section)
        if existing is not None:
            show_page(section)
            return

        waiting = _placeholder(
            _preview_text("loading", section=_section_label(section))
        )
        pages[section] = waiting
        stack.addWidget(waiting)
        stack.setCurrentWidget(waiting)
        status_label.setText(
            _preview_text(
                "status_section",
                section=_section_label(section),
                count=int(analysis.section_counts.get(section, 0)),
            )
        )
        future = executor.submit(render_livery_section, record.livery_path, section)
        futures[section] = future

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
        for section, future in list(futures.items()):
            if not future.done():
                continue
            futures.pop(section, None)
            try:
                result = future.result()
                image = QImage.fromData(result.png_bytes)
                if image.isNull():
                    raise LiveryPreviewError("렌더링 결과 PNG를 읽지 못했습니다.")
                viewer = ZoomableImageView(QPixmap.fromImage(image))
                replace_page(section, viewer)
                if stack.currentWidget() is viewer:
                    status = _preview_text(
                        "status_section",
                        section=_section_label(section),
                        count=result.placement_count,
                    )
                    if result.skipped_raster_logos:
                        status += _preview_text(
                            "status_raster",
                            count=result.skipped_raster_logos,
                        )
                    status_label.setText(status)
                    QTimer.singleShot(0, viewer.fit_image)
                if result.skipped_raster_logos:
                    warning_label.setText(
                        _preview_text("note") + " " + _preview_text("warning")
                    )
            except Exception as exc:
                failed = _placeholder(
                    _preview_text(
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
    controls.addStretch(1)
    layout.addLayout(controls)
    layout.addWidget(status_label)
    layout.addWidget(warning_label)

    help_label = QLabel(_preview_text("controls"))
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


def apply_v1_4_patches(MainWindow) -> None:
    """Apply v1.4 read-only C_livery analysis and section-preview UI."""
    global _ORIGINAL_SHOW_LIVERY_IMAGE

    if getattr(MainWindow, "_fh6_v14_patched", False):
        return

    original_init = MainWindow.__init__
    _ORIGINAL_SHOW_LIVERY_IMAGE = MainWindow._show_livery_image

    def patched_init(self, project_root) -> None:
        original_init(self, project_root)
        self.setWindowTitle("FH6 Assistant v1.4")
        for label in self.findChildren(QLabel):
            if label.text().startswith("v1.3.1\n") or label.text().startswith("v1.3\n"):
                suffix = label.text().split("\n", 1)[1] if "\n" in label.text() else "LIVERY & TUNING"
                label.setText(f"v1.4\n{suffix}")
                break

    MainWindow.__init__ = patched_init
    MainWindow._show_livery_metadata = _show_livery_metadata
    MainWindow._show_livery_image = _show_livery_image
    MainWindow._fh6_v14_patched = True
