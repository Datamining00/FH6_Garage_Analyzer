from __future__ import annotations

import sys
import weakref
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QWidget


@dataclass(slots=True)
class ViewStateSnapshot:
    """Restorable state for one saved-content grid.

    The card at the top of the viewport is preferred over a raw scrollbar
    value.  Group headers and responsive column changes alter the total layout
    height, so restoring only a pixel value can move the user to unrelated
    content.
    """

    content_type: str
    scroll_value: int = 0
    scroll_ratio: float = 0.0
    anchor_key: str = ""
    anchor_offset: int = 0
    page_index: int | None = None
    focused_widget: weakref.ReferenceType[QWidget] | None = None

    @classmethod
    def capture(cls, owner: Any, content_type: str) -> ViewStateSnapshot:
        snapshot = cls(content_type=content_type)

        pages = getattr(owner, "pages", None)
        if pages is not None:
            try:
                snapshot.page_index = int(pages.currentIndex())
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

        focused = QApplication.focusWidget()
        focus_belongs_to_owner = False
        if focused is not None and isinstance(owner, QWidget):
            try:
                focus_belongs_to_owner = (
                    focused is owner or owner.isAncestorOf(focused)
                )
            except RuntimeError:
                focus_belongs_to_owner = False
        if focus_belongs_to_owner:
            try:
                snapshot.focused_widget = weakref.ref(focused)
            except TypeError:
                pass

        scroll = getattr(owner, f"{content_type}_grid_scroll", None)
        if scroll is None:
            return snapshot
        try:
            scrollbar = scroll.verticalScrollBar()
            snapshot.scroll_value = int(scrollbar.value())
            maximum = max(0, int(scrollbar.maximum()))
            if maximum:
                snapshot.scroll_ratio = snapshot.scroll_value / maximum
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return snapshot

        cards = getattr(owner, f"_{content_type}_grid_cards", ())
        best_card: Any | None = None
        best_distance: int | None = None
        viewport_top = snapshot.scroll_value
        for card in cards:
            try:
                if not card.isVisible():
                    continue
                top = int(card.geometry().top())
                bottom = int(card.geometry().bottom())
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
            if bottom < viewport_top:
                continue
            distance = abs(top - viewport_top)
            if best_distance is None or distance < best_distance:
                best_card = card
                best_distance = distance

        if best_card is not None:
            try:
                snapshot.anchor_key = str(
                    best_card.property("annotationKey") or ""
                )
                snapshot.anchor_offset = int(best_card.geometry().top()) - viewport_top
            except (AttributeError, RuntimeError, TypeError, ValueError):
                snapshot.anchor_key = ""
        return snapshot

    def restore(self, owner: Any) -> None:
        """Restore immediately and after Qt's deferred layout passes."""

        owner_ref = weakref.ref(owner)

        def apply() -> None:
            target = owner_ref()
            if target is None or not isinstance(target, QObject):
                return
            try:
                pages = getattr(target, "pages", None)
                if self.page_index is not None and pages is not None:
                    pages.setCurrentIndex(self.page_index)

                scroll = getattr(
                    target,
                    f"{self.content_type}_grid_scroll",
                    None,
                )
                if scroll is not None:
                    scrollbar = scroll.verticalScrollBar()
                    value: int | None = None
                    if self.anchor_key:
                        card_map = getattr(
                            target,
                            f"_{self.content_type}_card_by_key",
                            {},
                        )
                        card = card_map.get(self.anchor_key)
                        if card is not None and card.isVisible():
                            value = int(card.geometry().top()) - self.anchor_offset
                    if value is None:
                        maximum = max(0, int(scrollbar.maximum()))
                        if maximum and self.scroll_ratio:
                            value = round(maximum * self.scroll_ratio)
                        else:
                            value = self.scroll_value
                    scrollbar.setValue(
                        max(0, min(int(value), int(scrollbar.maximum())))
                    )

                if self.focused_widget is not None:
                    widget = self.focused_widget()
                    if widget is not None and widget.isVisible():
                        widget.setFocus()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                # Window shutdown or a deleted card can race a deferred restore.
                return

        def schedule(delay_ms: int) -> None:
            target = owner_ref()
            if target is None or not isinstance(target, QObject):
                return
            try:
                timer = QTimer(target)
                timer.setSingleShot(True)
                timers = getattr(target, "_fh6_view_restore_timers", None)
                if timers is None:
                    timers = []
                    target._fh6_view_restore_timers = timers
                timers.append(timer)

                def run() -> None:
                    try:
                        apply()
                    finally:
                        current_owner = owner_ref()
                        if current_owner is not None:
                            active = getattr(
                                current_owner,
                                "_fh6_view_restore_timers",
                                [],
                            )
                            if timer in active:
                                active.remove(timer)
                        timer.deleteLater()

                timer.timeout.connect(run)
                timer.start(delay_ms)
            except (AttributeError, RuntimeError):
                return

        apply()
        schedule(0)
        schedule(30)


@dataclass(slots=True)
class _PendingViewOperation:
    generation: int
    content_type: str
    message: str
    callback: Callable[[], None]
    snapshot: ViewStateSnapshot


class ViewOperationCoordinator:
    """Coalesce expensive saved-content operations on the GUI event loop.

    Button state and preferences are updated synchronously by ``MainWindow``.
    The expensive filter/sort/group layout is queued one event-loop turn later,
    allowing the busy overlay to paint first.  If several requests arrive in
    the same interaction burst, only the newest callback runs.
    """

    def __init__(self, owner: Any) -> None:
        self._owner_ref = weakref.ref(owner)
        self._pending: _PendingViewOperation | None = None
        self._generation = 0
        self._timer_posted = False
        self._busy = False
        self.requested = 0
        self.completed = 0
        self.coalesced = 0
        self.order_cache_hits = 0
        self.order_cache_misses = 0
        self._order_cache: OrderedDict[tuple[Any, ...], tuple[Any, ...]] = (
            OrderedDict()
        )
        self._order_cache_limit = 12

    def cached_order(
        self,
        cache_key: tuple[Any, ...],
        factory: Callable[[], list[Any]],
    ) -> list[Any]:
        """Return a cached immutable ordering for repeated view rebuilds."""

        cached = self._order_cache.pop(cache_key, None)
        if cached is not None:
            self._order_cache[cache_key] = cached
            self.order_cache_hits += 1
            return list(cached)

        ordered = tuple(factory())
        self._order_cache[cache_key] = ordered
        self.order_cache_misses += 1
        while len(self._order_cache) > self._order_cache_limit:
            self._order_cache.popitem(last=False)
        return list(ordered)

    def clear_order_cache(self) -> None:
        self._order_cache.clear()

    def request(
        self,
        content_type: str,
        message: str,
        callback: Callable[[], None],
    ) -> int:
        if content_type not in {"livery", "tuning"}:
            raise ValueError(f"Unsupported content type: {content_type}")

        owner = self._owner_ref()
        if owner is None:
            return self._generation

        self._generation += 1
        self.requested += 1
        if self._pending is not None:
            self.coalesced += 1
        self._pending = _PendingViewOperation(
            generation=self._generation,
            content_type=content_type,
            message=message,
            callback=callback,
            snapshot=ViewStateSnapshot.capture(owner, content_type),
        )

        if not self._busy:
            self._busy = True
            owner._begin_busy(message)
        else:
            self._set_busy_message(owner, message)

        if not self._timer_posted:
            self._timer_posted = True
            QTimer.singleShot(0, self._run_latest)
        return self._generation

    @staticmethod
    def _set_busy_message(owner: Any, message: str) -> None:
        try:
            overlay = getattr(owner, "_busy_overlay", None)
            if overlay is not None:
                overlay.message.setText(message)
                overlay.update()
        except (AttributeError, RuntimeError):
            pass

    def _run_latest(self) -> None:
        self._timer_posted = False
        owner = self._owner_ref()
        pending = self._pending
        self._pending = None
        if owner is None or pending is None:
            self._finish(owner)
            return

        self._set_busy_message(owner, pending.message)
        try:
            pending.callback()
            self.completed += 1
            pending.snapshot.restore(owner)
        except Exception:  # noqa: BLE001 - restore busy state, then report
            exc_type, exc, traceback = sys.exc_info()
            self._finish(owner)
            if exc_type is not None and exc is not None:
                sys.excepthook(exc_type, exc, traceback)
            return

        if self._pending is not None:
            self._timer_posted = True
            QTimer.singleShot(0, self._run_latest)
            return
        self._finish(owner)

    def _finish(self, owner: Any | None) -> None:
        if self._busy and owner is not None:
            try:
                owner._end_busy()
            except (AttributeError, RuntimeError):
                pass
        self._busy = False

    def cancel_pending(self) -> None:
        """Invalidate queued work during shutdown or scan-result replacement."""

        self._generation += 1
        self._pending = None
        owner = self._owner_ref()
        self._finish(owner)

    def stats(self) -> dict[str, int]:
        return {
            "view_operations_requested": self.requested,
            "view_operations_completed": self.completed,
            "view_operations_coalesced": self.coalesced,
            "view_order_cache_hits": self.order_cache_hits,
            "view_order_cache_misses": self.order_cache_misses,
            "view_order_cache_entries": len(self._order_cache),
        }
