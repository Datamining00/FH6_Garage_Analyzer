"""Backup duplicate and destructive-action policy without UI side effects."""
from .app_options import load_options


def duplicate_key(kind, digest, name, options=None):
    options = options or load_options()
    key = (str(kind or '').strip().casefold(), str(digest or '').strip().casefold())
    return (*key, str(name or '').strip()) if options.backup_allow_different_name else key


def record_locked(window, record):
    from .v1_3_4_card_features_patch import _lock_pref_key
    getter = getattr(getattr(window, 'local_preferences', None), 'get_bool', None)
    key_fn = getattr(window, '_content_annotation_key', None)
    if getter and key_fn and getter(_lock_pref_key(key_fn('livery', record)), False):
        return True
    digest = str(getattr(record, 'content_sha256', '') or '')
    for card in getattr(window, '_livery_grid_cards', []) or []:
        if not card.property('fh6MoveLocked'):
            continue
        resolver = getattr(window, '_record_for_content_key', None)
        other = resolver('livery', str(card.property('annotationKey') or '')) if resolver else None
        if other is not None and (other.container_path == record.container_path or
                (digest and digest == other.content_sha256 and record.kind == other.kind)):
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
