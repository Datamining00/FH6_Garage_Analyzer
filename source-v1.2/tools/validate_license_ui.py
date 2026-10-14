"""Temporary-settings UI verification; sends no input to the game or other apps."""
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
with tempfile.TemporaryDirectory(prefix='fh6-license-ui-') as state:
    os.environ['LOCALAPPDATA'] = state
    from PySide6.QtCore import QTimer, Qt, QSettings
    from PySide6.QtGui import QFont, QFontDatabase, QInputMethodEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLineEdit, QTextBrowser
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, state)
    app = QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
    app.setFont(QFont('Malgun Gothic', 10))
    from fh6garage.application_controls import SettingsDialog
    dialog = SettingsDialog()
    dialog.resize(560, 720)
    dialog.show()
    app.processEvents()
    field = QLineEdit(dialog)
    field.show()
    field.setFocus()
    QTest.keyClicks(field, 'FH6')
    event = QInputMethodEvent()
    event.setCommitString('한글 입력')
    QApplication.sendEvent(field, event)
    assert field.text() == 'FH6한글 입력', field.text()
    field.hide()
    result = {'latin_key_events': True, 'korean_input_method_commit': True,
              'physical_windows_ime_tested': False}
    errors = []
    def inspect():
        modal = QApplication.activeModalWidget()
        try:
            assert isinstance(modal, QDialog)
            text = modal.findChild(QTextBrowser)
            choices = modal.findChild(QComboBox)
            assert 'PySide6/Qt' in text.toPlainText()
            index = next(i for i in range(choices.count()) if choices.itemText(i).endswith('KFPS-LICENSE.txt'))
            choices.setCurrentIndex(index)
            assert 'Permission is hereby granted' in text.toPlainText()
            result['notices_dialog'] = True
            result['license_count'] = choices.count()
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            if modal: modal.reject()
    QTimer.singleShot(100, inspect)
    QTest.mouseClick(dialog.licenses_button, Qt.MouseButton.LeftButton)
    assert not errors, errors
    assert result.get('notices_dialog')
    dialog.reject()
    print(json.dumps(result, ensure_ascii=False))
