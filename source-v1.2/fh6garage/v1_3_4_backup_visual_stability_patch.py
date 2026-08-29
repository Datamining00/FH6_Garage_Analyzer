from __future__ import annotations

from typing import Any

from . import v1_3_4_backup_export_patch as _backup_ui
from . import v1_3_4_backup_loading_resilience_patch as _resilience


_ORIGINAL_SMOOTH_RELAYOUT = _resilience._smooth_relayout_backup
_ORIGINAL_FINISH_RELAYOUT = _resilience._finish_relayout


def _set_backup_grid_updates(window: Any, enabled: bool) -> None:
    """Freeze only the backup grid paint while time-sliced layout is in flight.

    The loading dialog is a separate top-level widget, so its indeterminate
    progress animation continues to repaint while the grid itself stays visually
    stable. Geometry may change internally, but users see only the final layout.
    """
    seen: set[int] = set()
    targets: list[Any] = []

    scroll = getattr(window, "backup_grid_scroll", None)
    if scroll is not None:
        targets.append(scroll)
        try:
            viewport = scroll.viewport()
        except RuntimeError:
            viewport = None
        if viewport is not None:
            targets.append(viewport)

    host = getattr(window, "backup_grid_host", None)
    if host is not None:
        targets.append(host)

    for target in targets:
        if id(target) in seen:
            continue
        seen.add(id(target))
        try:
            target.setUpdatesEnabled(bool(enabled))
            if enabled:
                target.update()
        except RuntimeError:
            pass


def _finish_relayout_without_jitter(
    window: Any,
    generation: int,
    started_ns: int,
    visible_cards: int,
) -> None:
    try:
        _ORIGINAL_FINISH_RELAYOUT(window, generation, started_ns, visible_cards)
    finally:
        current = int(getattr(window, "_fh6_backup_relayout_generation", 0) or 0)
        active = bool(getattr(window, "_fh6_backup_relayout_active", False))
        if generation == current and not active:
            _set_backup_grid_updates(window, True)


def _relayout_without_jitter(window: Any) -> None:
    # The previous implementation intentionally exposed each 8-card chunk with
    # show()/setFixedWidth(). QGridLayout and QScrollArea therefore recalculated
    # geometry on every timer tick, producing visible vertical card shaking.
    # Keep the same time-sliced workload but suppress repaint until completion.
    _set_backup_grid_updates(window, False)
    try:
        _ORIGINAL_SMOOTH_RELAYOUT(window)
    except Exception:
        _set_backup_grid_updates(window, True)
        raise

    # Planning can fail synchronously (for example if widgets were destroyed).
    # In that case there will be no async finish callback to thaw the grid.
    if not bool(getattr(window, "_fh6_backup_relayout_active", False)):
        _set_backup_grid_updates(window, True)


def apply_v1_3_4_backup_visual_stability_patch(MainWindow: Any) -> None:
    if getattr(MainWindow, "_fh6_v134_backup_visual_stability_patched", False):
        return

    # _smooth_relayout_backup resolves _finish_relayout through its module
    # globals at runtime, so replacing it here thaws the frozen grid exactly at
    # the final generation's completion without changing the chunking logic.
    _resilience._finish_relayout = _finish_relayout_without_jitter
    _backup_ui._relayout_backup = _relayout_without_jitter
    MainWindow._fh6_v134_backup_visual_stability_patched = True
