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

- `CONFIRMED`: directly documented format framing or already independently
  validated format facts.
- `PROVISIONAL`: implemented conservatively from documented grammar but not yet
  validated against the intended standalone FH6 `C_group` raw-sample corpus.
- `UNKNOWN`: deliberately not assigned a semantic interpretation.

## Milestone 2 scope

Status: `PROVISIONAL`

Milestone 2 is strictly:

`standalone C_group -> inflate -> raw records -> group tree -> structural JSON`

It validates and exposes direct child count, child bitmap, nested group count,
leaf count, shape id, local transform records, confirmed `0x60` mask-group
ancestry, source span / source offset, parent path, and unknown record
preservation.

It does not parse `C_livery` section bodies, flatten the scene tree, infer global
draw order, connect to the renderer, modify save data, or encode `C_group`.

## Container

Status: `CONFIRMED` as documented framing

Standalone `C_group` uses an 8-byte little-endian compressed/uncompressed length
wrapper followed by a zlib payload. The decompressed payload begins with `gyvl`.
Length mismatches are fatal structural errors; the decoder does not scan past a
malformed wrapper.

## Root header and direct-child bitmap

Status: `CONFIRMED` as documented framing

The decoder follows the documented standalone root layout and validates
`child_blocks = ceil(direct_child_count / 8)`. Bitmap bits are read LSB-first:
`0 = shape`, `1 = group`.

The parent bitmap is authoritative for which child type may be parsed. Marker-like
bytes are not promoted to a shape/group when the bitmap requires the other type.

## Counted and markerless groups

Counted group framing (`20/60 + u16 count + u16 blocks + reserved[2] + bitmap`) is
`CONFIRMED` as documented framing. Scene semantics remain `PROVISIONAL` pending
real standalone sample validation.

Markerless groups remain `PROVISIONAL`; because their framing is ambiguous, they
are accepted only when the parent requires a group and a documented transform
immediately precedes the markerless header.

## Shape records

Status: `CONFIRMED` as documented framing; standalone corpus validation pending

Only the documented 32-byte `00 02` / `01 02` and 31-byte bare `02` physical
records are recognized. A leading `0x02` alone is never enough to create a
`ShapeNode`; the parent bitmap must require a shape and the complete record must
be structurally readable.

Raw `shape_id` words are preserved without renderer-registry validation.

## Transform records

Status: framing `CONFIRMED`; binding behavior `PROVISIONAL`

Documented marker families and optional `30 + f32 scale_y` are recognized. A
transform preceding a required group can bind to that group. Inline transform
ownership is preserved conservatively; ambiguous multiple/consecutive transforms
are not heuristically composed or repaired.

## Mask semantics

`0x60` group ancestry is `CONFIRMED` and inherited by descendants.

Contextual odd record leads such as `01 02` remain `UNKNOWN` for production mask
semantics in Milestone 2. The decoder does not infer record generation from the
root transform marker alone. A potentially affected previous shape receives an
unresolved (`None`) mask state rather than a forced boolean.

## Unknown preservation

Status: `CONFIRMED` implementation invariant

`Unknown is data, not an error.`

If a required child cannot be parsed safely from documented framing, an
`UnknownNode` preserves the unresolved tail verbatim, a diagnostic is emitted,
and semantic parsing stops. No byte-by-byte recovery scan searches for a later
plausible shape or group.

## Raw record coverage

Status: `CONFIRMED` implementation invariant

Every inflated input byte is represented by chronological `RawRecord` spans.
`lossless_record_coverage=true` is reported only when spans are contiguous from
offset zero through the final payload byte. Trailing bytes after a completed root
are preserved without interpretation.

## Parent path and source offset

Status: `CONFIRMED` representation rule

Each scene node records a structural direct-child path and original source span.
`source_offset` is provenance only; Milestone 2 makes no draw-order claim and
performs no global layer reversal.

## Synthetic structural validation

Status: `CONFIRMED` as test coverage, not binary corpus evidence

The unit suite covers flat shapes, nested counted groups, bitmap child typing,
preceding transforms, markerless groups after transforms, `0x60` mask inheritance,
unresolved contextual odd leads, inline first-child transform cases, unknown-tail
preservation, consecutive-transform uncertainty, root zero padding, zlib/inflated
equivalence, bitmap mismatch rejection, and contiguous raw-byte coverage.

These are synthetic fixtures from documented layouts and are not real FH6
`C_group` regression evidence.

## Current evidence limitation

Status: `PROVISIONAL`

No standalone raw FH6 `C_group` binary is currently stored in the repository or
available in the active File Library search results. Therefore Milestone 2 is not
yet corpus-validated. Before Milestone 3 begins, at least one real game-generated
standalone `C_group` should be decoded and compared against independently
observable structure/FLS output.

## Milestone 3

Status: `NOT STARTED`

Milestone 3 will parse the eleven `C_livery` section bodies using the stabilized
C_group grammar. It will not assume a universal fixed `+18` section-boundary rule.

## Sources and attribution

Format facts were checked against ForzaLiveryStudio public `docs/CGROUP.md`, the
independently validated Milestone 1 format notes, and existing FH6 Assistant
differential diagnostics only as secondary regression context. No FLS
implementation source is part of this decoder, and the new modules have no
runtime dependency on FLS or KFPS.
