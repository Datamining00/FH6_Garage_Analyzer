from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton

from . import v1_3_2_patch as v132


def fixed_default_thumbnail_cache(
    local_appdata: Path | None = None,
) -> Optional[Path]:
    """Return the default FH6 CacheThumbnails path without probing the filesystem."""
    if local_appdata is None:
        raw = os.environ.get("LOCALAPPDATA", "").strip()
        if not raw:
            return None
        local_appdata = Path(raw)

    return (
        Path(local_appdata)
        / "Packages"
        / "Microsoft.ForteBaseGame_8wekyb3d8bbwe"
        / "LocalCache"
        / "Local"
        / "LocalStorage_Cache"
        / "CacheThumbnails"
    )


def _install_fixed_cache_row(self) -> None:
    """Install a save-path-style cache row without any automatic path search.

    The default path is deterministic. Users may still explicitly choose another
    CacheThumbnails folder; the chosen path is persisted by the existing v1.3.2
    picker. No package/Steam/fallback discovery is performed.
    """
    if hasattr(self, "cache_path_edit"):
        return

    content = self.path_edit.parentWidget()
    layout = content.layout() if content is not None else None
    if layout is None or not hasattr(layout, "insertLayout"):
        return

    row = QHBoxLayout()
    self.cache_path_edit = QLineEdit()
    self.cache_path_edit.setReadOnly(True)
    self.cache_path_edit.setPlaceholderText(v132._t("cache_placeholder"))

    choose = QPushButton(v132._t("cache_choose"))
    choose.setObjectName("primary")
    choose.clicked.connect(self._fh6_v132_choose_cache_folder)

    refresh = QPushButton(
        "새로고침" if (v132.get_language() or "ko").lower().startswith("ko") else "Refresh"
    )
    refresh.setObjectName("secondary")
    refresh.clicked.connect(lambda _checked=False: v132._refresh_for_cache_change(self))

    row.addWidget(self.cache_path_edit, 1)
    row.addWidget(choose)
    row.addWidget(refresh)
    layout.insertLayout(1, row)


def apply_v1_3_2_startup_patches() -> None:
    """Use one deterministic default path while preserving manual path selection."""
    # patched_init in v1_3_2_patch calls this symbol. It returns only the fixed
    # default path and never enumerates Packages or probes Steam/fallback paths.
    v132.auto_detect_thumbnail_cache = fixed_default_thumbnail_cache

    # Keep a visible manual picker, styled and arranged like the save-folder row.
    # The previous Auto-detect control is deliberately omitted.
    v132._install_cache_row = _install_fixed_cache_row
