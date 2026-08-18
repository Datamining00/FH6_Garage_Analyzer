from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QInputDialog, QLabel

from .i18n import get_language
from .models import LiveryRecord
from .web_canvas_preview import render_livery_section_web_canvas

WEB_TEST_VERSION_LABEL = "v1.4 Web Canvas Test"
RENDERER_SETTING_KEY = "livery_preview_renderer_web_canvas_test"
_ACTIVE_BACKEND = "pillow"
_REFERENCE_RENDERER = None


def _ko() -> bool:
    return str(get_language() or "").lower().startswith("ko")


def _dispatch_renderer(path, section, quality):
    if _ACTIVE_BACKEND == "web":
        return render_livery_section_web_canvas(path, section, quality)
    if _REFERENCE_RENDERER is None:
        raise RuntimeError("Pillow reference renderer is not initialized.")
    return _REFERENCE_RENDERER(path, section, quality)


def apply_v1_4_web_canvas_test_patch(MainWindow) -> None:
    """Add a per-viewer Pillow/Web Canvas A/B choice without changing final v1.4 files."""
    global _REFERENCE_RENDERER
    if getattr(MainWindow, "_fh6_v14_web_canvas_test_applied", False):
        return

    from . import v1_4_preview2_patch as preview2_patch

    _REFERENCE_RENDERER = preview2_patch.render_livery_section_preview2
    preview2_patch.render_livery_section_preview2 = _dispatch_renderer

    original_init = MainWindow.__init__
    original_show = MainWindow._show_livery_image

    def patched_init(self, project_root) -> None:
        original_init(self, project_root)
        self.setWindowTitle(f"FH6 Assistant {WEB_TEST_VERSION_LABEL}")
        for label in self.findChildren(QLabel):
            text = label.text()
            if text.startswith("v1.4 Preview 2\n") or text.startswith("v1.4\n"):
                suffix = text.split("\n", 1)[1] if "\n" in text else "LIVERY & TUNING"
                label.setText(f"{WEB_TEST_VERSION_LABEL}\n{suffix}")
                break

    def patched_show(self: Any, record: Any) -> None:
        global _ACTIVE_BACKEND
        if isinstance(record, LiveryRecord) and record.livery_path:
            saved = str(self.settings.value(RENDERER_SETTING_KEY, "pillow", str) or "pillow").lower()
            options = (
                ["Pillow (현재 기준)", "Web Canvas (Edge Canvas2D)"]
                if _ko()
                else ["Pillow (reference)", "Web Canvas (Edge Canvas2D)"]
            )
            current = 1 if saved == "web" else 0
            title = "리버리 렌더러 A/B 테스트" if _ko() else "Livery renderer A/B test"
            prompt = (
                "이번 미리보기에 사용할 렌더러를 선택하세요.\n같은 면·같은 품질로 두 렌더러를 비교할 수 있습니다."
                if _ko()
                else "Choose the renderer for this preview.\nCompare both backends using the same section and quality."
            )
            choice, accepted = QInputDialog.getItem(self, title, prompt, options, current, False)
            if not accepted:
                return
            _ACTIVE_BACKEND = "web" if choice == options[1] else "pillow"
            self.settings.setValue(RENDERER_SETTING_KEY, _ACTIVE_BACKEND)
            backend_label = "Web Canvas" if _ACTIVE_BACKEND == "web" else "Pillow"
            self.setWindowTitle(f"FH6 Assistant {WEB_TEST_VERSION_LABEL} — {backend_label}")
        return original_show(self, record)

    MainWindow.__init__ = patched_init
    MainWindow._show_livery_image = patched_show
    MainWindow._fh6_v14_web_canvas_test_applied = True
