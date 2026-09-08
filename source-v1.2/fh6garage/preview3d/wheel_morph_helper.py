from __future__ import annotations

import hashlib
from pathlib import Path
import sys

WHEEL_MORPH_HELPER_FILENAME = "Kfps.ChassisConverter.WheelMorph.exe"
WHEEL_MORPH_HELPER_SHA256 = "f51bb233514088060fb3ee931612612978c2c76496dba947dbeca42dcbf9375a"
WHEEL_MORPH_HELPER_REVISION = "kfps_6f53ca3_w3_transform_chain_v1"


class WheelMorphHelperError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bundled_wheel_morph_helper_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "runtime" / WHEEL_MORPH_HELPER_FILENAME)

    # Source/development builds may stage the verified helper next to the specs.
    source_root = Path(__file__).resolve().parents[2]
    candidates.append(source_root / "runtime" / WHEEL_MORPH_HELPER_FILENAME)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False)).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return tuple(unique)


def verified_bundled_wheel_morph_helper() -> Path | None:
    """Return the bundled patched KFPS helper only after SHA-256 verification."""
    for candidate in bundled_wheel_morph_helper_candidates():
        if not candidate.is_file():
            continue
        try:
            actual = sha256_file(candidate)
        except OSError as exc:
            raise WheelMorphHelperError(
                f"Bundled wheel morph helper could not be read: {candidate}: {exc}"
            ) from exc
        if actual.casefold() != WHEEL_MORPH_HELPER_SHA256.casefold():
            raise WheelMorphHelperError(
                "Bundled wheel morph helper failed integrity verification. "
                f"Expected {WHEEL_MORPH_HELPER_SHA256}, got {actual}."
            )
        return candidate.resolve()
    return None
