from __future__ import annotations


def apply_v1_3_2_card_parent_patches(MainWindow) -> None:
    """Prevent livery cards from ever existing as parentless top-level widgets.

    The base card factory creates QFrame() without a parent and only reparents it
    later when the grid layout is rebuilt. During long livery rebuilds the base
    code periodically calls QApplication.processEvents(). On Windows, that leaves
    a timing window where a card can surface as a stray top-level native window.

    Keep the original card construction and layout logic, but immediately attach
    every livery card (My Designs and SoulBound) to livery_grid_host before the
    factory call returns. The existing relayout code still controls visibility
    and geometry exactly as before.
    """
    if getattr(MainWindow, "_fh6_v132_card_parent_patched", False):
        return

    original_make_livery_card = MainWindow._make_livery_card

    def patched_make_livery_card(self, record, key):
        card = original_make_livery_card(self, record, key)
        host = getattr(self, "livery_grid_host", None)
        if host is not None and card.parentWidget() is not host:
            card.setParent(host)
        # Card visibility is still owned by the existing grid relayout/filter
        # path. Hiding here ensures processEvents() can never expose an
        # incompletely configured card as a native top-level window.
        card.hide()
        return card

    MainWindow._make_livery_card = patched_make_livery_card
    MainWindow._fh6_v132_card_parent_patched = True
