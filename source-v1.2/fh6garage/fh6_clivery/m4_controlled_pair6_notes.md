# Milestone 4 controlled FLS pair 6 — dedicated Left/Right UI-to-serialized oracle

Status: **CORPUS-VALIDATED FLS UI SIDE LABEL SWAP RELATIVE TO SERIALIZED INTERNAL SLOTS; DECODER SECTION NAMES UNCHANGED**

This note records a minimal user-produced `.3so -> C_livery` pair plus two FLS screenshots created specifically to resolve the side-label discrepancy first observed in controlled pair 5.

No FLS implementation source is used. Evidence consists only of the user-produced `.3so`, its decompressed JSON, the exported `C_livery`, and the two screenshots.

## Pinned external artifacts

- `.3so` SHA-256: `14092c91233dc6f50405486038ecd49377fbd14f3730549f97ef61e27ace1078`
- uncompressed project JSON SHA-256: `47eb35affee966238b2d2631946a8c9297dd4fcd4cb2b2c184088f881897e562`
- `C_livery` SHA-256: `4b757a4c8f536a8b9f52854e3b64df711247726854c4bc38fa9d2b18e6bd82f3`
- inflated `C_livery` SHA-256: `09dbf9860f76f3ccd0464b98077f3664c96c785df8530578ddaaf58d2d5eabf1`
- FLS UI `Right (1)` screenshot SHA-256: `e0412ba5b74aa31aaf660dbaa060568914b4e9f89d25be68e8b85012ae2c0635`
- FLS UI `Left (1)` screenshot SHA-256: `b3ee61873ce2a4c85ef78b7dd7006b2c974085ac294881bc4ebc45f585d89e57`
- Car ID: `1124`
- section counts: `[0,0,0,1,1,0,0,0,0,0,0]`
- total vector leaves: `2`

Raw artifacts/screenshots are external and are not committed.

## User-visible FLS evidence

The first screenshot has FLS UI `Right (1)` selected and visibly shows exactly one green circle:

```text
FLS UI Right
└─ Primitives_0x0066 / Shape 102 / green circle
```

The second screenshot has FLS UI `Left (1)` selected and visibly shows exactly one red square:

```text
FLS UI Left
└─ Primitives_0x0065 / Shape 101 / red square
```

No masks, groups, rotations, skew, or non-unit opacity are involved.

## Saved `.3so` evidence

The same saved project serializes the side sections as:

```text
internal slot 3, name Left
└─ Shape 102
   stored BGRA [0,255,0,255] -> semantic green

internal slot 4, name Right
└─ Shape 101
   stored BGRA [0,0,255,255] -> semantic red
```

Therefore the FLS UI side labels are opposite to the project's serialized/internal livery-section names for this dedicated minimal oracle:

```text
FLS UI Right -> internal slot 3 / Left
FLS UI Left  -> internal slot 4 / Right
```

This reproduces the pair-5 observation with unique single-layer identifiers on both sides and removes the ambiguity that existed in pair 5.

## Exported `C_livery` evidence

The exported `C_livery` has Car ID `1124` and section counts:

```text
[0,0,0,1,1,0,0,0,0,0,0]
```

The two exact direct Shape records are:

```text
inflated offset 148:
  marker 02
  Shape ID 102 / 0x0066
  stored BGRA 00 ff 00 ff

inflated offset 204:
  marker 02
  Shape ID 101 / 0x0065
  stored BGRA 00 00 ff ff
```

The independent decoder assigns them according to the established serialized counter/section order:

```text
slot 3 / Left  -> Shape 102 / green
slot 4 / Right -> Shape 101 / red
```

This matches the `.3so` internal scene exactly.

## Evidence conclusion

CONFIRMED for this FLS v3 livery workflow:

```text
FLS UI Right <-> serialized/internal Left (slot 3)
FLS UI Left  <-> serialized/internal Right (slot 4)
```

The swap is a **UI-facing side convention relative to the serialized section names**, not evidence that the binary section-counter order itself is wrong. The `.3so` internal slots and exported `C_livery` agree with one another.

Therefore the independent decoder keeps:

```text
slot 3 = Left
slot 4 = Right
```

and does **not** globally swap `SECTION_NAMES`.

Any renderer or FLS-comparison layer that consumes user-facing FLS side labels must account for this convention explicitly rather than mutating the binary decoder's section identities.

## Relevance to the original side-rendering issue

This result means FLS screenshots labelled `Left`/`Right` cannot be compared naively to decoder sections of the same displayed name. A side-specific renderer differential must first normalize:

```text
FLS UI Left  -> decoder/internal Right
FLS UI Right -> decoder/internal Left
```

This may explain some apparent side-to-side mismatches in prior visual comparisons, but it does not by itself prove the cause of any occlusion or mask-order bug. Geometry, mask semantics, and nested draw order still require their own evidence.

## Regression

`tests/test_clivery_fls_semantic_controlled6.py` locks:

- internal slot 3 / `Left` = green Shape 102;
- internal slot 4 / `Right` = red Shape 101;
- exact SHA-pinned `.3so` / `C_livery` pair identities;
- exact exported Shape record IDs/colors;
- full FLS-internal semantic scene versus independent `C_livery` flatten differential.

Opt-in real-pair environment variables:

```text
FH6_FLS_3SO_1124_SIDE_ORACLE
FH6_CLIVERY_1124_SIDE_ORACLE
```

The screenshots remain visual provenance and are SHA-pinned in this note rather than committed.
