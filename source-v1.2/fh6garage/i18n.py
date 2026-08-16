from __future__ import annotations

from collections.abc import Mapping


DEFAULT_LANGUAGE = "ko"
SUPPORTED_LANGUAGES: Mapping[str, str] = {
    "ko": "한국어",
    "en": "English",
}

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "language.label": {
        "ko": "언어",
        "en": "Language",
    },
    "language.korean": {
        "ko": "한국어",
        "en": "Korean",
    },
    "language.english": {
        "ko": "English",
        "en": "English",
    },
    "language.restart_required": {
        "ko": "언어 변경은 프로그램을 다시 시작하면 적용됩니다.",
        "en": "The language change will apply after restarting the application.",
    },
}

_current_language = DEFAULT_LANGUAGE


def normalize_language(language: object) -> str:
    """Return a supported language code, falling back to Korean."""
    if isinstance(language, str):
        candidate = language.strip().lower().replace("_", "-")
        if candidate in SUPPORTED_LANGUAGES:
            return candidate
        primary = candidate.split("-", 1)[0]
        if primary in SUPPORTED_LANGUAGES:
            return primary
    return DEFAULT_LANGUAGE


def set_language(language: object) -> str:
    """Set the process-wide UI language and return the normalized code."""
    global _current_language
    _current_language = normalize_language(language)
    return _current_language


def get_language() -> str:
    return _current_language


def tr(key: str, **values: object) -> str:
    """Translate a stable message key using the active language.

    Missing keys deliberately fall back to the key itself so a packaging or
    translation omission cannot make the application unusable.
    """
    entries = _TRANSLATIONS.get(key)
    if entries is None:
        template = key
    else:
        template = entries.get(_current_language) or entries.get(DEFAULT_LANGUAGE) or key
    if values:
        try:
            return template.format(**values)
        except (KeyError, IndexError, ValueError):
            return template
    return template
