from __future__ import annotations

from typing import Any


_PATCH_FLAG = "_fh6assistant_section_boundary_fix_v1"


def _direct_placement_at(decoder: Any, body: bytes, pos: int, end: int) -> bool:
    """Return True only for a direct 32-byte placement at the exact boundary.

    This deliberately does not scan forward and does not accept generic group or
    transform candidates. The fix is therefore limited to the failure mode seen
    in FH6 C_livery streams where the next populated section starts immediately
    with a valid 00/01 02 placement and the legacy unconditional 18-byte skip
    would consume that placement.
    """
    if pos < 0 or pos + 32 > end:
        return False
    return bool(
        decoder.is_valid_shape_at(body, pos, end)
        or decoder.is_livery_logo_at(body, pos, end)
    )


def _build_livery_sections_boundary_safe(decoder: Any, body: bytes, counts: list[int]):
    """Pinned KFPS section walker with one conservative boundary correction.

    The upstream walker always advances by LIVERY_POPULATED_REMNANT_SIZE after a
    populated section reaches its declared placement count. Some FH6 liveries do
    not have that remnant at a populated->populated boundary: the next section's
    first 32-byte placement begins exactly at the current parser position.

    In that specific, structurally provable case we preserve the placement and
    start the next section there. All other paths retain the pinned decoder's
    original 18-byte advancement behavior.
    """
    warnings: list[str] = []
    layers: list[dict[str, Any]] = []
    pos = 0
    end = len(body)
    section_names = tuple(decoder.LIVERY_SECTION_NAMES)
    empty_slot_size = int(decoder.LIVERY_EMPTY_SLOT_SIZE)
    populated_remnant_size = int(decoder.LIVERY_POPULATED_REMNANT_SIZE)

    for slot, name in enumerate(section_names):
        target = int(counts[slot]) if slot < len(counts) else 0
        section_start = pos
        if target <= 0:
            pos = min(end, pos + empty_slot_size)
            continue

        section_root = decoder.GroupNode(source="livery_section", offset=pos, section=name)
        holder = decoder.GroupNode(source="livery_holder")
        holder.items.append(section_root)
        state = decoder.WalkState(stack=[holder, section_root])

        reserved_tail = populated_remnant_size
        for later_slot in range(slot + 1, len(section_names)):
            later_target = int(counts[later_slot]) if later_slot < len(counts) else 0
            reserved_tail += empty_slot_size if later_target <= 0 else later_target * 32
        walk_limit = max(pos, end - reserved_tail)

        guard = 0
        while state.decoded_shapes < target and pos < walk_limit and guard < end + 4096:
            guard += 1
            decoder.close_complete_stack(state.stack)
            if len(state.stack) < 2:
                warnings.append(f"{name}: parser stack closed before reaching target {target}")
                break

            at_section_root = state.stack[-1] is section_root
            deficit = target - state.decoded_shapes
            next_slot_populated = (
                slot + 1 < len(section_names)
                and slot + 1 < len(counts)
                and int(counts[slot + 1]) > 0
            )

            if (
                at_section_root
                and not state.pending_transform
                and next_slot_populated
                and 0 < deficit <= 8
            ):
                next_section = decoder.valid_markerless_group_at(
                    body,
                    pos + populated_remnant_size,
                    end,
                    allow_count_one=True,
                    livery=True,
                )
                if next_section and next_section.count >= 8:
                    break

            if at_section_root and not state.pending_transform:
                markerless = decoder.valid_markerless_group_at(
                    body, pos, end, allow_count_one=True, livery=True
                )
                if markerless:
                    pos = decoder.push_markerless_group(
                        body, pos, end, markerless, state, livery=True
                    )
                    continue

            next_pos = decoder.walk_step(
                body,
                pos,
                end,
                state,
                livery=True,
                livery_invert_odd_rotation=slot != 2,
            )
            if next_pos <= pos:
                warnings.append(f"{name}: decoder made no progress at body offset 0x{pos:x}")
                break
            pos = next_pos

        decoded = decoder.flatten_tree(section_root, layer_start=0, section=name)
        if len(decoded) != target:
            warnings.append(f"{name}: decoded {len(decoded)} layer(s), stats target is {target}")
        for layer in decoded:
            layer["section_start"] = section_start
            layers.append(layer)

        pos = min(pos, walk_limit)
        next_target = (
            int(counts[slot + 1])
            if slot + 1 < len(section_names) and slot + 1 < len(counts)
            else 0
        )
        if next_target > 0 and _direct_placement_at(decoder, body, pos, end):
            warnings.append(
                f"{name}: preserved immediate next-section placement at body offset 0x{pos:x}; "
                f"legacy {populated_remnant_size}-byte remnant skip suppressed."
            )
        else:
            pos = min(end, pos + populated_remnant_size)

    return layers, warnings


def _bump_render_cache_revision() -> None:
    try:
        from . import livery_preview_quality_pipeline as quality_pipeline
        from . import livery_preview_tiled_quality as tiled_quality

        quality_pipeline.CACHE_VERSION = "v14-quality-pipeline-r3-section-boundary"
        tiled_quality.CACHE_VERSION = "v14-tiled-quality-r4-section-boundary"
        quality_pipeline.clear_quality_pipeline_cache()
        tiled_quality.clear_tiled_quality_cache()
    except Exception:
        pass


def apply_livery_section_boundary_fix_patch() -> None:
    """Install the conservative populated->populated section boundary fix."""
    from .livery_preview import _load_backend

    decoder, _renderer = _load_backend()
    if bool(getattr(decoder, _PATCH_FLAG, False)):
        return

    decoder.build_livery_sections = lambda body, counts: _build_livery_sections_boundary_safe(
        decoder, body, counts
    )
    setattr(decoder, _PATCH_FLAG, True)
    _bump_render_cache_revision()
