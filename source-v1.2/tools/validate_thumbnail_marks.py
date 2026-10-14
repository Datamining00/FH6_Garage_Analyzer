import os, sys, tempfile, time, json
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['FH6_ASSISTANT_SMOKE_TEST_MS'] = '60000'
with tempfile.TemporaryDirectory(prefix='fh6-thumb-ui-') as state:
    os.environ['LOCALAPPDATA'] = state
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QFontDatabase, QFont
    from PySide6.QtWidgets import QApplication, QToolButton
    from shiboken6 import delete
    from PIL import Image, ImageDraw
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, state)
    q = QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
    q.setFont(QFont('Malgun Gothic', 10))
    import app
    app._apply_runtime_patch_stack()
    from test_livery_watch import WatchTests
    from test_header_marker_independent import _creator_relative_header
    from fh6garage.parsers import read_header_file
    from fh6garage.models import ScanResult, SaveMetadata
    from fh6garage.app_options import AppOptions, save_options
    from fh6garage.application_controls import SettingsDialog
    from fh6garage.v1_3_4_card_features_patch import _set_livery_lock
    from fh6garage.recent_cards import make_card
    from fh6garage.refresh_history import _snapshot_entry
    from fh6garage.auction_thumbnails import _header_livery_token
    out = Path(sys.argv[1]).resolve(); out.mkdir(parents=True, exist_ok=True)
    f = WatchTests(); f.root = Path(state)/'save/current/ContainersRoot'; f.root.mkdir(parents=True)
    r = f.record(1)
    r.downloaded_at = 1789142400
    image = Image.new('RGB', (540, 300), '#eef0f5')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((90, 110, 450, 230), radius=35, fill='#c8cfdd')
    draw.ellipse((140, 200, 200, 260), fill='#636a79'); draw.ellipse((355, 200, 415, 260), fill='#636a79')
    r.thumbnail_path = r.container_path/'bigThumb.webp'; image.save(r.thumbnail_path, 'WEBP', lossless=True)
    cache = Path(state)/'CacheThumbnails'; cache.mkdir()
    auction_path = cache/'mapped.webp'; image.save(auction_path, 'WEBP', lossless=True)
    soul_dir = f.root/'SoulBoundLivery_123_2'; soul_dir.mkdir()
    (soul_dir/'header').write_bytes(_creator_relative_header('SoulBoundLivery', 123, 2, b'\1\0'))
    (soul_dir/'C_livery').write_bytes(r.livery_path.read_bytes())
    soul = replace(r, kind='SoulBoundLivery', container_name=soul_dir.name, container_path=soul_dir,
        header=read_header_file(soul_dir/'header', 'SoulBoundLivery'), thumbnail_path=auction_path)
    original = {r.thumbnail_path: r.thumbnail_path.read_bytes(), auction_path: auction_path.read_bytes()}
    save_options(AppOptions(auto_livery_detection=False, show_auction_badge=True))
    w = app.MainWindow(project_root=ROOT); w._fh6_application_controller.timer.stop()
    w.path_edit.setText(str(f.root))
    w.result = ScanResult(SaveMetadata(f.root, f.root.parent.parent, f.root), liveries=[r, soul])
    w._reset_game_navigation_sessions(); w._populate_all(); w.resize(1100,760); w.show(); q.processEvents()
    soul.thumbnail_path = auction_path  # fixture has no on-disk binary manifest
    card = w._make_saved_content_card('livery', soul, w._content_annotation_key('livery', soul))
    card.setFixedWidth(540); card.show(); w._load_livery_card_thumbnail(card); q.processEvents()
    card._fh6_lock_placeholder_button.setChecked(True)
    q.processEvents()
    assert card._fh6_mark_label.auction.isVisible() and card._fh6_mark_label.lock.isVisible()
    assert card._fh6_download_date_label.y() == 6
    assert card._fh6_mark_label.y() > 200
    card.grab().save(str(out/'auction-lock-card.png'))
    main_cards = list(w._livery_grid_cards)
    w._fh6_observed_liveries = [r]
    entry = _snapshot_entry(r, Path(state)/'history')
    recent = make_card(w, 'added', entry, 540); recent.show(); q.processEvents()
    assert hasattr(recent, '_fh6_action_grid') and hasattr(recent, '_fh6_lock_placeholder_button')
    assert list(w._livery_grid_cards) == main_cards
    recent.grab().save(str(out/'recent-card.png'))
    removed = make_card(w, 'removed', entry, 540); removed.show(); q.processEvents()
    assert all(not b.isEnabled() for b in removed.findChildren(QToolButton) if b is not getattr(removed, '_fh6_zoom_button', None))
    removed.grab().save(str(out/'removed-card.png'))
    settings = SettingsDialog(w); settings.show(); q.processEvents()
    assert not settings.boxes['write_thumbnail_marks'].isChecked()
    assert not settings.reapply_button.isEnabled()
    settings.boxes['write_thumbnail_marks'].setChecked(True)
    assert settings.reapply_button.isEnabled()
    settings.boxes['write_thumbnail_marks'].setChecked(False)
    settings.grab().save(str(out/'settings.png')); settings.close()
    settings.boxes['write_thumbnail_marks'].setChecked(True)
    settings.reapply_button.click()
    assert settings.reapply_requested and settings.result() == settings.DialogCode.Accepted
    controller = w._fh6_thumbnail_marks
    def run_write(reapply=False):
        controller.request(reapply=reapply)
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            q.processEvents()
            if not controller.pending and controller.worker is None and not controller.timer.isActive():
                return
            time.sleep(.01)
        raise RuntimeError('thumbnail worker did not complete')
    rows = [NS(path=auction_path, car_id=soul.car_id, livery_token=_header_livery_token(soul))]
    with patch('fh6garage.v1_3_2_patch._current_cache_path', return_value=cache), patch('fh6garage.auction_thumbnails.read_thumbnail_manifest', return_value=rows):
        save_options(AppOptions(auto_livery_detection=False, write_thumbnail_marks=True, show_auction_badge=True))
        run_write()
        assert auction_path.read_bytes() != original[auction_path]
        assert r.thumbnail_path.read_bytes() == original[r.thumbnail_path]
        assert not card._fh6_image_label.pixmap().isNull()
        Image.open(auction_path).save(out/'written-auction-lock.png')
        save_options(AppOptions(auto_livery_detection=False, write_thumbnail_marks=True, show_auction_badge=False))
        run_write()
        assert auction_path.read_bytes() != original[auction_path]  # lock stays
        Image.open(auction_path).save(out/'written-lock-only.png')
        Image.new('RGB', (540, 300), '#c5d5e5').save(auction_path, 'WEBP', lossless=True)
        original[auction_path] = auction_path.read_bytes()
        run_write(reapply=True)
        assert auction_path.read_bytes() != original[auction_path]
        save_options(AppOptions(auto_livery_detection=False, write_thumbnail_marks=False))
        run_write()
        assert all(p.read_bytes() == data for p,data in original.items())
    (out/'ui-results.json').write_text(json.dumps({'recent_main_card_factory':True,'removed_actions_disabled':True,
        'write_on_worker':True,'auction_off_retains_lock':True,'write_off_exact_restore':True,'real_game_access':False},indent=2))
    for obj in (settings,card,recent,removed,w): delete(obj)
    q.processEvents()
    print('Thumbnail production UI and reversible worker checks passed')
