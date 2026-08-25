from __future__ import annotations

from .scan_result_processing import (
    assign_auction_thumbnails,
    populate_scan_result_ui,
)
from .ui import MainWindow as _UiMainWindow

__all__ = ["apply_v1_3_2_thread_affinity_fix", "assign_auction_thumbnails"]

# Capture the original Qt-decorated slot before any runtime monkey patches are
# applied. v1.3.2 previously replaced this method with plain Python functions,
# which caused ScanWorker.finished to invoke UI rebuild code in the worker thread.
_ORIGINAL_SCAN_FINISHED = _UiMainWindow._scan_finished


def apply_v1_3_2_thread_affinity_fix(MainWindow) -> None:
    """Restore GUI-thread scan completion and move v1.3.2 work into _populate_all.

    The original ui.MainWindow._scan_finished method is decorated with
    @Slot(object), so Qt queues ScanWorker.finished to the MainWindow thread.
    Replacing that slot with ordinary Python callables breaks that guarantee.

    Restore the exact original slot and perform the v1.3.2 thumbnail/index/list
    preparation from _populate_all(), which is called by that original slot after
    self.result has already been assigned on the GUI thread.
    """
    if getattr(MainWindow, "_fh6_v132_thread_affinity_fixed", False):
        return

    current_populate_all = MainWindow._populate_all

    def patched_populate_all(self) -> None:
        populate_scan_result_ui(self, lambda: current_populate_all(self))

    MainWindow._populate_all = patched_populate_all

    # Critical fix: restore the exact class-defined @Slot(object) method.
    # Do not wrap or redecorate it dynamically; preserving the original slot
    # keeps Qt AutoConnection queued to the MainWindow/GUI thread.
    MainWindow._scan_finished = _ORIGINAL_SCAN_FINISHED
    MainWindow._fh6_v132_thread_affinity_fixed = True
