from __future__ import annotations


_APPLIED = False


def apply_kfps_3_1_31_clean_baseline() -> None:
    """Keep v1.4 warning/scale UX without modifying upstream decoder order.

    The normal baseline behavior patch also installs source-offset normalization
    on ``decoder.decode_forza_source``.  That is intentionally omitted here so
    this A/B build measures KFPS 3.1.31's own C_livery scene semantics exactly.
    """
    global _APPLIED
    if _APPLIED:
        return

    from . import livery_baseline_behavior_patch as baseline

    baseline._install_warning_only_integrity_policy()
    baseline._install_scale_persistence()
    baseline._clear_preview_caches()
    _APPLIED = True
