"""Per-preview timings and local provenance; never reads or writes save data."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from ..subsystem_log import log_event

_CURRENT = ContextVar('fh6_preview_trace', default=None)


def record(event, **fields):
    trace = _CURRENT.get()
    if trace is not None:
        trace['events'].append({'event': event, **fields})


@contextmanager
def stage(name):
    started = time.perf_counter()
    outcome = 'ok'
    try:
        yield
    except BaseException:
        outcome = 'error'
        raise
    finally:
        record(name, elapsed_ms=round((time.perf_counter() - started) * 1000, 3), outcome=outcome)


def timed(name):
    def decorate(function):
        @wraps(function)
        def measured(*args, **kwargs):
            with stage(name):
                return function(*args, **kwargs)
        return measured
    return decorate


def _persist(trace):
    try:
        local = os.environ.get('LOCALAPPDATA')
        base = Path(local) / 'FH6GarageAnalyzer' if local else Path.home() / '.fh6garageanalyzer'
        root = base / 'preview3d_runtime' / 'diagnostics' / 'pipeline'
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"preview_{trace['run_id']}.json"
        path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding='utf-8')
        # Retain enough cold/warm pairs without unbounded diagnostic growth.
        previous = sorted(root.glob('preview_*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for old in previous[32:]:
            old.unlink(missing_ok=True)
    except (OSError, TypeError, ValueError):
        pass


@contextmanager
def preview_trace(kind, **fields):
    trace = {'format': 'fh6_preview_pipeline_v1', 'run_id': uuid4().hex,
             'kind': kind, 'started_unix': time.time(), 'events': [], **fields}
    token = _CURRENT.set(trace)
    started = time.perf_counter()
    try:
        yield trace
    finally:
        trace['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 3)
        _CURRENT.reset(token)
        _persist(trace)
        log_event('PERFORMANCE', 'preview_pipeline', run_id=trace['run_id'],
                  kind=kind, elapsed_ms=trace['elapsed_ms'])


def trace_worker(function):
    @wraps(function)
    def measured(self, *args, **kwargs):
        with preview_trace(type(self).__name__, car_id=getattr(self, 'car_id', None),
                           glb_path=getattr(self, 'glb_path', None)):
            return function(self, *args, **kwargs)
    return measured
