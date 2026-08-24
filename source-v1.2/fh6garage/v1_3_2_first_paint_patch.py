from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer


FIRST_PAINT_SETTLE_MS = 140
_CONTENT_TYPES = ("livery", "tuning")


def _grid_objects(self: Any, content_type: str):
    scroll = getattr(self, f"{content_type}_grid_scroll", None)
    host = getattr(self, f"{content_type}_grid_host", None)
    layout = getattr(self, f"{content_type}_grid_layout", None)
    cards = getattr(self, f"_{content_type}_grid_cards", None)
    return scroll, host, layout, cards


def _set_paint_barrier(self: Any, enabled: bool) -> None:
    """Block visible grid painting without disturbing layout calculations."""
    for content_type in _CONTENT_TYPES:
        scroll, host, _layout, _cards = _grid_objects(self, content_type)
        viewport = scroll.viewport() if scroll is not None else None
        if enabled:
            if viewport is not None:
                viewport.setUpdatesEnabled(False)
            if host is not None:
                host.setUpdatesEnabled(False)
        else:
            if host is not None:
                host.setUpdatesEnabled(True)
                host.update()
            if viewport is not None:
                viewport.setUpdatesEnabled(True)
                viewport.update()

    self._fh6_v132_first_paint_blocked = bool(enabled)


def _stabilize_content(self: Any, content_type: str) -> None:
    """Resolve columns, card widths and visible thumbnails before first paint."""
    scroll, host, layout, cards = _grid_objects(self, content_type)
    if scroll is None or host is None or layout is None or cards is None:
        return

    sync = getattr(self, f"_sync_{content_type}_grid_card_widths", None)
    if callable(sync):
        sync()

    layout.activate()

    if content_type == "livery":
        refresh = getattr(self, "_refresh_visible_livery_thumbnails", None)
    else:
        refresh = getattr(self, "_refresh_visible_tuning_thumbnails", None)
    if callable(refresh):
        refresh()

    # The aspect controller normally schedules itself for the next event-loop
    # turn. Apply it synchronously while painting is still blocked so the first
    # user-visible frame already has the correct thumbnail height.
    for card in list(cards):
        try:
            card_layout = card.layout()
            if card_layout is not None:
                card_layout.activate()
            shell = getattr(card, "_fh6_media_shell", None)
            shell_layout = shell.layout() if shell is not None else None
            if shell_layout is not None:
                shell_layout.activate()
            controller = getattr(card, "_fh6_aspect_thumbnail_controller", None)
            if controller is not None and getattr(card, "_fh6_thumbnail_loaded", False):
                controller.apply()
        except RuntimeError:
            continue

    layout.activate()


def _prepare_first_paint(self: Any, generation: int) -> None:
    if generation != getattr(self, "_fh6_v132_first_paint_generation", -1):
        return
    for content_type in _CONTENT_TYPES:
        _stabilize_content(self, content_type)

    # v1.3.1 intentionally debounces responsive column changes for 110 ms.
    # Keep the viewport unpainted slightly longer so a 2->3/4 column settle can
    # never leak the intermediate full-width card state to the user.
    QTimer.singleShot(
        FIRST_PAINT_SETTLE_MS,
        lambda owner=self, token=generation: _finish_first_paint(owner, token),
    )


def _finish_first_paint(self: Any, generation: int) -> None:
    if generation != getattr(self, "_fh6_v132_first_paint_generation", -1):
        return

    for content_type in _CONTENT_TYPES:
        _stabilize_content(self, content_type)

    _set_paint_barrier(self, False)


def apply_v1_3_2_first_paint_patch(MainWindow) -> None:
    """Hide transient saved-content layouts until their first frame is stable.

    During scan completion the grid can initially calculate the minimum two
    columns before the final viewport geometry is available. The old path then
    enables painting immediately, while width synchronization and thumbnail
    aspect correction happen on later timers. This exposes one frame containing
    an oversized card, the literal 'Thumbnail' placeholder and visually tiny
    20x20 action buttons.

    This patch blocks only painting (not event processing or geometry work)
    during _populate_all(). It resolves the final columns/widths/thumbnails,
    waits through the existing resize debounce, resolves once more, then reveals
    the grid in one stable frame.
    """
    if getattr(MainWindow, "_fh6_v132_first_paint_patched", False):
        return

    original_populate_all = MainWindow._populate_all

    def patched_populate_all(self) -> None:
        generation = getattr(self, "_fh6_v132_first_paint_generation", 0) + 1
        self._fh6_v132_first_paint_generation = generation
        _set_paint_barrier(self, True)

        try:
            original_populate_all(self)
        except Exception:
            _set_paint_barrier(self, False)
            raise

        # Re-disable the host explicitly because legacy relayout functions turn
        # host updates back on internally. The scroll viewport remains blocked
        # throughout, so no paint event can escape before this point either.
        _set_paint_barrier(self, True)
        QTimer.singleShot(
            0,
            lambda owner=self, token=generation: _prepare_first_paint(owner, token),
        )

    MainWindow._populate_all = patched_populate_all
    MainWindow._fh6_v132_set_first_paint_barrier = _set_paint_barrier
    MainWindow._fh6_v132_stabilize_first_paint_content = _stabilize_content
    MainWindow._fh6_v132_finish_first_paint = _finish_first_paint
    MainWindow._fh6_v132_first_paint_patched = True
