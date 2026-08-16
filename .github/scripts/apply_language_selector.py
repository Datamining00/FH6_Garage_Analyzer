from __future__ import annotations

from pathlib import Path

ROOT = Path("source-v1.2")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label} fragment not found: {old[:160]!r}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# app.py: restore saved language before MainWindow is constructed.
# ---------------------------------------------------------------------------
app_path = ROOT / "app.py"
app = app_path.read_text(encoding="utf-8")
app = replace_once(
    app,
    "try:\n    from PySide6.QtWidgets import QApplication\n    from PySide6.QtGui import QFont, QIcon",
    "try:\n    from PySide6.QtCore import QSettings\n    from PySide6.QtWidgets import QApplication\n    from PySide6.QtGui import QFont, QIcon",
    "app.py Qt imports",
)
app = replace_once(
    app,
    "from fh6garage.ui import MainWindow",
    "from fh6garage.i18n import DEFAULT_LANGUAGE, set_language\nfrom fh6garage.ui import MainWindow",
    "app.py i18n import",
)
app = replace_once(
    app,
    '    app.setOrganizationName("LocalOnly")\n\n    root = resource_root()',
    '    app.setOrganizationName("LocalOnly")\n\n    # Resolve the persisted UI language before constructing any translated widgets.\n    settings = QSettings()\n    set_language(settings.value("language", DEFAULT_LANGUAGE, str))\n\n    root = resource_root()',
    "app.py startup language",
)
app_path.write_text(app, encoding="utf-8")


# ---------------------------------------------------------------------------
# ui.py: sidebar selector. Save preference only; apply on next restart so the
# current window never becomes a half-Korean/half-English mixed UI.
# ---------------------------------------------------------------------------
ui_path = ROOT / "fh6garage" / "ui.py"
ui = ui_path.read_text(encoding="utf-8")
ui = replace_once(
    ui,
    "from .i18n import tr",
    "from .i18n import SUPPORTED_LANGUAGES, get_language, normalize_language, tr",
    "ui.py i18n import",
)

handler = '''    @Slot(int)
    def _on_language_preference_changed(self, index: int) -> None:
        """Persist a language choice and apply it cleanly on the next launch."""
        if index < 0:
            return
        raw_language = self.language_combo.itemData(index)
        if not isinstance(raw_language, str):
            return
        normalized = normalize_language(raw_language)
        self.settings.setValue("language", normalized)
        if normalized != get_language():
            self._show_status(tr("language.restart_required"), 6000)

'''
ui = replace_once(
    ui,
    "    @Slot(bool)\n    def _set_always_on_top",
    handler + "    @Slot(bool)\n    def _set_always_on_top",
    "ui.py language handler",
)

sidebar_old = '''        side.addStretch(1)
        self.always_on_top_box = QCheckBox(tr("sidebar.always_on_top"))'''
sidebar_new = '''        side.addStretch(1)

        self.language_label = QLabel(tr("language.label"))
        self.language_label.setStyleSheet(
            "color:#8d91a0; padding:0 6px 2px 6px; font-size:9pt;"
        )
        side.addWidget(self.language_label)

        self.language_combo = QComboBox()
        self.language_combo.setAccessibleName(tr("language.label"))
        for language_code, display_name in SUPPORTED_LANGUAGES.items():
            self.language_combo.addItem(display_name, language_code)
        active_language_index = self.language_combo.findData(get_language())
        if active_language_index >= 0:
            self.language_combo.setCurrentIndex(active_language_index)
        self.language_combo.setStyleSheet(
            "QComboBox { background:#242632; color:#f0f1f5; "
            "border:1px solid #343746; border-radius:7px; padding:6px 8px; }"
            "QComboBox:hover { border-color:#6e4bf2; }"
            "QComboBox::drop-down { border:0; width:22px; }"
            "QComboBox QAbstractItemView { background:#242632; color:#f0f1f5; "
            "selection-background-color:#6e4bf2; selection-color:white; }"
        )
        self.language_combo.currentIndexChanged.connect(
            self._on_language_preference_changed
        )
        side.addWidget(self.language_combo)

        self.always_on_top_box = QCheckBox(tr("sidebar.always_on_top"))'''
ui = replace_once(ui, sidebar_old, sidebar_new, "ui.py sidebar selector")
ui_path.write_text(ui, encoding="utf-8")


# ---------------------------------------------------------------------------
# Stage 1 regression test: do not couple the test to an exact import spelling.
# The implementation may import additional i18n helpers while still using tr().
# ---------------------------------------------------------------------------
stage1_path = ROOT / "tests" / "test_i18n_stage1.py"
stage1 = stage1_path.read_text(encoding="utf-8")
stage1 = replace_once(
    stage1,
    "        required = (\n            'from .i18n import tr',\n",
    "        required = (\n",
    "test_i18n_stage1.py import contract",
)
stage1_path.write_text(stage1, encoding="utf-8")


# ---------------------------------------------------------------------------
# Regression contract test. It deliberately avoids importing PySide6 so the
# existing lightweight CI remains unchanged.
# ---------------------------------------------------------------------------
test_path = ROOT / "tests" / "test_language_selector.py"
test_path.write_text(
    '''from pathlib import Path\nimport unittest\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\nclass LanguageSelectorContractTests(unittest.TestCase):\n    def test_saved_language_is_applied_before_window_construction(self):\n        source = (ROOT / "app.py").read_text(encoding="utf-8")\n        apply_call = 'set_language(settings.value("language", DEFAULT_LANGUAGE, str))'\n        window_call = "window = MainWindow(project_root=root)"\n        self.assertIn(apply_call, source)\n        self.assertIn(window_call, source)\n        self.assertLess(source.index(apply_call), source.index(window_call))\n\n    def test_sidebar_selector_persists_without_live_language_switch(self):\n        source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")\n        start = source.index("    def _on_language_preference_changed")\n        end = source.index("    @Slot(bool)", start)\n        handler = source[start:end]\n        self.assertIn('self.settings.setValue("language", normalized)', handler)\n        self.assertIn('tr("language.restart_required")', handler)\n        self.assertNotIn("set_language(", handler)\n        self.assertIn("SUPPORTED_LANGUAGES.items()", source)\n        self.assertIn("self.language_combo.currentIndexChanged.connect", source)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

print("Language selector patch prepared")
