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

All group frames observed in the two supplied `C_livery` files are conformal:
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

Status: `CORPUS-VALIDATED` for direct shape siblings; group-terminal odd state
remains `UNKNOWN`.

`0x60` ancestry is authoritative. Outside such ancestry, the current corpus
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

## FLS `.3so` black-box oracle bridge

Status: `IMPLEMENTED INSPECTION/EVIDENCE BRIDGE; REAL ORACLE ARTIFACT PENDING`.

FLS public `docs/DEV.md` documents `.3so` as the editor project JSON wrapped in a
gzip stream, with the project document containing a recursive `root` scene tree of
kind-discriminated layer nodes. `fls_oracle.py` uses only that documented container
fact. It does not inspect or reproduce FLS implementation code.

The bridge strictly decompresses gzip, requires UTF-8 JSON with the documented
`root`, records raw/uncompressed SHA-256 values, inventories top-level keys,
observed string-valued node `kind` values, exact per-kind key signatures, and
candidate child-bearing keys. It intentionally makes no field-to-`SemanticLayer`
mapping until a real `.3so` produced from one of the SHA-pinned livery samples is
observed.

The bridge exposes a generic JSON loader and `kind`-node iterator. Each observed
node is returned with its exact JSON path and untouched dictionary. This is
structural evidence only: no undocumented key is renamed or assigned transform,
mask, shape, section, or draw-order meaning.

For reproducible handoff, the module CLI can write both the compact inventory and
an optional raw kind-node/path dump from the same single file read:

```text
python -m fh6garage.fh6_clivery.fls_oracle sample.3so \
  -o inventory.json \
  --nodes-output nodes.json
```

The dump carries the source `.3so` raw/uncompressed SHA-256 values so later
semantic mapping can be tied to one exact black-box artifact.

The public package API also exports the loader, inventory, iterator, and node-dump
helpers. An opt-in real regression hook is present: setting `FH6_FLS_3SO_2997` to
an untouched `.3so` saved after importing the SHA-pinned Car 2997 `C_livery` makes
the suite validate documented container/root framing and verify that inventory
count and generic node traversal agree. Exact FLS key/value expectations will be
pinned only after that real artifact is observed.

The synthetic/oracle bridge suite currently covers container inventory,
determinism, loader hashes, exact JSON paths, raw node-dump preservation, CLI
output, public API exports, invalid gzip/JSON/root rejection, and the opt-in real
Car 2997 hook.

This two-step policy prevents guessing FLS scene-field names or silently importing
implementation assumptions. Once a real `.3so` is observed, only fields present in
that black-box output will be normalized into the existing neutral comparator.

A full **FLS-vs-ours** M4 sign-off still requires an untouched FLS `.3so` saved
after importing one of the same SHA-pinned `C_livery` samples. Until that oracle
artifact is available and compared field-by-field, Milestone 4 remains partially
complete rather than signed off.
