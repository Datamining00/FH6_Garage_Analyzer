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
        ui_source = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
        followup_source = (ROOT / "fh6garage" / "ui_followup.py").read_text(
            encoding="utf-8"
        )
        builder_source = (ROOT / "fh6garage" / "main_window_builder.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("persist_language_preference(self, index)", ui_source)
        self.assertIn('owner.settings.setValue("language", normalized)', followup_source)
        self.assertIn('tr("language.restart_required")', followup_source)
        self.assertNotIn("set_language(", followup_source)
        self.assertIn("SUPPORTED_LANGUAGES.items()", builder_source)
        self.assertIn(
            "owner.language_combo.currentIndexChanged.connect", builder_source
        )


if __name__ == "__main__":
    unittest.main()
