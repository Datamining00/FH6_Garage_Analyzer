from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QFileDialog, QFrame, QMessageBox, QPushButton

from .diagnostic_export import export_diagnostics
from .i18n import get_language
from .subsystem_log import log_event


def _txt(ko: str, en: str) -> str:
    return ko if (get_language() or "ko").lower().startswith("ko") else en


def apply_v1_4_diagnostic_export_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v14_diagnostic_export_patched", False):
        return

    original_build_ui = MainWindow._build_ui

    def patched_build_ui(self: Any) -> None:
        original_build_ui(self)
        sidebar = self.findChild(QFrame, "sidebar")
        if sidebar is None or sidebar.layout() is None:
            return
        button = QPushButton(_txt("진단 내보내기", "Export diagnostics"), sidebar)
        button.setObjectName("fh6DiagnosticExportButton")
        button.setStyleSheet(
            "QPushButton { color:#c7c9d4; background:#242632; border:1px solid #343746; "
            "border-radius:7px; padding:7px 8px; text-align:left; }"
            "QPushButton:hover { color:white; border-color:#6e4bf2; }"
        )
        button.clicked.connect(self._fh6_export_diagnostics)
        self.diagnostic_export_button = button

        layout = sidebar.layout()
        anchor = getattr(self, "always_on_top_box", None)
        index = layout.indexOf(anchor) if anchor is not None else -1
        if index >= 0:
            layout.insertWidget(index, button)
        else:
            layout.addWidget(button)

    def export_from_ui(self: Any) -> None:
        default_name = f"FH6_Assistant_Diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        default_path = str(Path.home() / default_name)
        selected, _ = QFileDialog.getSaveFileName(
            self,
            _txt("진단 파일 저장", "Save diagnostic package"),
            default_path,
            _txt("ZIP 파일 (*.zip)", "ZIP files (*.zip)"),
        )
        if not selected:
            return
        try:
            path = export_diagnostics(self, Path(selected))
        except Exception as exc:
            log_event("PERFORMANCE", "diagnostic.export_failed", error=type(exc).__name__)
            QMessageBox.warning(
                self,
                _txt("진단 내보내기 실패", "Diagnostic export failed"),
                _txt("진단 파일을 생성하지 못했습니다.", "Could not create the diagnostic package."),
            )
            return

        log_event("PERFORMANCE", "diagnostic.export_complete")
        QMessageBox.information(
            self,
            _txt("진단 내보내기 완료", "Diagnostic export complete"),
            _txt(f"진단 파일을 저장했습니다.\n{path}", f"Diagnostic package saved.\n{path}"),
        )

    MainWindow._build_ui = patched_build_ui
    MainWindow._fh6_export_diagnostics = export_from_ui
    MainWindow._fh6_v14_diagnostic_export_patched = True
