from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "source-v1.2" / "fh6garage" / "ui.py"
TEST_PATH = ROOT / "source-v1.2" / "tests" / "test_v1_3_features.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


ui = UI_PATH.read_text(encoding="utf-8")
ui = replace_once(
    ui,
    '''            def clear_creator_notes() -> None:\n                self._clear_notes_for_same_creator(key)\n                refresh_creator_count()\n''',
    '''            def clear_creator_notes() -> None:\n                self._clear_notes_for_same_creator(key)\n                # The selected livery was cleared by the creator-wide action too.\n                # Keep the open editor in sync so pressing Save cannot restore it.\n                editor.clear()\n                refresh_creator_count()\n''',
    "clear creator notes editor sync",
)
UI_PATH.write_text(ui, encoding="utf-8")

test = TEST_PATH.read_text(encoding="utf-8")
test = replace_once(
    test,
    '''        self.assertIn('tr("memo.append_confirm_message"', UI)\n''',
    '''        self.assertIn('"memo.append_confirm_message"', UI)\n''',
    "memo confirmation test",
)
TEST_PATH.write_text(test, encoding="utf-8")

print("FH6 Assistant v1.3 verification patch applied successfully.")
