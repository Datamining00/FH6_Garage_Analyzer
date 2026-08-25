from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def fixed_default_thumbnail_cache(
    local_appdata: Path | None = None,
) -> Optional[Path]:
    """Return the deterministic Microsoft Store CacheThumbnails location."""
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
