from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel

from .livery_preview_mask_semantics import validate_exact_assets_and_filter_noops
from .livery_preview_quality_pipeline import (
    DEFAULT_QUALITY,
    render_livery_section_quality_pipeline,
)
from .livery_preview_raster_policy import (
    filter_missing_visible_rasters,
    preflight_raster_layers_fail_soft,
)
from .models import LiveryRecord

TEST_VERSION_LABEL = "v1.4 Quality Pipeline Test"
SHARPEN_SETTING_KEY = "livery_preview_quality_pipeline_sharpen"
QUALITY_SETTING_KEY = "livery_preview_quality_pipeline_quality"


def _dispatch_renderer(path, section, quality):
    return render_livery_section_quality_pipeline(
        path,
        section,
        quality,
        sharpen=False,
    )


def apply_v1_4_quality_pipeline_patch(MainWindow) -> None:
    """Promote the D-derived exact renderer as the fixed default path."""
    if getattr(MainWindow, "_fh6_v14_quality_pipeline_applied", False):
        return

    from . import livery_preview as preview_core
    from . import livery_preview_quality_pipeline as quality_pipeline
    from . import livery_preview_tiled_quality as tiled_quality
    from . import v1_4_preview2_patch as preview2_patch

    def fail_soft_preflight(layers, raster_resolver) -> None:
        _decoder, renderer = preview_core._load_backend()
        preflight_raster_layers_fail_soft(renderer, layers, raster_resolver)

    def fail_soft_validator(renderer, layers, raster_resolver):
        filtered, _missing_ids = filter_missing_visible_rasters(renderer, layers, raster_resolver)
        return validate_exact_assets_and_filter_noops(renderer, filtered, raster_resolver)

    # Correct the zero-alpha native mask handling for every preview path that is
    # active in this process. Normal native masks are geometry cutouts and must
    # not be removed merely because their color alpha is zero.
    preview_core._validate_exact_assets_and_filter_noops = fail_soft_validator
    quality_pipeline._validate_exact_assets_and_filter_noops = fail_soft_validator
    tiled_quality.validate_exact_assets_and_filter_noops = fail_soft_validator

    # A missing non-mask built-in raster decal must not abort an otherwise useful
    # section preview. Missing raster masks remain fatal because cutout semantics
    # cannot be reconstructed safely without the source texture.
    quality_pipeline._preflight_raster_layers = fail_soft_preflight
    tiled_quality._preflight_raster_layers = fail_soft_preflight

    preview2_patch.render_livery_section_preview2 = _dispatch_renderer
    preview2_patch.DEFAULT_QUALITY = DEFAULT_QUALITY
    preview2_patch.QUALITY_SETTING_KEY = QUALITY_SETTING_KEY

    original_text = preview2_patch._text

    def quality_text(key: str, **values) -> str:
        overrides_ko = {
            "quality_fast": "1× 빠름",
            "quality_balanced": "2× 균형",
            "quality_high": "4× 고품질",
            "quality_tip": "모든 품질은 고정밀 D 기반 renderer를 사용합니다. 기본값은 4×입니다.",
            "note": "",
            "warning": "",
        }
        overrides_en = {
            "quality_fast": "1× Fast",
            "quality_balanced": "2× Balanced",
            "quality_high": "4× High quality",
            "quality_tip": "Every level uses the high-precision D-derived renderer. Default is 4×.",
            "note": "",
            "warning": "",
        }
        from .i18n import get_language
        overrides = overrides_ko if str(get_language() or "").lower().startswith("ko") else overrides_en
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
        if isinstance(record, LiveryRecord) and record.livery_path:
            # Exact render with no sharpening is the fixed default. No modal
            # sharpness question is shown when opening the preview anymore.
            self.settings.setValue(SHARPEN_SETTING_KEY, False)
            self.settings.setValue(QUALITY_SETTING_KEY, "high")
            self.settings.sync()
        return original_show(self, record)

    MainWindow.__init__ = patched_init
    MainWindow._show_livery_image = patched_show
    MainWindow._fh6_v14_quality_pipeline_applied = True
