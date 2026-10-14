"""Production UI, simulated completion events, temporary data only."""
import os
import sys
import tempfile
import json
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['FH6_ASSISTANT_SMOKE_TEST_MS'] = '60000'

with tempfile.TemporaryDirectory(prefix='fh6-ui-update-') as state:
    os.environ['LOCALAPPDATA'] = state
    from PySide6.QtCore import QSettings, QPoint
    from PySide6.QtGui import QFont, QFontDatabase, QPalette, QColor
    from PySide6.QtWidgets import QApplication, QMessageBox, QToolTip, QLabel, QToolButton
    from shiboken6 import delete
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, state)
    q = QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
    q.setFont(QFont('Malgun Gothic', 10))
    palette = q.palette()
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor('#cccccc'))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor('#ffffff'))
    q.setPalette(palette)
    import app
    app._apply_runtime_patch_stack()
    from fh6garage.app_options import AppOptions, save_options
    from fh6garage.application_controls import SettingsDialog, apply_card_options
    from test_livery_watch import WatchTests
    from fh6garage.models import ScanResult, SaveMetadata
    from fh6garage.memory_applied_state import MemoryScanResult
    from fh6garage import v1_3_2_memory_state_patch as memory
    from fh6garage.backup_export import export_records, backup_records
    from fh6garage.v1_3_4_backup_import_refinement_patch import _configure_backup_card
    from fh6garage.v1_4_vehicle_data_source_patch import HDR_SOURCE, USER_SOURCE
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixture = WatchTests()
    fixture.root = Path(state) / 'save' / 'current' / 'ContainersRoot'
    fixture.root.mkdir(parents=True)
    regular = fixture.record(1)
    regular.header.name = 'Regular livery'
    soul = replace(regular, kind='SoulBoundLivery', container_name='SoulBoundLivery_123_2',
                   downloaded_at=1789142400)
    w = app.MainWindow(project_root=ROOT)
    w._fh6_application_controller.timer.stop()
    w.path_edit.setText(str(fixture.root))
    w.result = ScanResult(SaveMetadata(fixture.root, fixture.root.parent.parent, fixture.root), liveries=[regular, soul])
    w._reset_game_navigation_sessions()
    w._populate_all()
    w.resize(1100, 760)
    w.show()
    q.processEvents()
    settings = SettingsDialog(w)
    settings.show()
    q.processEvents()
    assert settings.boxes['disable_export_cut'].isChecked()
    assert not settings.boxes['render_cache'].isChecked()
    assert not settings.boxes['show_auction_badge'].isChecked()
    settings.grab().save(str(output / 'settings-defaults.png'))
    settings.close()
    save_options(AppOptions(show_auction_badge=True, show_hide_button=False))
    card = w._make_saved_content_card('livery', soul, 'test-soul')
    card.setFixedWidth(540)
    card.show()
    q.processEvents()
    badge = card._fh6_auction_badge
    assert badge.text() == 'Auction' and badge.isVisible()
    assert abs(badge.geometry().center().x() - badge.parentWidget().rect().center().x()) <= 1
    assert not card._fh6_hide_button.isEnabled() and not card._fh6_hide_button.isHidden()
    card.grab().save(str(output / 'auction-centered.png'))
    delete(card)
    save_options(AppOptions())
    backup = Path(state) / 'backups'
    export_records(backup, [regular])
    entry, record = backup_records(backup)[0]
    card = w._fh6_backup_original_make_saved_content_card('livery', record, 'test-backup')
    _configure_backup_card(w, card, record, entry, 'backup')
    card.setFixedWidth(540)
    card.show()
    q.processEvents()
    button = card.findChild(QToolButton, 'fh6BackupDeleteButton')
    QToolTip.showText(button.mapToGlobal(QPoint(10, 30)), button.toolTip(), button)
    q.processEvents()
    tips = [t for t in q.topLevelWidgets() if t.objectName() == 'qtooltip_label']
    assert tips, 'tooltip missing'
    tip = tips[0]
    color = tip.palette().color(QPalette.ColorRole.WindowText).name()
    assert color in ('#303341', '#171924'), color
    tip.grab().save(str(output / 'backup-tooltip.png'))
    card.grab().save(str(output / 'backup-card.png'))
    QToolTip.hideText()
    delete(card)
    refreshes = []
    w.refresh_scan = lambda: refreshes.append('refresh')
    # No memory read: deliver a fixture result to the real completion handler.
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
        memory._on_memory_finished(w, MemoryScanResult(0, 'HIGH', frozenset()))
    q.processEvents()
    assert len(refreshes) == 1
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
        memory._on_memory_finished(w, MemoryScanResult(0, 'HIGH', frozenset()))
    q.processEvents()
    assert len(refreshes) == 1
    with patch.object(QMessageBox, 'warning'):
        memory._on_memory_finished(w, MemoryScanResult(0, 'LOW', frozenset()))
    q.processEvents()
    assert len(refreshes) == 1
    # No network: exercise both database completion branches with local data.
    for source in (HDR_SOURCE, USER_SOURCE):
        with patch.object(QMessageBox, 'information'):
            w._car_db_update_finished(NS(source=source, count=1, cache_path=Path(state) / 'db.json'))
        q.processEvents()
    assert len(refreshes) == 3, refreshes
    (output / 'ui-results.json').write_text(json.dumps({
        'settings_defaults': True, 'auction_centered': True, 'hide_disabled_visible': True,
        'backup_tooltip_text_color': color, 'memory_apply_refresh': True,
        'memory_declined_or_invalid_no_refresh': True, 'both_db_sources_refresh': True,
        'actual_game_access': False}, indent=2), encoding='utf8')
    delete(settings)
    delete(w)
    q.processEvents()
    print('Production UI checks passed')
