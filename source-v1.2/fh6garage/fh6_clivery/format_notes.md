# FH6 `C_livery` independent format notes

This document records binary-format facts used by the FH6 Assistant read-only
decoder. It is not a description of the old KFPS patch stack and it does not
define renderer behavior.

Implementation description:

> Independent reimplementation based on documented format facts, real binary
> evidence, and black-box/differential validation.

ForzaLiveryStudio (FLS) is used only as format documentation/reference behavior.
No FLS implementation source, control flow, binary, DLL, or static library is
copied, ported, vendored, or linked by this decoder.

Evidence states:

- `CONFIRMED`: supported by public format documentation and/or direct repeated
  binary observations that agree.
- `PROVISIONAL`: sufficient for a guarded Milestone 1 read, but not yet verified
  independently across the intended real-sample corpus.
- `UNKNOWN`: deliberately not interpreted.

## Milestone 1 scope

Status: `CONFIRMED`

Milestone 1 stops after:

`C_livery -> inflate -> car id -> gyvl/body range -> 11 section counts -> JSON`

It does not parse groups, shapes, transforms, masks, render order, or scene
flattening. It does not modify save data and it does not encode `C_livery`.

## Container header

Status: `CONFIRMED`

Observed/documented layout:

```text
u32 little-endian  compressed length
u32 little-endian  decompressed length
byte[]             zlib payload
```

The zlib stream begins at file offset `8`.

Evidence:

- FLS public `docs/CLIVERY.md`.
- Existing real FH6 sample observation beginning
  `34 07 02 00 a6 39 04 00 78 9c ...`.
- Direct decompression behavior previously verified in FH6 Assistant diagnostics.

Milestone 1 accepts either this container or an already-inflated payload beginning
with `vlrc`. Length mismatches are errors; the decoder does not recover by scanning
past a malformed container.

## `vlrc` root and target car identifier

Status: `CONFIRMED`

The inflated FH6 livery payload begins with `vlrc`.

Relevant field:

```text
0x10  u32 little-endian  target car identifier
```

Evidence:

- FLS public `docs/CLIVERY.md`.
- Real sample observation: offset `0x10` decodes to Car ID `3761`.

No Car ID is used to select parsing rules.

## `gyvl` artwork header

Status: `CONFIRMED`

Relevant header layout:

```text
0x00  "gyvl"
...
0x14  u8 control
0x15  section stream begins
```

Therefore:

`body_start = gyvl_offset + 0x15`

Evidence:

- FLS public `docs/CLIVERY.md`.
- Real sample diagnostics with `gyvl_offset = 51` and `body_start = 72`.

The production decoder locates the tag structurally. It does not hardcode
`gyvl_offset = 51`.

## Artwork body end

Status: `PROVISIONAL`

Current Milestone 1 rule:

- Find a structurally usable `yrvl` after the `gyvl` header.
- Treat that position as `body_end` only when enough bytes remain for the
  documented section-counter record.

Evidence:

- FLS documents the tagged ordering as artwork `gyvl` followed by a `yrvl`
  section-counter record.
- Existing FH6 Assistant differential diagnostics report this boundary
  consistently for the available samples.
- KFPS public reverse-engineering material uses the same post-artwork tag
  boundary.

Limitation:

FLS documents that the preceding livery-information record stores the `gyvl`
body length, but Milestone 1 does not yet independently decode and cross-check
that length field. Until real binary corpus validation is complete, the
`body_end` rule remains `PROVISIONAL`.

## Section-counter record

Status: `PROVISIONAL`

Milestone 1 reads eleven little-endian `u32` values immediately after the
post-artwork `yrvl` tag. A further `u32` is retained only as a diagnostic trailing
counter.

Section slot order:

| Slot | Name |
| ---: | --- |
| 0 | Front |
| 1 | Back |
| 2 | Top |
| 3 | Left |
| 4 | Right |
| 5 | Spoiler |
| 6 | FrontWindshield |
| 7 | BackWindshield |
| 8 | TopWindow |
| 9 | LeftWindow |
| 10 | RightWindow |

Evidence:

- FLS `docs/CLIVERY.md` documents eleven positional FH6 sections and a following
  section-counter record containing eleven section counts plus one trailing
  counter.
- KFPS public reverse-engineering material identifies the counters as consecutive
  little-endian 32-bit values immediately after that tag.
- Existing FH6 Assistant diagnostic outputs agree with the expected counts for
  the two named regression samples.

This byte layout remains `PROVISIONAL` until the raw regression binaries are
available in CI or are directly rechecked against a broader corpus.

## Regression evidence: Car ID 3761 / Fluorite AKE family

Status: `CONFIRMED` as sample evidence, not as a universal rule

Known metadata:

```text
car_id       3761
gyvl_offset  51
body_start   72
body_end     275791

Front               1
Back               21
Top              2980
Left             2761
Right            2785
Spoiler             3
FrontWindshield      0
BackWindshield       0
TopWindow            0
LeftWindow          18
RightWindow          0
```

The numbers above belong only to this sample. They are allowed in regression
tests and must never become production parsing conditions.

## Regression evidence: `Livery_2997_20260817150058`

Status: `CONFIRMED` as diagnostic evidence, pending raw binary fixture

Known metadata from existing differential output:

```text
gyvl_offset  51
body_start   72
body_end     293929

Front              24
Back              156
Top              2894
Left             2989
Right            2964
Spoiler              0
FrontWindshield      18
BackWindshield       41
TopWindow             0
LeftWindow            0
RightWindow           0
```

The raw `C_livery` file is not stored in the repository at the time of Milestone 1.
The regression test is therefore opt-in and skipped unless a real sample path is
provided.

## Group / shape / transform records

Status: `UNKNOWN` for this milestone

Milestone 1 deliberately does not classify artwork body records. In particular,
a leading `0x02`, transform-looking float sequence, source offset, or record size
is not enough to create a shape or transform node.

Future rule:

`Unknown is data, not an error.`

Unknown spans will be preserved when the raw-record tokenizer is implemented.
No byte-by-byte "find the next plausible shape" recovery rule is introduced here.

## Draw order and `source_offset`

Status: `UNKNOWN` for this milestone

`source_offset` is provenance. Milestone 1 makes no draw-order claim and performs
no global layer reversal.

## Sources and attribution

Format facts were checked against:

- ForzaLiveryStudio public binary-format documentation:
  `docs/CLIVERY.md` and, for later milestones only, `docs/CGROUP.md`.
- KFPS public reverse-engineering material as a secondary format-fact reference.
- Real FH6 `C_livery` observations and FH6 Assistant differential diagnostics.

FLS implementation code is not part of this decoder. The independent decoder has
no runtime dependency on FLS or KFPS.
