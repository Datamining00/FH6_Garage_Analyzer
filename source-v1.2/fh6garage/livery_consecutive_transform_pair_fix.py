from __future__ import annotations

from typing import Any


_PATCH_FLAG = "_fh6assistant_consecutive_livery_transform_pair_fix_v1"
_EXTENDED_CHILD_MARKER = b"\x00\x02\x00\x01\x00\x00\x00\x03"
_PARENT_MARKER = b"\x00"


def _group_boundary_after(decoder: Any, data: bytes, pos: int, end: int) -> bool:
    try:
        if decoder.valid_counted_group_at(data, pos, end, livery=True) is not None:
            return True
        if decoder.valid_markerless_group_at(
            data,
            pos,
            end,
            allow_count_one=True,
            livery=True,
        ) is not None:
            return True
    except Exception:
        return False
    return False


def _consecutive_transform_pair_candidate(
    decoder: Any,
    data: bytes,
    pos: int,
    end: int,
    state: Any,
):
    """Return the second transform when a proven FH6 parent/child pair is present.

    FH6 C_livery can encode a parent transform as an ordinary zero-marker livery
    transform immediately followed by the extended child-transform marker
    ``00 02 00 01 00 00 00 03``.  The pinned decoder recognizes both records,
    but its normal walk stores only one pending transform, so the second record
    replaces the first before the following group is pushed.

    This detector is deliberately narrow.  It only accepts the exact observed
    grammar family: a clean pending zero-marker parent, an exact extended child
    marker at the current offset, and a structurally valid livery group boundary
    immediately after the child transform.  It does not scan forward and does
    not use car IDs, section names, source offsets, or coordinates.
    """
    if state.pending_transform is None:
        return None
    if bytes(getattr(state, "pending_marker", b"") or b"") != _PARENT_MARKER:
        return None
    if bytes(getattr(state, "pending_prefix", b"") or b""):
        return None
    if int(getattr(state, "pending_flags", 0) or 0) != 0:
        return None
    if bool(getattr(state, "pending_mask", False)):
        return None

    pos = int(pos)
    end = int(end)
    if pos < 0 or pos + len(_EXTENDED_CHILD_MARKER) + 16 > end:
        return None
    if data[pos : pos + len(_EXTENDED_CHILD_MARKER)] != _EXTENDED_CHILD_MARKER:
        return None

    try:
        record = decoder.read_livery_transform(
            data,
            pos,
            end,
            invert_odd_rotation=True,
        )
    except Exception:
        record = None
    if record is None:
        return None

    size, transform, marker = record
    if bytes(marker) != _EXTENDED_CHILD_MARKER:
        return None
    next_pos = pos + int(size)
    if not _group_boundary_after(decoder, data, next_pos, end):
        return None
    return int(size), transform, bytes(marker)


def _bump_render_cache_revision() -> None:
    try:
        from . import livery_preview_quality_pipeline as quality_pipeline
        from . import livery_preview_tiled_quality as tiled_quality

        quality_pipeline.CACHE_VERSION = "v14-quality-pipeline-r4-consecutive-transform-pair"
        tiled_quality.CACHE_VERSION = "v14-tiled-quality-r5-consecutive-transform-pair"
        quality_pipeline.clear_quality_pipeline_cache()
        tiled_quality.clear_tiled_quality_cache()
    except Exception:
        pass


def apply_livery_consecutive_transform_pair_fix() -> None:
    """Preserve a recognized parent transform across an extended child transform.

    The normal decoder intentionally keeps only one pending transform.  For the
    proven FH6 consecutive-transform grammar that loses the parent record.  This
    wrapper materializes that parent as a two-child GroupNode, then keeps the
    second transform pending for the first child group.  The existing stack
    completion logic naturally leaves the parent open for the second child and
    closes it after both child groups are complete.
    """
    from .livery_preview import _load_backend

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    original_walk_step = decoder.walk_step

    def walk_step_with_consecutive_pair(
        data,
        pos,
        end,
        state,
        livery: bool = False,
        game: str | None = None,
        livery_invert_odd_rotation: bool = True,
    ):
        if livery:
            candidate = _consecutive_transform_pair_candidate(
                decoder,
                data,
                pos,
                end,
                state,
            )
            if candidate is not None:
                size, child_transform, child_marker = candidate
                parent_transform = state.pending_transform
                parent_marker = bytes(state.pending_marker or b"")
                parent_offset = max(0, int(pos) - (len(parent_marker) + 16))
                node = decoder.GroupNode(
                    transform=parent_transform,
                    expected_children=2,
                    flags=0,
                    mask=False,
                    offset=parent_offset,
                    marker=parent_marker,
                    source="implicit_consecutive_livery_transform_pair",
                )
                state.stack[-1].items.append(node)
                state.stack.append(node)
                state.pending_transform = child_transform
                state.pending_marker = child_marker
                state.pending_prefix = b""
                state.pending_flags = 0
                state.pending_mask = False
                return int(pos) + int(size)

        return original_walk_step(
            data,
            pos,
            end,
            state,
            livery=livery,
            game=game,
            livery_invert_odd_rotation=livery_invert_odd_rotation,
        )

    decoder.walk_step = walk_step_with_consecutive_pair
    setattr(decoder, _PATCH_FLAG, True)
    _bump_render_cache_revision()
