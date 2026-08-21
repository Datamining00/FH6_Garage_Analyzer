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
Public FLS format/development documentation is reference material only.

## Structural flatten order

Status: `CONFIRMED` as a representation invariant; renderer draw order remains
`PROVISIONAL`.

Leaves are emitted by depth-first traversal of each `GroupNode.children` list in
its stored structural order. The implementation never sorts by `source_offset`
and never performs a global reversal. `source_offset` remains provenance.

## Effective group transform

Status: `CORPUS-VALIDATED` for the current FH6 samples.

All group frames observed in the supplied `C_livery` files are conformal:
`abs(sx) == abs(sy)` within floating-point tolerance. For that bounded case a
child origin `(x, y)` is transformed by the parent frame as:

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

If a future file contains a non-conformal group frame, M4 fails closed rather
than silently applying this bounded decomposition outside its evidence set.

## Record-level mask state

Status: `CORPUS-VALIDATED` for direct shape siblings and terminal direct
achromatic shapes; group-terminal odd state remains `UNKNOWN`.

`0x60` ancestry is authoritative. Outside such ancestry, the current corpus
shows that a direct shape physically led by `01 02` carries trailing state for
the immediately preceding **direct Shape sibling**, not for itself. The state is
promoted to a mask only when that preceding shape is achromatic (`R == G == B`).
A chromatic predecessor is retained as an ordinary layer.

A second controlled FLS `.3so -> C_livery` pair proves the terminal variant. A
single Top-section shape with `mask=true` is emitted as an ordinary `02` shape
record followed by a populated-section remnant whose first byte is `01`:

```text
shape ID 2217: 287..317
section tree_end: 318
remnant: 01 00 00 00 00 00 00 00 00 00 00 80 3f 00 00 00 00 00
         ^^
```

For this bounded context, terminal state `01` masks the terminal direct
achromatic Shape. State after a terminal Group, chromatic-terminal state, and
values outside `{0,1}` fail closed rather than being inferred.

The Car ID 2997 sample provides an exact direct-sibling regression oracle:

```text
Left  mask source offsets:  99686, 99782
Right mask source offsets: 196104, 196200
```

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
gzip stream, with the project document containing a recursive `root` scene tree of
kind-discriminated layer nodes. `fls_oracle.py` uses only that documented container
fact. It does not inspect or reproduce FLS implementation code.

The bridge strictly decompresses gzip, requires UTF-8 JSON with the documented
`root`, records raw/uncompressed SHA-256 values, inventories top-level keys,
observed string-valued node `kind` values, exact per-kind key signatures, and
candidate child-bearing keys. The generic loader and iterator preserve exact JSON
paths and untouched node dictionaries for black-box evidence.

## Controlled FLS differential pair 1

Pinned user-authored pair:

```text
.3so SHA-256:
2b7edae070afce33360ce87087045f8fc84d9f5714d153d89c8ccb8c886fc4f4

uncompressed project JSON SHA-256:
2fa99cb36a5321c8449239638358891062cbe6490f8f89823bd6b58dc501c69a

C_livery SHA-256:
bd15497668848ad2a9ecefb71105f31953208f97a308866c1519ee1bdf076476
```

Car ID 2017, section counts `[2,0,0,2,1,0,0,0,0,0,0]`, five vector leaves.
This pair confirms section mapping, vector shape IDs, nested group structure,
color, effective group composition, and the fact that FLS may recenter a group
and rebake child local coordinates while preserving the same effective leaf
geometry. `visible=false` leaves can still be exported and are therefore not
omitted by the semantic adapter.

## Controlled FLS differential pair 2

Pinned user-authored reflection/mask/rotation pair:

```text
.3so SHA-256:
999c619a062c8c68aa7f3f41ca17579a43e43b76bd25d3c1a94e693021ee9e53

uncompressed project JSON SHA-256:
10e9299f99951f5df004373f292c86bbc5df8845ef5da09545ed6beb632122ac

C_livery SHA-256:
4bc0e733963f64fef2756932873bc315676e377aad29482094049887182860b6
```

Car ID 2017, section counts `[2,3,1,3,1,0,0,0,0,0,0]`, ten vector leaves.
This pair confirms:

- direct Shape reflection canonicalization (`rotation=180, sy=-1` in FLS ->
  equivalent `rotation=0, sx=-1, sy=1` in `C_livery`);
- non-zero Shape rotation (`45.280401...` -> float32 `45.280403...`);
- terminal direct achromatic mask state via section-remnant byte `01`;
- the complete ten-leaf neutral semantic comparison within the existing
  `2e-5` transform tolerance.

Maximum observed transform-component difference for this pair is approximately
`1.4582e-5`.

## Remaining M4 evidence gaps

Still not signed off:

- reflected Group frames (pair 2 validates a direct Shape reflection, not a Group);
- non-zero group rotation combined with reflection;
- non-zero skew;
- chromatic mask behavior;
- mask state crossing a completed Group boundary;
- raster/logo layers;
- non-unit opacity;
- final renderer draw-order semantics.

Raw `.3so` and game binaries remain external opt-in fixtures; they are not
committed to the repository.
