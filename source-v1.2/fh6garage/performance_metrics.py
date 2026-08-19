from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_LOCK = threading.RLock()
_SCHEMA = 1


def _base_dir() -> Path:
    override = os.environ.get("FH6_ASSISTANT_PERF_DIR")
    if override:
        return Path(override)
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "FH6GarageAnalyzer"


def metrics_path() -> Path:
    return _base_dir() / "performance_last.json"


def _read_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema": _SCHEMA, "metrics": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"schema": _SCHEMA, "metrics": {}}
    if not isinstance(payload, dict) or payload.get("schema") != _SCHEMA:
        return {"schema": _SCHEMA, "metrics": {}}
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    return {"schema": _SCHEMA, "metrics": metrics}


def record_metric(name: str, duration_ms: float, **details: Any) -> None:
    """Persist the latest timing for one performance stage.

    This intentionally stores only the latest value for each metric so profiling
    does not grow an unbounded log in LocalAppData.
    """
    path = metrics_path()
    with _LOCK:
        payload = _read_payload(path)
        payload["updated_utc"] = datetime.now(timezone.utc).isoformat()
        metrics = payload.setdefault("metrics", {})
        metrics[str(name)] = {
            "duration_ms": round(float(duration_ms), 3),
            **details,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        except OSError:
            # Performance telemetry is diagnostic-only and must never interrupt
            # save scanning or preview rendering.
            return


def read_metrics() -> dict[str, Any]:
    with _LOCK:
        return _read_payload(metrics_path())
