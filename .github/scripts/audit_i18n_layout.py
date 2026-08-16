from __future__ import annotations

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2] / "source-v1.2"
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QToolButton,
    QWidget,
)

from fh6garage.i18n import set_language
from fh6garage.ui import MainWindow


OUT = Path(os.environ.get("RUNNER_TEMP", ".")) / "fh6-i18n-layout"
OUT.mkdir(parents=True, exist_ok=True)


def widget_path(widget: QWidget) -> str:
    parts: list[str] = []
    current: QWidget | None = widget
    while current is not None:
        name = current.objectName().strip()
        label = current.__class__.__name__
        if name:
            label += f"#{name}"
        parts.append(label)
        current = current.parentWidget()
    return "/".join(reversed(parts))


def visible_text(widget: QWidget) -> str:
    if isinstance(widget, QAbstractButton):
        return widget.text().replace("&", "")
    if isinstance(widget, QLabel):
        return widget.text()
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, QLineEdit):
        return widget.text() or widget.placeholderText()
    return ""


def audit_widget_width(widget: QWidget, issues: list[str]) -> None:
    if not widget.isVisible() or widget.width() <= 0:
        return
    text = visible_text(widget).strip()
    if not text or "\n" in text:
        return
    if isinstance(widget, QLabel) and widget.wordWrap():
        return
    if isinstance(widget, (QPlainTextEdit, QTableWidget)):
        return

    hint = widget.sizeHint().width()
    tolerance = 8
    if hint > widget.width() + tolerance:
        issues.append(
            f"TEXT_WIDTH {widget_path(widget)} width={widget.width()} sizeHint={hint} text={text!r}"
        )


def audit_parent_bounds(window: QMainWindow, issues: list[str]) -> None:
    for widget in window.findChildren(QWidget):
        if not widget.isVisible() or widget.isWindow():
            continue
        parent = widget.parentWidget()
        if parent is None or not parent.isVisible():
            continue
        if parent.inherits("QAbstractScrollArea") or widget.inherits("QScrollBar"):
            continue
        top_left = widget.mapTo(parent, QPoint(0, 0))
        rect = widget.rect().translated(top_left)
        parent_rect = parent.rect()
        if rect.right() > parent_rect.right() + 2 or rect.bottom() > parent_rect.bottom() + 2:
            if widget.inherits("QMenu") or parent.inherits("QComboBoxPrivateContainer"):
                continue
            issues.append(
                f"OUT_OF_BOUNDS {widget_path(widget)} child={rect.getRect()} parent={parent_rect.getRect()}"
            )


def audit_table_headers(window: QMainWindow, issues: list[str]) -> None:
    for table in window.findChildren(QTableWidget):
        if not table.isVisible():
            continue
        header = table.horizontalHeader()
        if not header.isVisible():
            continue
        model = table.model()
        for col in range(table.columnCount()):
            text = str(model.headerData(col, Qt.Orientation.Horizontal) or "")
            if not text:
                continue
            needed = header.fontMetrics().horizontalAdvance(text) + 22
            actual = header.sectionSize(col)
            if needed > actual + 6:
                issues.append(
                    f"HEADER_WIDTH {widget_path(table)} col={col} width={actual} needed={needed} text={text!r}"
                )


def audit_state(window: MainWindow, language: str, size: QSize, page: int) -> list[str]:
    issues: list[str] = []
    window.resize(size)
    window.pages.setCurrentIndex(page)
    window.show()
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()

    if window.width() > size.width() + 2 or window.height() > size.height() + 2:
        issues.append(
            f"WINDOW_EXPANDED requested={size.width()}x{size.height()} actual={window.width()}x{window.height()}"
        )

    min_hint = window.minimumSizeHint()
    if min_hint.width() > 960 or min_hint.height() > 680:
        issues.append(
            f"MIN_HINT {min_hint.width()}x{min_hint.height()} exceeds declared 960x680"
        )

    audited_types = (QPushButton, QToolButton, QCheckBox, QComboBox, QLabel, QLineEdit)
    for widget in window.findChildren(QWidget):
        if isinstance(widget, audited_types):
            audit_widget_width(widget, issues)
    audit_table_headers(window, issues)
    audit_parent_bounds(window, issues)

    page_name = ("dashboard", "livery", "tuning")[page]
    shot = OUT / f"{language}_{size.width()}x{size.height()}_{page_name}.png"
    window.grab().save(str(shot), "PNG")
    return issues


def main() -> int:
    app = QApplication([])
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("FH6 Assistant Layout Audit")
    app.setOrganizationName("FH6AssistantCI")

    all_issues: list[str] = []
    for language in ("ko", "en"):
        set_language(language)
        window = MainWindow(project_root=ROOT)
        try:
            for size in (QSize(960, 680), QSize(1460, 900)):
                for page in range(3):
                    issues = audit_state(window, language, size, page)
                    prefix = f"[{language} {size.width()}x{size.height()} page={page}]"
                    for issue in issues:
                        all_issues.append(f"{prefix} {issue}")
        finally:
            window.close()
            app.processEvents()

    report = OUT / "layout-audit.txt"
    report.write_text("\n".join(all_issues) + ("\n" if all_issues else "PASS\n"), encoding="utf-8")

    print(f"Layout screenshots: {OUT}")
    if all_issues:
        print(f"Detected {len(all_issues)} possible layout issue(s):")
        for issue in all_issues:
            print(issue)
        return 1

    print("PASS: no clipping/overflow candidates detected at 960x680 and 1460x900 in ko/en.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
