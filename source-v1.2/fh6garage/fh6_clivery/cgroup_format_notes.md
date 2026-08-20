# FH6 standalone `C_group` Milestone 2 format notes

This document records binary-format facts used by the independent, read-only
FH6 Assistant `C_group -> Scene Tree` decoder.

Implementation description:

> Independent reimplementation based on documented format facts, real binary
> evidence, and black-box/differential validation.

ForzaLiveryStudio (FLS) is used only as public format documentation/reference
behavior. No FLS implementation source, control flow, binary, DLL, or static
library is copied, ported, vendored, or linked by this decoder.

Evidence states:

- `CONFIRMED`: directly documented framing or independently validated raw-binary
  behavior.
- `PROVISIONAL`: implemented conservatively from documented grammar but not yet
  validated against the relevant standalone FH6 `C_group` raw-sample case.
- `UNKNOWN`: deliberately not assigned a semantic interpretation.

## Milestone 2 scope

Status: `CORPUS-VALIDATED FOR FLAT SHAPES AND COUNTED NESTED GROUPS`

Milestone 2 is strictly:

`standalone C_group -> inflate -> raw records -> group tree -> structural JSON`

It validates and exposes direct child count, child bitmap, nested group count,
leaf count, shape id, local transform records, confirmed `0x60` mask-group
ancestry, source span / source offset, parent path, and unknown record
preservation.

It does not parse `C_livery` section bodies, flatten the scene tree, infer global
draw order, connect to the renderer, modify save data, or encode `C_group`.

## Container

Status: `CONFIRMED`

Standalone `C_group` uses an 8-byte little-endian compressed/uncompressed length
wrapper followed by a zlib payload. The decompressed payload begins with `gyvl`.
This framing is present in the supplied real FH6 flat and nested samples.
Length mismatches remain fatal structural errors; the decoder does not scan past a
malformed wrapper.

## Root header and direct-child bitmap

Status: `CONFIRMED`

The decoder follows the standalone root layout and validates
`child_blocks = ceil(direct_child_count / 8)`. Bitmap bits are read LSB-first:
`0 = shape`, `1 = group`.

The parent bitmap is authoritative for which child type may be parsed. Marker-like
bytes are not promoted to a shape/group when the bitmap requires the other type.

Real flat samples confirmed all-zero shape bitmaps, including a 1999-direct-shape
sample. The nested sample identified below has `root_count = 2` and
`root_bitmap = 0x03`, confirming two direct root groups.

## Counted and markerless groups

Counted group framing (`20/60 + u16 count + u16 blocks + reserved[2] + bitmap`) is
`CONFIRMED` for normal `0x20` nested groups by the supplied game-generated nested
sample. Its decoded structure contains four non-root counted groups and seven leaf
shapes with a maximum group depth of two.

Markerless groups remain `PROVISIONAL`; because their framing is ambiguous, they
are accepted only when the parent requires a group and a documented transform
immediately precedes the markerless header.

## Group-to-shape inter-child control byte

Status: framing `CONFIRMED`; higher semantic meaning `UNKNOWN`

The supplied nested sample contains the same boundary form twice:

```text
completed counted Group
00
next bitmap-declared Shape record
```

The bytes occur at inflated offsets `0x96` and `0x14A`. In both cases the parent
bitmap declares the next child as a shape and a complete documented shape record
begins exactly one byte after the `00`.

The independent decoder therefore accepts exactly one `0x00` as a
`group_to_shape_control` record only when all of the following are true:

1. the previous direct child is a completed `GroupNode`;
2. the current parent bitmap requires a shape for the next direct child;
3. the current offset is not itself a valid shape record; and
4. a complete documented shape record begins exactly one byte later.

No repeated skip, scan, or free-form recovery is permitted. If the following
shape framing is not valid, parsing preserves the unresolved tail as `UnknownNode`
and stops. The control byte does not currently alter mask state or draw order.

## Shape records

Status: `CONFIRMED`

The documented 32-byte `00 02` / `01 02` and 31-byte bare `02` physical records
are present in the supplied real FH6 samples. A leading `0x02` alone is never
enough to create a `ShapeNode`; the parent bitmap must require a shape and the
complete record must be structurally readable.

Raw `shape_id` words are preserved without renderer-registry validation.

## Transform records

Status: framing `CONFIRMED`; ownership/binding semantics partly `PROVISIONAL`

Documented marker families and optional `30 + f32 scale_y` are recognized. The
nested raw sample independently confirms transform framing around counted groups,
including a `00 01 03` family form. The decoder still keeps ambiguous inline
ownership conservative; multiple/consecutive transforms are not heuristically
composed or repaired.

## Mask semantics

`0x60` group ancestry remains structurally supported and inherited by descendants,
but an actual supplied standalone `0x60` sample has not yet been validated.

Contextual odd record leads such as `01 02` remain `UNKNOWN` for production mask
semantics in Milestone 2. The decoder does not infer record generation from the
root transform marker alone. A potentially affected previous direct shape receives
an unresolved (`None`) mask state rather than a forced boolean.

## Unknown preservation

Status: `CONFIRMED` implementation invariant

`Unknown is data, not an error.`

If a required child cannot be parsed safely from bounded structural framing, an
`UnknownNode` preserves the unresolved tail verbatim, a diagnostic is emitted,
and semantic parsing stops. No byte-by-byte recovery scan searches for a later
plausible shape or group.

## Raw record coverage

Status: `CONFIRMED`

Every inflated input byte is represented by chronological `RawRecord` spans.
`lossless_record_coverage=true` is reported only when spans are contiguous from
offset zero through the final payload byte. Trailing bytes after a completed root
are preserved without interpretation.

For the nested sample, the full 366-byte inflated payload is covered without gaps.
The final `00 01 01` remains preserved as `trailing_bytes` with semantic state
`UNKNOWN`.

## Parent path and source offset

Status: `CONFIRMED` representation rule

Each scene node records a structural direct-child path and original source span.
`source_offset` is provenance only; Milestone 2 makes no draw-order claim and
performs no global layer reversal.

## Real FH6 regression evidence

The game-generated nested sample is intentionally not committed. Its identity and
expected invariants are recorded in an opt-in regression test:

```text
raw SHA-256:
00e2d548fc91af5d8d449020f26c468b6a2d63820596d828561b56a8fd6028f9

inflated payload SHA-256:
68ff616748d2cbf64b69d681fa4707612f4d0a8db6177deb313c297df873fc7e

raw length:       170 bytes
inflated length:  366 bytes
root count:       2
root bitmap:      03
nested groups:    4
leaf shapes:      7
max depth:        2
unknown nodes:    0
control offsets:  0x96, 0x14A
trailing bytes:   00 01 01
```

The same regression also verifies that concatenating every chronological
`RawRecord.raw` value reproduces the complete inflated payload byte-for-byte.

## Synthetic structural validation

Status: `CONFIRMED` as test coverage

The existing unit suite covers flat shapes, nested counted groups, bitmap child
typing, preceding transforms, markerless groups after transforms, `0x60` mask
inheritance, unresolved contextual odd leads, inline first-child transform cases,
unknown-tail preservation, consecutive-transform uncertainty, root zero padding,
zlib/inflated equivalence, bitmap mismatch rejection, and contiguous raw-byte
coverage.

Additional tests cover the bounded single-`00` group-to-shape control rule and a
negative case proving that the byte is not skipped when the following complete
shape framing is absent.

## Remaining Milestone 2 evidence limits

Status: `PROVISIONAL` for the cases below

Real standalone samples are still desirable for:

- explicit `0x60` mask groups;
- markerless groups;
- generation-specific contextual mask behavior;
- additional transform-ownership combinations.

These unresolved cases remain explicit rather than being generalized from the
current nested sample.

## Milestone 3

Status: `NOT STARTED`

Milestone 3 will parse the eleven `C_livery` section bodies using the stabilized
C_group grammar. It will not assume a universal fixed `+18` section-boundary rule.

## Sources and attribution

Format facts were checked against ForzaLiveryStudio public `docs/CGROUP.md`, the
independently validated Milestone 1 format notes, and supplied real FH6 raw binary
evidence. No FLS implementation source is part of this decoder, and the new modules
have no runtime dependency on FLS or KFPS.
