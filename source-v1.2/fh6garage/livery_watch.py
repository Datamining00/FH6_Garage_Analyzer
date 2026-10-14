"""Read-only, conservative save observation; never publishes a main scan."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
from time import monotonic

from .models import LiveryRecord
from .parsers import read_header_file
from .refresh_history import _snapshot_entry, _load_snapshot, default_refresh_history_dir, diff_livery_snapshots

KINDS = {'livery': 'Livery'}


def fingerprint(root):
    """Metadata only. Any missing required file/access failure rejects the sample."""
    values = []
    with os.scandir(root) as entries:
        for entry in entries:
            kind = KINDS.get(entry.name.split('_', 1)[0].casefold())
            if kind is None:
                continue
            if not entry.is_dir(follow_symlinks=False):
                raise OSError('Container is unavailable')
            directory = entry.stat(follow_symlinks=False)
            files = []
            for name in ('header', 'C_livery'):
                st = (Path(entry.path) / name).stat()
                if st.st_size == 0:
                    raise OSError('Incomplete container')
                files.append((name, st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino))
            values.append((entry.name, kind, directory.st_ino, tuple(files)))
    st = Path(root).stat()
    return (st.st_dev, st.st_ino, tuple(sorted(values)))


def snapshot(records, cache_images=False):
    thumbs = default_refresh_history_dir() / 'thumbnails'
    return [_snapshot_entry(r if cache_images else replace(r, thumbnail_path=None), thumbs)
            for r in records if r.kind in KINDS.values()]


class Observation:
    def __init__(self, root, records, car_db=None):
        self.root = Path(root)
        self.car_db = car_db
        self.baseline = snapshot(records)
        _, saved = _load_snapshot(default_refresh_history_dir() / 'snapshot.json')
        saved = {entry.identity: entry for entry in saved}
        for entry in self.baseline:
            previous = saved.get(entry.identity)
            if previous and previous.change_fingerprint() == entry.change_fingerprint():
                entry.thumbnail_cache = previous.thumbnail_cache
        self.candidate = None
        self.since = 0.0
        self.accepted = None
        self.cache = {}
        self.cancelled = False

    def check(self, now=None):
        now = monotonic() if now is None else now
        try:
            if self.cancelled:
                return None
            before = fingerprint(self.root)
            if before != self.candidate:
                self.candidate, self.since = before, now
                return None
            if now - self.since < 2 or before == self.accepted:
                return None
            records, cache = [], {}
            for item in before[2]:
                if self.cancelled:
                    return None
                name, kind, _, _ = item
                record = self.cache.get(item)
                if record is None:
                    path = self.root / name
                    header = read_header_file(path / 'header', kind)
                    if self.car_db is not None:
                        from .scanner import _resolve_car_id
                        header = replace(header, car_id=_resolve_car_id(name, kind, header.car_id, self.car_db))
                    raw = (path / 'C_livery').read_bytes()
                    from .preview3d.livery_paint_provenance import unwrap_forza_container_bytes
                    unwrap_forza_container_bytes(raw)
                    record = LiveryRecord(name, path, kind, header,
                        livery_path=path / 'C_livery', content_sha256=hashlib.sha256(raw).hexdigest() if kind == 'Livery' else '')
                    from .scanner import _file_created_timestamp
                    record.downloaded_at = _file_created_timestamp(path / 'C_livery')
                    for thumb in ('bigThumb.webp', 'BigThumb.webp'):
                        if (path / thumb).is_file():
                            record.thumbnail_path = path / thumb
                            break
                cache[item] = record
                records.append(record)
            if self.cancelled or fingerprint(self.root) != before:
                self.candidate = None
                return None
            current = snapshot(records, cache_images=True)
            if fingerprint(self.root) != before:
                self.candidate = None
                return None
            diff = diff_livery_snapshots(self.baseline, current)
            # A uniquely reconciled relocation is still the same livery.
            diff.changed = [c for c in diff.changed
                            if c.before.change_fingerprint() != c.after.change_fingerprint()]
            self.cache, self.accepted = cache, before
            return diff, records
        except Exception:
            # Invalid parsing, partial deletion and access failures are unknown,
            # never an empty save. Require a new stable sample before retrying.
            self.candidate = None
            return None
