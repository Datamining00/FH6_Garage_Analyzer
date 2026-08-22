from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from . import v1_3_2_patch as v132


def fast_auto_detect_thumbnail_cache(
    local_appdata: Path | None = None,
) -> Optional[Path]:
    """Find FH6 CacheThumbnails without broadly probing every UWP package.

    v1.3.2 initially enumerated every ``Microsoft.*`` package and performed
    filesystem checks before the main window was shown. On some Windows
    installations those package probes can be slow enough for Explorer to mark
    the application as not responding during startup.

    Check the verified FH6 paths first, then inspect package *names* only for the
    two FH6 package families observed so far. Unrelated UWP package directories
    are never stat'ed or opened.
    """
    if local_appdata is None:
        raw = os.environ.get("LOCALAPPDATA", "").strip()
        if not raw:
            return None
        local_appdata = Path(raw)

    local_appdata = Path(local_appdata)
    relative = (
        Path("LocalCache")
        / "Local"
        / "LocalStorage_Cache"
        / "CacheThumbnails"
    )

    candidates = (
        local_appdata
        / "Packages"
        / "Microsoft.ForteBaseGame_8wekyb3d8bbwe"
        / relative,
        local_appdata
        / "ForzaHorizon6"
        / "LocalStorage_Cache"
        / "CacheThumbnails",
    )
    for candidate in candidates:
        try:
            if candidate.is_dir() and (candidate / ".manifest").is_file():
                return candidate
        except OSError:
            continue

    packages = local_appdata / "Packages"
    try:
        with os.scandir(packages) as entries:
            for entry in entries:
                name = entry.name.casefold()
                if not (
                    name.startswith("microsoft.fortebasegame_")
                    or name.startswith("microsoft.624f8b84b80_")
                ):
                    continue
                candidate = Path(entry.path) / relative
                try:
                    if candidate.is_dir() and (candidate / ".manifest").is_file():
                        return candidate
                except OSError:
                    continue
    except OSError:
        pass

    return None


def apply_v1_3_2_startup_patches() -> None:
    """Install the startup-safe cache detector used by the v1.3.2 UI patch."""
    v132.auto_detect_thumbnail_cache = fast_auto_detect_thumbnail_cache
