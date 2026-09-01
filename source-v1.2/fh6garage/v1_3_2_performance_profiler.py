from __future__ import annotations

from time import perf_counter

from PySide6.QtCore import QThread

from .performance_metrics import write_latest_performance


def apply_v1_3_2_performance_profiler(MainWindow) -> None:
    """Install the final population-performance writer after feature post-processing."""
    if getattr(MainWindow, "_fh6_v132_performance_profiler_installed", False):
        return

    def _write_population_performance(self, result, ui_started: float) -> None:
        ui_timings = {
            "ui.scan_result_to_initial_paint": round(
                (perf_counter() - ui_started) * 1000.0,
                3,
            )
        }
        indexes = getattr(self, "_fh6_record_by_key", {})
        counters = {
            "gui_thread_confirmed": QThread.currentThread() is self.thread(),
            "livery_index_entries": len(indexes.get("livery", {})),
            "tuning_index_entries": len(indexes.get("tuning", {})),
            "livery_cards_created": getattr(
                self, "_fh6_ui_livery_cards_created", 0
            ),
            "livery_cards_reused": getattr(
                self, "_fh6_ui_livery_cards_reused", 0
            ),
            "tuning_cards_created": getattr(
                self, "_fh6_ui_tuning_cards_created", 0
            ),
            "tuning_cards_reused": getattr(
                self, "_fh6_ui_tuning_cards_reused", 0
            ),
            "cards_discarded": getattr(self, "_fh6_ui_cards_discarded", 0),
        }
        pixmaps = getattr(self, "_fh6_thumbnail_pixmap_cache", None)
        if pixmaps is not None and hasattr(pixmaps, "stats"):
            counters.update(pixmaps.stats())
        refresh_diff = getattr(self, "_fh6_latest_livery_diff", None)
        if refresh_diff is not None:
            counters.update(
                {
                    "refresh_thumbnail_cache_files": getattr(
                        refresh_diff, "cache_files", 0
                    ),
                    "refresh_thumbnail_cache_bytes": getattr(
                        refresh_diff, "cache_bytes", 0
                    ),
                    "refresh_cache_cleanup_removed_files": getattr(
                        refresh_diff, "cleanup_removed_files", 0
                    ),
                    "refresh_cache_cleanup_removed_bytes": getattr(
                        refresh_diff, "cleanup_removed_bytes", 0
                    ),
                }
            )
        write_latest_performance(
            {
                "app_version": "1.3.2",
                "scan": getattr(result, "diagnostics", {}),
                "ui": {
                    "timings_ms": ui_timings,
                    "counters": counters,
                },
            }
        )

    MainWindow._fh6_v132_write_population_performance = _write_population_performance
    MainWindow._fh6_v132_performance_profiler_installed = True
