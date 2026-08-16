from __future__ import annotations

from collections.abc import Mapping


DEFAULT_LANGUAGE = "ko"
SUPPORTED_LANGUAGES: Mapping[str, str] = {
    "ko": "한국어",
    "en": "English",
}

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "language.label": {"ko": "언어", "en": "Language"},
    "language.korean": {"ko": "한국어", "en": "Korean"},
    "language.english": {"ko": "English", "en": "English"},
    "language.restart_required": {
        "ko": "언어 변경은 프로그램을 다시 시작하면 적용됩니다.",
        "en": "The language change will apply after restarting the application.",
    },
    "common.copied": {"ko": "클립보드에 복사되었습니다", "en": "Copied to clipboard"},
    "common.filter": {"ko": "필터", "en": "Filter"},
    "common.filter_count": {"ko": "필터 {count}", "en": "Filter {count}"},
    "common.processing": {"ko": "처리 중…", "en": "Processing…"},
    "common.close": {"ko": "닫기", "en": "Close"},
    "common.unavailable": {"ko": "확인 불가", "en": "Unavailable"},
    "common.ascending": {"ko": "{label} 오름차순", "en": "Sort {label} ascending"},
    "common.descending": {"ko": "{label} 내림차순", "en": "Sort {label} descending"},
    "nav.dashboard": {"ko": "대시보드", "en": "Dashboard"},
    "nav.livery": {"ko": "리버리", "en": "Livery"},
    "nav.tuning": {"ko": "튜닝", "en": "Tuning"},
    "sidebar.always_on_top": {"ko": "항상 위에 표시", "en": "Always on top"},
    "sidebar.always_on_top_tip": {
        "ko": "인게임 이동을 시작하면 포르자 화면을 가리지 않도록 분석기 창을 최소화합니다.",
        "en": "When in-game navigation starts, the analyzer window is minimized so it does not cover Forza.",
    },
    "save.placeholder": {
        "ko": "FH6 세이브 루트/current/버전/ContainersRoot 폴더를 선택하세요",
        "en": "Select the FH6 save root, current, version, or ContainersRoot folder",
    },
    "save.choose_folder": {"ko": "세이브 폴더 선택", "en": "Choose save folder"},
    "save.folder_dialog": {"ko": "FH6 세이브 폴더 선택", "en": "Choose FH6 save folder"},
    "save.refresh": {"ko": "새로고침", "en": "Refresh"},
    "dashboard.title": {"ko": "차고 분석 대시보드", "en": "Garage analysis dashboard"},
    "dashboard.garage_cars": {"ko": "차고 차량", "en": "Garage cars"},
    "dashboard.saved_livery": {"ko": "저장 리버리", "en": "Saved liveries"},
    "dashboard.saved_tuning": {"ko": "저장 튜닝", "en": "Saved tunings"},
    "dashboard.by_vehicle": {"ko": "차종별 저장 콘텐츠", "en": "Saved content by vehicle"},
    "dashboard.by_creator": {"ko": "제작자별 콘텐츠", "en": "Content by creator"},
    "dashboard.search_vehicle": {"ko": "Car ID / 차량명 검색", "en": "Search Car ID / vehicle name"},
    "dashboard.select_vehicle": {"ko": "차량을 선택하세요", "en": "Select a vehicle"},
    "db.title": {"ko": "차량 DB", "en": "Vehicle database"},
    "db.last_update_unavailable": {"ko": "/ 마지막 업데이트: 확인 불가", "en": "/ Last update: unavailable"},
    "db.check_update": {"ko": "업데이트 확인", "en": "Check for updates"},
    "db.check_update_tip": {
        "ko": "차량 DB의 새로운 버전을 확인합니다.",
        "en": "Check for a newer version of the vehicle database.",
    },
    "db.source": {"ko": "DB 출처", "en": "DB source"},
    "db.source_tip": {
        "ko": "차량 DB 원본 페이지를 브라우저에서 엽니다.",
        "en": "Open the original vehicle database page in your browser.",
    },
    "db.source_accessible": {"ko": "차량 DB 출처 열기", "en": "Open vehicle database source"},
    "db.override": {"ko": "사용자 차량 이름 지정", "en": "Custom vehicle names"},
    "db.override_tip": {
        "ko": "Car ID에 대응하는 차량 이름을 직접 지정하거나 수정합니다.",
        "en": "Assign or edit the vehicle name associated with a Car ID.",
    },
    "table.car_id": {"ko": "Car ID", "en": "Car ID"},
    "table.vehicle": {"ko": "차량", "en": "Vehicle"},
    "table.vehicle_name": {"ko": "차량명", "en": "Vehicle"},
    "table.livery": {"ko": "리버리", "en": "Livery"},
    "table.tuning": {"ko": "튜닝", "en": "Tuning"},
    "table.total": {"ko": "합계", "en": "Total"},
    "table.creator": {"ko": "제작자명", "en": "Creator"},
    "table.creator_short": {"ko": "제작자", "en": "Creator"},
    "table.livery_name": {"ko": "리버리 이름", "en": "Livery name"},
    "table.tuning_name": {"ko": "튜닝 이름", "en": "Tuning name"},
    "table.name": {"ko": "이름", "en": "Name"},
    "table.size": {"ko": "크기", "en": "Size"},
    "table.status": {"ko": "상태", "en": "Status"},
    "table.description": {"ko": "설명", "en": "Description"},
    "table.memo": {"ko": "메모", "en": "Memo"},
    "table.created": {"ko": "생성일", "en": "Created"},
    "table.downloaded": {"ko": "다운로드일", "en": "Downloaded"},
    "content.search_placeholder": {
        "ko": "이름 / 제작자 / Car ID / 차량명 / 설명 / 메모 검색",
        "en": "Search name / creator / Car ID / vehicle / description / memo",
    },
    "content.sort_label": {"ko": "정렬:", "en": "Sort:"},
    "content.sort_default": {"ko": "기본", "en": "Default"},
    "content.sort_brand": {"ko": "브랜드명", "en": "Brand"},
    "content.sort_creator": {"ko": "제작자명", "en": "Creator"},
    "content.sort_download": {"ko": "다운로드", "en": "Downloaded"},
    "content.group_vehicle": {"ko": "동일 차량끼리 묶기", "en": "Group by vehicle"},
    "content.group_vehicle_tip": {
        "ko": "같은 차량의 항목을 모으고 차량명과 현재 표시 개수를 구분 제목으로 표시합니다.",
        "en": "Group items for the same vehicle and show the vehicle name and visible item count as a section heading.",
    },
    "content.group_header": {"ko": "{vehicle} · {noun} {count}개", "en": "{vehicle} · {count} {noun}"},
    "content.noun_livery": {"ko": "리버리", "en": "liveries"},
    "content.noun_tuning": {"ko": "튜닝", "en": "tunings"},
    "content.sorting": {"ko": "{noun} 목록을 정렬하는 중…", "en": "Sorting {noun} list…"},
    "content.rebuilding_livery": {"ko": "리버리 목록을 다시 구성하는 중…", "en": "Rebuilding livery list…"},
    "status.check": {"ko": "원 표시", "en": "Circle mark"},
    "status.triangle": {"ko": "삼각형 표시", "en": "Triangle mark"},
    "status.excluded": {"ko": "X 표시", "en": "X mark"},
    "status.none": {"ko": "분류 없음", "en": "Unclassified"},
    "status.memo_yes": {"ko": "메모 있음", "en": "Has memo"},
    "status.memo_no": {"ko": "메모 없음", "en": "No memo"},
    "status.duplicate_livery": {"ko": "중복 리버리", "en": "Duplicate livery"},
    "status.duplicate_livery_only": {"ko": "중복 리버리만", "en": "Duplicate liveries only"},
    "status.filter_tip": {
        "ko": "상태 필터 · 여러 항목을 동시에 선택할 수 있습니다.",
        "en": "Status filter · You can select multiple items at once.",
    },
    "scan.loading": {"ko": "세이브와 썸네일을 불러오는 중…", "en": "Loading save data and thumbnails…"},
    "scan.scanning": {"ko": "세이브 스캔 중…", "en": "Scanning save data…"},
    "scan.complete": {"ko": "완료 — {liveries} liveries / {tunings} tunings", "en": "Complete — {liveries} liveries / {tunings} tunings"},
    "scan.failed": {"ko": "스캔 실패", "en": "Scan failed"},
    "scan.failed_title": {"ko": "세이브 스캔 실패", "en": "Save scan failed"},
    "file.timestamp_unavailable": {
        "ko": "파일 생성 시각을 확인할 수 없습니다.",
        "en": "The file creation time is unavailable.",
    },
    "detail.livery_prefix": {"ko": "리버리: {name}", "en": "Livery: {name}"},
    "detail.no_title": {"ko": "(제목 없음)", "en": "(untitled)"},
    "detail.description": {"ko": "설명", "en": "Description"},
    "detail.no_description": {"ko": "설명 없음", "en": "No description"},
    "detail.uploaded": {"ko": "제작자 업로드 날짜: {date}", "en": "Creator upload date: {date}"},
    "detail.tuning_title": {"ko": "튜닝 세부 정보", "en": "Tuning details"},
    "detail.basic_info": {"ko": "[기본 정보]", "en": "[Basic information]"},
    "detail.title_line": {"ko": "제목: {value}", "en": "Title: {value}"},
    "detail.creator_line": {"ko": "제작자: {value}", "en": "Creator: {value}"},
    "detail.description_line": {"ko": "설명: {value}", "en": "Description: {value}"},
    "detail.data_file": {"ko": "[Data 파일]", "en": "[Data file]"},
    "detail.data_missing": {"ko": "Data 파일을 찾을 수 없습니다.", "en": "The Data file could not be found."},
    "detail.read_failed": {"ko": "세부 정보를 읽을 수 없습니다: {error}", "en": "Could not read details: {error}"},
    "detail.format_version": {"ko": "형식 버전: {value}", "en": "Format version: {value}"},
    "detail.lock_state": {"ko": "잠금 상태: {value}", "en": "Lock state: {value}"},
    "detail.locked": {"ko": "잠김", "en": "Locked"},
    "detail.unlocked": {"ko": "잠기지 않음", "en": "Unlocked"},
    "detail.car_ordinal": {"ko": "차량 Ordinal ID: {value}", "en": "Car Ordinal ID: {value}"},
    "detail.installed_parts": {"ko": "[장착 부품 ID]", "en": "[Installed part IDs]"},
    "detail.tuning_values": {"ko": "[세부 튜닝 값]", "en": "[Detailed tuning values]"},
    "detail.validation": {"ko": "[검증 참고]", "en": "[Validation reference]"},
    "detail.header_car_id": {"ko": "header Car ID: {value}", "en": "Header Car ID: {value}"},
    "detail.data_ordinal": {"ko": "Data Ordinal ID: {value}", "en": "Data Ordinal ID: {value}"},
    "tune_data.size_error": {
        "ko": "Data 파일 크기가 {actual}바이트입니다. 예상 크기는 {expected}바이트입니다.",
        "en": "The Data file is {actual} bytes; expected {expected} bytes.",
    },
    "tune_data.nonfinite_error": {
        "ko": "튜닝 값에 NaN 또는 무한대가 포함되어 있습니다.",
        "en": "The tuning data contains NaN or infinite values.",
    },
}

_TUNE_LABELS_EN: dict[str, str] = {
    "엔진": "Engine", "구동계": "Drivetrain", "차체": "Chassis", "모터": "Motor", "브레이크": "Brakes",
    "스프링·댐퍼": "Springs & dampers", "전륜 안티롤바": "Front anti-roll bar", "후륜 안티롤바": "Rear anti-roll bar",
    "타이어 컴파운드": "Tire compound", "리어 윙": "Rear wing", "전륜 휠 크기": "Front wheel size", "후륜 휠 크기": "Rear wheel size",
    "캠축": "Camshaft", "밸브": "Valves", "배기량": "Displacement", "피스톤·압축": "Pistons & compression",
    "연료 시스템": "Fuel system", "점화": "Ignition", "배기": "Exhaust", "흡기": "Intake", "플라이휠": "Flywheel",
    "매니폴드": "Manifold", "리스트릭터 플레이트": "Restrictor plate", "오일 냉각": "Oil cooling", "싱글 터보": "Single turbo",
    "트윈 터보": "Twin turbo", "쿼드 터보": "Quad turbo", "용적식 슈퍼차저": "Positive-displacement supercharger",
    "원심식 슈퍼차저": "Centrifugal supercharger", "인터쿨러": "Intercooler", "클러치": "Clutch", "변속기": "Transmission",
    "드라이브라인": "Driveline", "디퍼렌셜": "Differential", "전면 범퍼": "Front bumper", "후면 범퍼": "Rear bumper",
    "보닛": "Hood", "사이드 스커트": "Side skirts", "전륜 타이어 폭": "Front tire width", "후륜 타이어 폭": "Rear tire width",
    "경량화": "Weight reduction", "차체 보강·롤케이지": "Chassis reinforcement & roll cage", "모터 부품": "Motor parts",
    "휠 스타일": "Wheel style", "과급 방식": "Forced-induction type", "전륜 트랙 폭": "Front track width", "후륜 트랙 폭": "Rear track width",
    "전륜 타이어 편평비": "Front tire profile", "후륜 타이어 편평비": "Rear tire profile", "후륜 휠 스타일": "Rear wheel style",
    "전륜 다운포스": "Front downforce", "후륜 다운포스": "Rear downforce", "최종감속비": "Final drive ratio",
    "브레이크 압력": "Brake pressure", "브레이크 밸런스": "Brake balance", "핸드브레이크 압력": "Handbrake pressure",
    "센터 디퍼렌셜": "Center differential", "TCS 슬립 기준": "TCS slip threshold", "전륜 공기압": "Front tire pressure",
    "전륜 캠버": "Front camber", "전륜 토": "Front toe", "전륜 캐스터": "Front caster", "전륜 스프링": "Front spring",
    "전륜 차고": "Front ride height", "전륜 범프 강성": "Front bump stiffness", "전륜 리바운드 강성": "Front rebound stiffness",
    "전륜 디퍼렌셜 가속": "Front differential acceleration", "전륜 디퍼렌셜 감속": "Front differential deceleration",
    "후륜 공기압": "Rear tire pressure", "후륜 캠버": "Rear camber", "후륜 토": "Rear toe", "후륜 캐스터": "Rear caster",
    "후륜 스프링": "Rear spring", "후륜 차고": "Rear ride height", "후륜 범프 강성": "Rear bump stiffness",
    "후륜 리바운드 강성": "Rear rebound stiffness", "후륜 디퍼렌셜 가속": "Rear differential acceleration",
    "후륜 디퍼렌셜 감속": "Rear differential deceleration",
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


def tune_label(label: str) -> str:
    """Translate a canonical Korean tune-data label for the active UI language."""
    if _current_language == "ko":
        return label
    if _current_language == "en":
        translated = _TUNE_LABELS_EN.get(label)
        if translated is not None:
            return translated
        if label.endswith("단 기어비"):
            gear = label.removesuffix("단 기어비").strip()
            if gear.isdigit():
                return f"Gear {gear} ratio"
    return label
