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
    "common.copied": {
        "ko": "클립보드에 복사되었습니다",
        "en": "Copied to clipboard",
    },
    "common.filter": {
        "ko": "필터",
        "en": "Filter",
    },
    "common.processing": {
        "ko": "처리 중…",
        "en": "Processing…",
    },
    "common.ascending": {
        "ko": "{label} 오름차순",
        "en": "Sort {label} ascending",
    },
    "common.descending": {
        "ko": "{label} 내림차순",
        "en": "Sort {label} descending",
    },
    "nav.dashboard": {
        "ko": "대시보드",
        "en": "Dashboard",
    },
    "nav.livery": {
        "ko": "리버리",
        "en": "Livery",
    },
    "nav.tuning": {
        "ko": "튜닝",
        "en": "Tuning",
    },
    "sidebar.always_on_top": {
        "ko": "항상 위에 표시",
        "en": "Always on top",
    },
    "sidebar.always_on_top_tip": {
        "ko": "인게임 이동을 시작하면 포르자 화면을 가리지 않도록 분석기 창을 최소화합니다.",
        "en": "When in-game navigation starts, the analyzer window is minimized so it does not cover Forza.",
    },
    "save.placeholder": {
        "ko": "FH6 세이브 루트/current/버전/ContainersRoot 폴더를 선택하세요",
        "en": "Select the FH6 save root, current, version, or ContainersRoot folder",
    },
    "save.choose_folder": {
        "ko": "세이브 폴더 선택",
        "en": "Choose save folder",
    },
    "save.refresh": {
        "ko": "새로고침",
        "en": "Refresh",
    },
    "dashboard.title": {
        "ko": "차고 분석 대시보드",
        "en": "Garage analysis dashboard",
    },
    "dashboard.garage_cars": {
        "ko": "차고 차량",
        "en": "Garage cars",
    },
    "dashboard.saved_livery": {
        "ko": "저장 리버리",
        "en": "Saved liveries",
    },
    "dashboard.saved_tuning": {
        "ko": "저장 튜닝",
        "en": "Saved tunings",
    },
    "dashboard.by_vehicle": {
        "ko": "차종별 저장 콘텐츠",
        "en": "Saved content by vehicle",
    },
    "dashboard.by_creator": {
        "ko": "제작자별 콘텐츠",
        "en": "Content by creator",
    },
    "dashboard.search_vehicle": {
        "ko": "Car ID / 차량명 검색",
        "en": "Search Car ID / vehicle name",
    },
    "dashboard.select_vehicle": {
        "ko": "차량을 선택하세요",
        "en": "Select a vehicle",
    },
    "db.title": {
        "ko": "차량 DB",
        "en": "Vehicle database",
    },
    "db.last_update_unavailable": {
        "ko": "/ 마지막 업데이트: 확인 불가",
        "en": "/ Last update: unavailable",
    },
    "db.check_update": {
        "ko": "업데이트 확인",
        "en": "Check for updates",
    },
    "db.check_update_tip": {
        "ko": "차량 DB의 새로운 버전을 확인합니다.",
        "en": "Check for a newer version of the vehicle database.",
    },
    "db.source": {
        "ko": "DB 출처",
        "en": "DB source",
    },
    "db.source_tip": {
        "ko": "차량 DB 원본 페이지를 브라우저에서 엽니다.",
        "en": "Open the original vehicle database page in your browser.",
    },
    "db.source_accessible": {
        "ko": "차량 DB 출처 열기",
        "en": "Open vehicle database source",
    },
    "db.override": {
        "ko": "사용자 차량 이름 지정",
        "en": "Custom vehicle names",
    },
    "db.override_tip": {
        "ko": "Car ID에 대응하는 차량 이름을 직접 지정하거나 수정합니다.",
        "en": "Assign or edit the vehicle name associated with a Car ID.",
    },
    "table.car_id": {
        "ko": "Car ID",
        "en": "Car ID",
    },
    "table.vehicle": {
        "ko": "차량",
        "en": "Vehicle",
    },
    "table.livery": {
        "ko": "리버리",
        "en": "Livery",
    },
    "table.tuning": {
        "ko": "튜닝",
        "en": "Tuning",
    },
    "table.total": {
        "ko": "합계",
        "en": "Total",
    },
    "table.creator": {
        "ko": "제작자명",
        "en": "Creator",
    },
    "table.creator_short": {
        "ko": "제작자",
        "en": "Creator",
    },
    "table.livery_name": {
        "ko": "리버리 이름",
        "en": "Livery name",
    },
    "table.name": {
        "ko": "이름",
        "en": "Name",
    },
    "table.size": {
        "ko": "크기",
        "en": "Size",
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
