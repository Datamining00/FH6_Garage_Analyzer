from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QInputDialog, QLabel

from .i18n import get_language
from .livery_preview_projection_quality_test import (
    DEFAULT_MODE,
    mode_label,
    normalize_mode,
    render_livery_section_projection_quality_test,
)
from .models import LiveryRecord


TEST_VERSION_LABEL = "v1.4 Projection Quality Test"
MODE_SETTING_KEY = "livery_preview_projection_quality_test_mode"
_ACTIVE_MODE = DEFAULT_MODE


def _ko() -> bool:
    return str(get_language() or "").lower().startswith("ko")


def _dispatch_renderer(path, section, quality):
    return render_livery_section_projection_quality_test(
        path,
        section,
        quality,
        mode=_ACTIVE_MODE,
    )


def apply_v1_4_projection_quality_test_patch(MainWindow) -> None:
    """Add an A/B/C/D projection-quality selector on top of the retained-resolution test."""
    global _ACTIVE_MODE
    if getattr(MainWindow, "_fh6_v14_projection_quality_test_applied", False):
        return

    from . import v1_4_native_resolution_test_patch as native_patch
    from . import v1_4_preview2_patch as preview2_patch

    preview2_patch.render_livery_section_preview2 = _dispatch_renderer

    original_init = MainWindow.__init__
    original_show = MainWindow._show_livery_image

    def patched_init(self, project_root) -> None:
        original_init(self, project_root)
        self.setWindowTitle(f"FH6 Assistant {TEST_VERSION_LABEL}")
        for label in self.findChildren(QLabel):
            text = label.text()
            if (
                text.startswith("v1.4 Native Resolution Test\n")
                or text.startswith("v1.4 Preview 2\n")
                or text.startswith("v1.4\n")
            ):
                suffix = text.split("\n", 1)[1] if "\n" in text else "LIVERY & TUNING"
                label.setText(f"{TEST_VERSION_LABEL}\n{suffix}")
                break

    def patched_show(self: Any, record: Any) -> None:
        global _ACTIVE_MODE
        if isinstance(record, LiveryRecord) and record.livery_path:
            saved = normalize_mode(
                self.settings.value(MODE_SETTING_KEY, DEFAULT_MODE, str)
            )
            modes = ["a", "b", "c", "d"]
            options = [mode_label(mode) for mode in modes]
            current = modes.index(saved) if saved in modes else 0
            if _ko():
                title = "4× projection 품질 A/B/C/D 테스트"
                prompt = (
                    "같은 리버리·같은 면을 비교할 처리 방식을 선택하세요.\n"
                    "정확한 비교를 위해 아래 렌더 품질은 4× 정밀로 유지하는 것을 권장합니다."
                )
            else:
                title = "4× projection quality A/B/C/D test"
                prompt = (
                    "Choose the processing path for the same livery and section.\n"
                    "Keep Render quality at 4× Precision for a controlled comparison."
                )
            choice, accepted = QInputDialog.getItem(
                self,
                title,
                prompt,
                options,
                current,
                False,
            )
            if not accepted:
                return
            selected = modes[options.index(choice)]
            _ACTIVE_MODE = selected
            self.settings.setValue(MODE_SETTING_KEY, selected)
            # Every viewer starts at retained 4x. The existing 1x/2x/4x control
            # remains available for secondary experiments, but A/B/C/D comparison
            # should be done at 4x.
            self.settings.setValue(native_patch.SETTING_KEY, "high")
            self.settings.sync()
            self.setWindowTitle(
                f"FH6 Assistant {TEST_VERSION_LABEL} — {mode_label(selected)}"
            )
        return original_show(self, record)

    MainWindow.__init__ = patched_init
    MainWindow._show_livery_image = patched_show
    MainWindow._fh6_v14_projection_quality_test_applied = True
