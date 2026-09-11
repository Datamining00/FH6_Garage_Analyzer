"""Backup duplicate and destructive-action policy without UI side effects."""
from .app_options import load_options


def duplicate_key(kind, digest, name, options=None):
    options = options or load_options()
    key = (str(kind or '').strip().casefold(), str(digest or '').strip().casefold())
    return (*key, str(name or '').strip()) if options.backup_allow_different_name else key


def record_locked(window, record):
    from .v1_3_4_card_features_patch import _lock_pref_key
    getter = getattr(getattr(window, 'local_preferences', None), 'get_bool', None)
    path_key = 'backup-path::' + str(record.container_path.resolve()).casefold()
    if getter and getter(_lock_pref_key(path_key), False):
        return True
    key_fn = getattr(window, '_content_annotation_key', None)
    is_backup = str(record.container_path.resolve()).casefold() in getattr(window, '_fh6_backup_lock_paths', set())
    if not is_backup and getter and key_fn and getter(_lock_pref_key(key_fn('livery', record)), False):
        return True
    for card in (getattr(window, '_livery_grid_cards', []) or []) + (getattr(window, '_fh6_backup_cards', []) or []):
        if not card.property('fh6MoveLocked'):
            continue
        resolver = getattr(window, '_record_for_content_key', None)
        other = card.property('backupRecord') or (resolver('livery', str(card.property('annotationKey') or '')) if resolver else None)
        if other is not None and other.container_path == record.container_path:
            return True
    return False


def record_applied(window, record):
    state = getattr(window, '_fh6_memory_livery_state_for_record', None)
    if callable(state) and state(record) == 'applied':
        return True
    fn = getattr(window, '_fh6_v132_is_auction_applied', None) if record.kind == 'SoulBoundLivery' else None
    if callable(fn):
        return bool(fn(record))
    return False
