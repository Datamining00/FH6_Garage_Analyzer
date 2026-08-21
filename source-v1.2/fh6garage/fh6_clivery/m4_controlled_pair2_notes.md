# Milestone 4 controlled FLS pair 2 — reflection, mask, rotation

This note records a second user-produced black-box oracle pair. No FLS implementation
source is used. The `.3so` project and exported `C_livery` are not committed; only
hashes and observed invariants are retained.

## Pinned artifacts

```text
FLS .3so SHA-256:
999c619a062c8c68aa7f3f41ca17579a43e43b76bd25d3c1a94e693021ee9e53

FLS uncompressed project JSON SHA-256:
10e9299f99951f5df004373f292c86bbc5df8845ef5da09545ed6beb632122ac

Exported C_livery SHA-256:
4bc0e733963f64fef2756932873bc315676e377aad29482094049887182860b6

Car ID: 2017
Section counts: [2, 3, 1, 3, 1, 0, 0, 0, 0, 0, 0]
Leaf count: 10
Shape IDs: [2104, 2105, 2126, 2135, 2137, 2217, 2106, 2110, 2123, 2116]
```

## Direct shape reflection — CONFIRMED

FLS project shape `2137` is represented as:

```text
rotation = 180
scale_x  = 1
scale_y  = -1
x        = -239.4631208486271
y        = 181.17758620070686
```

The exported `C_livery` stores the equivalent canonical frame as:

```text
rotation = 0
scale_x  = -1
scale_y  = 1
x        = -239.46311950683594
y        = 181.17758178710938
```

The independent M4 canonicalization therefore matches the black-box export. This
validates a **direct Shape reflection** only. It does not yet validate reflection on
a Group frame.

## Non-zero shape rotation — CONFIRMED

FLS shape `2123` has rotation `45.280401250039816` degrees. The exported decoder
produces `45.28040313720703`, consistent with float32 serialization. No global or
section-level reversal is involved.

## Terminal direct-shape mask state — CONFIRMED

The Top section contains one FLS vector shape (`2217`) with `mask=true`.

The corresponding `C_livery` section is structurally:

```text
section_start = 280
root header   = 280..286
shape record  = 287..317
shape marker  = 02
shape ID      = 2217
tree_end      = 318
section_end   = 336
```

The 18-byte post-tree remnant begins:

```text
01 00 00 00 00 00 00 00 00 00 00 80 3f 00 00 00 00 00
^^
```

The first byte is `01`. In the same controlled export, otherwise equivalent
non-masked populated sections use `00` in this position. The `.3so` oracle says the
terminal direct achromatic Shape is masked, proving the bounded semantic rule:

```text
post-tree terminal state 01
    -> terminal direct achromatic Shape mask = true
```

The rule is deliberately not generalized across a terminal Group boundary or to a
chromatic terminal Shape; those cases fail closed until a separate oracle proves
them.

## Differential result

After adding the terminal-state rule, all ten effective semantic leaves agree on:

- section and DFS order;
- shape identity;
- structural parent path;
- effective position/scale/rotation/skew;
- mask;
- RGBA color.

The maximum absolute transform-component difference is approximately
`1.4582e-5`, below the existing FLS-to-`C_livery` float32 tolerance of `2e-5`.

## Still not validated by this pair

- reflected Group frames;
- non-zero group rotation combined with reflection;
- non-zero skew;
- chromatic mask behavior;
- mask state crossing a completed Group boundary;
- raster/logo layers;
- non-unit opacity;
- renderer draw-order semantics.
