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
        "ko": "활성화하면 다른 창 위에 표시되며, 인게임 이동 중에도 창을 숨기지 않습니다.",
        "en": "Keep the assistant above other windows and visible during in-game navigation.",
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
    "dashboard.instant_move": {"ko": "즉시 이동", "en": "Open now"},
    "dashboard.instant_move_tip": {"ko": "현재 선택 항목을 기준으로 {noun} 탭에서 바로 검색합니다.", "en": "Open the {noun} tab filtered to the current dashboard selection."},
    "dashboard.instant_move_unavailable_title": {"ko": "즉시 이동 불가", "en": "Cannot open selection"},
    "dashboard.instant_move_unavailable_message": {"ko": "검색할 차량 또는 제작자 정보를 확인할 수 없습니다.", "en": "No vehicle or creator value is available for this selection."},
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
    "content.group_creator": {"ko": "동일 제작자로 묶기", "en": "Group by creator"},
    "content.group_creator_tip": {
        "ko": "같은 제작자의 항목을 모으고 제작자명과 현재 표시 개수를 구분 제목으로 표시합니다.",
        "en": "Group items by the same creator and show the creator name and visible item count as a section heading.",
    },
    "content.group_header": {"ko": "{vehicle} · {noun} {count}개", "en": "{vehicle} · {count} {noun}"},
    "content.creator_group_header": {"ko": "{creator} · {noun} {count}개", "en": "{creator} · {count} {noun}"},
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

    "common.copy_value": {"ko": "클릭하여 {label} 복사", "en": "Click to copy {label}"},
    "common.copy_value_detail": {"ko": "클릭하여 {label} 복사\n{value}", "en": "Click to copy {label}\n{value}"},
    "common.cancel": {"ko": "취소", "en": "Cancel"},
    "common.save": {"ko": "저장", "en": "Save"},
    "common.seconds_suffix": {"ko": "초", "en": " s"},
    "common.milliseconds_suffix": {"ko": "밀리초", "en": " ms"},
    "creator.none": {"ko": "(제작자 없음)", "en": "(No creator)"},
    "dashboard.sorting_vehicles": {"ko": "차량 목록을 정렬하는 중…", "en": "Sorting vehicle list…"},
    "dashboard.sorting_creators": {"ko": "제작자 목록을 정렬하는 중…", "en": "Sorting creator list…"},
    "dashboard.search_creator": {"ko": "제작자명 검색", "en": "Search creator"},
    "dashboard.selected_vehicle": {"ko": "차량명: {value}", "en": "Vehicle: {value}"},
    "dashboard.selected_creator": {"ko": "제작자명: {value}", "en": "Creator: {value}"},
    "navigation.pending_title": {"ko": "인게임 이동 대기 중", "en": "In-game navigation pending"},
    "navigation.pending_message": {"ko": "이미 예약된 인게임 이동이 있습니다.", "en": "An in-game navigation action is already scheduled."},
    "navigation.unavailable_title": {"ko": "인게임 이동 불가", "en": "In-game navigation unavailable"},
    "navigation.unavailable_message": {"ko": "현재 스캔 목록에서 대상 위치를 계산할 수 없습니다. 새로고침 후 다시 시도하세요.", "en": "The target position cannot be calculated from the current scan. Refresh and try again."},
    "navigation.dialog_title": {"ko": "리버리 위치로 이동", "en": "Move to livery position"},
    "navigation.description": {"ko": "FH6 리버리 목록의 첫 번째 항목을 기준으로 이동합니다. 버튼을 누르면 설정한 대기 시간 후 FH6 창을 활성화하고 방향키 입력을 시작합니다.\n\n리버리를 적용하고 목록으로 돌아오면 해당 항목이 선택됩니다.", "en": "Navigation starts from the first item in the FH6 livery list. After the configured delay, the FH6 window is activated and arrow-key input begins.\n\nAfter applying the livery and returning to the list, that item will be selected."},
    "navigation.delete_notice": {"ko": "삭제 위치로 이동한 항목은 현재 목록에서 제외됩니다. 실제 삭제를 취소한 경우 프로그램에서 목록을 새로 고치십시오.", "en": "An item navigated to for deletion is removed from the current session list. If you cancel the deletion in-game, refresh the list in the application."},
    "navigation.settings_title": {"ko": "실행 설정", "en": "Execution settings"},
    "navigation.delay": {"ko": "대기 시간", "en": "Delay"},
    "navigation.arrow_interval": {"ko": "방향키 간격", "en": "Arrow-key interval"},
    "navigation.auto_activate": {"ko": "FH6 창 자동 활성화", "en": "Automatically activate FH6 window"},
    "navigation.auto_activate_tip": {"ko": "대기 시간이 지나면 FH6 창을 찾아 전경으로 전환합니다.\n항상 위 표시가 활성화된 경우 이동 전에 이 창을 최소화합니다.", "en": "After the delay, find the FH6 window and bring it to the foreground.\nIf Always on top is enabled, this window is minimized before navigation."},
    "navigation.move_delete": {"ko": "삭제 위치로 이동", "en": "Move to delete position"},
    "navigation.move_apply": {"ko": "적용 위치로 이동", "en": "Move to apply position"},
    "navigation.delay_text": {"ko": "{value}초", "en": "{value} s"},
    "navigation.wait_auto": {"ko": "{delay} 후 FH6 창을 자동 활성화하여 이동합니다", "en": "Navigation will start after {delay} and automatically activate FH6"},
    "navigation.wait_manual": {"ko": "{delay} 후 이동합니다 — 지금 FH6 창으로 전환하세요", "en": "Navigation will start after {delay} — switch to the FH6 window now"},
    "navigation.cancelled_refresh": {"ko": "새로고침으로 예약된 인게임 이동이 취소되었습니다", "en": "Scheduled in-game navigation was cancelled by a refresh"},
    "navigation.cancelled_changed": {"ko": "대상이 변경되어 인게임 이동을 취소했습니다", "en": "In-game navigation was cancelled because the target changed"},
    "navigation.cancel_title": {"ko": "인게임 이동 취소", "en": "In-game navigation cancelled"},
    "navigation.focus_failed": {"ko": "FH6 활성 창을 확인하지 못해 키 입력을 취소했습니다", "en": "Key input was cancelled because the active FH6 window could not be verified"},
    "navigation.complete_deleted": {"ko": "{count}회 이동 완료 — 삭제 대상으로 세션 목록에 반영했습니다 ({window})", "en": "Navigation complete ({count} moves) — marked as deleted in the session list ({window})"},
    "navigation.complete_applied": {"ko": "{count}회 이동 완료 — 적용 대상 위치입니다 ({window})", "en": "Navigation complete ({count} moves) — apply target reached ({window})"},
    "navigation.no_items": {"ko": "이동 가능한 항목이 없습니다.", "en": "There are no items available for navigation."},
    "navigation.target_missing": {"ko": "대상이 현재 인게임 목록에 없습니다.", "en": "The target is not in the current in-game list."},
    "navigation.window_not_found": {"ko": "실행 중인 Forza Horizon 6 창을 찾지 못했습니다.", "en": "A running Forza Horizon 6 window could not be found."},
    "navigation.activation_failed": {"ko": "Forza Horizon 6 창을 활성화하지 못했습니다: {title}", "en": "Could not activate the Forza Horizon 6 window: {title}"},
    "navigation.windows_only": {"ko": "인게임 키 입력은 Windows에서만 지원됩니다.", "en": "In-game key input is supported only on Windows."},
    "navigation.no_active_window": {"ko": "활성 창을 확인할 수 없습니다.", "en": "The active window could not be determined."},
    "navigation.wrong_window": {"ko": "활성 창이 Forza Horizon 6이 아닙니다: {title}", "en": "The active window is not Forza Horizon 6: {title}"},
    "navigation.focus_changed": {"ko": "이동 중 활성 창이 변경되어 남은 입력을 중단했습니다.", "en": "The active window changed during navigation, so the remaining input was stopped."},
    "navigation.unsupported_key": {"ko": "지원하지 않는 이동 키: {key}", "en": "Unsupported navigation key: {key}"},
    "status.toggle_check": {"ko": "체크 상태 전환", "en": "Toggle check status"},
    "status.accessible_check": {"ko": "{noun} 체크 상태", "en": "{noun} check status"},
    "status.toggle_triangle": {"ko": "삼각형 분류 상태 전환", "en": "Toggle triangle classification"},
    "status.accessible_triangle": {"ko": "{noun} 삼각형 분류 상태", "en": "{noun} triangle classification"},
    "status.toggle_excluded": {"ko": "X 분류 상태 전환", "en": "Toggle X classification"},
    "status.accessible_excluded": {"ko": "{noun} X 분류 상태", "en": "{noun} X classification"},
    "status.checked": {"ko": "체크됨", "en": "Checked"},
    "status.unchecked": {"ko": "미체크", "en": "Unchecked"},
    "preview.enlarge": {"ko": "미리보기 크게 보기", "en": "Enlarge preview"},
    "memo.edit_suffix": {"ko": "\n\n클릭하여 메모 수정", "en": "\n\nClick to edit memo"},
    "memo.none_add": {"ko": "메모 없음\n\n클릭하여 메모 추가", "en": "No memo\n\nClick to add memo"},
    "memo.accessible": {"ko": "{noun} 메모", "en": "{noun} memo"},
    "memo.saved": {"ko": "메모 저장 완료", "en": "Memo saved"},
    "memo.creator_value": {"ko": "제작자: {creator}", "en": "Creator: {creator}"},
    "memo.creator_note_count": {"ko": "이 제작자에 대한 메모가 {count}개 존재합니다.", "en": "There are {count} memos for this creator."},
    "memo.add_same_creator": {"ko": "동일 제작자에 현재 메모 일괄 추가", "en": "Append current memo to same creator"},
    "memo.clear_same_creator": {"ko": "동일 제작자의 모든 메모 제거", "en": "Remove all memos for same creator"},
    "memo.append_confirm_title": {"ko": "동일 제작자 메모 일괄 추가", "en": "Append memo to same creator"},
    "memo.append_confirm_message": {"ko": "대상 제작자: {creator}\n대상 리버리: {targets}개\n현재 메모가 있는 항목: {existing}개\n\n기존 메모 내용은 유지되며, 현재 입력한 메모가 기존 내용 아래에 추가됩니다.\n\n계속하시겠습니까?", "en": "Creator: {creator}\nTarget liveries: {targets}\nItems that already have memos: {existing}\n\nExisting memo content will be preserved, and the current memo will be appended below it.\n\nContinue?"},
    "memo.creator_missing_title": {"ko": "제작자 정보 없음", "en": "Creator information unavailable"},
    "memo.creator_missing_apply": {"ko": "이 리버리에는 제작자 정보가 없어 일괄 추가할 수 없습니다.", "en": "This livery has no creator information, so the memo cannot be appended in bulk."},
    "memo.creator_missing_remove": {"ko": "이 리버리에는 제작자 정보가 없어 일괄 제거할 수 없습니다.", "en": "This livery has no creator information, so memos cannot be removed in bulk."},
    "memo.missing_title": {"ko": "메모 없음", "en": "No memo"},
    "memo.enter_first": {"ko": "추가할 메모를 먼저 입력하세요.", "en": "Enter the memo to append first."},
    "memo.apply_status": {"ko": "{creator} 제작자 리버리에 메모 추가 완료", "en": "Memo appended to liveries by {creator}"},
    "memo.apply_title": {"ko": "동일 제작자 메모 추가 완료", "en": "Memo appended to same creator"},
    "memo.apply_message": {"ko": "제작자: {creator}\n대상 리버리: {targets}개\n메모가 추가된 항목: {affected}개\n\n기존 메모 내용은 유지되었습니다.", "en": "Creator: {creator}\nTarget liveries: {targets}\nItems updated: {affected}\n\nExisting memo content was preserved."},
    "memo.none_to_remove_title": {"ko": "제거할 메모 없음", "en": "No memos to remove"},
    "memo.none_to_remove_message": {"ko": "{creator} 제작자의 저장된 메모가 없습니다.", "en": "There are no saved memos for liveries by {creator}."},
    "memo.clear_title": {"ko": "동일 제작자 메모 전부 제거", "en": "Remove all memos for same creator"},
    "memo.clear_message": {"ko": "제작자: {creator}\n메모가 있는 리버리: {count}개\n\n이 제작자의 모든 리버리 메모를 제거하시겠습니까?\n체크 상태는 유지됩니다.", "en": "Creator: {creator}\nLiveries with memos: {count}\n\nRemove all livery memos for this creator?\nCheck status will be preserved."},
    "memo.clear_status": {"ko": "{creator} 제작자의 메모 {count}개 제거 완료", "en": "Removed {count} memos for {creator}"},
    "memo.select_livery_title": {"ko": "리버리 선택", "en": "Select livery"},
    "memo.select_livery_message": {"ko": "세부 보기에서 리버리를 하나 선택하세요.", "en": "Select one livery in the detail view."},
    "memo.livery_title": {"ko": "리버리 메모", "en": "Livery memo"},
    "memo.tuning_title": {"ko": "튜닝 메모", "en": "Tuning memo"},
    "memo.label": {"ko": "메모", "en": "Memo"},
    "content.game_move_tip": {"ko": "인게임에서 이 썸네일 위치로 이동", "en": "Move to this thumbnail position in-game"},
    "content.game_move_accessible": {"ko": "{noun} 인게임 위치로 이동", "en": "Move to {noun} position in-game"},
    "content.livery_info_tip": {"ko": "리버리 설명 및 제작자 업로드 날짜 보기", "en": "View livery description and creator upload date"},
    "content.tuning_info_tip": {"ko": "튜닝 Data 세부 정보 보기", "en": "View tuning Data details"},
    "card.vehicle_label": {"ko": "차량명", "en": "Vehicle"},
    "card.title_label": {"ko": "제목", "en": "Title"},
    "card.creator_label": {"ko": "제작자명", "en": "Creator"},
    "db.last_update": {"ko": "/ 마지막 업데이트: {date}", "en": "/ Last update: {date}"},
    "db.local_download_time": {"ko": "로컬 DB 다운로드 시각: {value}", "en": "Local DB download time: {value}"},
    "db.source_last_modified": {"ko": "\n원본 Last-Modified: {value}", "en": "\nSource Last-Modified: {value}"},
    "db.not_updated_tip": {"ko": "아직 수동 차량 DB 업데이트를 적용하지 않았습니다.", "en": "No manual vehicle database update has been applied yet."},
    "db.update_title": {"ko": "차량 DB 업데이트", "en": "Vehicle database update"},
    "db.update_prompt": {"ko": "공개 GitHub의 FH6 CarOrdinal JSON을 내려받아 LocalAppData의 차량명 캐시만 갱신합니다.\n\n세이브 파일, 세이브 경로, XUID, 리버리/튜닝 데이터는 전송하지 않습니다. 계속하시겠습니까?", "en": "Download the public FH6 CarOrdinal JSON from GitHub and update only the vehicle-name cache in LocalAppData.\n\nSave files, save paths, XUID, livery data, and tuning data are not transmitted. Continue?"},
    "db.checking": {"ko": "업데이트 확인 중…", "en": "Checking for updates…"},
    "db.updating_busy": {"ko": "차량 DB를 내려받아 갱신하는 중…", "en": "Downloading and updating the vehicle database…"},
    "db.downloading": {"ko": "차량 DB 다운로드 중…", "en": "Downloading vehicle database…"},
    "db.update_complete_status": {"ko": "차량 DB 업데이트 완료 — {count} vehicles", "en": "Vehicle database update complete — {count} vehicles"},
    "db.update_complete_title": {"ko": "차량 DB 업데이트 완료", "en": "Vehicle database update complete"},
    "db.update_complete_message": {"ko": "{count}개의 Car ID 매핑을 적용했습니다.\n저장 위치: {path}", "en": "Applied {count} Car ID mappings.\nSaved to: {path}"},
    "db.update_failed": {"ko": "차량 DB 업데이트 실패", "en": "Vehicle database update failed"},
    "db.override_title": {"ko": "차량명 사용자 오버라이드", "en": "Custom vehicle name overrides"},
    "db.override_applied_tip": {"ko": "사용자 오버라이드 적용 중", "en": "User override applied"},
    "db.override_edit_tip": {"ko": "더블클릭하여 차량명 수정", "en": "Double-click to edit vehicle name"},
    "db.name_check_title": {"ko": "차량명 확인", "en": "Check vehicle name"},
    "db.name_empty_message": {"ko": "Car ID {car_id}의 차량명이 비어 있습니다.", "en": "The vehicle name for Car ID {car_id} is empty."},
    "db.override_save_failed": {"ko": "오버라이드 저장 실패", "en": "Failed to save overrides"},
    "db.override_saved": {"ko": "사용자 오버라이드 저장 완료 — {count}개", "en": "User overrides saved — {count}"},
    "detail.livery_info_title": {"ko": "리버리 정보", "en": "Livery information"},
    "image.none_title": {"ko": "이미지 없음", "en": "No image"},
    "image.none_message": {"ko": "이 항목의 썸네일을 찾을 수 없습니다.", "en": "The thumbnail for this item could not be found."},
    "image.read_failed": {"ko": "이미지 읽기 실패", "en": "Failed to read image"},
    "image.format_failed": {"ko": "썸네일 이미지 형식을 읽을 수 없습니다.", "en": "The thumbnail image format could not be read."},
    "image.zoom_out": {"ko": "축소", "en": "Zoom out"},
    "image.zoom_out_accessible": {"ko": "이미지 축소", "en": "Zoom out image"},
    "image.actual_size": {"ko": "원본 픽셀 크기", "en": "Actual pixel size"},
    "image.fit": {"ko": "맞춤", "en": "Fit"},
    "image.fit_tip": {"ko": "창에 맞추기", "en": "Fit to window"},
    "image.zoom_in": {"ko": "확대", "en": "Zoom in"},
    "image.zoom_in_accessible": {"ko": "이미지 확대", "en": "Zoom in image"},
    "image.hint": {"ko": "마우스 휠: 확대/축소 · 드래그: 이동 · 더블클릭: 100%", "en": "Mouse wheel: zoom · Drag: pan · Double-click: 100%"},
    "car_db.cache_older_warning": {"ko": "기존 업데이트 DB가 내장 DB보다 오래되어 사용하지 않음", "en": "Existing update database is older than the bundled database and was not used"},
    "car_db.id_positive": {"ko": "Car ID는 1 이상의 정수여야 합니다.", "en": "Car ID must be a positive integer."},
    "car_db.name_required_id": {"ko": "Car ID {car_id}의 차량명은 비워둘 수 없습니다.", "en": "The vehicle name for Car ID {car_id} cannot be empty."},
    "car_db.name_required": {"ko": "차량명은 비워둘 수 없습니다.", "en": "Vehicle name cannot be empty."},
    "car_db.response_too_large": {"ko": "차량 DB 응답이 예상 크기(1 MiB)를 초과했습니다.", "en": "The vehicle database response exceeded the expected size (1 MiB)."},
    "car_db.download_failed": {"ko": "차량 DB 다운로드 실패: {error}", "en": "Vehicle database download failed: {error}"},
    "car_db.json_failed": {"ko": "차량 DB JSON 파싱 실패: {error}", "en": "Vehicle database JSON parsing failed: {error}"},
    "car_db.too_few": {"ko": "차량 DB 항목이 {count}개뿐입니다. 불완전한 응답으로 판단하여 적용하지 않았습니다.", "en": "The vehicle database contains only {count} entries. The response appears incomplete and was not applied."},
    "car_db.root_not_object": {"ko": "차량 DB 최상위 JSON이 object가 아닙니다.", "en": "The top-level vehicle database JSON value is not an object."},
    "car_db.duplicate_id": {"ko": "동일 Car ID {car_id}에 서로 다른 이름이 존재합니다: '{first}' / '{second}'", "en": "Different names exist for the same Car ID {car_id}: '{first}' / '{second}'"},
    "car_db.cache_read_failed": {"ko": "업데이트 DB를 읽지 못함: {error}", "en": "Could not read update database: {error}"},
    "car_db.cache_format_invalid": {"ko": "업데이트 DB 형식이 잘못됨", "en": "Update database format is invalid"},
    "car_db.count_mismatch": {"ko": "업데이트 DB count 메타데이터가 실제 항목 수와 다름", "en": "Update database count metadata does not match the actual entry count"},
    "car_db.count_invalid": {"ko": "업데이트 DB count 메타데이터가 잘못됨", "en": "Update database count metadata is invalid"},
    "car_db.override_read_failed": {"ko": "사용자 override를 읽지 못함: {error}", "en": "Could not read user overrides: {error}"},
    "scanner.invalid_folder": {"ko": "선택한 경로가 폴더가 아닙니다.", "en": "The selected path is not a folder."},
    "scanner.containers_missing": {"ko": "ContainersRoot를 찾지 못했습니다. FH6 세이브 루트/current/버전 폴더 중 하나를 선택하세요.", "en": "ContainersRoot could not be found. Select the FH6 save root, current folder, or a version folder."},
    "scanner.header_missing": {"ko": "{container}: header 없음", "en": "{container}: header missing"},
    "scanner.header_parse_failed": {"ko": "{container}: header 파싱 실패 ({error})", "en": "{container}: header parsing failed ({error})"},
    "scanner.car_id_fallback": {"ko": "{container}: header Car ID {header_id} 대신 컨테이너 CarOrdinal {car_id} 사용", "en": "{container}: using container CarOrdinal {car_id} instead of header Car ID {header_id}"},
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
