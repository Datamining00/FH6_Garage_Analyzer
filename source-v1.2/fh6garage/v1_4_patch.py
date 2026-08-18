from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .i18n import get_language, tr
from .livery_analysis import (
    LIVERY_SECTION_NAMES,
    LiveryAnalysisError,
    analyze_livery_file,
)
from .ui import APP_STYLE


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
        "unavailable": "내부 분석 불가",
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
        "unavailable": "Internal analysis unavailable",
        "missing": "C_livery is missing, so internal information cannot be analyzed.",
        "failed": "C_livery analysis failed: {error}",
        "mismatch": "Note: header decal count ({header:,}) differs from the C_livery section total ({internal:,}).",
        "readonly": "Read-only analysis · the original C_livery is not modified.",
    }
    template = (ko if _ko() else en)[key]
    return template.format(**values)


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
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setShowGrid(False)
    table.setMinimumHeight(278)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(0, table.horizontalHeader().ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(1, table.horizontalHeader().ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(2, table.horizontalHeader().ResizeMode.ResizeToContents)

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


def apply_v1_4_patches(MainWindow) -> None:
    """Apply v1.4 stage-1 read-only C_livery analysis UI."""
    if getattr(MainWindow, "_fh6_v14_patched", False):
        return

    original_init = MainWindow.__init__

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
    MainWindow._fh6_v14_patched = True
