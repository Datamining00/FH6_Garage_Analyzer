from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QInputDialog, QLabel

from .i18n import get_language
from .livery_preview_quality_pipeline import (
    DEFAULT_QUALITY,
    render_livery_section_quality_pipeline,
)
from .models import LiveryRecord

TEST_VERSION_LABEL = "v1.4 Quality Pipeline Test"
SHARPEN_SETTING_KEY = "livery_preview_quality_pipeline_sharpen"
QUALITY_SETTING_KEY = "livery_preview_quality_pipeline_quality"
_ACTIVE_SHARPEN = False


def _ko() -> bool:
    return str(get_language() or "").lower().startswith("ko")


def _dispatch_renderer(path, section, quality):
    return render_livery_section_quality_pipeline(
        path,
        section,
        quality,
        sharpen=_ACTIVE_SHARPEN,
    )


def apply_v1_4_quality_pipeline_patch(MainWindow) -> None:
    """Promote D to the default renderer and expose only the optional mild sharpen switch."""
    global _ACTIVE_SHARPEN
    if getattr(MainWindow, "_fh6_v14_quality_pipeline_applied", False):
        return

    from . import v1_4_native_resolution_test_patch as native_patch
    from . import v1_4_preview2_patch as preview2_patch

    preview2_patch.render_livery_section_preview2 = _dispatch_renderer
    preview2_patch.DEFAULT_QUALITY = DEFAULT_QUALITY
    preview2_patch.QUALITY_SETTING_KEY = QUALITY_SETTING_KEY

    original_text = preview2_patch._text

    def quality_text(key: str, **values) -> str:
        if _ko():
            overrides = {
                "quality_fast": "1× 빠름",
                "quality_balanced": "2× 균형",
                "quality_high": "4× 고품질",
                "quality_tip": "모든 품질은 D 기반 subpixel/high-precision renderer를 사용합니다. 기본값은 4×입니다.",
                "note": "Quality Pipeline: D 방식이 기본입니다. native geometry는 adaptive local oversampling과 float32 alpha를 사용하고 projection/mask는 고정밀 경로로 처리합니다.",
                "warning": "현재 UI는 1×/2×/4×를 지원합니다. 렌더 계획 구조는 이후 8×/16× tiled renderer를 연결할 수 있도록 분리되어 있습니다.",
            }
        else:
            overrides = {
                "quality_fast": "1× Fast",
                "quality_balanced": "2× Balanced",
                "quality_high": "4× High quality",
                "quality_tip": "Every level uses the D-derived subpixel/high-precision renderer. Default is 4×.",
                "note": "Quality Pipeline: D is the default. Native geometry uses adaptive local oversampling and float32 alpha; projection/masks use the high-precision path.",
                "warning": "The UI currently exposes 1×/2×/4×. The render-plan architecture is separated so an 8×/16× tiled backend can be attached later.",
            }
        if key in overrides:
            return overrides[key].format(**values)
        return original_text(key, **values)

    preview2_patch._text = quality_text

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
                or text.startswith("v1.4 Projection Quality Test\n")
                or text.startswith("v1.4\n")
            ):
                suffix = text.split("\n", 1)[1] if "\n" in text else "LIVERY & TUNING"
                label.setText(f"{TEST_VERSION_LABEL}\n{suffix}")
                break

    def patched_show(self: Any, record: Any) -> None:
        global _ACTIVE_SHARPEN
        if isinstance(record, LiveryRecord) and record.livery_path:
            saved_sharpen = self.settings.value(SHARPEN_SETTING_KEY, False, bool)
            if _ko():
                options = ["정확 렌더 · 샤프닝 없음", "약한 선명도 보정"]
                title = "리버리 최종 선명도"
                prompt = "D 렌더러는 항상 사용됩니다. 최종 후처리만 선택하세요."
            else:
                options = ["Exact render · no sharpening", "Mild sharpness correction"]
                title = "Livery final sharpness"
                prompt = "The D renderer is always used. Choose only the final post-process."
            current = 1 if saved_sharpen else 0
            choice, accepted = QInputDialog.getItem(self, title, prompt, options, current, False)
            if not accepted:
                return
            _ACTIVE_SHARPEN = choice == options[1]
            self.settings.setValue(SHARPEN_SETTING_KEY, _ACTIVE_SHARPEN)
            # Start each precision inspection at 4×. The viewer still permits 1×/2×.
            self.settings.setValue(native_patch.SETTING_KEY, "high")
            self.settings.setValue(QUALITY_SETTING_KEY, "high")
            self.settings.sync()
        return original_show(self, record)

    MainWindow.__init__ = patched_init
    MainWindow._show_livery_image = patched_show
    MainWindow._fh6_v14_quality_pipeline_applied = True
