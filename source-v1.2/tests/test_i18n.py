from __future__ import annotations

import unittest

from fh6garage.i18n import (
    DEFAULT_LANGUAGE,
    get_language,
    normalize_language,
    set_language,
    tr,
)


class I18nTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(DEFAULT_LANGUAGE)

    def test_default_language_is_korean(self) -> None:
        set_language("ko")
        self.assertEqual(get_language(), "ko")
        self.assertEqual(tr("language.label"), "언어")

    def test_english_translation(self) -> None:
        set_language("en")
        self.assertEqual(get_language(), "en")
        self.assertEqual(tr("language.label"), "Language")
        self.assertIn("restarting", tr("language.restart_required"))

    def test_locale_variant_is_normalized(self) -> None:
        self.assertEqual(normalize_language("en-US"), "en")
        self.assertEqual(normalize_language("ko_KR"), "ko")

    def test_unsupported_language_falls_back_to_korean(self) -> None:
        self.assertEqual(set_language("ja"), "ko")
        self.assertEqual(tr("language.label"), "언어")

    def test_missing_key_is_safe(self) -> None:
        set_language("en")
        self.assertEqual(tr("missing.translation.key"), "missing.translation.key")


if __name__ == "__main__":
    unittest.main()
