from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source-v1.2"
UI_PATH = SRC / "fh6garage" / "ui.py"
APP_PATH = SRC / "app.py"
BUILD_PATH = SRC / "build_exe.ps1"
VERSION_PATH = SRC / "version_info.txt"
SPEC_PATH = SRC / "FH6_Assistant_v1.3.spec"
TEST_PATH = SRC / "tests" / "test_v1_3_runtime.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


ui = UI_PATH.read_text(encoding="utf-8")
ui = replace_once(
    ui,
    'self.setWindowTitle("FH6 Assistant v1.2")',
    'self.setWindowTitle("FH6 Assistant v1.3")',
    "window title version",
)
ui = replace_once(
    ui,
    'version = QLabel("v1.2\\nLIVERY & TUNING")',
    'version = QLabel("v1.3\\nLIVERY & TUNING")',
    "sidebar version",
)
ui = replace_once(
    ui,
    '''            def clear_creator_notes() -> None:\n                self._clear_notes_for_same_creator(key)\n                # The selected livery was cleared by the creator-wide action too.\n                # Keep the open editor in sync so pressing Save cannot restore it.\n                editor.clear()\n                refresh_creator_count()\n''',
    '''            def clear_creator_notes() -> None:\n                if self._clear_notes_for_same_creator(key):\n                    # The selected livery was cleared by the creator-wide action too.\n                    # Keep the open editor in sync so pressing Save cannot restore it.\n                    editor.clear()\n                    refresh_creator_count()\n''',
    "memo editor clear only after confirmed bulk clear",
)
ui = replace_once(
    ui,
    '    def _clear_notes_for_same_creator(self, source_key: str) -> None:\n',
    '    def _clear_notes_for_same_creator(self, source_key: str) -> bool:\n',
    "creator clear return type",
)
# The first four early exits inside the creator-wide clear method represent:
# missing record, missing creator, nothing to clear, and user cancellation.
method_start = ui.index('    def _clear_notes_for_same_creator(self, source_key: str) -> bool:\n')
method_end = ui.index('\n\n\n    def _refresh_annotation_widgets', method_start)
method = ui[method_start:method_end]
if method.count('            return\n') != 4:
    raise RuntimeError(
        "creator clear early exits: expected four plain returns, "
        f"found {method.count('            return\\n')}"
    )
method = method.replace('            return\n', '            return False\n')
status_line = '        self._show_status(tr("memo.clear_status", creator=creator, count=with_notes), 3500)\n'
if status_line not in method:
    raise RuntimeError("creator clear success status line not found")
method = method.replace(status_line, status_line + '        return True\n', 1)
ui = ui[:method_start] + method + ui[method_end:]
UI_PATH.write_text(ui, encoding="utf-8")

app = APP_PATH.read_text(encoding="utf-8")
app = replace_once(
    app,
    'app.setApplicationVersion("1.2")',
    'app.setApplicationVersion("1.3")',
    "application version",
)
APP_PATH.write_text(app, encoding="utf-8")

BUILD_PATH.write_text(
    '''$ErrorActionPreference = "Stop"\nSet-Location $PSScriptRoot\n\n$venv = Join-Path $PSScriptRoot ".build-venv"\nif (-not (Test-Path $venv)) {\n    py -3 -m venv $venv\n}\n\n$python = Join-Path $venv "Scripts\\python.exe"\n& $python -m pip install --upgrade pip\n& $python -m pip install -r .\\requirements.txt pyinstaller\n& $python -m PyInstaller --clean --noconfirm .\\FH6_Assistant_v1.3.spec\n\nWrite-Host ""\nWrite-Host "Build complete:"\nWrite-Host (Join-Path $PSScriptRoot "dist\\FH6 Assistant v1.3.exe")\n''',
    encoding="utf-8",
)

VERSION_PATH.write_text(
    '''# UTF-8\nVSVersionInfo(\n  ffi=FixedFileInfo(\n    filevers=(1, 3, 0, 0),\n    prodvers=(1, 3, 0, 0),\n    mask=0x3f,\n    flags=0x0,\n    OS=0x40004,\n    fileType=0x1,\n    subtype=0x0,\n    date=(0, 0)\n  ),\n  kids=[\n    StringFileInfo([\n      StringTable(\n        '040904B0',\n        [\n          StringStruct('FileDescription', 'FH6 Assistant'),\n          StringStruct('FileVersion', '1.3.0.0'),\n          StringStruct('InternalName', 'FH6 Assistant'),\n          StringStruct('OriginalFilename', 'FH6 Assistant v1.3.exe'),\n          StringStruct('ProductName', 'FH6 Assistant'),\n          StringStruct('ProductVersion', '1.3')\n        ]\n      )\n    ]),\n    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n  ]\n)\n''',
    encoding="utf-8",
)

SPEC_PATH.write_text(
    '''# -*- mode: python ; coding: utf-8 -*-\nfrom pathlib import Path\n\nproject_root = Path(SPECPATH)\n\na = Analysis(\n    ['app.py'],\n    pathex=[str(project_root)],\n    binaries=[],\n    datas=[\n        (str(project_root / 'data' / 'car_names.json'), 'data'),\n        (str(project_root / 'icons' / 'FH6_Assistant.ico'), 'icons'),\n    ],\n    hiddenimports=[],\n    hookspath=[],\n    hooksconfig={},\n    runtime_hooks=[],\n    excludes=[],\n    noarchive=False,\n    optimize=0,\n)\npyz = PYZ(a.pure)\n\nexe = EXE(\n    pyz,\n    a.scripts,\n    a.binaries,\n    a.datas,\n    [],\n    name='FH6 Assistant v1.3',\n    debug=False,\n    bootloader_ignore_signals=False,\n    strip=False,\n    upx=False,\n    console=False,\n    icon=str(project_root / 'icons' / 'FH6_Assistant.ico'),\n    version=str(project_root / 'version_info.txt'),\n)\n''',
    encoding="utf-8",
)

TEST_PATH.write_text(
    '''from __future__ import annotations\n\nimport os\nimport unittest\nfrom pathlib import Path\n\nos.environ.setdefault("QT_QPA_PLATFORM", "offscreen")\n\nfrom PySide6.QtCore import Qt\nfrom PySide6.QtWidgets import QApplication, QTableWidgetItem\n\nfrom fh6garage.i18n import set_language\nfrom fh6garage.ui import MainWindow\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\nclass V13RuntimeUiTests(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls) -> None:\n        cls.app = QApplication.instance() or QApplication([])\n        cls.app.setOrganizationName("FH6AssistantTests")\n        cls.app.setApplicationName("FH6AssistantV13Runtime")\n        set_language("ko")\n\n    def setUp(self) -> None:\n        self.window = MainWindow(project_root=ROOT)\n\n    def tearDown(self) -> None:\n        self.window.close()\n        self.window.deleteLater()\n        self.app.processEvents()\n\n    def test_v13_window_and_group_controls_exist(self) -> None:\n        self.assertEqual(self.window.windowTitle(), "FH6 Assistant v1.3")\n        self.assertEqual(self.window.livery_creator_group_button.text(), "동일 제작자로 묶기")\n        self.assertEqual(self.window.tuning_creator_group_button.text(), "동일 제작자로 묶기")\n\n    def test_group_modes_are_mutually_exclusive(self) -> None:\n        vehicle = self.window.livery_group_button\n        creator = self.window.livery_creator_group_button\n        vehicle.setChecked(True)\n        creator.setChecked(True)\n        self.assertTrue(creator.isChecked())\n        self.assertFalse(vehicle.isChecked())\n        vehicle.setChecked(True)\n        self.assertTrue(vehicle.isChecked())\n        self.assertFalse(creator.isChecked())\n\n    def test_dashboard_vehicle_instant_move_sets_livery_search(self) -> None:\n        table = self.window.car_table\n        table.setRowCount(1)\n        car_id = 1229\n        for col, text in enumerate((str(car_id), "vehicle", "1", "1")):\n            item = QTableWidgetItem(text)\n            item.setData(Qt.ItemDataRole.UserRole, car_id)\n            table.setItem(0, col, item)\n        table.selectRow(0)\n        self.window.dashboard_content_stack.setCurrentIndex(0)\n        expected = self.window._car_label(car_id)\n        self.window._jump_to_dashboard_selection("livery")\n        self.assertEqual(self.window.pages.currentIndex(), 1)\n        self.assertEqual(self.window.livery_search.text(), expected)\n\n    def test_dashboard_creator_instant_move_sets_tuning_search(self) -> None:\n        table = self.window.creator_table\n        table.setRowCount(1)\n        creator = "RuntimeCreator"\n        for col, text in enumerate(("2", creator, "1", "1")):\n            item = QTableWidgetItem(text)\n            item.setData(Qt.ItemDataRole.UserRole, creator)\n            table.setItem(0, col, item)\n        table.selectRow(0)\n        self.window.dashboard_content_stack.setCurrentIndex(1)\n        self.window._jump_to_dashboard_selection("tuning")\n        self.assertEqual(self.window.pages.currentIndex(), 2)\n        self.assertEqual(self.window.tuning_search.text(), creator)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

print("FH6 Assistant v1.3 finalization applied successfully.")
