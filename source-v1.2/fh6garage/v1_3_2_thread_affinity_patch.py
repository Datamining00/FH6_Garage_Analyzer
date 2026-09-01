from __future__ import annotations

from .v1_3_2_performance_profiler import apply_v1_3_2_performance_profiler
from .v1_3_2_scan_postprocessing import (
    apply_v1_3_2_scan_postprocessing,
    assign_auction_thumbnails,
)
from .ui import MainWindow as _UiMainWindow

# Capture the original Qt-decorated slot before any runtime monkey patches are
# applied. v1.3.2 previously replaced this method with plain Python functions,
# which caused ScanWorker.finished to invoke UI rebuild code in the worker thread.
_ORIGINAL_SCAN_FINISHED = _UiMainWindow._scan_finished


def apply_v1_3_2_thread_affinity_fix(MainWindow) -> None:
    """Restore the original Qt-decorated scan completion slot as the final patch."""
    if getattr(MainWindow, "_fh6_v132_thread_affinity_fixed", False):
        return

    # Critical fix: restore the exact class-defined @Slot(object) method.
    # Do not wrap or redecorate it dynamically; preserving the original slot
    # keeps Qt AutoConnection queued to the MainWindow/GUI thread.
    MainWindow._scan_finished = _ORIGINAL_SCAN_FINISHED
    MainWindow._fh6_v132_thread_affinity_fixed = True
