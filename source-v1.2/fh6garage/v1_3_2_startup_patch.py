from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from . import v1_3_2_patch as v132


def fixed_default_thumbnail_cache(
    local_appdata: Path | None = None,
) -> Optional[Path]:
    """Return the single supported FH6 CacheThumbnails path.

    No package enumeration, Steam probing, alternate-package probing, or
    filesystem discovery is performed. The caller may later validate the
    returned directory when it actually needs to read the manifest.
    """
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


def apply_v1_3_2_startup_patches() -> None:
    """Force v1.3.2 to use the single default CacheThumbnails path."""
    v132.auto_detect_thumbnail_cache = fixed_default_thumbnail_cache
