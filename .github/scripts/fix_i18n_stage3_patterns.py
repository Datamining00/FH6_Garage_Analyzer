from pathlib import Path

path = Path('.github/scripts/apply_i18n_stage3.py')
text = path.read_text(encoding='utf-8')

patterns = [
    "ui = replace_once(ui, '''        description = QLabel(",
    "ui = replace_once(ui, '''        auto_activate_box.setToolTip(",
    "ui = replace_once(ui, '''        memo_button.setToolTip(",
    "ui = replace_once(ui, '''        QMessageBox.information(\n            self,\n            \"동일 제작자 메모 적용\"",
    "ui = replace_once(ui, '''        answer = QMessageBox.question(\n            self,\n            \"동일 제작자 메모 전부 제거\"",
    "ui = replace_once(ui, '''                tooltip += (",
]

changed = 0
for old in patterns:
    new = old.replace("ui = replace_once(ui, '''", "ui = replace_once(ui, r'''", 1)
    if old in text:
        text = text.replace(old, new, 1)
        changed += 1

if changed < 6:
    raise SystemExit(f'Expected to fix 6 raw-string patterns, fixed {changed}')

path.write_text(text, encoding='utf-8')
print(f'Fixed {changed} escaped-newline patterns')
