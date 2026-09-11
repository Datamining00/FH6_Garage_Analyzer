from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ALLOWED = {
    "SCAN", "INDEX", "THUMBNAIL", "POPULATE",
    "MEMORY", "NAVIGATION", "PERFORMANCE", "THREAD",
}
_MAX_BYTES = 2 * 1024 * 1024
_ROTATIONS = 2
_lock = threading.RLock()


def log_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "FH6GarageAnalyzer" / "logs"


def log_path() -> Path:
    return log_dir() / "diagnostic.log"


def _rotate(path: Path) -> None:
    try:
        if not path.is_file() or path.stat().st_size < _MAX_BYTES:
            return
    except OSError:
        return
    for index in range(_ROTATIONS, 0, -1):
        src = path if index == 1 else path.with_suffix(path.suffix + f".{index - 1}")
        dst = path.with_suffix(path.suffix + f".{index}")
        try:
            if src.exists():
                dst.unlink(missing_ok=True)
                src.replace(dst)
        except OSError:
            pass


def _safe(value: Any) -> str:
    text = str(value)
    return text.replace("\r", " ").replace("\n", " ")[:240]


def log_event(subsystem: str, event: str, **fields: Any) -> None:
    """Append one non-blocking subsystem diagnostic entry."""
    tag = str(subsystem).upper()
    if tag not in _ALLOWED:
        tag = "PERFORMANCE"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    details = " ".join(
        f"{key}={_safe(value)}" for key, value in sorted(fields.items())
        if value is not None
    )
    line = f"{timestamp} [{tag}] {_safe(event)}"
    if details:
        line += " " + details
    try:
        with _lock:
            path = log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate(path)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
    except OSError:
        pass
