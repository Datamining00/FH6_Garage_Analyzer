"""Compatibility exports for the integrated thumbnail display."""

from .thumbnail_display import (
    DEFAULT_THUMBNAIL_ASPECT,
    _AspectFitThumbnailController,
    _configure_aspect_card,
    _load_original_pixmap,
    _relax_fixed_card_text_heights,
)


def apply_v1_3_2_global_ui_patch(MainWindow) -> None:
    MainWindow._fh6_v132_global_ui_integrated = True


__all__ = [
    "DEFAULT_THUMBNAIL_ASPECT",
    "_AspectFitThumbnailController",
    "_configure_aspect_card",
    "_load_original_pixmap",
    "_relax_fixed_card_text_heights",
    "apply_v1_3_2_global_ui_patch",
]
