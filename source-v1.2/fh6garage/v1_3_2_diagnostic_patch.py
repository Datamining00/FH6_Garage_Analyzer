from __future__ import annotations

import faulthandler
import os
import threading
import time
from pathlib import Path


def _diagnostic_log_path() -> Path:
    raw = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(raw) if raw else Path.home()
    path = base / "FH6 Assistant" / "diagnostics" / "v1.3.2-startup.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_log(message: str) -> None:
    try:
        path = _diagnostic_log_path()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def _dump_threads(reason: str) -> None:
    try:
        path = _diagnostic_log_path()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{stamp}] WATCHDOG: {reason}\n")
            faulthandler.dump_traceback(file=handle, all_threads=True)
            handle.write("\n")
    except Exception:
        pass


def apply_v1_3_2_diagnostic_patches(MainWindow) -> None:
    """Instrument the real Windows startup path without changing list semantics.

    This patch is intentionally diagnostic. It records the exact stage and livery
    card index reached by the GUI and dumps Python thread stacks if no progress is
    observed for 12 seconds while the livery rebuild is active.
    """
    if getattr(MainWindow, "_fh6_v132_diagnostic_patched", False):
        return

    original_populate_saved_content_table = MainWindow._populate_saved_content_table
    original_populate_livery_grid = MainWindow._populate_livery_grid
    original_make_livery_card = MainWindow._make_livery_card
    original_relayout_livery_grid = MainWindow._relayout_livery_grid
    original_refresh_visible_livery_thumbnails = MainWindow._refresh_visible_livery_thumbnails
    original_scan_finished = MainWindow._scan_finished
    original_scan_failed = MainWindow._scan_failed

    def mark(self, stage: str, *, overlay: str | None = None) -> None:
        self._fh6_diag_stage = stage
        self._fh6_diag_last_progress = time.monotonic()
        _append_log(stage)
        if overlay and hasattr(self, "_busy_overlay"):
            try:
                self._busy_overlay.message.setText(overlay)
            except Exception:
                pass

    def start_watchdog(self) -> None:
        generation = getattr(self, "_fh6_diag_watchdog_generation", 0) + 1
        self._fh6_diag_watchdog_generation = generation
        self._fh6_diag_watchdog_active = True

        def watch() -> None:
            last_dump_for = ""
            while getattr(self, "_fh6_diag_watchdog_active", False):
                if generation != getattr(self, "_fh6_diag_watchdog_generation", generation):
                    return
                time.sleep(2.0)
                last_progress = float(getattr(self, "_fh6_diag_last_progress", time.monotonic()))
                stalled = time.monotonic() - last_progress
                stage = str(getattr(self, "_fh6_diag_stage", "unknown"))
                if stalled >= 12.0 and stage != last_dump_for:
                    _dump_threads(f"no progress for {stalled:.1f}s at stage: {stage}")
                    last_dump_for = stage

        threading.Thread(target=watch, name="FH6-v132-watchdog", daemon=True).start()

    def stop_watchdog(self) -> None:
        self._fh6_diag_watchdog_active = False
        self._fh6_diag_watchdog_generation = (
            getattr(self, "_fh6_diag_watchdog_generation", 0) + 1
        )

    def patched_populate_saved_content_table(self, content_type: str) -> None:
        if content_type != "livery":
            return original_populate_saved_content_table(self, content_type)
        try:
            total = len(self._sorted_saved_content("livery"))
        except Exception:
            total = -1
        mark(self, f"livery table START total={total}", overlay="리버리 표 구성 중…")
        original_populate_saved_content_table(self, content_type)
        mark(self, f"livery table END rows={self.livery_table.rowCount()}")

    def patched_populate_livery_grid(self) -> None:
        try:
            total = len(self._sorted_liveries())
        except Exception:
            total = -1
        self._fh6_diag_card_index = 0
        self._fh6_diag_card_total = total
        mark(self, f"livery grid START total={total}", overlay=f"리버리 카드 구성 0/{total if total >= 0 else '?'}")
        original_populate_livery_grid(self)
        mark(self, f"livery grid END cards={len(self._livery_grid_cards)}")

    def patched_make_livery_card(self, record, key):
        index = int(getattr(self, "_fh6_diag_card_index", 0)) + 1
        self._fh6_diag_card_index = index
        total = int(getattr(self, "_fh6_diag_card_total", -1))
        container_name = str(getattr(record, "container_name", ""))
        if index == 1 or index % 10 == 0 or index == total:
            total_text = str(total) if total >= 0 else "?"
            mark(
                self,
                f"livery card BEGIN {index}/{total_text} {container_name}",
                overlay=f"리버리 카드 구성 {index}/{total_text}",
            )
        card = original_make_livery_card(self, record, key)
        if index == 1 or index % 10 == 0 or index == total:
            self._fh6_diag_last_progress = time.monotonic()
            _append_log(f"livery card END {index}/{total if total >= 0 else '?'} {container_name}")
        return card

    def patched_relayout_livery_grid(self, text: str = "") -> None:
        mark(self, "livery relayout START", overlay="리버리 레이아웃 구성 중…")
        original_relayout_livery_grid(self, text)
        mark(self, "livery relayout END")

    def patched_refresh_visible_livery_thumbnails(self) -> None:
        mark(self, "visible thumbnail refresh START")
        original_refresh_visible_livery_thumbnails(self)
        mark(self, "visible thumbnail refresh END")

    def patched_scan_finished(self, result) -> None:
        try:
            path = _diagnostic_log_path()
            path.write_text("FH6 Assistant v1.3.2 startup diagnostic\n", encoding="utf-8")
        except Exception:
            pass
        mark(self, "scan finished callback START")
        start_watchdog(self)
        try:
            original_scan_finished(self, result)
            mark(self, "scan finished callback END")
        finally:
            stop_watchdog(self)

    def patched_scan_failed(self, message: str) -> None:
        _append_log(f"scan FAILED: {message}")
        stop_watchdog(self)
        original_scan_failed(self, message)

    MainWindow._populate_saved_content_table = patched_populate_saved_content_table
    MainWindow._populate_livery_grid = patched_populate_livery_grid
    MainWindow._make_livery_card = patched_make_livery_card
    MainWindow._relayout_livery_grid = patched_relayout_livery_grid
    MainWindow._refresh_visible_livery_thumbnails = patched_refresh_visible_livery_thumbnails
    MainWindow._scan_finished = patched_scan_finished
    MainWindow._scan_failed = patched_scan_failed
    MainWindow._fh6_v132_diagnostic_log_path = staticmethod(_diagnostic_log_path)
    MainWindow._fh6_v132_diagnostic_patched = True
