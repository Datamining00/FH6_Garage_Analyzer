# FH6 `C_livery` Milestone 3 section-walk notes

This document records independently validated binary-format facts used by the
read-only FH6 Assistant `C_livery -> section scene trees` decoder.

ForzaLiveryStudio (FLS) public `docs/CLIVERY.md` and `docs/CGROUP.md` are used as
format documentation/reference only. No FLS implementation source, binary, DLL,
control flow, or linked runtime component is copied or used by this decoder.

## Scope

Milestone 3 parses the eleven positional artwork slots between
`body_start = gyvl + 0x15` and the post-artwork `yrvl` boundary. It reuses the
Milestone 2 shape/group framing rules and adds livery-specific transform,
section-remnant, empty-scaffold, and positional-slot framing.

It does not flatten scene trees, infer global draw order, connect to the renderer,
or interpret descriptor-weighted raster occupancy. `source_offset` remains
provenance only.

## Real raw corpus

Two supplied FH6 `C_livery` files were validated without committing game binaries:

```text
Car ID 3761 / Fluorite AKE
raw SHA-256 565e75445c70501dc98c00cc76c1d162d703b1921fd55735fcccb857757dac18
body_start 72
body_end   275791
counts     [1,21,2980,2761,2785,3,0,0,0,18,0]

Car ID 2997
raw SHA-256 677751360dba1a7fe6eead246236094836e9e1433709a0fd8dc5a1b2635f7ded
body_start 72
body_end   293929
counts     [24,156,2894,2989,2964,0,18,41,0,0,0]
```

Across the two files the section walker decoded all eleven slots and ended exactly
at `body_end` with contiguous raw-record coverage. The populated sections contain
78 non-root nested groups in total and reach maximum group depth 4. Every populated
section in these two samples has physical leaf count equal to its declared counter.

## Confirmed section framing

A populated section begins with a markerless group header:

```text
u16 direct_child_count
u16 bitmap_blocks
reserved[2]
bitmap[ceil(count/8)]
```

The bitmap is authoritative (`0 = shape`, `1 = group`). Section roots are positional;
the decoder does not search ahead for them.

The supplied corpus contains five section-root inline four-float group transforms,
73 separate group transforms, 74 counted nested groups, and four transformed
markerless nested groups. One-byte `00` and `01` transform leads are directly
observed; three `00` transforms use a `30 + f32 scale_y` suffix. The documented
`00 01` lead, `70 + f32` suffix, and exact nine-byte successor trailer are accepted
only under bounded structural proof and remain provisional where not present in the
supplied corpus.

After a transform, a successor group is considered only immediately, after exactly
one control byte, or after the exact nine-byte trailer ending `09 00`. No arbitrary
scan is allowed.

A one-byte control can make a markerless header appear as a shifted 256x count/block
header. When both offsets frame, the decoder rejects the shifted image and uses the
one-byte-later header. This is required by the Car ID 3761 sample.

## Section boundaries

A populated section with later populated artwork has an 18-byte remnant:

```text
1 byte state/control
16 bytes: f32 x, f32 y, f32 scale, f32 rotation
1 byte trailing control
```

The decoder does not blindly apply `tree_end + 18`. It accepts that boundary only
when the tree closed structurally, the remnant transform is finite with non-zero
scale, and the resulting offset is a structurally valid start for the next slot.
Twelve such remnants are present across the two real samples.

The final populated slot retains one terminal state byte. Two such final populated
boundaries are directly observed.

Every empty slot occupies 23 bytes. Before later populated artwork, the observed
form is a zero-count six-byte markerless header + 16-byte finite section transform
+ one control byte. After the final populated section, the observed trailing-empty
form is a 16-byte finite section transform + seven preserved control/reserved bytes.
Both forms are validated only at the known positional slot boundary.

## Unknown and raw coverage policy

`Unknown is data, not an error.` If a child, remnant, or scaffold cannot be framed
from the bounded grammar, parsing does not search forward for a plausible next
section. The unresolved artwork remainder is preserved as raw unknown data and
later section boundaries are marked unavailable.

For both supplied samples, concatenating chronological Milestone 3 `RawRecord.raw`
values exactly reproduces `payload[body_start:body_end]` with no gap or overlap.

## Remaining evidence limits

The following remain `PROVISIONAL` / `UNKNOWN` pending matching raw samples:

- `70 + f32 scale_y` mask semantics;
- retained `00 01` transform lead in FH6 livery data;
- nine-byte transform-successor trailer in the supplied corpus;
- generation-specific trailing record-mask semantics;
- raster descriptor logical weighting;
- flattening and final draw order.
