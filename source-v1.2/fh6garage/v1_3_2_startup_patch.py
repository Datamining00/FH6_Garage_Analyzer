from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QLineEdit

from . import v1_3_2_patch as v132


def fixed_default_thumbnail_cache(
    local_appdata: Path | None = None,
) -> Optional[Path]:
    """Return the one supported FH6 CacheThumbnails path without probing."""
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


def _install_fixed_cache_holder(self) -> None:
    """Provide the cache path internally without adding cache-path UI controls."""
    if hasattr(self, "cache_path_edit"):
        return

    # Discard any path saved by earlier v1.3.2 test builds. This release always
    # uses the single default Microsoft Store/Xbox path.
    self.settings.remove(v132._CACHE_SETTING_KEY)

    holder = QLineEdit(self)
    holder.setReadOnly(True)
    holder.setVisible(False)
    default = fixed_default_thumbnail_cache()
    holder.setText(str(default) if default is not None else "")
    self.cache_path_edit = holder


def apply_v1_3_2_startup_patches() -> None:
    """Force v1.3.2 to use only the default cache path and expose no path picker."""
    # patched_init in v1_3_2_patch still calls this symbol, but it now performs
    # no discovery: it simply returns the fixed path.
    v132.auto_detect_thumbnail_cache = fixed_default_thumbnail_cache

    # patched_build_ui resolves this global when the MainWindow is constructed.
    # Replace the previous visible [path / choose / auto-detect] row with a hidden
    # internal holder so no alternate path can be selected or scanned.
    v132._install_cache_row = _install_fixed_cache_holder
