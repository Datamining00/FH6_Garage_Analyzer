from __future__ import annotations

from pathlib import Path

ROOT = Path("source-v1.2/fh6garage")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label} fragment not found: {old[:160]!r}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Translation catalog
# ---------------------------------------------------------------------------
i18n_path = ROOT / "i18n.py"
i18n = i18n_path.read_text(encoding="utf-8")
marker = "\n}\n\n_TUNE_LABELS_EN"
if marker not in i18n:
    raise SystemExit("i18n catalog insertion marker not found")
if '"navigation.pending_title"' in i18n:
    raise SystemExit("stage 3 translations already present")

entries = r'''
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
    "memo.creator_missing_title": {"ko": "제작자 정보 없음", "en": "Creator information unavailable"},
    "memo.creator_missing_apply": {"ko": "이 리버리에는 제작자 정보가 없어 일괄 적용할 수 없습니다.", "en": "This livery has no creator information, so the memo cannot be applied in bulk."},
    "memo.creator_missing_remove": {"ko": "이 리버리에는 제작자 정보가 없어 일괄 제거할 수 없습니다.", "en": "This livery has no creator information, so memos cannot be removed in bulk."},
    "memo.missing_title": {"ko": "메모 없음", "en": "No memo"},
    "memo.enter_first": {"ko": "적용할 메모를 먼저 입력하세요.", "en": "Enter the memo to apply first."},
    "memo.apply_status": {"ko": "{creator} 제작자 리버리에 메모 적용 완료", "en": "Memo applied to liveries by {creator}"},
    "memo.apply_title": {"ko": "동일 제작자 메모 적용", "en": "Apply memo to same creator"},
    "memo.apply_message": {"ko": "제작자: {creator}\n대상 리버리: {targets}개\n새로 추가된 메모: {affected}개\n\n기존 메모는 유지되었습니다.", "en": "Creator: {creator}\nTarget liveries: {targets}\nNew memos added: {affected}\n\nExisting memos were preserved."},
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
'''
i18n = i18n.replace(marker, "\n" + entries + "}\n\n_TUNE_LABELS_EN", 1)
i18n_path.write_text(i18n, encoding="utf-8")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
ui_path = ROOT / "ui.py"
ui = ui_path.read_text(encoding="utf-8")

simple_ui = [
    ('        self.setToolTip(f"클릭하여 {prefix} 복사")', '        self.setToolTip(tr("common.copy_value", label=prefix))'),
    ('                bar.showMessage("클립보드에 복사되었습니다", 1000)', '                bar.showMessage(tr("common.copied"), 1000)'),
    ('        self._begin_busy("차량 목록을 정렬하는 중…")', '        self._begin_busy(tr("dashboard.sorting_vehicles"))'),
    ('        self._begin_busy("제작자 목록을 정렬하는 중…")', '        self._begin_busy(tr("dashboard.sorting_creators"))'),
    ('        dialog.setWindowTitle("리버리 위치로 이동")', '        dialog.setWindowTitle(tr("navigation.dialog_title"))'),
    ('        target_name = record.header.name or "(제목 없음)"', '        target_name = record.header.name or tr("detail.no_title")'),
    ('        settings_title = QLabel("실행 설정")', '        settings_title = QLabel(tr("navigation.settings_title"))'),
    ('        settings_layout.addWidget(QLabel("대기 시간"), 1, 0)', '        settings_layout.addWidget(QLabel(tr("navigation.delay")), 1, 0)'),
    ('        delay_spin.setSuffix("초")', '        delay_spin.setSuffix(tr("common.seconds_suffix"))'),
    ('        settings_layout.addWidget(QLabel("방향키 간격"), 2, 0)', '        settings_layout.addWidget(QLabel(tr("navigation.arrow_interval")), 2, 0)'),
    ('        arrow_interval_spin.setSuffix("밀리초")', '        arrow_interval_spin.setSuffix(tr("common.milliseconds_suffix"))'),
    ('        auto_activate_box = QCheckBox("FH6 창 자동 활성화")', '        auto_activate_box = QCheckBox(tr("navigation.auto_activate"))'),
    ('        delete_button = QPushButton("삭제 위치로 이동")', '        delete_button = QPushButton(tr("navigation.move_delete"))'),
    ('        apply_button = QPushButton("적용 위치로 이동")', '        apply_button = QPushButton(tr("navigation.move_apply"))'),
    ('        delay_text = f"{delay:g}초"', '        delay_text = tr("navigation.delay_text", value=f"{delay:g}")'),
    ('            self._show_status("새로고침으로 예약된 인게임 이동이 취소되었습니다", 5000)', '            self._show_status(tr("navigation.cancelled_refresh"), 5000)'),
    ('            self._show_status("대상이 변경되어 인게임 이동을 취소했습니다", 5000)', '            self._show_status(tr("navigation.cancelled_changed"), 5000)'),
    ('            QMessageBox.warning(self, "인게임 이동 취소", str(exc))', '            QMessageBox.warning(self, tr("navigation.cancel_title"), str(exc))'),
    ('            self._show_status("FH6 활성 창을 확인하지 못해 키 입력을 취소했습니다", 5000)', '            self._show_status(tr("navigation.focus_failed"), 5000)'),
    ('            check_item.setText("상태")', '            check_item.setText(tr("table.status"))'),
    ('        check_box.setToolTip("체크 상태 전환")', '        check_box.setToolTip(tr("status.toggle_check"))'),
    ('        triangle_box.setToolTip("삼각형 분류 상태 전환")', '        triangle_box.setToolTip(tr("status.toggle_triangle"))'),
    ('        excluded_box.setToolTip("X 분류 상태 전환")', '        excluded_box.setToolTip(tr("status.toggle_excluded"))'),
    ('        zoom_button.setToolTip("미리보기 크게 보기")', '        zoom_button.setToolTip(tr("preview.enlarge"))'),
    ('        zoom_button.setAccessibleName("미리보기 크게 보기")', '        zoom_button.setAccessibleName(tr("preview.enlarge"))'),
    ('        game_move_button.setToolTip("인게임에서 이 썸네일 위치로 이동")', '        game_move_button.setToolTip(tr("content.game_move_tip"))'),
    ('            info_tooltip = "리버리 설명 및 제작자 업로드 날짜 보기"', '            info_tooltip = tr("content.livery_info_tip")'),
    ('            info_tooltip = "튜닝 Data 세부 정보 보기"', '            info_tooltip = tr("content.tuning_info_tip")'),
    ('        vehicle = CopyValueLabel("차량명", vehicle_name)', '        vehicle = CopyValueLabel(tr("card.vehicle_label"), vehicle_name)'),
    ('        vehicle.setToolTip(f"클릭하여 차량명 복사\\n{vehicle_name}")', '        vehicle.setToolTip(tr("common.copy_value_detail", label=tr("card.vehicle_label"), value=vehicle_name))'),
    ('        title_box = CopyValueLabel("제목", content_name)', '        title_box = CopyValueLabel(tr("card.title_label"), content_name)'),
    ('        title_box.setToolTip(f"클릭하여 제목 복사\\n{content_name}")', '        title_box.setToolTip(tr("common.copy_value_detail", label=tr("card.title_label"), value=content_name))'),
    ('        creator_box = CopyValueLabel("제작자명", creator_name)', '        creator_box = CopyValueLabel(tr("card.creator_label"), creator_name)'),
    ('        creator_box.setToolTip(f"클릭하여 제작자명 복사\\n{creator_name}")', '        creator_box.setToolTip(tr("common.copy_value_detail", label=tr("card.creator_label"), value=creator_name))'),
    ('            self.db_last_update_label.setText("/ 마지막 업데이트: 확인 불가")', '            self.db_last_update_label.setText(tr("db.last_update_unavailable"))'),
    ('        self.db_update_button.setText("업데이트 확인 중…")', '        self.db_update_button.setText(tr("db.checking"))'),
    ('        self._begin_busy("차량 DB를 내려받아 갱신하는 중…")', '        self._begin_busy(tr("db.updating_busy"))'),
    ('        self._show_status("차량 DB 다운로드 중…")', '        self._show_status(tr("db.downloading"))'),
    ('        self._show_status(f"차량 DB 업데이트 완료 — {update.count} vehicles", 8000)', '        self._show_status(tr("db.update_complete_status", count=update.count), 8000)'),
    ('        self._show_status("차량 DB 업데이트 실패", 6000)', '        self._show_status(tr("db.update_failed"), 6000)'),
    ('        QMessageBox.critical(self, "차량 DB 업데이트 실패", message)', '        QMessageBox.critical(self, tr("db.update_failed"), message)'),
    ('            self.db_update_button.setText("차량 DB 업데이트 확인")', '            self.db_update_button.setText(tr("db.check_update"))'),
    ('        dialog.setWindowTitle("차량명 사용자 오버라이드")', '        dialog.setWindowTitle(tr("db.override_title"))'),
    ('        table = self._table(("Car ID", "차량명"))', '        table = self._table((tr("table.car_id"), tr("table.vehicle_name")))'),
    ('        save_button = QPushButton("저장")', '        save_button = QPushButton(tr("common.save"))'),
    ('            self.car_search.setPlaceholderText("Car ID / 차량명 검색")', '            self.car_search.setPlaceholderText(tr("dashboard.search_vehicle"))'),
    ('            self.car_search.setPlaceholderText("제작자명 검색")', '            self.car_search.setPlaceholderText(tr("dashboard.search_creator"))'),
    ('        self.selected_title.setText(f"제작자명: {creator}")', '        self.selected_title.setText(tr("dashboard.selected_creator", value=creator))'),
    ('        dialog.setWindowTitle("리버리 정보")', '        dialog.setWindowTitle(tr("detail.livery_info_title"))'),
    ('            QMessageBox.warning(self, "이미지 읽기 실패", str(exc))', '            QMessageBox.warning(self, tr("image.read_failed"), str(exc))'),
    ('        minus_button.setToolTip("축소")', '        minus_button.setToolTip(tr("image.zoom_out"))'),
    ('        minus_button.setAccessibleName("이미지 축소")', '        minus_button.setAccessibleName(tr("image.zoom_out_accessible"))'),
    ('        actual_button.setToolTip("원본 픽셀 크기")', '        actual_button.setToolTip(tr("image.actual_size"))'),
    ('        fit_button = QPushButton("맞춤")', '        fit_button = QPushButton(tr("image.fit"))'),
    ('        fit_button.setToolTip("창에 맞추기")', '        fit_button.setToolTip(tr("image.fit_tip"))'),
    ('        plus_button.setToolTip("확대")', '        plus_button.setToolTip(tr("image.zoom_in"))'),
    ('        plus_button.setAccessibleName("이미지 확대")', '        plus_button.setAccessibleName(tr("image.zoom_in_accessible"))'),
    ('        label = QLabel("메모")', '        label = QLabel(tr("memo.label"))'),
    ('        editor.setPlaceholderText("메모")', '        editor.setPlaceholderText(tr("memo.label"))'),
    ('        item.setToolTip("체크됨" if checked else "미체크")', '        item.setToolTip(tr("status.checked") if checked else tr("status.unchecked"))'),
]
for old, new in simple_ui:
    ui = replace_once(ui, old, new, "ui")

ui = replace_once(
    ui,
    '    def _begin_busy(self, message: str = "처리 중…") -> None:\n        self._busy_depth += 1',
    '    def _begin_busy(self, message: str | None = None) -> None:\n        if message is None:\n            message = tr("common.processing")\n        self._busy_depth += 1',
    "ui",
)
ui = ui.replace('"(제작자 없음)"', 'tr("creator.none")')

ui = replace_once(ui, '                "인게임 이동 대기 중",\n                "이미 예약된 인게임 이동이 있습니다.",', '                tr("navigation.pending_title"),\n                tr("navigation.pending_message"),', "ui")
ui = replace_once(ui, '                "인게임 이동 불가",\n                "현재 스캔 목록에서 대상 위치를 계산할 수 없습니다. 새로고침 후 다시 시도하세요.",', '                tr("navigation.unavailable_title"),\n                tr("navigation.unavailable_message"),', "ui")
ui = replace_once(ui, '''        description = QLabel(
            "FH6 리버리 목록의 첫 번째 항목을 기준으로 이동합니다. "
            "버튼을 누르면 설정한 대기 시간 후 FH6 창을 활성화하고 "
            "방향키 입력을 시작합니다.\n\n"
            "리버리를 적용하고 목록으로 돌아오면 해당 항목이 선택됩니다."
        )''', '        description = QLabel(tr("navigation.description"))', "ui")
ui = replace_once(ui, '''        delete_notice = QLabel(
            "삭제 위치로 이동한 항목은 현재 목록에서 제외됩니다. "
            "실제 삭제를 취소한 경우 프로그램에서 목록을 새로 고치십시오."
        )''', '        delete_notice = QLabel(tr("navigation.delete_notice"))', "ui")
ui = replace_once(ui, '''        auto_activate_box.setToolTip(
            "대기 시간이 지나면 FH6 창을 찾아 전경으로 전환합니다.\n"
            "항상 위 표시가 활성화된 경우 이동 전에 이 창을 최소화합니다."
        )''', '        auto_activate_box.setToolTip(tr("navigation.auto_activate_tip"))', "ui")
ui = ui.replace('cancel_button = QPushButton("취소")', 'cancel_button = QPushButton(tr("common.cancel"))')
ui = ui.replace('cancel_btn = QPushButton("취소")', 'cancel_btn = QPushButton(tr("common.cancel"))')
ui = ui.replace('save_btn = QPushButton("저장")', 'save_btn = QPushButton(tr("common.save"))')
ui = ui.replace('            QMessageBox.warning(self, "인게임 이동 불가", str(exc))', '            QMessageBox.warning(self, tr("navigation.unavailable_title"), str(exc))')
ui = replace_once(ui, '''        wait_message = (
            f"{delay_text} 후 FH6 창을 자동 활성화하여 이동합니다"
            if auto_activate
            else f"{delay_text} 후 이동합니다 — 지금 FH6 창으로 전환하세요"
        )''', '        wait_message = (\n            tr("navigation.wait_auto", delay=delay_text)\n            if auto_activate\n            else tr("navigation.wait_manual", delay=delay_text)\n        )', "ui")
ui = replace_once(ui, '''            message = (
                f"{count}회 이동 완료 — 삭제 대상으로 세션 목록에 반영했습니다 "
                f"({window_title})"
            )''', '            message = tr("navigation.complete_deleted", count=count, window=window_title)', "ui")
ui = replace_once(ui, '            message = f"{count}회 이동 완료 — 적용 대상 위치입니다 ({window_title})"', '            message = tr("navigation.complete_applied", count=count, window=window_title)', "ui")

ui = replace_once(ui, '        item_label = "리버리" if content_type == "livery" else "튜닝"', '        item_label = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")', "ui")
ui = replace_once(ui, '        check_box.setAccessibleName(f"{item_label} 체크 상태")', '        check_box.setAccessibleName(tr("status.accessible_check", noun=item_label))', "ui")
ui = replace_once(ui, '        triangle_box.setAccessibleName(f"{item_label} 삼각형 분류 상태")', '        triangle_box.setAccessibleName(tr("status.accessible_triangle", noun=item_label))', "ui")
ui = replace_once(ui, '        excluded_box.setAccessibleName(f"{item_label} X 분류 상태")', '        excluded_box.setAccessibleName(tr("status.accessible_excluded", noun=item_label))', "ui")
ui = replace_once(ui, '        memo_button.setAccessibleName(f"{item_label} 메모")', '        memo_button.setAccessibleName(tr("memo.accessible", noun=item_label))', "ui")
ui = replace_once(ui, '        game_move_button.setAccessibleName(f"{item_label} 인게임 위치로 이동")', '        game_move_button.setAccessibleName(tr("content.game_move_accessible", noun=item_label))', "ui")
ui = replace_once(ui, '''        memo_button.setToolTip(
            (annotation.note.strip() + "\n\n클릭하여 메모 수정")
            if annotation.note.strip()
            else "메모 없음\n\n클릭하여 메모 추가"
        )''', '        memo_button.setToolTip(\n            (annotation.note.strip() + tr("memo.edit_suffix"))\n            if annotation.note.strip()\n            else tr("memo.none_add")\n        )', "ui")

ui = ui.replace('self._show_status("메모 저장 완료", 2500)', 'self._show_status(tr("memo.saved"), 2500)')
ui = ui.replace('note\n                            + "\\n\\n클릭하여 메모 수정"', 'note\n                            + tr("memo.edit_suffix")')
ui = ui.replace('else "메모 없음\\n\\n클릭하여 메모 추가"', 'else tr("memo.none_add")')
ui = replace_once(ui, '            QMessageBox.information(self, "제작자 정보 없음", "이 리버리에는 제작자 정보가 없어 일괄 적용할 수 없습니다.")', '            QMessageBox.information(self, tr("memo.creator_missing_title"), tr("memo.creator_missing_apply"))', "ui")
ui = replace_once(ui, '            QMessageBox.information(self, "메모 없음", "적용할 메모를 먼저 입력하세요.")', '            QMessageBox.information(self, tr("memo.missing_title"), tr("memo.enter_first"))', "ui")
ui = replace_once(ui, '        self._show_status(f"{creator} 제작자 리버리에 메모 적용 완료", 3500)', '        self._show_status(tr("memo.apply_status", creator=creator), 3500)', "ui")
ui = replace_once(ui, '''        QMessageBox.information(
            self,
            "동일 제작자 메모 적용",
            f"제작자: {creator}\n대상 리버리: {sum(1 for r in self._custom_liveries() if (r.header.creator or '').strip().casefold() == creator_key)}개\n새로 추가된 메모: {affected}개\n\n기존 메모는 유지되었습니다.",
        )''', '''        QMessageBox.information(
            self,
            tr("memo.apply_title"),
            tr(
                "memo.apply_message",
                creator=creator,
                targets=sum(1 for r in self._custom_liveries() if (r.header.creator or "").strip().casefold() == creator_key),
                affected=affected,
            ),
        )''', "ui")
ui = replace_once(ui, '            QMessageBox.information(self, "제작자 정보 없음", "이 리버리에는 제작자 정보가 없어 일괄 제거할 수 없습니다.")', '            QMessageBox.information(self, tr("memo.creator_missing_title"), tr("memo.creator_missing_remove"))', "ui")
ui = replace_once(ui, '            QMessageBox.information(self, "제거할 메모 없음", f"{creator} 제작자의 저장된 메모가 없습니다.")', '            QMessageBox.information(self, tr("memo.none_to_remove_title"), tr("memo.none_to_remove_message", creator=creator))', "ui")
ui = replace_once(ui, '''        answer = QMessageBox.question(
            self,
            "동일 제작자 메모 전부 제거",
            f"제작자: {creator}\n메모가 있는 리버리: {with_notes}개\n\n"
            "이 제작자의 모든 리버리 메모를 제거하시겠습니까?\n체크 상태는 유지됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )''', '''        answer = QMessageBox.question(
            self,
            tr("memo.clear_title"),
            tr("memo.clear_message", creator=creator, count=with_notes),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )''', "ui")
ui = replace_once(ui, '        self._show_status(f"{creator} 제작자의 메모 {with_notes}개 제거 완료", 3500)', '        self._show_status(tr("memo.clear_status", creator=creator, count=with_notes), 3500)', "ui")
ui = ui.replace('(note + "\\\\n\\\\n클릭하여 메모 수정") if note else "메모 없음\\\\n\\\\n클릭하여 메모 추가"', '(note + tr("memo.edit_suffix")) if note else tr("memo.none_add")')
ui = replace_once(ui, '            QMessageBox.information(self, "리버리 선택", "세부 보기에서 리버리를 하나 선택하세요.")', '            QMessageBox.information(self, tr("memo.select_livery_title"), tr("memo.select_livery_message"))', "ui")

ui = replace_once(ui, '                f"/ 마지막 업데이트: {date_text}"', '                tr("db.last_update", date=date_text)', "ui")
ui = replace_once(ui, '            tooltip = f"로컬 DB 다운로드 시각: {raw}"', '            tooltip = tr("db.local_download_time", value=raw)', "ui")
ui = replace_once(ui, '''                tooltip += (
                    "\n원본 Last-Modified: "
                    + status.cache_source_last_modified
                )''', '                tooltip += tr("db.source_last_modified", value=status.cache_source_last_modified)', "ui")
ui = replace_once(ui, '                "아직 수동 차량 DB 업데이트를 적용하지 않았습니다."', '                tr("db.not_updated_tip")', "ui")
ui = replace_once(ui, '            "차량 DB 업데이트",\n            "공개 GitHub의 FH6 CarOrdinal JSON을 내려받아 LocalAppData의 차량명 캐시만 갱신합니다.\\n\\n"\n            "세이브 파일, 세이브 경로, XUID, 리버리/튜닝 데이터는 전송하지 않습니다. 계속하시겠습니까?",', '            tr("db.update_title"),\n            tr("db.update_prompt"),', "ui")
ui = replace_once(ui, '            "차량 DB 업데이트 완료",\n            f"{update.count}개의 Car ID 매핑을 적용했습니다.\\n저장 위치: {update.cache_path}",', '            tr("db.update_complete_title"),\n            tr("db.update_complete_message", count=update.count, path=update.cache_path),', "ui")
ui = ui.replace('name_item.setToolTip("사용자 오버라이드 적용 중")', 'name_item.setToolTip(tr("db.override_applied_tip"))')
ui = ui.replace('name_item.setToolTip("더블클릭하여 차량명 수정")', 'name_item.setToolTip(tr("db.override_edit_tip"))')
ui = replace_once(ui, '                        "차량명 확인",\n                        f"Car ID {car_id}의 차량명이 비어 있습니다.",', '                        tr("db.name_check_title"),\n                        tr("db.name_empty_message", car_id=car_id),', "ui")
ui = replace_once(ui, '                    "오버라이드 저장 실패",', '                    tr("db.override_save_failed"),', "ui")
ui = replace_once(ui, '                f"사용자 오버라이드 저장 완료 — {len(desired)}개",', '                tr("db.override_saved", count=len(desired)),', "ui")
ui = replace_once(ui, '            f"차량명: {summary.label if summary else self._car_label(car_id)}"', '            tr("dashboard.selected_vehicle", value=summary.label if summary else self._car_label(car_id))', "ui")

ui = replace_once(ui, '                "이미지 없음",\n                "이 항목의 썸네일을 찾을 수 없습니다.",', '                tr("image.none_title"),\n                tr("image.none_message"),', "ui")
ui = replace_once(ui, '                "이미지 읽기 실패",\n                "썸네일 이미지 형식을 읽을 수 없습니다.",', '                tr("image.read_failed"),\n                tr("image.format_failed"),', "ui")
ui = replace_once(ui, '        hint = QLabel(\n            "마우스 휠: 확대/축소 · 드래그: 이동 · 더블클릭: 100%"\n        )', '        hint = QLabel(tr("image.hint"))', "ui")
ui = replace_once(ui, '''        dialog.setWindowTitle(
            "리버리 메모"
            if content_type == "livery"
            else "튜닝 메모"
        )''', '        dialog.setWindowTitle(\n            tr("memo.livery_title")\n            if content_type == "livery"\n            else tr("memo.tuning_title")\n        )', "ui")

ui = ui.replace('button.setToolTip("체크 상태 전환")', 'button.setToolTip(tr("status.toggle_check"))')
ui = ui.replace('button.setToolTip("삼각형 분류 상태 전환")', 'button.setToolTip(tr("status.toggle_triangle"))')
ui = ui.replace('button.setToolTip("X 분류 상태 전환")', 'button.setToolTip(tr("status.toggle_excluded"))')
ui = replace_once(ui, '''        button.setAccessibleName(
            "리버리 체크 상태"
            if content_type == "livery"
            else "튜닝 체크 상태"
        )''', '        noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")\n        button.setAccessibleName(tr("status.accessible_check", noun=noun))', "ui")
ui = replace_once(ui, '''        button.setAccessibleName(
            "리버리 삼각형 분류 상태"
            if content_type == "livery"
            else "튜닝 삼각형 분류 상태"
        )''', '        noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")\n        button.setAccessibleName(tr("status.accessible_triangle", noun=noun))', "ui")
ui = replace_once(ui, '''        button.setAccessibleName(
            "리버리 메모"
            if content_type == "livery"
            else "튜닝 메모"
        )''', '        noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")\n        button.setAccessibleName(tr("memo.accessible", noun=noun))', "ui")
ui = replace_once(ui, '        button.setAccessibleName(\n            "리버리 X 분류 상태" if content_type == "livery" else "튜닝 X 분류 상태"\n        )', '        noun = tr("content.noun_livery") if content_type == "livery" else tr("content.noun_tuning")\n        button.setAccessibleName(tr("status.accessible_excluded", noun=noun))', "ui")
ui = ui.replace('(note + "\\\\n\\\\n클릭하여 메모 수정") if note else "메모 없음\\\\n\\\\n클릭하여 메모 추가"', '(note + tr("memo.edit_suffix")) if note else tr("memo.none_add")')
ui = ui.replace('(clean_note + "\\n\\n클릭하여 메모 수정")\n                    if clean_note\n                    else "메모 없음\\n\\n클릭하여 메모 추가"', '(clean_note + tr("memo.edit_suffix"))\n                    if clean_note\n                    else tr("memo.none_add")')
ui = ui.replace('            "메모 저장 완료",', '            tr("memo.saved"),')
ui = ui.replace('item.setToolTip(note + "\\\\n\\\\n클릭하여 메모 수정")', 'item.setToolTip(note + tr("memo.edit_suffix"))')
ui = ui.replace('item.setToolTip("메모 없음\\\\n\\\\n클릭하여 메모 추가")', 'item.setToolTip(tr("memo.none_add"))')

ui_path.write_text(ui, encoding="utf-8")


# ---------------------------------------------------------------------------
# Car database errors/warnings
# ---------------------------------------------------------------------------
car_db_path = ROOT / "car_db.py"
car_db = car_db_path.read_text(encoding="utf-8")
car_db = replace_once(car_db, 'from .models import CarName', 'from .i18n import tr\nfrom .models import CarName', "car_db")
car_replacements = [
    ('"기존 업데이트 DB가 내장 DB보다 오래되어 사용하지 않음"', 'tr("car_db.cache_older_warning")'),
    ('raise ValueError("Car ID는 1 이상의 정수여야 합니다.")', 'raise ValueError(tr("car_db.id_positive"))'),
    ('raise ValueError(f"Car ID {car_id}의 차량명은 비워둘 수 없습니다.")', 'raise ValueError(tr("car_db.name_required_id", car_id=car_id))'),
    ('raise ValueError("차량명은 비워둘 수 없습니다.")', 'raise ValueError(tr("car_db.name_required"))'),
    ('raise CarDatabaseError("차량 DB 응답이 예상 크기(1 MiB)를 초과했습니다.")', 'raise CarDatabaseError(tr("car_db.response_too_large"))'),
    ('raise CarDatabaseError(f"차량 DB 다운로드 실패: {exc}") from exc', 'raise CarDatabaseError(tr("car_db.download_failed", error=exc)) from exc'),
    ('raise CarDatabaseError(f"차량 DB JSON 파싱 실패: {exc}") from exc', 'raise CarDatabaseError(tr("car_db.json_failed", error=exc)) from exc'),
    ('f"차량 DB 항목이 {len(normalized)}개뿐입니다. 불완전한 응답으로 판단하여 적용하지 않았습니다."', 'tr("car_db.too_few", count=len(normalized))'),
    ('raise CarDatabaseError("차량 DB 최상위 JSON이 object가 아닙니다.")', 'raise CarDatabaseError(tr("car_db.root_not_object"))'),
    ('f"동일 Car ID {car_id}에 서로 다른 이름이 존재합니다: \'{previous.label}\' / \'{label}\'"', 'tr("car_db.duplicate_id", car_id=car_id, first=previous.label, second=label)'),
    ('self._load_warnings.append(f"업데이트 DB를 읽지 못함: {exc}")', 'self._load_warnings.append(tr("car_db.cache_read_failed", error=exc))'),
    ('self._load_warnings.append("업데이트 DB 형식이 잘못됨")', 'self._load_warnings.append(tr("car_db.cache_format_invalid"))'),
    ('self._load_warnings.append("업데이트 DB count 메타데이터가 실제 항목 수와 다름")', 'self._load_warnings.append(tr("car_db.count_mismatch"))'),
    ('self._load_warnings.append("업데이트 DB count 메타데이터가 잘못됨")', 'self._load_warnings.append(tr("car_db.count_invalid"))'),
    ('self._load_warnings.append(f"사용자 override를 읽지 못함: {exc}")', 'self._load_warnings.append(tr("car_db.override_read_failed", error=exc))'),
]
for old, new in car_replacements:
    if old not in car_db:
        raise SystemExit(f"car_db fragment not found: {old!r}")
    car_db = car_db.replace(old, new)
car_db_path.write_text(car_db, encoding="utf-8")


# ---------------------------------------------------------------------------
# Game navigation errors
# ---------------------------------------------------------------------------
game_path = ROOT / "game_navigation.py"
game = game_path.read_text(encoding="utf-8")
game = replace_once(game, 'from typing import Iterable\n', 'from typing import Iterable\n\nfrom .i18n import tr\n', "game_navigation")
game_replacements = [
    ('raise GameNavigationError("이동 가능한 항목이 없습니다.")', 'raise GameNavigationError(tr("navigation.no_items"))'),
    ('raise GameNavigationError("대상이 현재 인게임 목록에 없습니다.")', 'raise GameNavigationError(tr("navigation.target_missing"))'),
    ('raise GameNavigationError("실행 중인 Forza Horizon 6 창을 찾지 못했습니다.")', 'raise GameNavigationError(tr("navigation.window_not_found"))'),
    ('f"Forza Horizon 6 창을 활성화하지 못했습니다: {title or \'(제목 없음)\'}"', 'tr("navigation.activation_failed", title=title or tr("detail.no_title"))'),
    ('raise GameNavigationError("인게임 키 입력은 Windows에서만 지원됩니다.")', 'raise GameNavigationError(tr("navigation.windows_only"))'),
    ('raise GameNavigationError("활성 창을 확인할 수 없습니다.")', 'raise GameNavigationError(tr("navigation.no_active_window"))'),
    ('f"활성 창이 Forza Horizon 6이 아닙니다: {title or \'(제목 없음)\'}"', 'tr("navigation.wrong_window", title=title or tr("detail.no_title"))'),
    ('"이동 중 활성 창이 변경되어 남은 입력을 중단했습니다."', 'tr("navigation.focus_changed")'),
    ('raise GameNavigationError(f"지원하지 않는 이동 키: {name}")', 'raise GameNavigationError(tr("navigation.unsupported_key", key=name))'),
]
for old, new in game_replacements:
    if old not in game:
        raise SystemExit(f"game_navigation fragment not found: {old!r}")
    game = game.replace(old, new)
game_path.write_text(game, encoding="utf-8")


# ---------------------------------------------------------------------------
# Scanner errors/warnings
# ---------------------------------------------------------------------------
scanner_path = ROOT / "scanner.py"
scanner = scanner_path.read_text(encoding="utf-8")
scanner = replace_once(scanner, 'from .car_db import CarDatabase\n', 'from .car_db import CarDatabase\nfrom .i18n import tr\n', "scanner")
scanner_replacements = [
    ('raise SaveLayoutError("선택한 경로가 폴더가 아닙니다.")', 'raise SaveLayoutError(tr("scanner.invalid_folder"))'),
    ('raise SaveLayoutError("ContainersRoot를 찾지 못했습니다. FH6 세이브 루트/current/버전 폴더 중 하나를 선택하세요.")', 'raise SaveLayoutError(tr("scanner.containers_missing"))'),
    ('warnings.append(f"{container.name}: header 없음")', 'warnings.append(tr("scanner.header_missing", container=container.name))'),
    ('warnings.append(f"{container.name}: header 파싱 실패 ({exc})")', 'warnings.append(tr("scanner.header_parse_failed", container=container.name, error=exc))'),
    ('f"{container.name}: header Car ID {parsed_car_id} 대신 컨테이너 CarOrdinal {resolved_car_id} 사용"', 'tr("scanner.car_id_fallback", container=container.name, header_id=parsed_car_id, car_id=resolved_car_id)'),
]
for old, new in scanner_replacements:
    if old not in scanner:
        raise SystemExit(f"scanner fragment not found: {old!r}")
    scanner = scanner.replace(old, new)
scanner_path.write_text(scanner, encoding="utf-8")


# ---------------------------------------------------------------------------
# Stage 3 regression tests
# ---------------------------------------------------------------------------
tests = Path("source-v1.2/tests/test_i18n_stage3.py")
tests.write_text(r'''from __future__ import annotations

from pathlib import Path
import unittest

from fh6garage.game_navigation import GameGridSession, GameNavigationError
from fh6garage.i18n import DEFAULT_LANGUAGE, set_language, tr

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "fh6garage" / "ui.py").read_text(encoding="utf-8")
CAR_DB = (ROOT / "fh6garage" / "car_db.py").read_text(encoding="utf-8")
GAME_NAV = (ROOT / "fh6garage" / "game_navigation.py").read_text(encoding="utf-8")
SCANNER = (ROOT / "fh6garage" / "scanner.py").read_text(encoding="utf-8")

class I18nStage3Tests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(DEFAULT_LANGUAGE)

    def test_navigation_runtime_errors_follow_language(self) -> None:
        set_language("ko")
        with self.assertRaisesRegex(GameNavigationError, "이동 가능한 항목"):
            GameGridSession([]).plan_to("missing")
        set_language("en")
        with self.assertRaisesRegex(GameNavigationError, "no items available"):
            GameGridSession([]).plan_to("missing")

    def test_stage3_catalog_english(self) -> None:
        set_language("en")
        self.assertEqual(tr("common.cancel"), "Cancel")
        self.assertEqual(tr("memo.saved"), "Memo saved")
        self.assertEqual(tr("image.fit"), "Fit")
        self.assertEqual(tr("db.update_failed"), "Vehicle database update failed")
        self.assertIn("1229", tr("db.name_empty_message", car_id=1229))

    def test_ui_uses_stage3_translation_keys(self) -> None:
        for fragment in (
            'tr("navigation.dialog_title")',
            'tr("navigation.auto_activate")',
            'tr("status.toggle_check")',
            'tr("preview.enlarge")',
            'tr("memo.saved")',
            'tr("db.update_prompt")',
            'tr("db.override_title")',
            'tr("image.hint")',
            'tr("dashboard.search_creator")',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, UI)

    def test_error_modules_are_i18n_aware(self) -> None:
        self.assertIn('from .i18n import tr', CAR_DB)
        self.assertIn('tr("car_db.download_failed"', CAR_DB)
        self.assertIn('from .i18n import tr', GAME_NAV)
        self.assertIn('tr("navigation.window_not_found")', GAME_NAV)
        self.assertIn('from .i18n import tr', SCANNER)
        self.assertIn('tr("scanner.containers_missing")', SCANNER)

    def test_major_user_facing_literals_removed(self) -> None:
        for fragment in (
            'QMessageBox.information(self, "제작자 정보 없음"',
            'dialog.setWindowTitle("리버리 정보")',
            'dialog.setWindowTitle("차량명 사용자 오버라이드")',
            'setToolTip("체크 상태 전환")',
            'setToolTip("미리보기 크게 보기")',
        ):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, UI)

if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")

print("Stage 3 i18n patch prepared.")
