"""Persisted application options shared by UI and background workers."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path

from .local_storage import write_json_atomic


@dataclass(frozen=True)
class AppOptions:
    write_thumbnail_marks: bool = False
    auto_backup: bool = False
    auto_livery_detection: bool = True
    render_cache: bool = False
    disable_export_cut: bool = True
    show_download_date: bool = True
    show_auction_badge: bool = False
    show_hide_button: bool = True
    backup_allow_different_name: bool = False
    backup_allow_duplicates: bool = False
    warn_applied_delete_move: bool = True
    render_workers: int = 0  # zero: automatic
    skip_vehicle_materials: bool = False


_snapshot = ContextVar('fh6_app_options', default=None)


def options_path() -> Path:
    base = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
    return base / 'FH6GarageAnalyzer' / 'app_options.json'


def load_options() -> AppOptions:
    current = _snapshot.get()
    if current is not None:
        return current
    defaults = AppOptions()
    try:
        values = json.loads(options_path().read_text(encoding='utf-8'))
        clean = {}
        for field in fields(defaults):
            value = values.get(field.name)
            if field.name == 'render_workers':
                if type(value) is int and 0 <= value <= 256:
                    clean[field.name] = value
            elif type(value) is bool:
                clean[field.name] = value
        return AppOptions(**clean)
    except (OSError, ValueError, TypeError, AttributeError):
        return defaults


def save_options(options: AppOptions) -> bool:
    return write_json_atomic(options_path(), asdict(options))


@contextmanager
def options_snapshot():
    token = _snapshot.set(load_options())
    try:
        yield
    finally:
        _snapshot.reset(token)
