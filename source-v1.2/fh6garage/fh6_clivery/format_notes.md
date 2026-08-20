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
- Direct observations of the two validated FH6 regression binaries listed below.
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
- Raw sample observations: offset `0x10` decodes to Car ID `3761` and `2997`
  respectively in the two regression files below.

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
- Both validated raw samples have `gyvl_offset = 51` and `body_start = 72`.

The production decoder locates the tag structurally. It does not hardcode
`gyvl_offset = 51`.

## Artwork body end

Status: `CONFIRMED`

Milestone 1 uses the post-artwork `yrvl` boundary and independently cross-checks
it against the declared `gyvl` length stored in the four bytes immediately before
the `gyvl` tag:

```text
declared_gyvl_length = u32_le[gyvl_offset - 4]
actual_gyvl_length   = body_end - gyvl_offset
```

The candidate is accepted only when these values match and enough bytes remain
for the section-counter record and a following `yrvl` tag.

Direct raw evidence:

```text
Car 3761:
  declared_gyvl_length = 275740
  body_end - gyvl      = 275791 - 51 = 275740

Car 2997:
  declared_gyvl_length = 293878
  body_end - gyvl      = 293929 - 51 = 293878
```

This directly confirms the length-field interpretation for the two validated FH6
samples and removes the earlier Milestone 1 provisional boundary rule.

## Section-counter record

Status: `CONFIRMED`

Milestone 1 reads eleven little-endian `u32` values immediately after the
post-artwork `yrvl` tag. One additional little-endian `u32` follows those eleven
values. Its position is confirmed; Milestone 1 deliberately does not assign a
higher-level semantic meaning to it.

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
- Direct parsing of the two raw FH6 regression binaries reproduces the previously
  recorded differential counts exactly.
- In both validated files the additional trailing `u32` is `0`.

## Regression evidence: Car ID 3761 / Fluorite AKE

Status: `CONFIRMED` as sample evidence, not as a universal rule

Raw file identity:

```text
file size     132924 bytes
payload size  276902 bytes
SHA-256       565e75445c70501dc98c00cc76c1d162d703b1921fd55735fcccb857757dac18
```

Validated metadata:

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

Status: `CONFIRMED` as sample evidence, not as a universal rule

Raw file identity:

```text
file size     221057 bytes
payload size  295148 bytes
SHA-256       677751360dba1a7fe6eead246236094836e9e1433709a0fd8dc5a1b2635f7ded
```

Validated metadata:

```text
car_id       2997
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

The numbers above belong only to this sample. The regression test remains opt-in
because the game save binaries themselves are not committed to the repository.

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
- Direct inspection of the two raw FH6 `C_livery` regression files listed above.
- Existing FH6 Assistant differential diagnostics.

FLS implementation code is not part of this decoder. The independent decoder has
no runtime dependency on FLS or KFPS.
