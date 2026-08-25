"""Auction livery source selection, cache location, and card presentation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

from .auction_thumbnails import is_thumbnail_cache_dir
from .i18n import get_language
from .models import LiveryRecord
from .thumbnail_cache_location import fixed_default_thumbnail_cache
from .ui_cleanup import (
    _align_path_rows,
    _configure_livery_source_switch,
    _normalize_path_rows,
)

_CACHE_SETTING_KEY = "auction_thumbnail_cache_path_v1_3_2"
_SHOW_MY_DESIGNS_KEY = "livery_show_my_designs_v1_3_2"
_SHOW_AUCTION_KEY = "livery_show_auction_v1_3_2"


_TEXT = {
    "ko": {
        "cache_label": "경매장 썸네일 캐시",
        "cache_placeholder": "CacheThumbnails 폴더를 선택하세요",
        "cache_choose": "캐시 경로 선택",
        "cache_auto": "자동 감지",
        "cache_dialog": "경매장 썸네일 캐시 폴더 선택",
        "cache_invalid_title": "캐시 경로 확인",
        "cache_invalid": "선택한 폴더에서 .manifest를 찾을 수 없습니다.\nCacheThumbnails 폴더를 선택하세요.",
        "cache_not_found_title": "자동 감지 실패",
        "cache_not_found": "FH6 CacheThumbnails 폴더를 자동으로 찾지 못했습니다. 직접 선택해 주세요.",
        "cache_detected": "경매장 썸네일 캐시를 찾았습니다.",
        "show_label": "표시:",
        "my_designs": "내 디자인 리버리",
        "auction": "경매장 리버리",
        "auction_badge": "경매장",
        "livery_page": "리버리",
    },
    "en": {
        "cache_label": "Auction thumbnail cache",
        "cache_placeholder": "Select the CacheThumbnails folder",
        "cache_choose": "Choose cache folder",
        "cache_auto": "Auto-detect",
        "cache_dialog": "Select auction thumbnail cache folder",
        "cache_invalid_title": "Check cache folder",
        "cache_invalid": "No .manifest was found in the selected folder.\nSelect the CacheThumbnails folder.",
        "cache_not_found_title": "Auto-detect failed",
        "cache_not_found": "FH6 CacheThumbnails could not be detected automatically. Select it manually.",
        "cache_detected": "Auction thumbnail cache detected.",
        "show_label": "Show:",
        "my_designs": "My Designs liveries",
        "auction": "Auction liveries",
        "auction_badge": "Auction",
        "livery_page": "Liveries",
    },
}


def _t(key: str) -> str:
    language = (get_language() or "ko").lower()
    table = _TEXT["ko" if language.startswith("ko") else "en"]
    return table[key]


def _set_cache_path(self: Any, path: Path, *, persist: bool = True) -> None:
    path = Path(path)
    self.cache_path_edit.setText(str(path))
    self.cache_path_edit.setToolTip(str(path))
    if persist:
        self.settings.setValue(_CACHE_SETTING_KEY, str(path))
        self.settings.sync()


def _current_cache_path(self: Any) -> Path | None:
    if not hasattr(self, "cache_path_edit"):
        return None
    raw = self.cache_path_edit.text().strip()
    if not raw:
        return None
    path = Path(raw)
    return path if is_thumbnail_cache_dir(path) else None


def _refresh_for_cache_change(self: Any) -> None:
    if self.path_edit.text() and Path(self.path_edit.text()).is_dir():
        self.start_scan(Path(self.path_edit.text()))


def _choose_cache_folder(self: Any) -> None:
    start = self.cache_path_edit.text().strip() or str(Path.home())
    selected = QFileDialog.getExistingDirectory(
        self,
        _t("cache_dialog"),
        start,
    )
    if not selected:
        return
    path = Path(selected)
    if not is_thumbnail_cache_dir(path):
        QMessageBox.warning(
            self,
            _t("cache_invalid_title"),
            _t("cache_invalid"),
        )
        return
    _set_cache_path(self, path)
    _refresh_for_cache_change(self)


def _auto_detect_cache(self: Any, *, silent: bool = False, rescan: bool = True) -> bool:
    path = fixed_default_thumbnail_cache()
    if path is None:
        if not silent:
            QMessageBox.information(
                self,
                _t("cache_not_found_title"),
                _t("cache_not_found"),
            )
        return False
    _set_cache_path(self, path)
    if not silent:
        self._show_status(_t("cache_detected"), 3000)
    if rescan:
        _refresh_for_cache_change(self)
    return True


def _source_enabled(self: Any, source: str) -> bool:
    if source == "auction":
        button = getattr(self, "livery_auction_toggle", None)
        if button is not None:
            return button.isChecked()
        return self.local_preferences.get_bool(_SHOW_AUCTION_KEY, True)
    button = getattr(self, "livery_my_designs_toggle", None)
    if button is not None:
        return button.isChecked()
    return self.local_preferences.get_bool(_SHOW_MY_DESIGNS_KEY, True)


def _set_source_enabled(self: Any, source: str, enabled: bool) -> None:
    key = _SHOW_AUCTION_KEY if source == "auction" else _SHOW_MY_DESIGNS_KEY
    self.local_preferences.set_bool(key, bool(enabled))
    if self.result is None:
        return
    self._begin_busy()
    try:
        self._populate_livery_table()
        self.livery_grid_scroll.verticalScrollBar().setValue(0)
    finally:
        self._end_busy()


def _display_liveries(self: Any) -> list[LiveryRecord]:
    if self.result is None:
        return []
    show_saved = _source_enabled(self, "my_designs")
    show_auction = _source_enabled(self, "auction")
    return [
        record
        for record in self.result.liveries
        if (
            (record.kind == "Livery" and show_saved)
            or (record.kind == "SoulBoundLivery" and show_auction)
        )
    ]


def _sort_display_liveries(self: Any) -> list[LiveryRecord]:
    records = _display_liveries(self)
    mode = self._livery_sort_mode
    descending = self._livery_sort_descending

    if mode == "brand":
        ordered = sorted(records, key=self._vehicle_brand_sort_key)
        return list(reversed(ordered)) if descending else ordered

    if mode == "creator":
        def creator_key(record: LiveryRecord) -> tuple:
            creator = (record.header.creator or "").strip()
            return (
                1 if not creator else 0,
                creator.casefold(),
                self._vehicle_brand_sort_key(record),
                (record.header.name or "").casefold(),
            )

        ordered = sorted(records, key=creator_key)
        if not descending:
            return ordered
        available = [r for r in ordered if (r.header.creator or "").strip()]
        unavailable = [r for r in ordered if not (r.header.creator or "").strip()]
        return list(reversed(available)) + unavailable

    if mode == "download":
        available = [r for r in records if r.downloaded_at is not None]
        unavailable = [r for r in records if r.downloaded_at is None]
        return sorted(
            available,
            key=lambda record: record.downloaded_at or 0.0,
            reverse=descending,
        ) + unavailable

    if mode == "default" and descending:
        return list(reversed(records))
    return records


def _install_cache_row(self: Any) -> None:
    if hasattr(self, "cache_path_edit"):
        return
    content = self.path_edit.parentWidget()
    layout = content.layout() if content is not None else None
    if layout is None or not hasattr(layout, "insertLayout"):
        return

    row = QHBoxLayout()
    self.cache_path_edit = QLineEdit()
    self.cache_path_edit.setReadOnly(True)
    self.cache_path_edit.setPlaceholderText(_t("cache_placeholder"))

    choose = QPushButton(_t("cache_choose"))
    choose.setObjectName("primary")
    choose.clicked.connect(self._fh6_v132_choose_cache_folder)

    refresh = QPushButton(
        "새로고침" if (get_language() or "ko").lower().startswith("ko") else "Refresh"
    )
    refresh.setObjectName("secondary")
    refresh.clicked.connect(lambda _checked=False: _refresh_for_cache_change(self))

    row.addWidget(self.cache_path_edit, 1)
    row.addWidget(choose)
    row.addWidget(refresh)
    layout.insertLayout(1, row)


def _restore_cache_path(self: Any) -> None:
    stored = self.settings.value(_CACHE_SETTING_KEY, "", str).strip()
    if stored and is_thumbnail_cache_dir(Path(stored)):
        _set_cache_path(self, Path(stored), persist=False)
    else:
        self._fh6_v132_auto_detect_cache(silent=True, rescan=False)


def _install_source_controls(self: Any, controls: Any) -> None:
    row = QHBoxLayout()
    row.setSpacing(7)
    label = QLabel(_t("show_label"))
    label.setObjectName("muted")
    row.addWidget(label)

    saved = QPushButton(_t("my_designs"))
    saved.setObjectName("secondary")
    saved.setCheckable(True)
    saved.setChecked(
        self.local_preferences.get_bool(_SHOW_MY_DESIGNS_KEY, True)
    )

    auction = QPushButton(_t("auction"))
    auction.setObjectName("secondary")
    auction.setCheckable(True)
    auction.setChecked(
        self.local_preferences.get_bool(_SHOW_AUCTION_KEY, True)
    )

    self.livery_my_designs_toggle = saved
    self.livery_auction_toggle = auction

    saved.toggled.connect(
        lambda enabled: self._fh6_v132_set_source_enabled(
            "my_designs", enabled
        )
    )
    auction.toggled.connect(
        lambda enabled: self._fh6_v132_set_source_enabled(
            "auction", enabled
        )
    )
    row.addWidget(saved)
    row.addWidget(auction)
    row.addStretch(1)
    controls.insertLayout(1, row)


def _add_auction_badge(card: Any) -> None:
    image_label = getattr(card, "_fh6_image_label", None)
    host = image_label.parentWidget() if image_label is not None else None
    if host is None:
        return
    badge = QLabel(_t("auction_badge"), host)
    badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    badge.setStyleSheet(
        "QLabel { background:rgba(238,233,255,245); color:#5f39d8; "
        "border:1px solid #cfc2ff; border-radius:7px; padding:4px 8px; "
        "font-size:9pt; font-weight:700; }"
    )
    badge.adjustSize()
    badge.move(10, 10)
    badge.show()
    badge.raise_()
    card._fh6_auction_badge = badge
