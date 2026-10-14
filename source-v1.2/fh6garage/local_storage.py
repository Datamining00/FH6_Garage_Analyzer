from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, payload: Any, *, indent: int | None = 2) -> bool:
    """Best-effort atomic JSON write for optional LocalAppData state.

    User preferences and UI annotations should remain usable in memory even if
    LocalAppData is temporarily unavailable, read-only, or full.  A unique
    temporary file also prevents two application instances from sharing the
    same in-progress filename.
    """

    target = Path(path)
    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f"{target.stem}.",
            suffix=".tmp",
            dir=str(target.parent),
        )
        os.close(fd)
        temporary = Path(temporary_name)
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=indent),
            encoding="utf-8",
        )
        os.replace(temporary, target)
        return True
    except (OSError, TypeError, ValueError):
        return False
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
