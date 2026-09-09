from __future__ import annotations

import hashlib
from pathlib import Path
import sys

# This verified helper carries the established wheel/transform chain plus the
# read-only embedded MaterialBlob shader/Texture2D provenance exporter and the
# TXCB/TXCH native swatchbin-to-DDS decoder consumed by the 3D viewer pipeline.
WHEEL_MORPH_HELPER_FILENAME = "Kfps.ChassisConverter.WheelMorph.exe"
WHEEL_MORPH_HELPER_SHA256 = "b9c7234900d11ec81da1a4505dd575d68d0a99c16e1a2baf71b8eb1ec96ab65e"
WHEEL_MORPH_HELPER_REVISION = "kfps_6f53ca3_w3_native_material_swatchbin_decoder_v9"


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
