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

from .auction_thumbnails import (
    auto_detect_thumbnail_cache,
    is_thumbnail_cache_dir,
)
from .i18n import get_language
from .models import LiveryRecord
from .ui import SummaryCard
from .ui_cleanup import _normalize_path_rows

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
    path = auto_detect_thumbnail_cache()
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
    row.setSpacing(8)
    label = QLabel(_t("cache_label"))
    label.setObjectName("muted")
    label.setMinimumWidth(132)

    self.cache_path_edit = QLineEdit()
    self.cache_path_edit.setReadOnly(True)
    self.cache_path_edit.setPlaceholderText(_t("cache_placeholder"))

    choose = QPushButton(_t("cache_choose"))
    choose.setObjectName("secondary")
    choose.clicked.connect(self._fh6_v132_choose_cache_folder)

    auto = QPushButton(_t("cache_auto"))
    auto.setObjectName("secondary")
    auto.clicked.connect(
        lambda _checked=False: self._fh6_v132_auto_detect_cache(
            silent=False,
            rescan=True,
        )
    )

    row.addWidget(label)
    row.addWidget(self.cache_path_edit, 1)
    row.addWidget(choose)
    row.addWidget(auto)
    layout.insertLayout(1, row)


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


def apply_v1_3_2_patches(MainWindow) -> None:
    """Add auction/SoulBound livery browsing without touching game navigation order."""
    if getattr(MainWindow, "_fh6_v132_patched", False):
        return

    original_init = MainWindow.__init__
    original_build_ui = MainWindow._build_ui
    original_dashboard_page = MainWindow._dashboard_page
    original_livery_page = MainWindow._livery_page
    original_build_controls = MainWindow._build_saved_content_controls
    original_populate_all = MainWindow._populate_all
    original_sorted_saved_content = MainWindow._sorted_saved_content
    original_record_for_content_key = MainWindow._record_for_content_key
    original_make_card = MainWindow._make_saved_content_card
    original_livery_search_text = MainWindow._livery_search_text

    def patched_build_ui(self) -> None:
        original_build_ui(self)
        _install_cache_row(self)
        _normalize_path_rows(self)

    def patched_dashboard_page(self):
        page = original_dashboard_page(self)
        self.card_livery.title.setText(_t("my_designs"))

        page_layout = page.layout()
        cards = page_layout.itemAt(1).layout() if page_layout is not None else None
        if cards is not None:
            cards.removeWidget(self.card_tuning)
            self.card_auction = SummaryCard(_t("auction"), "—")
            cards.addWidget(self.card_auction, 0, 2)
            cards.addWidget(self.card_tuning, 0, 3)

        section = getattr(self, "saved_livery_section", None)
        if section is not None:
            for label in section.findChildren(QLabel):
                label.setText(_t("my_designs"))
                break
        return page

    def patched_livery_page(self):
        page = original_livery_page(self)
        for label in page.findChildren(QLabel):
            if label.objectName() == "pageTitle":
                label.setText(_t("livery_page"))
                break
        return page

    def patched_build_controls(self, content_type: str):
        result = original_build_controls(self, content_type)
        if content_type == "livery":
            _install_source_controls(self, result[0])
        return result

    def patched_init(self, project_root) -> None:
        original_init(self, project_root)
        self.setWindowTitle("FH6 Assistant v1.3.2")
        for label in self.findChildren(QLabel):
            if label.text().startswith("v1.3.1\n") or label.text().startswith("v1.3\n"):
                label.setText("v1.3.2\nLIVERY & TUNING")
                break

        stored = self.settings.value(_CACHE_SETTING_KEY, "", str).strip()
        if stored and is_thumbnail_cache_dir(Path(stored)):
            _set_cache_path(self, Path(stored), persist=False)
        else:
            self._fh6_v132_auto_detect_cache(
                silent=True,
                rescan=False,
            )

    def patched_populate_all(self) -> None:
        original_populate_all(self)
        if self.result is None:
            return
        self.card_livery.title.setText(_t("my_designs"))
        if hasattr(self, "card_auction"):
            count = sum(
                record.kind == "SoulBoundLivery"
                for record in self.result.liveries
            )
            self.card_auction.value.setText(str(count))

    def patched_sorted_saved_content(self, content_type: str):
        if content_type != "livery":
            return original_sorted_saved_content(self, content_type)
        return _sort_display_liveries(self)

    def patched_record_for_content_key(self, content_type: str, key: str):
        if content_type != "livery" or self.result is None:
            return original_record_for_content_key(self, content_type, key)
        for record in self.result.liveries:
            if record.kind not in {"Livery", "SoulBoundLivery"}:
                continue
            if self._content_annotation_key("livery", record) == key:
                return record
        return None

    def patched_make_card(self, content_type: str, record, key: str):
        card = original_make_card(self, content_type, record, key)
        if (
            content_type == "livery"
            and isinstance(record, LiveryRecord)
            and record.kind == "SoulBoundLivery"
        ):
            move_button = getattr(card, "_fh6_game_move_button", None)
            if move_button is not None:
                move_button.setEnabled(False)
                move_button.hide()
            card.setProperty("liverySource", "auction")
            _add_auction_badge(card)
        elif content_type == "livery":
            card.setProperty("liverySource", "my_designs")
        return card

    def patched_livery_search_text(self, record: LiveryRecord, note: str = "") -> str:
        base = original_livery_search_text(self, record, note)
        source = _t("auction") if record.kind == "SoulBoundLivery" else _t("my_designs")
        return f"{base} {source}".lower()

    MainWindow.__init__ = patched_init
    MainWindow._build_ui = patched_build_ui
    MainWindow._dashboard_page = patched_dashboard_page
    MainWindow._livery_page = patched_livery_page
    MainWindow._build_saved_content_controls = patched_build_controls
    MainWindow._populate_all = patched_populate_all
    MainWindow._sorted_saved_content = patched_sorted_saved_content
    MainWindow._record_for_content_key = patched_record_for_content_key
    MainWindow._make_saved_content_card = patched_make_card
    MainWindow._livery_search_text = patched_livery_search_text

    MainWindow._fh6_v132_choose_cache_folder = _choose_cache_folder
    MainWindow._fh6_v132_auto_detect_cache = _auto_detect_cache
    MainWindow._fh6_v132_set_source_enabled = _set_source_enabled
    MainWindow._fh6_v132_current_cache_path = _current_cache_path
    MainWindow._fh6_v132_display_liveries = _display_liveries
    MainWindow._fh6_v132_patched = True
