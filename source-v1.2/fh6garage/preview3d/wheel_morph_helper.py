from __future__ import annotations

import hashlib
from pathlib import Path
import sys

# The v16 verified helper carries the established wheel/transform chain plus
# the read-only embedded MaterialBlob shader/Texture2D provenance exporter,
# exact material UV-tiling provenance, native UV4 pass-through, TXCB/TXCH
# native swatchbin-to-DDS decoder, the P3F read-only materialbin reference
# exporter, and typed materialbin override + shaderbin default parameter
# composition diagnostics. It retains the FH6 v3.4 sampler-alignment contract
# from v15 and additionally fails closed for Durango/Xbox swatchbin payloads
# until their tiled texture memory is XG-detiled/dealigned before DDS creation.
# PC-linear swatchbin decoding remains supported. No FH6 game/save data is
# modified and parameter composition does not render.
WHEEL_MORPH_HELPER_FILENAME = "Kfps.ChassisConverter.WheelMorph.exe"
WHEEL_MORPH_HELPER_SHA256 = "3c90cc38a939bb91f7fb3ef71c8330c1665a18708be1b9e4018b01402adb5411"
WHEEL_MORPH_HELPER_REVISION = "kfps_6f53ca3_w3_p3f_material_shader_parameters_uv4_durango_guard_v16"


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
