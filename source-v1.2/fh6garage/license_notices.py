"""Offline third-party notices, shared by source and frozen distributions."""
from pathlib import Path
import os
import sys
import tempfile


def resources_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def install_kfps_notices(runtime_root):
    """Backfill notices without downloading, rebuilding, or changing render data."""
    runtime_root = Path(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    for source_name, target_name in (
        ('KFPS-LICENSE.txt', 'LICENSE'),
        ('KFPS-custom-importer-LICENSE.txt', 'LICENSE.custom-importer'),
    ):
        data = (resources_root() / 'licenses' / source_name).read_bytes()
        target = runtime_root / target_name
        if target.exists() and target.read_bytes() == data:
            continue
        fd, name = tempfile.mkstemp(prefix='.license-', dir=runtime_root)
        temporary = Path(name)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(data)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def show_licenses(parent):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QTextBrowser, QDialogButtonBox
    dialog = QDialog(parent)
    dialog.setWindowTitle('오픈소스 및 라이선스')
    dialog.resize(720, 560)
    layout = QVBoxLayout(dialog)
    choices = QComboBox()
    root = resources_root()
    files = [root / 'THIRD_PARTY_NOTICES.md', root / 'SOURCE_AND_RELINKING.md']
    files += sorted(p for p in (root / 'licenses').rglob('*') if p.is_file())
    for path in files:
        choices.addItem(str(path.relative_to(root)), str(path))
    text = QTextBrowser()
    text.setOpenExternalLinks(False)
    text.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
    def display(_index):
        try:
            text.setPlainText(Path(choices.currentData()).read_text(encoding='utf-8-sig', errors='replace'))
        except OSError as exc:
            text.setPlainText('라이선스 문서를 읽지 못했습니다: ' + str(exc))
        text.verticalScrollBar().setValue(0)
    choices.currentIndexChanged.connect(display)
    layout.addWidget(choices)
    layout.addWidget(text)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    display(0)
    dialog.exec()
