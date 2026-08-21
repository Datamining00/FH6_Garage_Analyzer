# Milestone 4 semantic-flatten notes

## Scope

Milestone 4 begins only after the independent read-only decoder has a lossless
`C_livery -> Scene Tree` result. This stage does **not** connect the result to the
FH6 Assistant renderer and does not encode or modify game data.

The target is differential semantic validation. A neutral semantic layer record
contains the fields needed to compare our decoder with an independently produced
oracle such as an FLS export:

- section / slot membership;
- raw shape identity word;
- structural parent path and traversal order;
- effective transform;
- mask state;
- RGBA color;
- source position; and
- leaf count.

No ForzaLiveryStudio runtime or implementation source is imported by this module.
Public FLS format/development documentation and user-produced black-box artifacts
are validation inputs only.

## Structural flatten order

Status: `CONFIRMED` as a representation invariant; renderer draw order remains
`PROVISIONAL`.

Leaves are emitted by depth-first traversal of each `GroupNode.children` list in
its stored structural order. The implementation never sorts by `source_offset`
and never performs a global reversal. `source_offset` remains provenance.

## Effective group transform

Status: `CORPUS-VALIDATED` for the current FH6 samples and controlled FLS pairs.

All serialized group frames observed in the supplied `C_livery` files are
conformal: `abs(sx) == abs(sy)` within floating-point tolerance. For that bounded
case a child origin `(x, y)` is transformed by the parent frame as:

```text
dx = parent.sx * child.x
dy = parent.sy * child.y
X  = parent.x + cos(parent.rotation) * dx - sin(parent.rotation) * dy
Y  = parent.y + sin(parent.rotation) * dx + cos(parent.rotation) * dy
```

Scale is component-wise. A reflected parent (`parent.sx * parent.sy < 0`)
negates the child's rotation and skew contribution. Only final leaf parameters
are canonicalized to non-negative `sy`; if `sy < 0`, both scales are negated and
180 degrees is added to rotation. Group frames themselves are not canonicalized
before descendant composition because their reflection parity is semantic.

Controlled pair 3 additionally shows that the FLS **Group Flip** UI can keep the
saved Group frame at identity and rebake the reflection into child Shape
transforms. This validates the UI operation, but not a serialized Group frame
whose own scale is negative.

If a future file contains a non-conformal group frame, M4 fails closed rather
than silently applying this bounded decomposition outside its evidence set.

## Record-level mask state

Status: `CORPUS-VALIDATED` for direct Shape siblings in the currently observed
achromatic context and for terminal direct Shapes of both achromatic and
chromatic colors. Group-terminal odd state remains `UNKNOWN`.

`0x60` ancestry is authoritative. Outside such ancestry, the current corpus
shows that a direct Shape physically led by `01 02` carries trailing state for
the immediately preceding **direct Shape sibling**, not for itself. Current
black-box evidence only promotes that preceding sibling when it is achromatic
(`R == G == B`). Chromatic `01 02` sibling behavior is still not inferred.

Controlled pair 2 proved the section-terminal variant with a white Top Shape
`2217`: an ordinary `02` Shape record is followed by a populated-section remnant
whose first byte is `01`.

Controlled pair 4 changes the same masked Shape to `[255,85,0,255]` and proves
that the terminal rule is **not** restricted by color. The Shape color bytes
change while the section-terminal state remains `01`. Therefore, in the bounded
context of a terminal direct Shape, state `01` masks that Shape regardless of
whether it is achromatic or chromatic.

State after a terminal Group and values outside `{0,1}` still fail closed rather
than being inferred.

The Car ID 2997 sample provides an exact direct-sibling regression oracle:

```text
Left  mask source offsets:  99686, 99782
Right mask source offsets: 196104, 196200
```

## C_livery vector color byte order

Status: `CORPUS-VALIDATED` for controlled `C_livery` vector Shape records.

Controlled pair 4 stores FLS color `[255,85,0,255]` as the final four bytes of
the Top Shape record:

```text
ff 55 00 ff
```

The bytes therefore map directly to **RGBA** for this `C_livery` record. The
independent decoder scopes this correction to raw records whose kind is
`livery_shape_record`.

Standalone `C_group` color byte order is deliberately left unchanged because no
colored standalone `C_group` corpus sample has yet independently established its
semantics.

## Current real-sample flatten evidence

Car ID 2997 / raw SHA-256
`677751360dba1a7fe6eead246236094836e9e1433709a0fd8dc5a1b2635f7ded`:

```text
Left:  declared 2989, flattened 2989, first 99623, last 195981
Right: declared 2964, flattened 2964, first 196041, last 291592
```

Representative nested and reflected transforms match the retained independent M4
oracle at source offsets `99905`, `194176`, and `194336` within numerical
tolerance. The full supplied Car 2997 scene flattens to 9086 leaves, matching all
11 declared section counts. Car 3761 similarly flattens to 8569 leaves.

## Differential comparator

`semantic_diff.py` compares neutral `SemanticLayer` sequences. It reports field
level differences for section, structural order, raw shape identity, parent path,
transform, mask, color, source offset, and total leaf count. It deliberately has
no FLS-specific runtime or implementation dependency.

## FLS `.3so` black-box oracle bridge

FLS public `docs/DEV.md` documents `.3so` as the editor project JSON wrapped in a
gzip stream, with the project document containing a recursive `root` scene tree
of kind-discriminated layer nodes. `fls_oracle.py` uses only that documented
container fact. It does not inspect or reproduce FLS implementation code.

The bridge strictly decompresses gzip, requires UTF-8 JSON with the documented
`root`, records raw/uncompressed SHA-256 values, inventories top-level keys,
observed string-valued node `kind` values, exact per-kind key signatures, and
candidate child-bearing keys. The generic loader and iterator preserve exact JSON
paths and untouched node dictionaries for black-box evidence.

## Controlled FLS differential pair 1

```text
.3so: 2b7edae070afce33360ce87087045f8fc84d9f5714d153d89c8ccb8c886fc4f4
JSON: 2fa99cb36a5321c8449239638358891062cbe6490f8f89823bd6b58dc501c69a
C_livery: bd15497668848ad2a9ecefb71105f31953208f97a308866c1519ee1bdf076476
```

Car ID 2017, counts `[2,0,0,2,1,0,0,0,0,0,0]`, five vector leaves. This pair
confirms section mapping, vector Shape IDs, nested group structure, effective
group composition, white color, and `mask=false`. It also shows that FLS may
recenter a group and rebake child local coordinates while preserving effective
leaf geometry, and that `visible=false` leaves can still be exported.

## Controlled FLS differential pair 2

```text
.3so: 999c619a062c8c68aa7f3f41ca17579a43e43b76bd25d3c1a94e693021ee9e53
JSON: 10e9299f99951f5df004373f292c86bbc5df8845ef5da09545ed6beb632122ac
C_livery: 4bc0e733963f64fef2756932873bc315676e377aad29482094049887182860b6
```

Car ID 2017, counts `[2,3,1,3,1,0,0,0,0,0,0]`, ten vector leaves. Confirms direct
Shape reflection canonicalization, non-zero Shape rotation, terminal direct
achromatic mask state, and the complete ten-leaf neutral semantic comparison
within `2e-5` transform tolerance.

## Controlled FLS differential pair 3

```text
.3so: 1afa34a9142fa937a419264b7ae92f003fb1acb08b93cfb1fe7c958878303b2c
JSON: 11338cc1b1308c1ba507d053595fc5508662dd170a535c9c32305dab1c016e07
C_livery: b2751da36f17f7fbd80c5825261237820d9bad0b10bacff9206a36437ce74b1e
```

Confirms FLS Group Flip UI rebaking into the two child Shape transforms while the
saved Group frame remains identity. It does not supply a serialized reflected
Group frame.

## Controlled FLS differential pair 4

```text
.3so: 0f143449078f74820bda819a043dac6d755cc6cfcf1cbea83ae457df17425029
JSON: 888f8572f1eb013d9f1902e3dd2a5986d50fe3d3d23cfe515f95b322db616126
C_livery: 1c48aa8e3acd6f659aae1ac4f821b7ef1a26ba9c8932aa5c73d73eb6f51f7f33
inflated C_livery: ce42cae71b455922ba11685e8ed2972ba77096e5a069c80c92d7b5cc84c58dd9
```

Same 10-leaf structure as pair 3. The Top Shape 2217 remains `mask=true` but its
color becomes `[255,85,0,255]`. Compared with pair 3, exactly two inflated bytes
change, both in the Shape color field; terminal state `01` remains unchanged.
This confirms chromatic terminal direct-Shape mask behavior and `C_livery` RGBA
vector color bytes. Full semantic comparison remains within the existing `2e-5`
tolerance; maximum observed transform-component difference is approximately
`1.4582e-5`.

## Remaining M4 evidence gaps

Still not signed off:

- a serialized reflected Group frame;
- non-zero Group rotation combined with a serialized reflected Group frame;
- non-zero skew;
- chromatic behavior of the **direct-sibling `01 02`** mask state;
- mask state crossing a completed Group boundary;
- standalone colored `C_group` byte order;
- raster/logo layers;
- non-unit opacity;
- final renderer draw-order semantics.

Raw `.3so` and game binaries remain external opt-in fixtures; they are not
committed to the repository.
