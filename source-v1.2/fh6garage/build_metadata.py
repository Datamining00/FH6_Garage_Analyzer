from __future__ import annotations

from .version import WINDOW_TITLE


STANDARD_NAME = WINDOW_TITLE
PORTABLE_DIR_NAME = f"{WINDOW_TITLE} Portable"
STANDARD_SPEC = "FH6_Assistant_v1.3.2.spec"
PORTABLE_SPEC = "FH6_Assistant_v1.3.2_portable.spec"


def build_metadata() -> dict[str, str]:
    return {
        "standard_name": STANDARD_NAME,
        "portable_dir_name": PORTABLE_DIR_NAME,
        "standard_spec": STANDARD_SPEC,
        "portable_spec": PORTABLE_SPEC,
    }
