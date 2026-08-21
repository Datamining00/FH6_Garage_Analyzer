# Milestone 4 controlled FLS pair 4 — chromatic terminal mask and C_livery RGBA

Status: **CORPUS-VALIDATED CHROMATIC TERMINAL DIRECT-SHAPE MASK; C_livery VECTOR COLOR BYTES RGBA**

This note records a user-produced black-box `.3so -> C_livery` pair derived from the controlled pair-3 project. The only intentional semantic change was the color of the existing Top Shape `2217`, while its `mask=true` state was retained.

No FLS implementation source is used as a format oracle. The evidence consists only of the user-produced `.3so`, its decompressed JSON, the exported `C_livery`, and byte-for-byte comparison with the preceding controlled pair.

## Pinned artifacts

- `.3so` SHA-256: `0f143449078f74820bda819a043dac6d755cc6cfcf1cbea83ae457df17425029`
- uncompressed project JSON SHA-256: `888f8572f1eb013d9f1902e3dd2a5986d50fe3d3d23cfe515f95b322db616126`
- exported `C_livery` SHA-256: `1c48aa8e3acd6f659aae1ac4f821b7ef1a26ba9c8932aa5c73d73eb6f51f7f33`
- inflated `C_livery` SHA-256: `ce42cae71b455922ba11685e8ed2972ba77096e5a069c80c92d7b5cc84c58dd9`
- Car ID: `2017`
- section counts: `[2,3,1,3,1,0,0,0,0,0,0]`
- total vector leaves: `10`

## FLS scene evidence

The Top section contains one direct Shape:

```text
Shape ID: 2217
mask: true
color: [255, 85, 0, 255]
transform:
  x=-36.22636
  y=-149.77848
  scale_x=1
  scale_y=1
  rotation=0
  skew=0
```

All other controlled scene semantics remain the same as pair 3.

## Exported C_livery evidence

The Top Shape record begins at inflated payload offset `287` and is 31 bytes long. Its final four bytes are:

```text
ff 55 00 ff
```

These bytes exactly match the FLS project color `[255,85,0,255]` in **RGBA** order.

The 18-byte post-tree section remnant starts at offset `318` and still begins:

```text
01 00 00 00 00 00 00 00 00 00 00 80 3f 00 00 00 00 00
^^
```

Therefore terminal state `01` continues to encode the mask state even though the target Shape is chromatic.

Compared with controlled pair 3, the inflated `C_livery` length is unchanged and exactly two bytes differ:

```text
offset 315: ff -> 55
offset 316: ff -> 00
```

Both offsets are inside the Shape color field. The terminal state byte at offset `318` is unchanged.

## Evidence conclusions

CONFIRMED:

- section-terminal state `01` masks the terminal **direct Shape** independently of whether the Shape is achromatic or chromatic;
- the color and terminal-mask state are independently serialized in this controlled export;
- vector Shape color bytes in the controlled `C_livery` are RGBA, matching the FLS project color list directly;
- after the bounded decoder corrections, all ten controlled leaves match the FLS semantic oracle within the existing `2e-5` transform tolerance; maximum observed transform-component delta remains approximately `1.4582e-5`.

The RGBA correction is intentionally scoped to `C_livery` Shape records. A colored standalone `C_group` corpus sample has not yet independently established standalone color byte order.

NOT CONFIRMED by this pair:

- chromatic behavior of the separate direct-sibling `01 02` trailing-state rule;
- terminal mask state after a completed Group;
- standalone `C_group` color byte order;
- raster/logo color semantics;
- non-unit opacity or final renderer draw order.

## Regression

- `tests/test_clivery_color_order.py` locks the livery-specific RGBA interpretation while proving non-livery Shape records are not reinterpreted.
- `tests/test_clivery_terminal_mask.py` locks chromatic terminal direct-Shape mask behavior.
- `tests/test_clivery_fls_semantic_controlled4.py` provides an always-on observed FLS semantic test plus an opt-in complete real-pair differential using:

```text
FH6_FLS_3SO_2017_CHROMATIC_MASK
FH6_CLIVERY_2017_CHROMATIC_MASK
```

Raw user artifacts are not committed.
