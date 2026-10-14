"""Serialize repository read/modify/publish operations within the application."""
from functools import wraps
from threading import RLock

_repository_lock = RLock()


def repository_transaction(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with _repository_lock:
            return function(*args, **kwargs)
    return guarded


def backup_busy(window):
    return bool(getattr(window, '_busy_depth', 0)) or any(
        getattr(window, name, False) for name in (
            '_fh6_export_running', '_fh6_import_running',
            '_fh6_auto_backup_running', '_fh6_external_import_running', '_fh6_thumbnail_write_running'))
