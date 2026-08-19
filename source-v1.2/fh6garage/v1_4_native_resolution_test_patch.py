from __future__ import annotations

from PySide6.QtWidgets import QLabel

from .i18n import get_language
from .livery_preview_native_resolution_test import (
    DEFAULT_QUALITY,
    render_livery_section_native_resolution_test,
)


TEST_VERSION_LABEL = "v1.4 Native Resolution Test"
SETTING_KEY = "livery_preview_native_resolution_test_quality"


def _ko() -> bool:
    return str(get_language() or "").lower().startswith("ko")


def apply_v1_4_native_resolution_test_patch(MainWindow) -> None:
    """Switch Preview 2 to retained 1x/2x/4x output for visual A/B testing."""
    if getattr(MainWindow, "_fh6_v14_native_resolution_test_applied", False):
        return

    from . import v1_4_preview2_patch as preview2_patch

    preview2_patch.render_livery_section_preview2 = render_livery_section_native_resolution_test
    preview2_patch.DEFAULT_QUALITY = DEFAULT_QUALITY
    preview2_patch.QUALITY_SETTING_KEY = SETTING_KEY

    original_text = preview2_patch._text

    def test_text(key: str, **values) -> str:
        if _ko():
            overrides = {
                "quality_fast": "1× 원본 밀도",
                "quality_balanced": "2× 고해상도",
                "quality_high": "4× 정밀",
                "quality_tip": "최종 projection 결과를 다시 2048×1024로 축소하지 않습니다. 1×=2048×1024, 2×=4096×2048, 4×=8192×4096 atlas 밀도입니다.",
                "note": "Native Resolution Test: 차량 projection/mask까지 같은 배율로 계산한 뒤 최종 crop 해상도를 그대로 유지합니다.",
                "warning": "기본값은 4×입니다. 4×는 메모리를 많이 사용할 수 있으며, 완성된 결과는 별도 디스크 캐시에서 재사용됩니다.",
            }
        else:
            overrides = {
                "quality_fast": "1× native density",
                "quality_balanced": "2× high resolution",
                "quality_high": "4× precision",
                "quality_tip": "The finished projection is not reduced back to 2048×1024. 1×=2048×1024, 2×=4096×2048, 4×=8192×4096 atlas density.",
                "note": "Native Resolution Test: projection and vehicle-mask processing stay at the selected scale and the final crop keeps that raster density.",
                "warning": "Default is 4×. 4× may use substantial memory; completed results are reused from a separate disk cache.",
            }
        if key in overrides:
            return overrides[key].format(**values)
        return original_text(key, **values)

    preview2_patch._text = test_text

    original_init = MainWindow.__init__

    def patched_init(self, project_root) -> None:
        original_init(self, project_root)
        self.setWindowTitle(f"FH6 Assistant {TEST_VERSION_LABEL}")
        for label in self.findChildren(QLabel):
            text = label.text()
            if text.startswith("v1.4 Preview 2\n") or text.startswith("v1.4 Web Canvas Test\n") or text.startswith("v1.4\n"):
                suffix = text.split("\n", 1)[1] if "\n" in text else "LIVERY & TUNING"
                label.setText(f"{TEST_VERSION_LABEL}\n{suffix}")
                break

    MainWindow.__init__ = patched_init
    MainWindow._fh6_v14_native_resolution_test_applied = True
