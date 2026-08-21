# Milestone 4 semantic-flatten notes

## Scope

Milestone 4 begins only after the independent read-only decoder has a lossless
`C_livery -> Scene Tree` result. The target is differential semantic validation
and, in M4d, evidence-driven connection of those semantics to the existing FH6
Assistant preview path.

The independent decoder remains read-only and does not encode or modify game
data. It does not import, link, or copy FLS implementation code. Public FLS
format/development documentation and user-produced black-box artifacts are
validation inputs only.

A neutral semantic layer record contains the fields needed to compare our decoder
with an independently produced oracle:

- section / slot membership;
- raw shape identity word;
- structural parent path and traversal order;
- effective transform;
- mask state;
- semantic RGBA color;
- source position; and
- leaf count.

## Structural flatten order

Status: `CONFIRMED` as an independent representation invariant and
`CORPUS-VALIDATED` for flat direct-sibling paint order. Nested Group/mask renderer
order still requires final sign-off.

Leaves are emitted by depth-first traversal of each `GroupNode.children` list in
stored structural order. The independent implementation never sorts by
`source_offset` and never performs a global reversal. `source_offset` remains
provenance.

Controlled FLS pair 5 proves that flat direct siblings are painted in stored child
order: earlier child first, later child over it. FLS Layers UI shows the same
stack topmost-first and is therefore visually reversed relative to stored order.
This does not prove that raw byte offset is a general z-order key for nested
Group scenes.

M4d renderer tracing found that the FH6 Assistant legacy wrapper was sorting the
pinned decoder output by ascending `source_offset`. That unsupported normalization
has been removed. The legacy preview wrapper now preserves decoder structural
order into the renderer and records `fh6assistant_layer_order_policy =
decoder_structural_dfs`.

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

Controlled pair 3 shows that the FLS Group Flip UI can keep the saved Group frame
at identity and rebake reflection into child Shape transforms. This validates that
UI operation, but not a serialized Group frame whose own scale is negative.

If a future file contains a non-conformal group frame, M4 fails closed rather
than applying this bounded decomposition outside its evidence set.

## Shape skew

Status: `CORPUS-VALIDATED` for a nonzero direct Shape value.

Controlled pair 5 stores direct Top Shape 101 with FLS `skew=2.3`. The exported
`C_livery` Shape record decodes as `2.299999952316284`, the expected float32
representation. Group skew remains outside the current evidence set.

## Record-level mask state

Status: `CORPUS-VALIDATED` for direct Shape siblings and terminal direct Shapes,
including chromatic targets. State crossing a completed Group remains `UNKNOWN`.

`0x60` ancestry is authoritative. Outside such ancestry, controlled pair 5 proves
that a direct Shape physically led by `01 02` carries trailing state for the
immediately preceding direct Shape sibling and that the rule is independent of
predecessor color.

Controlled pairs 2 and 4 prove the section-terminal `01` variant for achromatic
and chromatic terminal direct Shapes respectively.

State after a terminal/completed Group and values outside the validated set still
fail closed rather than being inferred.

Car ID 2997 provides exact independent mask-source regression oracles:

```text
Left  mask source offsets:  99686, 99782
Right mask source offsets: 196104, 196200
```

All four currently confirmed Car-2997 masks are achromatic. Therefore the M4d
legacy-runtime correction for chromatic flat `01 02` masks is a real bounded bug
fix but does not by itself explain the original Car-2997 Left-side occlusion.

## Vector color storage and semantic channel order

Status: `CORPUS-VALIDATED` as BGRA storage normalized to semantic RGBA.

Controlled pair 5 primary-color screenshot evidence resolves the channel order:

```text
stored [0,0,255,255] -> visually red
stored [0,255,0,255] -> green
stored [255,0,0,255] -> blue
```

Thus FLS v3 project vector color lists and corresponding `C_livery` Shape bytes
use BGRA storage. The decoder normalizes them to semantic RGBA. The earlier
pair-4 RGBA-storage interpretation was superseded by this visual calibration.

## Alpha versus node opacity

Controlled pair 5 contains a Shape with stored color alpha `164`, and the exported
`C_livery` preserves that alpha. The FLS node's separate `opacity` field remains
`1.0`; therefore non-unit node opacity is still unvalidated and fails closed.

## Controlled FLS differential pairs

### Pair 1 — basic vector/group oracle

```text
.3so: 2b7edae070afce33360ce87087045f8fc84d9f5714d153d89c8ccb8c886fc4f4
JSON: 2fa99cb36a5321c8449239638358891062cbe6490f8f89823bd6b58dc501c69a
C_livery: bd15497668848ad2a9ecefb71105f31953208f97a308866c1519ee1bdf076476
```

Confirms section mapping, Shape IDs, nested Group structure, effective Group
composition, white color, and `mask=false`.

### Pair 2 — reflection / rotation / terminal mask

```text
.3so: 999c619a062c8c68aa7f3f41ca17579a43e43b76bd25d3c1a94e693021ee9e53
JSON: 10e9299f99951f5df004373f292c86bbc5df8845ef5da09545ed6beb632122ac
C_livery: 4bc0e733963f64fef2756932873bc315676e377aad29482094049887182860b6
```

Confirms direct Shape reflection canonicalization, non-zero Shape rotation, and
terminal direct achromatic mask state.

### Pair 3 — FLS Group Flip UI behavior

```text
.3so: 1afa34a9142fa937a419264b7ae92f003fb1acb08b93cfb1fe7c958878303b2c
JSON: 11338cc1b1308c1ba507d053595fc5508662dd170a535c9c32305dab1c016e07
C_livery: b2751da36f17f7fbd80c5825261237820d9bad0b10bacff9206a36437ce74b1e
```

Confirms FLS Group Flip rebaking into child Shapes while the saved Group frame
remains identity.

### Pair 4 — chromatic terminal mask

```text
.3so: 0f143449078f74820bda819a043dac6d755cc6cfcf1cbea83ae457df17425029
JSON: 888f8572f1eb013d9f1902e3dd2a5986d50fe3d3d23cfe515f95b322db616126
C_livery: 1c48aa8e3acd6f659aae1ac4f821b7ef1a26ba9c8932aa5c73d73eb6f51f7f33
```

Confirms terminal direct Shape mask behavior is color-independent. Pair 5 later
supersedes the initial color-channel interpretation with visual primary-color
evidence.

### Pair 5 — chromatic sibling mask / skew / alpha / flat draw order

```text
.3so: be05f4ed0b53ce94b47f0dc2d0675d2b2202e579af4a77655b2ff5d8676b8175
JSON: b7dbd2bb95bba76bea4638068b9c8baa1729673c629f36d72d527afc6bd55fdd
C_livery: 564181e1657e7485281036e3b80492f2bce8183f88a9c24be044185c17003b9c
```

Confirms chromatic direct-sibling `01 02` mask, direct Shape nonzero skew, Shape
color alpha serialization, BGRA storage -> semantic RGBA, and flat direct-sibling
paint order. The intended completed-Group mask-boundary case and non-unit node
opacity were not actually present.

### Pair 6 — dedicated FLS UI Left/Right oracle

```text
.3so: 14092c91233dc6f50405486038ecd49377fbd14f3730549f97ef61e27ace1078
JSON: 47eb35affee966238b2d2631946a8c9297dd4fcd4cb2b2c184088f881897e562
C_livery: 4b757a4c8f536a8b9f52854e3b64df711247726854c4bc38fa9d2b18e6bd82f3
```

FLS UI Right visibly contains green Shape 102 while UI Left contains red Shape
101. The saved project and exported `C_livery` store green Shape 102 in internal
slot 3 / `Left` and red Shape 101 in slot 4 / `Right`.

Confirmed FLS UI-facing convention for this workflow:

```text
FLS UI Right <-> serialized/internal Left (slot 3)
FLS UI Left  <-> serialized/internal Right (slot 4)
```

This does not indicate a corrupt binary section order. `SECTION_NAMES` remains
unchanged; FLS UI labels are normalized only when used as a visual oracle.

## Real Car-2997 evidence

Independent decoder / raw SHA-256
`677751360dba1a7fe6eead246236094836e9e1433709a0fd8dc5a1b2635f7ded`:

```text
all 11 sections complete
9086 / 9086 leaves
Left  2989
Right 2964
unknown spans 0
```

Representative independent nested/reflected Left landmarks include:

```text
offset 194176: shape 124, parent_path (3,14,0)
offset 194336: shape 124, parent_path (3,14,5), reflected final frame
```

A retained diagnostic of the old pinned/local preview decoder reports 9085 total
layers with Left 2988 and Right 2964. Thus that old renderer input path was one
Left leaf short relative to the independently validated scene. This is a concrete
runtime discrepancy but does not by itself explain an extra occluding polygon.

## M4d renderer integration

Status: `IN PROGRESS`.

The runtime preview chain has been traced from `app.py` through pinned decode,
local recovery/wrappers, section grouping, canvas rendering, exact vehicle
projection, and display rotation.

Two evidence-driven corrections are now connected to the existing preview path:

1. the wrapper no longer reorders layers by `source_offset`; decoder structural
   order is preserved;
2. the strictly verified flat-section recovery re-applies chromatic direct-sibling
   `01 02` mask state after the pinned conversion, with explicit evidence metadata.

No global reversal, no Left/Right section swap, and no unresolved Group-boundary
mask inference is introduced.

Detailed findings and remaining Car-2997 root-cause work are recorded in
`m4_renderer_trace_notes.md`.

## Remaining M4 evidence gaps

Still not signed off:

- a serialized reflected Group frame;
- non-zero Group rotation combined with a serialized reflected Group frame;
- Group skew / general affine Group transforms;
- mask state crossing a completed Group boundary;
- raster/logo semantic oracle;
- non-unit FLS node opacity;
- nested Group/mask final renderer draw-order semantics;
- direct re-render confirmation that the original Car-2997 Left-side occlusion is resolved.

Raw `.3so`, screenshots, and game binaries remain external opt-in fixtures; they
are not committed to the repository.
