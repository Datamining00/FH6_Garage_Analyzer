from __future__ import annotations

from typing import Any, Callable


_PATCH_FLAG = "_fh6assistant_compact_shape_guard_v1"
_TYPE_CODE_BASE = 0x100000


def _compact_shape_word(body: bytes, pos: int, end: int) -> int | None:
    """Return the word only for the ambiguous one-byte 0x02 shape form."""
    if pos < 0 or pos + 31 > end or pos + 31 > len(body):
        return None
    if body[pos] != 0x02:
        return None
    return int.from_bytes(body[pos + 1 : pos + 3], "little", signed=False)


def _native_word_resolves(renderer: Any, word: int) -> bool:
    resolve = getattr(renderer, "_resolve_vinyl_resource", None)
    if not callable(resolve):
        # If the pinned renderer cannot verify identity, retain upstream behavior
        # rather than making decoding more restrictive.
        return True
    layer = {
        "type": _TYPE_CODE_BASE + (int(word) & 0xFFFF),
        "type_word": int(word) & 0xFFFF,
        "shape_word": int(word) & 0xFFFF,
    }
    try:
        return resolve(layer["type"], layer) is not None
    except Exception:
        return True


def _guarded_is_valid_shape_at(
    original: Callable[[bytes, int, int], bool],
    renderer: Any,
    body: bytes,
    pos: int,
    end: int,
) -> bool:
    """Keep explicit shapes unchanged; verify only ambiguous compact 0x02 records.

    The pinned decoder accepts a markerless 31-byte record whenever its floats
    are numerically plausible and the two-byte word is merely in a broad range.
    FH6 control/group payloads can accidentally satisfy that test.  Full
    00/01-02 placements are explicit and remain untouched.  For the ambiguous
    one-byte 0x02 form, require the word to resolve through the pinned FH6 native
    resource table before it may become a ShapeNode.
    """
    accepted = bool(original(body, pos, end))
    if not accepted:
        return False

    word = _compact_shape_word(body, pos, end)
    if word is None:
        return True
    return _native_word_resolves(renderer, word)


def _bump_render_cache_revision() -> None:
    try:
        from . import livery_preview_quality_pipeline as quality_pipeline
        from . import livery_preview_tiled_quality as tiled_quality

        quality_pipeline.CACHE_VERSION = "v14-quality-pipeline-r7-compact-shape-guard"
        tiled_quality.CACHE_VERSION = "v14-tiled-quality-r8-compact-shape-guard"
        quality_pipeline.clear_quality_pipeline_cache()
        tiled_quality.clear_tiled_quality_cache()
    except Exception:
        pass


def apply_livery_compact_shape_guard_patch() -> None:
    """Prevent unresolved ambiguous compact records from becoming native shapes."""
    from .livery_preview import _load_backend

    decoder, renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    original = decoder.is_valid_shape_at

    def guarded(body: bytes, pos: int, end: int) -> bool:
        return _guarded_is_valid_shape_at(original, renderer, body, pos, end)

    decoder.is_valid_shape_at = guarded
    setattr(decoder, _PATCH_FLAG, True)
    _bump_render_cache_revision()
