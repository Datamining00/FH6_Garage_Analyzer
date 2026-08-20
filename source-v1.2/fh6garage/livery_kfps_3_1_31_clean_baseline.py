from __future__ import annotations


_APPLIED = False


def apply_kfps_3_1_31_clean_baseline() -> None:
    """Keep v1.4 warning/scale UX without modifying upstream decoder order.

    The normal baseline behavior patch also installs source-offset normalization
    on ``decoder.decode_forza_source``. That is intentionally omitted here so
    this A/B build measures KFPS 3.1.31's own C_livery scene semantics exactly.
    """
    global _APPLIED
    if _APPLIED:
        return

    from . import livery_baseline_behavior_patch as baseline
    from . import livery_preview_quality_pipeline as quality_pipeline
    from . import livery_preview_tiled_quality as tiled_quality

    # Never reuse PNGs produced by the previous pinned decoder during the A/B
    # comparison. This changes cache identity only; it does not alter rendering.
    quality_pipeline.CACHE_VERSION = "v14-quality-kfps-3.1.31-clean"
    tiled_quality.CACHE_VERSION = "v14-tiled-kfps-3.1.31-clean"

    baseline._install_warning_only_integrity_policy()
    baseline._install_scale_persistence()
    baseline._clear_preview_caches()
    _APPLIED = True
