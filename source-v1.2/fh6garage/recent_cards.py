"""Recent changes use the same card factory as the main livery tab."""
from pathlib import Path
from PySide6.QtWidgets import QToolButton
from .models import HeaderInfo, LiveryRecord
from .refresh_history import cached_thumbnail_path


def make_card(window, category, entry, width):
    observed = getattr(window, '_fh6_observed_liveries', None)
    records = observed if observed is not None else getattr(getattr(window, 'result', None), 'liveries', [])
    matches = [r for r in records if r.kind == entry.kind and r.container_name.casefold() == entry.container_name.casefold()
               and (not entry.guid or r.header.guid == entry.guid)]
    live = category != 'removed' and len(matches) == 1
    if live:
        record = matches[0]
        key = window._content_annotation_key('livery', record)
    else:
        # No fake filesystem target: every source-dependent action is disabled.
        record = LiveryRecord(entry.container_name, Path('__missing_recent_record__'), entry.kind,
            HeaderInfo(name=entry.name, creator=entry.creator, car_id=entry.car_id, guid=entry.guid,
                       description=entry.description), thumbnail_path=cached_thumbnail_path(entry))
        key = 'recent-archive::' + entry.identity
    card = window._make_saved_content_card('livery', record, key)
    card.setFixedWidth(width)
    card.setProperty('fh6RecentCard', True)
    if not live:
        for button in card.findChildren(QToolButton):
            if button is not getattr(card, '_fh6_zoom_button', None):
                button.setEnabled(False)
                button.setToolTip('원본이 없는 이전 기록입니다.')
    window._load_livery_card_thumbnail(card)
    return card
