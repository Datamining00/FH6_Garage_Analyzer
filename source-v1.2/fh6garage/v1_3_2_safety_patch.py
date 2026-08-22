from __future__ import annotations

from .models import LiveryRecord


def apply_v1_3_2_safety_patches(MainWindow) -> None:
    """Keep auction records isolated from My Designs-only semantics."""
    if getattr(MainWindow, "_fh6_v132_safety_patched", False):
        return

    original_is_duplicate_livery = MainWindow._is_duplicate_livery

    def patched_is_duplicate_livery(self, record: LiveryRecord | None) -> bool:
        # SoulBoundLivery is a garage/auction-bound design and is not an entry in
        # FH6's My Designs list.  Even if its C_livery payload happens to hash to
        # the same bytes as a saved design, it must not participate in the
        # existing duplicate-My-Designs filter/group semantics.
        if record is not None and record.kind == "SoulBoundLivery":
            return False
        return original_is_duplicate_livery(self, record)

    MainWindow._is_duplicate_livery = patched_is_duplicate_livery
    MainWindow._fh6_v132_safety_patched = True
