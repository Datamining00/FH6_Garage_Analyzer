from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import v1_3_2_patch as _v132
from . import v1_3_2_responsiveness_sort_patch as _responsive
from .auction_manifest_registry import read_auction_manifest_registry
from .auction_thumbnails import (
    AuctionThumbnailManifestError,
    _header_livery_token,
    read_thumbnail_manifest,
)
from .i18n import get_language
from .memory_applied_state import (
    MemoryScanResult,
    PersistedAppliedState,
    build_persisted_state,
    load_applied_state,
    normalized_livery_name,
    save_applied_state,
    scan_applied_liveries,
)
from .models import LiveryRecord

FILTER_DEFAULT = "DEFAULT"
FILTER_APPLIED = "APPLIED_ONLY"
FILTER_UNAPPLIED = "UNAPPLIED_ONLY"

CARD_ACTION_BUTTON_SIZE = 30
CARD_ACTION_ICON_SIZE = 20


def _txt(ko: str, en: str) -> str:
    return ko if (get_language() or "ko").lower().startswith("ko") else en


_PAINT_ICON_COLORS = {
    # Mid-lightness saturated colors remain distinct on the white card overlay.
    "applied": QColor("#16a34a"),
    "same_car_applied": QColor("#d97706"),
    "unapplied": QColor("#6b7280"),
    "unknown": QColor("#8a94a3"),
}
_PAINT_ICON_CACHE: dict[tuple[str, int], QPixmap] = {}


def _paint_bucket_pixmap(state: str, size: int = CARD_ACTION_ICON_SIZE) -> QPixmap:
    """Tint the user-provided paint-bucket artwork for the current state."""
    key = (state, int(size))
    cached = _PAINT_ICON_CACHE.get(key)
    if cached is not None:
        return QPixmap(cached)

    from .card_icons import pixmap as card_pixmap

    color = _PAINT_ICON_COLORS.get(state, _PAINT_ICON_COLORS["unknown"])
    pixmap = card_pixmap("paint", color, size)
    _PAINT_ICON_CACHE[key] = QPixmap(pixmap)
    return pixmap


def _card_overlay(card: Any) -> QWidget | None:
    image_label = getattr(card, "_fh6_image_label", None)
    if image_label is None:
        return None
    host = image_label.parentWidget()
    stack = host.layout() if host is not None else None
    overlay = stack.currentWidget() if stack is not None and hasattr(stack, "currentWidget") else None
    return overlay if isinstance(overlay, QWidget) else None


def _center_in_overlay(widget: QWidget, overlay: QWidget) -> QPoint:
    return widget.mapTo(overlay, widget.rect().center())


def _top_left_for_center(center: QPoint, widget: QWidget) -> QPoint:
    return QPoint(
        center.x() - (widget.width() - 1) // 2,
        center.y() - (widget.height() - 1) // 2,
    )


class _AppliedStateAligner(QObject):
    _EVENTS = {
        QEvent.Type.Show,
        QEvent.Type.Resize,
        QEvent.Type.LayoutRequest,
        QEvent.Type.PolishRequest,
    }

    def __init__(self, card: Any, overlay: QWidget, button: QToolButton) -> None:
        super().__init__(overlay)
        self.card = card
        self.overlay = overlay
        self.button = button
        overlay.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in self._EVENTS:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.reposition)
        return False

    def reposition(self) -> None:
        folder = getattr(self.card, "_fh6_folder_button", None)
        memo = getattr(self.card, "_fh6_memo_button", None)
        if not isinstance(folder, QToolButton) or not isinstance(memo, QToolButton):
            return
        if not folder.isVisible() or not memo.isVisible():
            return
        x = _center_in_overlay(folder, self.overlay).x()
        y = _center_in_overlay(memo, self.overlay).y()
        self.button.move(_top_left_for_center(QPoint(x, y), self.button))
        self.button.raise_()


class _MemoryScanWorker(QObject):
    progress = Signal(int, int, int, int, float)
    finished = Signal(object)
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            result = scan_applied_liveries(
                progress=lambda done, total, read_bytes, failures, elapsed:
                self.progress.emit(done, total, read_bytes, failures, elapsed)
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)


def _memory_state_usable(window: Any) -> bool:
    state = getattr(window, "_fh6_memory_state", None)
    return isinstance(state, PersistedAppliedState) and state.usable


def _livery_state_for_record(window: Any, record: Any) -> str:
    if not isinstance(record, LiveryRecord) or not _memory_state_usable(window):
        return "unknown"
    state: PersistedAppliedState = window._fh6_memory_state
    name = normalized_livery_name(record.container_name)
    if not name:
        return "unknown"

    if record.kind == "SoulBoundLivery":
        if name in state.soulbound_applied_names:
            return "applied"
        if name in state.soulbound_unapplied_names:
            return "unapplied"
        return "unknown"

    if record.kind == "Livery":
        return "applied" if name in state.active_livery_names else "unapplied"
    return "unknown"


def _paint_state_for_record(window: Any, record: Any) -> str:
    """Return the three-color display state without changing filter semantics."""
    state = _livery_state_for_record(window, record)
    if state != "unapplied" or not isinstance(record, LiveryRecord):
        return state

    target_car_id = record.car_id
    if target_car_id is None:
        return "unapplied"
    for candidate in getattr(getattr(window, "result", None), "liveries", []):
        if not isinstance(candidate, LiveryRecord) or candidate.car_id != target_car_id:
            continue
        if _livery_state_for_record(window, candidate) == "applied":
            return "same_car_applied"
    return "unapplied"


def _set_card_state_icon(window: Any, card: Any, record: Any) -> None:
    button = getattr(card, "_fh6_applied_state_button", None)
    if not isinstance(button, QToolButton):
        return
    state = _paint_state_for_record(window, record)
    button.setIcon(QIcon(_paint_bucket_pixmap(state)))
    if state == "applied":
        button.setToolTip(_txt("현재 적용 중", "Currently applied"))
        button.setAccessibleName(_txt("현재 적용 중", "Currently applied"))
    elif state == "same_car_applied":
        button.setToolTip(
            _txt(
                "현재 미적용 · 동일 차량의 다른 리버리가 적용 중",
                "Currently unapplied · another livery for the same car is applied",
            )
        )
        button.setAccessibleName(
            _txt("동일 차량의 다른 리버리 적용 중", "Another same-car livery is applied")
        )
    elif state == "unapplied":
        button.setToolTip(
            _txt(
                "현재 미적용 · 해당 차량에 적용된 리버리 없음",
                "Currently unapplied · no applied livery for this car",
            )
        )
        button.setAccessibleName(_txt("현재 미적용", "Currently unapplied"))
    else:
        button.setToolTip(
            _txt(
                "적용 상태 미확인 · 메모리 스캔 후 확인할 수 있습니다.",
                "Application state unknown · Run a memory scan to verify.",
            )
        )
        button.setAccessibleName(_txt("적용 상태 미확인", "Application state unknown"))
    button.setProperty("fh6AppliedState", state)


def _install_card_state_icon(window: Any, card: Any, record: Any) -> None:
    if bool(card.property("fh6ArchiveCard")):
        return
    existing = getattr(card, "_fh6_applied_state_button", None)
    if isinstance(existing, QToolButton):
        _set_card_state_icon(window, card, record)
        return

    overlay = _card_overlay(card)
    folder = getattr(card, "_fh6_folder_button", None)
    memo = getattr(card, "_fh6_memo_button", None)
    if overlay is None or not isinstance(folder, QToolButton) or not isinstance(memo, QToolButton):
        return

    button = QToolButton(overlay)
    button.setObjectName("fh6AppliedStateButton")
    button.setFixedSize(CARD_ACTION_BUTTON_SIZE, CARD_ACTION_BUTTON_SIZE)
    button.setIconSize(QSize(CARD_ACTION_ICON_SIZE, CARD_ACTION_ICON_SIZE))
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCursor(Qt.CursorShape.ArrowCursor)
    button.setStyleSheet(
        "QToolButton { background:rgba(255,255,255,242); color:#626979; "
        "border:1px solid #dfe1e8; border-radius:8px; padding:0; }"
        "QToolButton:hover { border-color:#8c74ee; background:rgba(247,245,255,250); }"
    )
    button.show()
    card._fh6_applied_state_button = button

    native_grid = getattr(card, "_fh6_action_grid", None)
    if native_grid is not None:
        button.setIconSize(QSize(20, 20))
        native_grid.addWidget(
            button, 0, 1,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        _set_card_state_icon(window, card, record)
        return

    aligner = _AppliedStateAligner(card, overlay, button)
    card._fh6_applied_state_aligner = aligner
    _set_card_state_icon(window, card, record)

    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, aligner.reposition)
    QTimer.singleShot(50, aligner.reposition)


def _update_all_card_state_icons(window: Any) -> None:
    resolver = getattr(window, "_record_for_content_key", None)
    if not callable(resolver):
        return
    for card in getattr(window, "_livery_grid_cards", []):
        key = str(card.property("annotationKey") or "")
        record = resolver("livery", key) if key else None
        if record is not None:
            _install_card_state_icon(window, card, record)


def _set_status_filter_mode(window: Any, mode: str) -> None:
    current = getattr(window, "_fh6_memory_livery_filter_mode", FILTER_DEFAULT)
    new_mode = FILTER_DEFAULT if current == mode else mode
    window._fh6_memory_livery_filter_mode = new_mode

    applied = getattr(window, "livery_applied_toggle", None)
    unapplied = getattr(window, "livery_unapplied_toggle", None)
    if isinstance(applied, QPushButton) and isinstance(unapplied, QPushButton):
        applied.blockSignals(True)
        unapplied.blockSignals(True)
        applied.setChecked(new_mode == FILTER_APPLIED)
        unapplied.setChecked(new_mode == FILTER_UNAPPLIED)
        applied.blockSignals(False)
        unapplied.blockSignals(False)

    search = getattr(window, "livery_search", None)
    if search is not None:
        window._filter_saved_content_views("livery", search.text())


def _update_status_filter_availability(window: Any) -> None:
    enabled = _memory_state_usable(window)
    for name in ("livery_applied_toggle", "livery_unapplied_toggle"):
        button = getattr(window, name, None)
        if not isinstance(button, QPushButton):
            continue
        button.setEnabled(enabled)
        button.setToolTip(
            "" if enabled else _txt(
                "메모리 스캔 후 사용할 수 있습니다.",
                "Available after a memory scan.",
            )
        )
    if not enabled:
        window._fh6_memory_livery_filter_mode = FILTER_DEFAULT
        for name in ("livery_applied_toggle", "livery_unapplied_toggle"):
            button = getattr(window, name, None)
            if isinstance(button, QPushButton):
                button.setChecked(False)


def _install_source_and_state_controls(window: Any, controls: Any, original) -> None:
    original(window, controls)
    row_item = controls.itemAt(1)
    row = row_item.layout() if row_item is not None else None
    if row is None:
        return

    insert_at = max(0, row.count() - 1)
    separator = QLabel("││")
    separator.setObjectName("liveryStateSeparator")
    separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
    separator.setStyleSheet("color:#b1a8c9;font-weight:700;padding:0 2px;")

    applied = QPushButton(_txt("적용된 리버리", "Applied liveries"))
    unapplied = QPushButton(_txt("미적용 리버리", "Unapplied liveries"))
    for button in (applied, unapplied):
        button.setObjectName("secondary")
        button.setCheckable(True)

    window.livery_applied_toggle = applied
    window.livery_unapplied_toggle = unapplied
    window._fh6_memory_livery_filter_mode = FILTER_DEFAULT

    applied.clicked.connect(
        lambda _checked=False, owner=window: _set_status_filter_mode(owner, FILTER_APPLIED)
    )
    unapplied.clicked.connect(
        lambda _checked=False, owner=window: _set_status_filter_mode(owner, FILTER_UNAPPLIED)
    )

    row.insertWidget(insert_at, separator)
    row.insertWidget(insert_at + 1, applied)
    row.insertWidget(insert_at + 2, unapplied)
    _update_status_filter_availability(window)


def _classify_soulbound(
    window: Any,
    result: MemoryScanResult,
) -> tuple[set[str], set[str], set[str]]:
    records = [
        record
        for record in getattr(getattr(window, "result", None), "liveries", [])
        if isinstance(record, LiveryRecord) and record.kind == "SoulBoundLivery"
    ]
    if not records:
        return set(), set(), set()

    cache_getter = getattr(window, "_fh6_v132_current_cache_path", None)
    cache_dir = cache_getter() if callable(cache_getter) else None
    if cache_dir is None:
        return set(), set(), {normalized_livery_name(record.container_name) for record in records}

    try:
        entries = read_thumbnail_manifest(Path(cache_dir))
    except (AuctionThumbnailManifestError, OSError, ValueError):
        return set(), set(), {normalized_livery_name(record.container_name) for record in records}

    try:
        registry = read_auction_manifest_registry(Path(cache_dir))
        registered_names = registry.logical_names
    except (AuctionThumbnailManifestError, OSError, ValueError):
        registered_names = frozenset()

    by_identity: dict[tuple[int, str], list[Any]] = {}
    for entry in entries:
        if entry.livery_token:
            by_identity.setdefault((entry.car_id, entry.livery_token), []).append(entry)

    applied: set[str] = set()
    unapplied: set[str] = set()
    review: set[str] = set()

    for record in records:
        name = normalized_livery_name(record.container_name)
        if not name:
            continue
        exact_memory = name in result.active_livery_names
        token = _header_livery_token(record)
        candidates = by_identity.get((int(record.car_id or -1), token), []) if token else []

        if exact_memory and len(candidates) == 1:
            candidate = candidates[0]
            if candidate.logical_name in registered_names and candidate.path.is_file():
                applied.add(name)
                continue

        if not exact_memory and len(candidates) == 0:
            unapplied.add(name)
            continue

        review.add(name)

    return applied, unapplied, review


def _refresh_memory_page(window: Any) -> None:
    state = getattr(window, "_fh6_memory_state", None)
    if isinstance(state, PersistedAppliedState):
        window.memory_last_scan_label.setText(
            _txt("마지막 스캔: ", "Last scan: ") + (state.scanned_at or "—")
        )
        window.memory_status_value.setText(state.consensus_status)
        window.memory_applied_value.setText(str(len(state.active_livery_names)))
        window.memory_soulbound_applied_value.setText(str(len(state.soulbound_applied_names)))
        window.memory_soulbound_unapplied_value.setText(str(len(state.soulbound_unapplied_names)))
        window.memory_review_value.setText(str(len(state.soulbound_review_names)))
    else:
        window.memory_last_scan_label.setText(_txt("마지막 스캔: 없음", "Last scan: none"))
        for label in (
            window.memory_status_value,
            window.memory_applied_value,
            window.memory_soulbound_applied_value,
            window.memory_soulbound_unapplied_value,
            window.memory_review_value,
        ):
            label.setText("—")


def _memory_scan_page(window: Any) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(14)

    title = QLabel(_txt("메모리 스캔", "Memory scan"))
    title.setObjectName("pageTitle")
    layout.addWidget(title)

    subtitle = QLabel(
        _txt(
            "FH6 프로세스 메모리를 읽기 전용으로 검사하여 현재 적용된 리버리를 확인합니다.",
            "Reads the FH6 process in read-only mode to identify currently applied liveries.",
        )
    )
    subtitle.setObjectName("muted")
    subtitle.setWordWrap(True)
    layout.addWidget(subtitle)

    panel = QFrame()
    panel.setObjectName("panel")
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(18, 16, 18, 16)
    panel_layout.setSpacing(9)

    rows = (
        (_txt("판정 상태", "Scan status"), "memory_status_value"),
        (_txt("현재 적용 리버리", "Current applied liveries"), "memory_applied_value"),
        (_txt("경매장 리버리 적용", "Applied auction liveries"), "memory_soulbound_applied_value"),
        (_txt("경매장 리버리 미적용", "Unapplied auction liveries"), "memory_soulbound_unapplied_value"),
        (_txt("재검토 필요", "Needs review"), "memory_review_value"),
    )
    for caption, attr in rows:
        row = QHBoxLayout()
        label = QLabel(caption)
        label.setObjectName("muted")
        value = QLabel("—")
        value.setStyleSheet("font-weight:700;")
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(value)
        panel_layout.addLayout(row)
        setattr(window, attr, value)

    layout.addWidget(panel)

    refresh = QPushButton(_txt("메모리 새로고침", "Refresh memory scan"))
    refresh.setObjectName("primary")
    refresh.setMinimumHeight(40)
    refresh.clicked.connect(lambda _checked=False, owner=window: _request_memory_scan(owner))
    window.memory_refresh_button = refresh
    layout.addWidget(refresh, 0, Qt.AlignmentFlag.AlignLeft)

    last = QLabel(_txt("마지막 스캔: 없음", "Last scan: none"))
    last.setObjectName("muted")
    window.memory_last_scan_label = last
    layout.addWidget(last)

    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.hide()
    window.memory_scan_progress = progress
    layout.addWidget(progress)

    detail = QLabel("")
    detail.setObjectName("muted")
    detail.setWordWrap(True)
    window.memory_scan_detail = detail
    layout.addWidget(detail)
    layout.addStretch(1)
    return page


def _install_memory_navigation(window: Any) -> None:
    page = _memory_scan_page(window)
    window.memory_scan_page = page
    window.pages.addWidget(page)

    sidebar = window.findChild(QFrame, "sidebar")
    if sidebar is None or sidebar.layout() is None:
        return

    button = QPushButton(_txt("메모리 스캔", "Memory scan"), sidebar)
    button.setObjectName("nav")
    button.setCheckable(True)
    button.clicked.connect(
        lambda _checked=False, owner=window, target=page:
        owner.pages.setCurrentWidget(target)
    )
    window.nav_group.addButton(button)
    window.nav_buttons.append(button)

    alias = getattr(window, "creator_alias_button", None)
    layout = sidebar.layout()
    if alias is not None:
        index = layout.indexOf(alias)
        layout.insertWidget(index + 1 if index >= 0 else 1 + len(window.nav_buttons), button)
    else:
        layout.insertWidget(1 + len(window.nav_buttons) - 1, button)
    window.memory_nav_button = button


def _request_memory_scan(window: Any) -> None:
    if getattr(window, "_fh6_memory_scan_running", False):
        return
    answer = QMessageBox.question(
        window,
        _txt("메모리 스캔", "Memory scan"),
        _txt(
            "FH6의 실행 중인 프로세스 메모리를 읽기 전용으로 검사합니다.\n메모리 스캔을 수행하시겠습니까?",
            "FH6 process memory will be inspected in read-only mode.\nRun the memory scan?",
        ),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return
    _start_memory_scan(window)


def _start_memory_scan(window: Any) -> None:
    window._fh6_memory_scan_running = True
    window.memory_refresh_button.setEnabled(False)
    window.memory_scan_progress.setRange(0, 100)
    window.memory_scan_progress.setValue(0)
    window.memory_scan_progress.show()
    window.memory_scan_detail.setText(_txt("스캔 준비 중…", "Preparing scan…"))

    thread = QThread(window)
    worker = _MemoryScanWorker()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.progress.connect(
        lambda done, total, read_bytes, failures, elapsed, owner=window:
        _on_memory_progress(owner, done, total, read_bytes, failures, elapsed)
    )
    worker.finished.connect(lambda result, owner=window: _on_memory_finished(owner, result))
    worker.failed.connect(lambda message, owner=window: _on_memory_failed(owner, message))
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(lambda owner=window: _clear_memory_thread(owner))
    window._fh6_memory_thread = thread
    window._fh6_memory_worker = worker
    thread.start()


def _clear_memory_thread(window: Any) -> None:
    window._fh6_memory_thread = None
    window._fh6_memory_worker = None


def _on_memory_progress(window: Any, done: int, total: int, read_bytes: int, failures: int, elapsed: float) -> None:
    percent = 0 if total <= 0 else max(0, min(100, round(done * 100 / total)))
    window.memory_scan_progress.setValue(percent)
    gib = read_bytes / (1024 ** 3)
    window.memory_scan_detail.setText(
        _txt(
            f"영역 {done}/{total} · {gib:.2f} GB 읽음 · 읽기 실패 {failures} · {elapsed:.1f}초",
            f"Regions {done}/{total} · {gib:.2f} GB read · failures {failures} · {elapsed:.1f}s",
        )
    )


def _finish_scan_ui(window: Any) -> None:
    window._fh6_memory_scan_running = False
    window.memory_refresh_button.setEnabled(True)
    window.memory_scan_progress.hide()


def _on_memory_finished(window: Any, result: object) -> None:
    _finish_scan_ui(window)
    if not isinstance(result, MemoryScanResult):
        _on_memory_failed(
            window,
            _txt("알 수 없는 스캔 결과", "Unknown scan result"),
            already_finished=True,
        )
        return
    if not result.usable:
        window.memory_scan_detail.setText(
            _txt(
                f"판정을 확정하지 못했습니다 ({result.status}). 마지막 정상 스캔 결과를 유지합니다.",
                f"The scan was not conclusive ({result.status}). The last valid scan is retained.",
            )
        )
        QMessageBox.warning(
            window,
            _txt("메모리 스캔 결과", "Memory scan result"),
            window.memory_scan_detail.text(),
        )
        return

    applied, unapplied, review = _classify_soulbound(window, result)
    state = build_persisted_state(
        result,
        soulbound_applied_names=applied,
        soulbound_unapplied_names=unapplied,
        soulbound_review_names=review,
    )
    summary = _txt(
        f"현재 적용 {len(state.active_livery_names)} · 경매장 적용 {len(applied)} · "
        f"미적용 {len(unapplied)}"
        + (f" · 재검토 {len(review)}" if review else "")
        + "\n\n이 결과를 목록에 적용하시겠습니까?",
        f"Applied {len(state.active_livery_names)} · auction applied {len(applied)} · "
        f"unapplied {len(unapplied)}"
        + (f" · review {len(review)}" if review else "")
        + "\n\nApply this result to the list?",
    )
    answer = QMessageBox.question(
        window,
        _txt("메모리 스캔 결과", "Memory scan result"),
        summary,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        window.memory_scan_detail.setText(
            _txt(
                "스캔 결과를 적용하지 않았습니다. 마지막 정상 적용 결과를 유지합니다.",
                "The scan result was not applied. The last applied valid result is retained.",
            )
        )
        return

    window._fh6_memory_state = state
    save_applied_state(state)
    _refresh_memory_page(window)
    _update_status_filter_availability(window)
    _update_all_card_state_icons(window)

    window.memory_scan_detail.setText(
        _txt(
            f"완료 · 현재 적용 {len(state.active_livery_names)} · 경매장 적용 {len(applied)} · 미적용 {len(unapplied)}"
            + (f" · 재검토 {len(review)}" if review else ""),
            f"Complete · applied {len(state.active_livery_names)} · auction applied {len(applied)} · unapplied {len(unapplied)}"
            + (f" · review {len(review)}" if review else ""),
        )
    )

    search = getattr(window, "livery_search", None)
    if search is not None:
        window._filter_saved_content_views("livery", search.text())


def _on_memory_failed(window: Any, message: str, *, already_finished: bool = False) -> None:
    if not already_finished:
        _finish_scan_ui(window)
    text = _txt(
        f"메모리 스캔에 실패했습니다. 마지막 정상 스캔 결과를 유지합니다.\n\n{message}",
        f"Memory scan failed. The last valid scan is retained.\n\n{message}",
    )
    window.memory_scan_detail.setText(text)
    QMessageBox.warning(window, _txt("메모리 스캔 실패", "Memory scan failed"), text)


def _memory_filter_allows(window: Any, record: Any) -> bool:
    mode = getattr(window, "_fh6_memory_livery_filter_mode", FILTER_DEFAULT)
    if mode == FILTER_DEFAULT or not _memory_state_usable(window):
        return True
    state = _livery_state_for_record(window, record)
    if mode == FILTER_APPLIED:
        return state == "applied"
    if mode == FILTER_UNAPPLIED:
        return state == "unapplied"
    return True


def apply_v1_3_2_memory_state_patch(MainWindow: Any) -> None:
    """Integrate independent read-only applied-livery memory state into v1.3.2."""
    if getattr(MainWindow, "_fh6_v132_memory_state_patched", False):
        return

    original_source_controls = _v132._install_source_controls
    original_init = MainWindow.__init__
    original_make_card = MainWindow._make_saved_content_card
    original_populate_all = MainWindow._populate_all
    original_table_filter = MainWindow._filter_saved_content_table
    original_visibility = _responsive._livery_visibility_allowed

    def source_controls(window: Any, controls: Any) -> None:
        _install_source_and_state_controls(window, controls, original_source_controls)

    _v132._install_source_controls = source_controls

    def patched_init(self, *args, **kwargs) -> None:
        self._fh6_memory_state = load_applied_state()
        self._fh6_memory_livery_filter_mode = FILTER_DEFAULT
        self._fh6_memory_scan_running = False
        self._fh6_memory_thread = None
        self._fh6_memory_worker = None
        original_init(self, *args, **kwargs)
        _install_memory_navigation(self)
        _refresh_memory_page(self)
        _update_status_filter_availability(self)
        _update_all_card_state_icons(self)

    def patched_make_card(self, content_type: str, record: Any, key: str):
        card = original_make_card(self, content_type, record, key)
        if content_type == "livery" and isinstance(record, LiveryRecord):
            _install_card_state_icon(self, card, record)
        return card

    def patched_populate_all(self) -> None:
        original_populate_all(self)
        _update_all_card_state_icons(self)
        _refresh_memory_page(self)
        _update_status_filter_availability(self)

    def patched_table_filter(self, content_type: str, text: str) -> None:
        original_table_filter(self, content_type, text)
        if content_type != "livery" or not _memory_state_usable(self):
            return
        mode = getattr(self, "_fh6_memory_livery_filter_mode", FILTER_DEFAULT)
        if mode == FILTER_DEFAULT:
            return
        table = getattr(self, "livery_table", None)
        if table is None:
            return
        for row in range(table.rowCount()):
            if table.isRowHidden(row):
                continue
            item = table.item(row, 0)
            key = str(item.data(Qt.ItemDataRole.UserRole) or "") if item is not None else ""
            record = self._record_for_content_key("livery", key) if key else None
            if not _memory_filter_allows(self, record):
                table.setRowHidden(row, True)

    def memory_visibility(self, card: Any) -> bool:
        if not original_visibility(self, card):
            return False
        if not _memory_state_usable(self):
            return True
        mode = getattr(self, "_fh6_memory_livery_filter_mode", FILTER_DEFAULT)
        if mode == FILTER_DEFAULT:
            return True
        key = str(card.property("annotationKey") or "")
        record = self._record_for_content_key("livery", key) if key else None
        return _memory_filter_allows(self, record)

    def memory_auction_applied(self, record: Any) -> bool:
        if _memory_state_usable(self):
            return _livery_state_for_record(self, record) == "applied"
        path = getattr(record, "thumbnail_path", None)
        try:
            return bool(path is not None and path.is_file())
        except OSError:
            return False

    MainWindow.__init__ = patched_init
    MainWindow._make_saved_content_card = patched_make_card
    MainWindow._populate_all = patched_populate_all
    MainWindow._filter_saved_content_table = patched_table_filter
    MainWindow._fh6_memory_state_usable = _memory_state_usable
    MainWindow._fh6_memory_livery_state_for_record = _livery_state_for_record
    MainWindow._fh6_v132_is_auction_applied = memory_auction_applied
    _responsive._livery_visibility_allowed = memory_visibility
    MainWindow._fh6_v132_memory_state_patched = True
