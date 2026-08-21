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

Status: `CORPUS-VALIDATED`, including one controlled FLS `.3so -> C_livery` pair.

All group frames observed in the current `C_livery` corpus are conformal:
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

The controlled FLS export pair adds an important black-box fact: raw local group
frames are **not** stable across `.3so -> C_livery` export. In the supplied v3
project the user-created Left group has an identity transform and its two shapes
carry world positions directly. The exported `C_livery` recenters that group to
approximately `(-66.92936, -129.75479)` and rewrites the two child positions to
approximately `(+116.13744, +76.09004)` and `(-116.13744, -76.09004)`.
After structural composition, the final leaf positions match the `.3so` values to
within `9.3e-6`. Differential validation must therefore compare effective leaf
semantics, never raw local group frames.

If a future file contains a non-conformal group frame or non-zero group skew, M4
fails closed rather than silently applying this bounded decomposition outside its
evidence set.

## Record-level mask state

Status: `CORPUS-VALIDATED` for direct shape siblings; group-terminal odd state
remains `UNKNOWN`.

`0x60` ancestry is authoritative. Outside such ancestry, the current game corpus
shows that a direct shape physically led by `01 02` carries trailing state for
the immediately preceding **direct Shape sibling**, not for itself. The state is
promoted to a mask only when that preceding shape is achromatic (`R == G == B`).
A chromatic predecessor is retained as an ordinary layer.

The Car ID 2997 sample provides an exact regression oracle:

```text
Left  mask source offsets:  99686, 99782
Right mask source offsets: 196104, 196200
```

The parser does not yet chase an odd lead across a completed Group boundary to a
terminal descendant. That case remains explicit unknown semantics rather than a
heuristic.

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

For FLS comparison, source offsets are disabled because `.3so` has no C_livery
byte provenance. The controlled export pair demonstrates float32 serialization
round-off up to about `9.3e-6`, so `fls_semantic.py` currently uses a bounded
`2e-5` absolute transform tolerance. This tolerance is evidence-scoped and should
be revisited if a wider corpus requires it.

## FLS `.3so` black-box oracle bridge

Status: `CONTROLLED REAL PAIR VALIDATED FOR BASIC VECTOR/GROUP SEMANTICS`.

FLS public `docs/DEV.md` documents `.3so` as the editor project JSON wrapped in a
gzip stream, with the project document containing a recursive `root` scene tree.
`fls_oracle.py` uses only that documented container fact. It does not inspect or
reproduce FLS implementation code.

The generic bridge strictly decompresses gzip, requires UTF-8 JSON with the
documented `root`, records raw/uncompressed SHA-256 values, inventories top-level
keys, observed string-valued node `kind` values, exact per-kind key signatures,
and candidate child-bearing keys. It also exposes exact JSON paths and untouched
node dictionaries for black-box schema observation.

A user-produced controlled pair has now been observed:

```text
FLS .3so raw SHA-256:
2b7edae070afce33360ce87087045f8fc84d9f5714d153d89c8ccb8c886fc4f4

FLS uncompressed JSON SHA-256:
2fa99cb36a5321c8449239638358891062cbe6490f8f89823bd6b58dc501c69a

Exported C_livery raw SHA-256:
bd15497668848ad2a9ecefb71105f31953208f97a308866c1519ee1bdf076476

Car ID: 2017
Section leaf counts:
[2, 0, 0, 2, 1, 0, 0, 0, 0, 0, 0]
```

Observed `.3so` v3 schema facts used by `fls_semantic.py` are limited to this
black-box evidence:

- top-level `format = fls_editor_project`, `version = 3`, `is_livery = true`;
- integer `car_id`;
- `root.children` contains eleven `group` nodes marked `is_livery_section` with
  `livery_section_slot` 0..10;
- groups carry `children`, `transform`, and unit `opacity`;
- vector leaves are `kind=shape` with `visual.kind=vector`, integer `shape_id`,
  RGBA `color`, boolean `mask`, `transform`, and unit `opacity`;
- section and group transforms are structurally composed before comparing leaves.

The pair contains five vector leaves with shape IDs
`[2104, 2105, 2106, 2110, 2116]`. Their section membership, DFS order, structural
parent paths, shape IDs, masks, colors, and effective transforms all match the
independent `C_livery` result. The nested Left paths are `(3,0,0)` and `(3,0,1)`.

Three leaves in the `.3so` are `visible=false` yet remain present in the exported
`C_livery` with ordinary opaque shape records. Therefore editor visibility is not
used as a leaf-omission rule by the M4 oracle adapter. Non-unit opacity, raster
visuals, non-conformal group scales, and non-zero group skew remain fail-closed
until separate differential evidence exists.

No raw `.3so` or game binary is committed. Regression tests pin the hashes and
observed invariants; an opt-in pair test uses `FH6_FLS_3SO_2017` and
`FH6_CLIVERY_2017` to execute the complete field-by-field comparison when those
user-provided files are available locally.

## Current M4 status

The black-box bridge and a first real controlled FLS-to-C_livery differential are
now complete for basic vector shapes, one nested group, section identity, color,
mask=false, hidden editor leaves, and effective transform composition.

This is **not** a universal FLS semantic sign-off. A broader oracle is still needed
for at least:

- true mask export behavior;
- reflected group export;
- non-zero rotation/skew combinations;
- raster/logo layers;
- non-unit opacity;
- group-terminal odd-lead mask state; and
- final renderer draw-order semantics.

The original Car 2997 livery cannot currently supply that oracle because FLS blocks
importing the locked `C_livery` by privacy policy. The controlled user-authored pair
therefore establishes the safe M4c baseline without bypassing that policy.
