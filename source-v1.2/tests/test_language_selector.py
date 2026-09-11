from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LanguageSelectorContractTests(unittest.TestCase):
    def test_saved_language_is_applied_before_window_construction(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        apply_call = 'set_language(settings.value("language", DEFAULT_LANGUAGE, str))'
        window_call = "window = MainWindow(project_root=root)"
        self.assertIn(apply_call, source)
        self.assertIn(window_call, source)
        self.assertLess(source.index(apply_call), source.index(window_call))

    def test_sidebar_selector_persists_without_live_language_switch(self):
        source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        start = source.index("    def _on_language_preference_changed")
        end = source.index("    @Slot(bool)", start)
        handler = source[start:end]
        self.assertIn('self.settings.setValue("language", normalized)', handler)
        self.assertIn('tr("language.restart_required")', handler)
        self.assertNotIn("set_language(", handler)
        self.assertIn("SUPPORTED_LANGUAGES.items()", source)
        self.assertIn("self.language_combo.currentIndexChanged.connect", source)


if __name__ == "__main__":
    unittest.main()
