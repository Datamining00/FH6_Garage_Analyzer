from __future__ import annotations

from .models import LiveryRecord


def apply_v1_3_2_safety_patches(MainWindow) -> None:
    """Keep auction records isolated from My Designs-only semantics."""
    if getattr(MainWindow, "_fh6_v132_safety_patched", False):
        return

    original_is_duplicate_livery = MainWindow._is_duplicate_livery
    original_make_saved_content_card = MainWindow._make_saved_content_card
    original_request_game_navigation = MainWindow._request_game_navigation

    def patched_is_duplicate_livery(self, record: LiveryRecord | None) -> bool:
        # SoulBoundLivery is not an entry in FH6's My Designs list.
        if record is not None and record.kind == "SoulBoundLivery":
            return False
        return original_is_duplicate_livery(self, record)

    def patched_make_saved_content_card(self, content_type, record, key):
        card = original_make_saved_content_card(
            self,
            content_type,
            record,
            key,
        )
        if (
            content_type == "livery"
            and isinstance(record, LiveryRecord)
            and record.kind == "SoulBoundLivery"
        ):
            # v1.3.1's generic livery card creates a move button. Auction
            # liveries are not present in FH6 My Designs, so remove the control
            # from the widget tree before the card is ever displayed.
            move_button = getattr(card, "_fh6_game_move_button", None)
            if move_button is not None:
                move_button.hide()
                move_button.setParent(None)
                move_button.deleteLater()
            card._fh6_game_move_button = None
        return card

    def patched_request_game_navigation(self, content_type: str, key: str) -> None:
        # Defense in depth: even a stale shortcut/programmatic call can never
        # send navigation input for a SoulBound auction record.
        if content_type == "livery":
            record = self._record_for_content_key(content_type, key)
            if (
                isinstance(record, LiveryRecord)
                and record.kind == "SoulBoundLivery"
            ):
                return
        original_request_game_navigation(self, content_type, key)

    MainWindow._is_duplicate_livery = patched_is_duplicate_livery
    MainWindow._make_saved_content_card = patched_make_saved_content_card
    MainWindow._request_game_navigation = patched_request_game_navigation
    MainWindow._fh6_v132_safety_patched = True
