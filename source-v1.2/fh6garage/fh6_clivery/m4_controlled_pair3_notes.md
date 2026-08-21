# Milestone 4 controlled FLS pair 3 — Group Flip rebaking

Status: **CORPUS-VALIDATED FLS UI GROUP-FLIP BEHAVIOR; NO SERIALIZED REFLECTED GROUP FRAME OBSERVED**

This note records a user-produced black-box pair made from the same FLS project as controlled pair 2. The user selected the existing two-shape Left group and invoked **Flip Selection** once before saving `.3so` and exporting `C_livery`.

No FLS implementation source is used as a format oracle here. The evidence consists only of the user-produced `.3so`, its decompressed JSON, and the exported `C_livery`.

## Pinned artifacts

- `.3so` SHA-256: `1afa34a9142fa937a419264b7ae92f003fb1acb08b93cfb1fe7c958878303b2c`
- uncompressed project JSON SHA-256: `11338cc1b1308c1ba507d053595fc5508662dd170a535c9c32305dab1c016e07`
- exported `C_livery` SHA-256: `b2751da36f17f7fbd80c5825261237820d9bad0b10bacff9206a36437ce74b1e`
- inflated `C_livery` SHA-256: `2310b64608d28b54cdfe94101007aed36305a6a89fe6962743277d4049e664f3`
- Car ID: `2017`
- section counts: `[2,3,1,3,1,0,0,0,0,0,0]`

## Observed `.3so` behavior

The Left hierarchy remains:

```text
Left
├─ Group
│  ├─ Shape 2106
│  └─ Shape 2110
└─ Shape 2123
```

The saved Group transform itself remains identity:

```text
x=0, y=0, scale_x=1, scale_y=1, rotation=0, skew=0
```

The Flip operation is instead rebaked into the two child Shapes:

```text
Shape 2106
x=-183.066794619735
y=-53.664739879963065
rotation=180
scale_x=1
scale_y=-1

Shape 2110
x=49.208076139981586
y=-205.8448276190877
rotation=180
scale_x=1
scale_y=-1
```

Compared with controlled pair 2, the two child X positions are mirrored around the selected group bounds and both child transforms receive the reflected representation. Editor `visible` changes are ignored by semantic comparison, consistent with pair-1/2 evidence that visibility is not a `C_livery` omission rule.

## Observed `C_livery` delta from pair 2

Both exported inflated payloads have identical length and section boundaries. Only four bytes differ, all inside the two Left child Shape records.

Decoded child-local transforms:

```text
pair 2:
2106: x=+116.13743591308594, y=+76.09004211425781, sx=+1, sy=+1
2110: x=-116.13743591308594, y=-76.09004211425781, sx=+1, sy=+1

pair 3:
2106: x=-116.13743591308594, y=+76.09004211425781, sx=-1, sy=+1
2110: x=+116.13743591308594, y=-76.09004211425781, sx=-1, sy=+1
```

The surrounding serialized Group frame is unchanged. After normal group composition, effective leaf positions/reflections match the `.3so` semantic scene.

## Evidence conclusion

CONFIRMED:

- FLS **Group Flip** can preserve the group hierarchy while rebaking the reflection into child Shape transforms.
- The saved `.3so` does not necessarily contain a negative-scale Group frame after the UI operation.
- The exported `C_livery` may likewise keep the Group frame unchanged and encode the reflection on child Shape records.
- The independent decoder's existing reflected-Shape canonicalization is the correct semantic representation for this pair.

NOT CONFIRMED by this pair:

- serialization or export semantics of a Group node whose own stored transform has negative scale;
- reflected-group rotation parity when the Group frame itself is reflected;
- arbitrary affine/non-conformal Group transforms.

Therefore the previous M4 evidence gap must be described as **serialized reflected Group frame**, not merely "using the Group Flip UI".

## Regression

`tests/test_clivery_fls_semantic_controlled3.py` provides:

1. an always-on synthetic regression matching the observed v3 scene structure; and
2. an opt-in complete real-pair differential using:

```text
FH6_FLS_3SO_2017_GROUPFLIP
FH6_CLIVERY_2017_GROUPFLIP
```

Raw user artifacts are not committed.
