# Milestone 4 controlled FLS pair 5 — chromatic sibling mask, skew, alpha, and flat draw order

Status: **CORPUS-VALIDATED DIRECT-SIBLING CHROMATIC MASK + DIRECT-SHAPE SKEW + FLAT-SIBLING PAINT ORDER; GROUP-BOUNDARY MASK AND NON-UNIT NODE OPACITY NOT PRESENT**

This note records a user-produced `.3so -> C_livery` controlled pair plus one FLS canvas/layer-panel screenshot. The project was intended to cover several remaining M4 questions in separate livery sections.

No FLS implementation source is used. The evidence consists only of the user-produced project JSON, exported `C_livery`, and screenshot.

## Pinned external artifacts

- `.3so` SHA-256: `be05f4ed0b53ce94b47f0dc2d0675d2b2202e579af4a77655b2ff5d8676b8175`
- uncompressed project JSON SHA-256: `b7dbd2bb95bba76bea4638068b9c8baa1729673c629f36d72d527afc6bd55fdd`
- `C_livery` SHA-256: `564181e1657e7485281036e3b80492f2bce8183f88a9c24be044185c17003b9c`
- inflated `C_livery` SHA-256: `e77e0cd7ea5e9528011ce034c73f00aa8c051dadc75baf0d21b55f7b8cb06167`
- screenshot SHA-256: `2de5818bf045f1200c0e67724f5183aad65b270ea12ba785c7e478101d3aa074`
- Car ID: `2017`
- section counts: `[2,3,1,1,3,0,0,0,0,0,0]`
- total vector leaves: `10`

Raw artifacts and the screenshot remain external and are not committed.

## 1. Front — chromatic direct-sibling `01 02` mask

FLS project order:

```text
Front
├─ Shape 2104, mask=true, stored color [0,0,255,255]
└─ Shape 2110, mask=false, stored color [255,255,255,255]
```

Exported `C_livery`:

```text
Shape 2104 @ 79:  marker 02
Shape 2110 @ 110: marker 01 02
```

The first Shape is chromatic and explicitly `mask=true` in the FLS project. Its following direct sibling is physically led by `01 02`. Therefore the previously observed trailing-state rule is **not restricted to achromatic predecessors**:

```text
previous direct Shape
+ next direct Shape lead 01 02
=> previous direct Shape is masked
```

The state belongs to the immediately preceding direct Shape, not the `01 02` Shape itself.

The independent mask resolver now applies this bounded rule independent of color. A state crossing a completed Group remains unresolved.

## 2. Back — intended Group-boundary test was not actually created

The saved FLS project contains:

```text
Back
├─ Shape 2105
├─ Shape 2106
└─ Shape 2109
```

All three are direct Shapes. There is no Group node in this section, so this pair provides **no evidence** for a mask state crossing a completed Group boundary.

No production rule is changed for Group-boundary state.

## 3. Top — direct Shape skew

FLS project:

```text
Shape 101
skew = 2.3
```

Exported `C_livery` Shape 101 at offset `287` contains:

```text
skew = 2.299999952316284
```

This is the expected float32 representation of `2.3`. Therefore direct-Shape skew field mapping is corpus-validated for a nonzero value.

This does not yet validate Group skew or arbitrary affine Group composition.

## 4. Left — alpha was changed, not node opacity

The project node is:

```text
Shape 102
opacity = 1
stored color = [255,85,0,164]
```

The exported `C_livery` preserves the final stored color byte `164`. This validates color alpha storage for the Shape, but it does **not** validate FLS node `opacity != 1`.

The semantic adapter therefore continues to fail closed on non-unit node opacity.

## 5. Flat direct-sibling draw order and color-channel calibration

The project section with three overlapping primary-color Shapes is stored internally as slot 4 / `Right`:

```text
children[0] = Shape 101, stored [0,0,255,255]
children[1] = Shape 102, stored [0,255,0,255]
children[2] = Shape 103, stored [255,0,0,255]
```

The corresponding `C_livery` record order is identical:

```text
Shape 101 @ 399
Shape 102 @ 430
Shape 103 @ 462
```

The supplied FLS screenshot shows the overlapping result as:

```text
red square at the back
then green circle
then blue triangle on top
```

The Layers panel simultaneously shows top-to-bottom:

```text
#3 blue triangle
#2 green circle
#1 red square
```

Therefore, for **flat direct siblings in this controlled scene**:

```text
stored child / C_livery record order = paint order, back -> front
index 0 is painted first
later direct siblings paint over earlier siblings
FLS Layers UI displays the same stack topmost-first, i.e. reverse of stored child order
```

This is a bounded draw-order result. It does not justify a global layer reversal and does not yet sign off nested Group/mask renderer ordering.

### Color-channel calibration

The same screenshot establishes actual channel semantics:

```text
stored [0,0,255,255] -> red
stored [0,255,0,255] -> green
stored [255,0,0,255] -> blue
```

Thus FLS v3 project color lists are BGRA storage. The `C_livery` records preserve the same stored tuples, and the pre-existing shared low-level Shape parser's BGRA -> semantic RGBA conversion was correct.

The pair-4 conclusion that the raw bytes were RGBA storage is superseded. The livery-only `ShapeNode` raw-byte override added after pair 4 has been removed, and the FLS semantic adapter now converts stored BGRA to semantic RGBA before comparison.

## 6. New side-label discrepancy requiring a dedicated oracle

The screenshot header displays:

```text
Left (3)
```

for the three red/green/blue Shapes. However the saved `.3so` places those exact three Shape IDs under internal livery section slot `4` named `Right`; internal slot `3` named `Left` contains the single alpha-164 Shape.

This is direct evidence of an **FLS UI-facing Left/Right label versus serialized/internal section-name discrepancy** for this project. It may represent a view-side convention rather than a binary-format error.

No production section remapping is made from this single observation. A dedicated minimal side oracle is required before changing `SECTION_NAMES` or renderer side mapping:

```text
FLS UI Left  -> one unique Shape ID/color
FLS UI Right -> a different unique Shape ID/color
save .3so + export C_livery + screenshot both sides
```

This observation is potentially relevant to side-specific rendering issues, but no causal claim is made yet.

## Regression coverage

`tests/test_clivery_fls_semantic_controlled5.py` provides:

- always-on observed-scene semantics for chromatic mask, skew, alpha, BGRA normalization, and stored direct-sibling order;
- an opt-in complete real-pair differential using:

```text
FH6_FLS_3SO_2017_MASK_SKEW_ORDER
FH6_CLIVERY_2017_MASK_SKEW_ORDER
```

Other focused unit regressions ensure:

- chromatic previous direct Shapes receive the `01 02` trailing mask state;
- completed-Group boundary state remains unresolved;
- the livery-only raw color reinterpretation is absent.

## Evidence status after pair 5

CONFIRMED:

- chromatic direct-sibling `01 02` mask behavior;
- direct Shape nonzero skew;
- Shape color alpha serialization;
- FLS/C_livery BGRA storage -> semantic RGBA conversion;
- flat direct-sibling paint order: earlier stored child first, later child on top.

NOT CONFIRMED:

- mask state crossing a completed Group boundary;
- serialized negative-scale Group frame;
- Group skew;
- FLS node opacity other than 1.0;
- raster/logo layers;
- nested Group/mask final draw-order semantics;
- definitive FLS UI Left/Right to internal slot mapping.

## CI

Windows run `32479905577` at head `7914915f56913ffaae54ba70068a5c74a0d8b796` completed successfully:

```text
independent decoder/oracle: 65 tests, OK (skipped=7)
standalone C_group parser: 14 tests, OK
real livery opt-ins: 2 tests, OK (skipped=2)
full existing FH6 Assistant suite: 246 tests, OK (skipped=9)
```
