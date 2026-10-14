from __future__ import annotations

"""Native tire geometry diagnostic with corrected ForzaTech wire tag IDs.

The original W3 diagnostic implementation was first exercised only by synthetic
fixtures whose VLay/ILay/VerB tags were generated from the implementation's own
constants. Actual FH6 tire_slick.modelbin evidence showed the real serialized
IDs are ASCII tag integers VLay=0x564C6179, ILay=0x494C6179, VerB=0x56657242.
Keep the implementation in a separate module and patch those globals before any
bake function is called. This preserves the reviewed geometry logic while making
the public module use the actual native wire IDs.
"""

from pathlib import Path

from . import tire_morph_geometry_impl as _impl

# ForzaTech Bundle::BlobTag integer IDs (not little-endian byte strings).
_impl.VERTEX_BUFFER_TAG = 0x56657242  # VerB
_impl.VERTEX_LAYOUT_TAG = 0x564C6179  # VLay
_impl.INPUT_LAYOUT_TAG = 0x494C6179  # ILay

# Re-export the implementation, including diagnostic private helpers used by the
# existing regression tests. Function globals remain bound to _impl and therefore
# see the corrected tag constants above.
for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

del _name


_original_bake_tire_morph_selectors = _impl.bake_tire_morph_selectors


def bake_tire_morph_selectors(
    archive_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    write_glb: bool = True,
) -> TireSelectorBakeReport:
    """Bake selector evidence without requiring an output path for read-only runs.

    Structural eligibility checks intentionally request ``write_glb=False`` because
    they only need AABB evidence. The implementation still normalizes its output
    directory unconditionally, so a real existing parent directory is supplied in
    that no-write mode. No files are created or modified by this compatibility path.
    """
    if output_dir is None:
        if write_glb:
            raise TireMorphGeometryError(
                "output_dir is required when write_glb=True"
            )
        output_dir = Path(archive_path).expanduser().resolve().parent
    return _original_bake_tire_morph_selectors(
        archive_path,
        output_dir,
        write_glb=write_glb,
    )
