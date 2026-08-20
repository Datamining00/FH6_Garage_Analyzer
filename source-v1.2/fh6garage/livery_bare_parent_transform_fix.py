from __future__ import annotations

import math
from typing import Any


_PATCH_FLAG = "_fh6assistant_bare_parent_transform_pair_fix_v1"
_EXTENDED_CHILD_MARKER = b"\x00\x02\x00\x01\x00\x00\x00\x03"


def _finite_position(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) >= 50000.0:
        return None
    return number


def _bare_parent_transform_candidate(decoder: Any, data: bytes, pos: int, end: int):
    """Return a structurally proven bare parent transform, otherwise ``None``.

    One FH6 livery grammar variant stores a 16-byte parent transform directly
    before an extended child-transform record.  The pinned decoder recognizes
    the extended child transform but, without this guard, walks byte-by-byte
    through the bare parent.  Float bytes such as 0xff then leak into pending
    flags and the parent transform is lost entirely.

    The recovery is deliberately narrow: the current position must not already
    be a shape/logo/group, the 16 bytes must decode as a sane transform, and the
    byte immediately after them must be the exact extended livery transform
    marker whose own parser can prove a following group boundary.
    """
    pos = int(pos)
    end = int(end)
    if pos < 0 or pos + 16 + len(_EXTENDED_CHILD_MARKER) + 16 > end:
        return None

    try:
        if decoder.is_valid_shape_at(data, pos, end) or decoder.is_livery_logo_at(data, pos, end):
            return None
        if decoder.valid_counted_group_at(data, pos, end, livery=True) is not None:
            return None
        if decoder.valid_markerless_group_at(
            data,
            pos,
            end,
            allow_count_one=True,
            livery=True,
        ) is not None:
            return None
    except Exception:
        return None

    transform = decoder.read_transform_payload(data, pos, end)
    if transform is None:
        return None
    if _finite_position(getattr(transform, "x", None)) is None:
        return None
    if _finite_position(getattr(transform, "y", None)) is None:
        return None

    child_pos = pos + 16
    if data[child_pos : child_pos + len(_EXTENDED_CHILD_MARKER)] != _EXTENDED_CHILD_MARKER:
        return None
    try:
        child_record = decoder.read_livery_transform(
            data,
            child_pos,
            end,
            invert_odd_rotation=True,
        )
    except Exception:
        child_record = None
    if child_record is None:
        return None
    _size, _child_transform, marker = child_record
    if bytes(marker) != _EXTENDED_CHILD_MARKER:
        return None
    return transform


def _bump_render_cache_revision() -> None:
    """Prevent corrected transforms from reusing PNGs rendered by the old parser."""
    try:
        from . import livery_preview_quality_pipeline as quality_pipeline
        from . import livery_preview_tiled_quality as tiled_quality

        quality_pipeline.CACHE_VERSION = "v14-quality-pipeline-r3-bare-parent-transform"
        tiled_quality.CACHE_VERSION = "v14-tiled-quality-r4-bare-parent-transform"
        quality_pipeline.clear_quality_pipeline_cache()
        tiled_quality.clear_tiled_quality_cache()
    except Exception:
        pass


def apply_livery_bare_parent_transform_fix() -> None:
    """Preserve FH6 bare parent transforms before extended child transforms.

    The existing decoder already models transform-pair ownership with an
    implicit two-child GroupNode when a pending transform precedes direct
    placements.  This patch extends that same ownership concept to the proven
    bare-parent + extended-child-transform grammar without changing layer order,
    mask semantics, source-offset normalization, or renderer behavior.
    """
    from .livery_preview import _load_backend

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    original_walk_step = decoder.walk_step

    def walk_step_with_bare_parent_pair(
        data,
        pos,
        end,
        state,
        livery: bool = False,
        game: str | None = None,
        livery_invert_odd_rotation: bool = True,
    ):
        if (
            livery
            and state.pending_transform is None
            and not state.pending_marker
            and not state.pending_prefix
            and int(state.pending_flags or 0) == 0
            and not bool(state.pending_mask)
        ):
            transform = _bare_parent_transform_candidate(decoder, data, pos, end)
            if transform is not None:
                node = decoder.GroupNode(
                    transform=transform,
                    expected_children=2,
                    flags=0,
                    mask=False,
                    offset=int(pos),
                    marker=b"",
                    source="implicit_bare_transform_pair",
                )
                state.stack[-1].items.append(node)
                state.stack.append(node)
                return int(pos) + 16

        return original_walk_step(
            data,
            pos,
            end,
            state,
            livery=livery,
            game=game,
            livery_invert_odd_rotation=livery_invert_odd_rotation,
        )

    decoder.walk_step = walk_step_with_bare_parent_pair
    setattr(decoder, _PATCH_FLAG, True)
    _bump_render_cache_revision()
