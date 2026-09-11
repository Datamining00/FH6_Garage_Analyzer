"""Remove an explicitly selected indexed backup, never a game-side source."""
import os
from pathlib import Path
import shutil
import uuid

from .backup_export import BackupRepositoryError, load_index, save_index


def delete_backup(root: Path, relative: str) -> None:
    root = root.resolve()
    payload = load_index(root)
    matches = [e for e in payload.get('entries', []) if e.get('relative_path') == relative]
    if len(matches) != 1:
        raise BackupRepositoryError('The selected backup no longer has a unique index entry.')
    target = (root / relative).resolve()
    if target == root or root not in target.parents or not target.is_dir():
        raise BackupRepositoryError('Invalid backup directory.')
    if Path(root / relative).is_symlink():
        raise BackupRepositoryError('A linked backup directory cannot be deleted.')
    parking = root / '.delete_staging' / uuid.uuid4().hex
    if parking.parent.is_symlink() or parking.parent.resolve().parent != root:
        raise BackupRepositoryError('Invalid backup staging directory.')
    parking.parent.mkdir(exist_ok=True)
    os.replace(target, parking)
    remaining = [e for e in payload['entries'] if e is not matches[0]]
    try:
        save_index(root, {**payload, 'entries': remaining})
    except Exception:
        os.replace(parking, target)
        raise
    shutil.rmtree(parking)
    preview = str(matches[0].get('preview_relative') or '')
    if preview and not any(e.get('preview_relative') == preview for e in remaining):
        image = (root / preview).resolve()
        if image != root and root in image.parents and image.is_file():
            image.unlink()
