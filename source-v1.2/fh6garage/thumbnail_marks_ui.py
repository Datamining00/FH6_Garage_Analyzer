"""User-triggered thumbnail writing, separate from rendering caches."""
import os
from pathlib import Path
from collections import defaultdict

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QFrame, QMessageBox, QHBoxLayout

from .app_options import load_options
from .deferred_close import closing
from .thumbnail_marks import MarkStore, safe_path


def store_root():
    return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local') / 'FH6GarageAnalyzer/thumbnail_originals'


def excluded_auction(window, record):
    if record.kind != 'SoulBoundLivery':
        return False
    from .v1_3_2_auction_unapplied_recent_frame_fix import _record_is_unapplied_auction
    return _record_is_unapplied_auction(window, record)


def plan(records, containers, cache, options, locked, *, ownership=None, allowed_cache=None, entries=None, scope_records=None, folder_only=()):
    from .auction_thumbnails import read_thumbnail_manifest, _header_livery_token
    from .auction_thumbnails import _read_manifest_bytes
    from .auction_manifest_registry import read_auction_manifest_registry
    entries = entries or {}
    folder_only = {str(Path(p).absolute()) for p in folder_only}
    def auction(record):
        return (options.show_auction_badge and record.kind == 'SoulBoundLivery'
                and str(Path(record.container_path).absolute()) not in folder_only)
    flags_by_parent = defaultdict(set)
    for r, lock in zip(records, locked):
        flags_by_parent[str(Path(r.container_path).absolute())].add((auction(r), lock))
    conflicts = {p for p, flags in flags_by_parent.items() if len(flags) > 1}
    active_paths = {str(Path(p).absolute()) for p, e in entries.items() if e.get('active')}
    cache_restore = cache is not None and any(Path(p).parent == Path(cache).absolute() for p in active_paths)
    records_and_locks = [(r, lock) for r, lock in zip(records, locked)
                         if lock or auction(r)
                         or cache_restore or any(Path(p).parent == Path(r.container_path).absolute() for p in active_paths)]
    if not records_and_locks:
        return {}, []
    targets = defaultdict(set)
    skipped = [f'{p}: 공유 썸네일의 표시 상태가 달라 생략' for p in conflicts]
    rows = []
    registered = frozenset()
    if cache is not None and any(str(Path(r.container_path).absolute()) not in folder_only for r, _ in records_and_locks):
        try:
            data = _read_manifest_bytes(Path(cache) / '.manifest')
            rows = read_thumbnail_manifest(cache, data=data)
            registered = read_auction_manifest_registry(cache, data=data).logical_names
        except Exception as exc:
            rows = []
            skipped.append(f'경매장 썸네일 연결 확인 실패: {exc}')
    rows_by_token = defaultdict(list)
    for row in rows:
        rows_by_token[(row.car_id, row.livery_token)].append(row)
    owners = defaultdict(set)
    for record, lock in records_and_locks:
        if str(Path(record.container_path).absolute()) in conflicts:
            continue
        if record.kind not in ('Livery', 'SoulBoundLivery'):
            continue
        try:
            parent = safe_path(record.container_path)
            if parent.parent != safe_path(containers):
                continue  # backup cards and exported files never become targets
            header = getattr(record, 'header', None)
            if header is not None:
                from .parsers import read_header_file
                current = read_header_file(parent / 'header', record.kind)
                if current.guid != header.guid or current.name != header.name:
                    raise ValueError('스캔 이후 리버리가 변경되어 생략: 새로고침 필요')
            paths = set()
            flags = (auction(record), lock)
            # Both kinds can have an embedded thumbnail and a separately
            # materialized game-cache thumbnail. Neither substitutes the other.
            from .scanner import _detect_thumbnail
            candidate = _detect_thumbnail(parent, False)
            if candidate and safe_path(candidate).parent == parent and (any(flags) or str(Path(candidate).absolute()) in active_paths):
                paths.add(safe_path(candidate))
            # Commit the embedded thumbnail independently: a cache lookup or
            # ownership error must never discard this verified local target.
            for path in paths:
                owners[str(path)].add(str(parent))
                targets[str(path)].add(flags)
            paths.clear()
            if str(parent) in folder_only:
                continue
            token = _header_livery_token(record)
            matches = rows_by_token.get((getattr(record, 'car_id', None), token), []) if token else []
            candidates = {safe_path(row.path) for row in matches
                          if ((any(flags) and row.logical_name in registered)
                              or (not any(flags) and str(Path(row.path).absolute()) in active_paths)) and row.path.is_file()}
            # An omitted, unmarked record must not make a shared cache look
            # exclusively owned by the remaining marked record.
            if candidates:
                shared = any(other is not record and other.container_path != record.container_path
                             and getattr(other, 'car_id', None) == getattr(record, 'car_id', None)
                             and _header_livery_token(other) == token for other in (scope_records if scope_records is not None else records))
                conflicting_link = any(row.path in candidates and
                                       (row.car_id, row.livery_token) != (getattr(record, 'car_id', None), token)
                                       for row in rows)
                if shared or conflicting_link:
                    skipped.append(f'{record.container_name}: 공유 캐시의 소유자를 확정할 수 없어 생략')
                    candidates = set()
            if candidates and scope_records is not None:
                try:
                    from .thumbnail_ownership import verify_owner
                    verify_owner(record, containers, token, scope_records)
                except Exception as exc:
                    skipped.append(f'{record.container_name}: {exc}')
                    candidates = set()
            if len(candidates) == 1:
                candidate = candidates.pop()
                if cache is not None and candidate.parent == safe_path(cache):
                    if scope_records is not None or allowed_cache is None or allowed_cache.get(str(candidate)) == str(parent):
                        paths.add(candidate)
                    else:
                        skipped.append(f"{record.container_name}: 캐시 연결 검증 정보가 부족하여 생략")
            elif len(candidates) > 1 and any(flags):
                skipped.append(f'{record.container_name}: 캐시가 여러 개 연결되어 캐시 쓰기 생략')
            elif not any(flags):
                # Restoring previously marked, verified paths does not choose a
                # current rendering variant. Keep the same ownership guard.
                for candidate in candidates:
                    if cache is not None and candidate.parent == safe_path(cache) and (scope_records is not None or allowed_cache is None or allowed_cache.get(str(candidate)) == str(parent)):
                        paths.add(candidate)
            if not paths:
                continue
            for path in paths:
                owners[str(path)].add(str(parent))
                targets[str(path)].add(flags)
        except Exception as exc:
            skipped.append(f'{record.container_name}: {exc}')
    if ownership is not None:
        ownership.update({p: next(iter(owner)) for p, owner in owners.items() if len(owner) == 1})
    output = {}
    for path, flags in targets.items():
        if len(flags) == 1:
            output[path] = flags.pop()
        else:
            skipped.append(f'{path}: 공유 썸네일의 표시 상태가 달라 생략')
    return output, skipped


class Worker(QThread):
    completed = Signal(object)
    def __init__(self, owner, records, containers, cache, options, locks, *, reapply=False, partial=False, allowed_cache=None, scope_records=None, folder_only=()):
        super().__init__(owner)
        self.args = records, containers, cache, options, locks
        self.reapply = reapply
        self.partial = partial
        self.allowed_cache = allowed_cache
        self.scope_records = scope_records
        self.folder_only = folder_only

    def run(self):
        records, containers, cache, options, locks = self.args
        try:
            ownership = {}
            store = MarkStore(store_root())
            targets, skipped = plan(*self.args, ownership=ownership, allowed_cache=self.allowed_cache, entries=store.load(), scope_records=self.scope_records, folder_only=self.folder_only) if options.write_thumbnail_marks else ({}, [])
            result = store.apply(targets, restore_all=not options.write_thumbnail_marks, reapply=self.reapply, partial=self.partial)
            result["ownership"] = ownership
            result["partial"] = self.partial
            result['failures'].extend(skipped)
        except Exception as exc:
            result = {'written': 0, 'restored': 0, 'originals': {}, 'failures': [str(exc)], 'partial': True}
        self.completed.emit(result)


class Controller(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.worker = None
        self.pending = False
        self.pending_full = False
        self.pending_records = {}
        self.allowed_cache = {}
        self.active_records = None
        self.reapply = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.start)
        self.originals = {}
        if (store_root() / 'index.json').exists():
            self.request()

    def request(self, *, reapply=False, record=None):
        if closing(self.window):
            return
        if record is None or reapply:
            self.pending_full = True
        else:
            self.pending_records[str(record.container_path)] = record
        self.pending = True
        self.reapply = self.reapply or reapply
        self.timer.start(0)

    def start(self):
        if closing(self.window):
            return
        from .completion_refresh import _busy
        window = self.window
        if self.worker is not None or _busy(window):
            self.timer.start(250)
            return
        options = load_options()
        result = getattr(window, 'result', None)
        if options.write_thumbnail_marks and result is None:
            return
        from .v1_3_2_patch import _current_cache_path
        from .v1_3_4_card_features_patch import _lock_pref_key
        partial = not self.pending_full and options.write_thumbnail_marks
        records = list(result.liveries) if result is not None else []
        scope_records = list(records) if partial else None
        if partial:
            records = [r for r in records if str(r.container_path) in self.pending_records]
        folder_only = {str(r.container_path) for r in records if excluded_auction(window, r)}
        self.active_records = {str(r.container_path) for r in records} if options.write_thumbnail_marks else None
        self.pending_records.clear()
        self.pending_full = False
        if partial and not records:
            self.pending = False
            return
        locks = [window.local_preferences.get_bool(_lock_pref_key(window._content_annotation_key('livery', r)), False) for r in records]
        containers = result.metadata.containers_root if result else None
        self.pending = False
        window._fh6_thumbnail_write_running = True
        window._begin_busy('썸네일 표시를 적용·복원하는 중…')
        self.worker = Worker(self, records, containers, _current_cache_path(window), options, locks, reapply=self.reapply, partial=partial, allowed_cache=self.allowed_cache if partial else None, scope_records=scope_records, folder_only=folder_only)
        self.reapply = False
        self.worker.completed.connect(self.done)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    @Slot(object)
    def done(self, result):
        if result.get('partial'):
            for path in result.get('touched_paths', []):
                self.originals.pop(path, None)
            self.originals.update(result['originals'])
        else:
            self.originals = result['originals']
            self.allowed_cache = result.get('ownership', {})
        window = self.window
        for card in window.findChildren(QFrame):
            record = getattr(card, '_fh6_option_record', None)
            if record is None or (self.active_records is not None and str(record.container_path) not in self.active_records):
                continue
            previous_path = getattr(card, '_fh6_thumbnail_path', None)
            update_card(window, card, record)
            source_path = str(Path(record.thumbnail_path).absolute()).casefold() if record.thumbnail_path else ''
            if (previous_path == getattr(card, '_fh6_thumbnail_path', None)
                    and source_path not in result.get('changed_paths', [])):
                continue
            window._unload_livery_card_thumbnail(card)
            window._load_livery_card_thumbnail(card)
        text = f"썸네일: 쓰기 {result['written']} · 복원 {result['restored']} · 생략/실패 {len(result['failures'])}"
        if result.get('deleted_backups'):
            text += f" · 이전 백업 삭제 {result['deleted_backups']}"
        window._show_status(text, 8000)
        if result['failures']:
            box = QMessageBox(window)
            box.setWindowTitle('썸네일에 쓰기')
            box.setText(text)
            box.setInformativeText('생략한 파일과 보관된 원본은 유지됩니다.')
            box.setDetailedText('\n'.join(result['failures']))
            box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            box.show()

    @Slot()
    def finished(self):
        self.window._fh6_thumbnail_write_running = False
        self.window._end_busy()
        self.worker.deleteLater()
        self.worker = None
        if self.pending:
            self.timer.start(0)


def update_card(window, card, record):
    # Saved-content cards include tuning records, which have no livery kind.
    # Neither auction/lock overlays nor livery original-image routing applies.
    if getattr(record, 'kind', None) not in ('Livery', 'SoulBoundLivery'):
        return
    from .application_controls import _DatePositioner
    from .card_icons import icon
    image = getattr(card, '_fh6_image_label', None)
    if image is None:
        return
    controller = getattr(window, '_fh6_thumbnail_marks', None)
    if record.thumbnail_path:
        original = controller.originals.get(str(Path(record.thumbnail_path).absolute()).casefold()) if controller else None
        card._fh6_thumbnail_path = Path(original) if original else record.thumbnail_path
    label = getattr(card, '_fh6_mark_label', None)
    if label is None:
        label = QFrame(image.parentWidget())
        label.setObjectName('thumbnailMark')
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        label.setStyleSheet('QFrame#thumbnailMark {background:rgba(255,255,255,245); border:1px solid #c6baef; border-radius:7px;} QLabel {background:transparent; color:#4e329c; border:0; font-size:11pt; font-weight:700;}')
        row = QHBoxLayout(label)
        row.setContentsMargins(9, 4, 9, 4)
        row.setSpacing(7)
        label.auction = QLabel('Auction', label)
        label.lock = QLabel(label)
        label.lock.setPixmap(icon('lock', '#6e4bf2', 20).pixmap(20, 20))
        row.addWidget(label.auction)
        row.addWidget(label.lock)
        card._fh6_mark_label = label
        card._fh6_mark_positioner = _DatePositioner(image.parentWidget(), label, top=False)
    auction = record.kind == 'SoulBoundLivery' and load_options().show_auction_badge and not excluded_auction(window, record)
    locked = bool(card.property('fh6MoveLocked'))
    label.auction.setVisible(auction)
    label.lock.setVisible(locked)
    label.layout().activate()
    label.setVisible(auction or locked)
    card._fh6_mark_positioner.position()
    old = getattr(card, '_fh6_auction_badge', None)
    if old is not None:
        old.hide()


def request(window, *, reapply=False, record=None):
    controller = getattr(window, '_fh6_thumbnail_marks', None)
    if controller is not None:
        controller.request(reapply=reapply, record=record)
