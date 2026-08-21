# Milestone 4 controlled FLS pair 4 — chromatic terminal mask

Status: **CORPUS-VALIDATED CHROMATIC TERMINAL DIRECT-SHAPE MASK; COLOR STORAGE SEMANTICS CORRECTED BY PAIR 5**

This note records a user-produced black-box `.3so -> C_livery` pair derived from the controlled pair-3 project. The only intentional semantic change was the stored color of the existing Top Shape `2217`, while its `mask=true` state was retained.

No FLS implementation source is used as a format oracle. The evidence consists only of user-produced `.3so`, its decompressed JSON, the exported `C_livery`, and byte-for-byte comparison with the preceding controlled pair.

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
stored color list: [255, 85, 0, 255]
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

The Top Shape record begins at inflated payload offset `287` and is 31 bytes long. Its final four stored color bytes are:

```text
ff 55 00 ff
```

Pair 4 by itself proves that the FLS stored color tuple and the exported Shape color bytes are preserved one-for-one. It does **not**, by itself, establish the semantic channel labels of those four stored values.

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

## Pair-5 correction to color-channel interpretation

A later controlled pair includes primary-red/green/blue overlapping Shapes plus an FLS canvas screenshot. In that evidence:

```text
stored [0,0,255,255] -> visually red
stored [0,255,0,255] -> visually green
stored [255,0,0,255] -> visually blue
```

The FLS project list and `C_livery` Shape bytes are therefore **BGRA storage**, normalized by the decoder to semantic RGBA. Accordingly, pair 4's stored `[255,85,0,255]` / `ff 55 00 ff` corresponds to semantic RGBA `(0,85,255,255)`, not `(255,85,0,255)`.

The prior pair-4 RGBA-storage interpretation is explicitly superseded by this stronger primary-color visual oracle.

## Evidence conclusions

CONFIRMED:

- section-terminal state `01` masks the terminal **direct Shape** independently of whether the Shape is achromatic or chromatic;
- color storage bytes and terminal-mask state are independently serialized in this controlled export;
- FLS project stored color values are preserved into the corresponding `C_livery` Shape color bytes for this pair;
- after pair-5 channel calibration, those bytes are interpreted as BGRA storage and normalized to semantic RGBA;
- complete semantic comparison remains within the existing `2e-5` transform tolerance after the corrected channel mapping.

NOT CONFIRMED by pair 4 alone:

- chromatic behavior of the separate direct-sibling `01 02` trailing-state rule (confirmed later by pair 5);
- terminal mask state after a completed Group;
- standalone colored `C_group` channel semantics;
- raster/logo color semantics;
- non-unit opacity or general renderer draw order.

## Regression

- `tests/test_clivery_color_order.py` locks the shared BGRA-storage to semantic-RGBA behavior without a livery-only override.
- `tests/test_clivery_terminal_mask.py` locks chromatic terminal direct-Shape mask behavior.
- `tests/test_clivery_fls_semantic_controlled4.py` provides an always-on observed FLS semantic test plus an opt-in complete real-pair differential using:

```text
FH6_FLS_3SO_2017_CHROMATIC_MASK
FH6_CLIVERY_2017_CHROMATIC_MASK
```

Raw user artifacts are not committed.
