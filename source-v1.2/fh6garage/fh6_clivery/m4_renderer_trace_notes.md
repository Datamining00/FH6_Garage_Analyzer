# Milestone 4d renderer trace — evidence-driven integration

Status: **IN PROGRESS — INDEPENDENT VECTOR SCENE IS NOW BOUND TO THE PREVIEW RENDERER; ORIGINAL CAR-2997 LEFT-SIDE OCCLUSION STILL REQUIRES LOCAL VISUAL SIGN-OFF**

This note records the renderer-connection stage after the independent decoder and controlled FLS semantic work. It deliberately separates proven runtime contracts from hypotheses about the original visual defect.

No global layer reversal is introduced. `source_offset` remains provenance only. No Left/Right section-name swap is introduced from the FLS UI-side convention.

## Runtime chain after the M4d handoff

The current FH6 Assistant preview path is now:

```text
app.py
  -> apply_livery_decoder_recovery_patch()       # retained legacy fallback
  -> apply_livery_independent_render_bridge_patch()
  -> independent decode_clivery_file()
  -> independent flatten_livery_scene()
  -> render_adapter exact-vector validation
  -> existing native render_typecode_layers_canvas()
  -> existing exact vehicle projection
  -> existing display-only section rotation
```

When the independent scene cannot be bound safely, the bridge explicitly falls back to the pinned legacy preview decoder. The fallback is not silent: a stable diagnostic warning is attached.

The existing renderer, native FH6 shape resources, vehicle projection masks, and display transforms are unchanged. The new bridge changes only the source of placement dictionaries when independent semantics are proven.

## Independent renderer bridge acceptance contract

`fh6_clivery/render_adapter.py` accepts a `C_livery` for direct renderer use only when all of the following are true:

1. the complete 11-section scene is present in the canonical serialized section order;
2. every section is structurally complete;
3. every flattened leaf count equals its declared section count;
4. structural traversal indices are continuous in DFS order;
5. every renderer-bound leaf is within the independently validated vector Shape domain.

The bridge preserves the exact structural DFS sequence. It never sorts by `source_offset`.

Renderer dictionaries remain the neutral M4 contract:

```text
type = 0x100000 + type_word
data = [x, y, sx, sy, rotation, skew, mask_bit]
color = semantic RGBA
mask = resolved semantic mask
source_offset = provenance only
source_parent_path = structural ancestry
```

Successful bridge records are tagged:

```text
source_format = fh6-assistant-independent-render-bridge-v1
```

## Raster/logo fail-closed boundary

Independent M4 raster/logo semantics are still an evidence gap. A high-bit Shape/type word is therefore not guessed as a vector resource by the bridge.

```text
type_word & 0x8000 != 0
=> IndependentRenderAdapterError
=> explicit pinned-legacy preview fallback
```

This preserves current raster preview functionality without claiming independent raster semantics that have not yet been black-box validated.

## Correction A — preserve decoder structural order

Before this pass, `livery_baseline_behavior_patch.normalize_decoded_layer_order()` sorted every section by ascending `source_offset` whenever offsets were complete and unique.

That policy is unsupported for nested Group scenes and conflicts with the independent decoder contract. The wrapper now leaves decoder layer order unchanged. Regression tests use deliberately non-monotonic source offsets and require structural order to survive into renderer input.

Controlled FLS pair 5 independently establishes back-to-front paint order for flat direct siblings. It does not establish raw byte offset as a general nested-scene z-order key.

## Correction B — chromatic `01 02` mask in verified-flat legacy fallback

Controlled FLS pair 5 proves that a direct `01 02` Shape lead carries trailing mask state for the immediately preceding direct Shape sibling independent of predecessor color.

The legacy fallback recovery path repairs only the structurally proven flat case:

```text
verified flat root
+ direct 32-byte Shape children
+ following child lead = 01 02
=> immediately previous direct Shape mask = true
```

After legacy conversion the recovered target is normalized to:

```text
mask = true
data[6] = 1
fh6assistant_mask_evidence = verified_flat_0102_previous_direct_shape
```

No completed-Group boundary mask state is inferred.

## Car 2997 renderer-input discrepancy

The retained historical decoder differential for `Livery_2997_20260817150058` reports the old pinned/local runtime output as:

```text
legacy patched runtime total: 9085
legacy Left:  2988
legacy Right: 2964
```

The independent decoder on the same raw sample established exact byte coverage and:

```text
independent exact total: 9086
independent Left:  2989
independent Right: 2964
```

The historical differential itself is KFPS-revision-to-KFPS-revision diagnostic evidence, not an oracle for the independent implementation. The independently validated scene is the source now bound to the renderer when the vector-only acceptance contract succeeds.

This removes the old 9085/9086 parser-input discrepancy from the direct vector preview path by construction. It does **not** prove that the original person-obscuring polygon is fixed until that exact livery is rendered locally with the user's FH6 vehicle assets and visually checked.

### Offset-basis reconciliation and identity of the missing Left leaf

A later direct comparison against the raw `C_livery(2)` bytes resolved an important offset-basis mismatch in the retained historical differential:

```text
historical KFPS differential source_offset = artwork-body relative
independent decoder source_offset          = inflated-payload absolute
Car 2997 body_start                        = 72

independent absolute offset = historical offset + 72
```

After normalizing the two coordinate systems, the legacy first Left record at historical offset `99582` maps to independent absolute offset `99654`, which is the **second** independent Left leaf. The independently validated first Left leaf is therefore the one missing from the 2988-layer legacy Left stream:

```text
independent absolute offset: 99623
body-relative offset:        99551
shape_id/type_word:           101 / 0x0065 (Square)
parent_path:                  (3, 0)
position:                     (-56.0, 5.0)
scale:                        (8.718671798706055, 8.448664665222168)
rotation:                     0.0
color RGBA:                   (255, 244, 50, 255)
mask:                         false
```

This is a very large yellow Square, not a black occluding polygon. The real-sample regression now pins this first Left leaf explicitly so a future parser regression cannot silently drop it again.

The finding narrows the old 9085/9086 discrepancy: the missing leaf is a concrete parser-boundary error, but its visual identity does **not** support treating it as the direct source of the known person-obscuring black polygon. Investigation of any remaining visual defect should therefore focus on nested transform/mask/draw semantics in the independently reconstructed stream, not on this missing leaf.

## High-value Car 2997 nested transform landmarks

The independent Left scene retains corpus-validated nested/reflected landmarks including:

```text
source_offset 194176
shape_id 124
parent_path (3, 14, 0)
x  = 165.8598436178
y  = -19.3278817261
sx = 0.2054017781
sy = 0.2054018211
rotation = 112.9000778198

source_offset 194336
shape_id 124
parent_path (3, 14, 5)
x  = 153.2265189475
y  = -18.2161875276
sx = -0.0497239419
sy = 0.1314831851
rotation = 28.6999435425
```

The bridge forwards these already-flattened independent transforms without legacy tree reconstruction or `source_offset` resorting.

## Left/Right convention

Controlled FLS pair 6 proves the FLS UI-facing convention:

```text
FLS UI Right <-> serialized/internal Left slot 3
FLS UI Left  <-> serialized/internal Right slot 4
```

This remains a UI convention only. The binary section order and FH6 Assistant serialized section names are unchanged.

## Cache boundary

Because the renderer-input decoder changed, M4d bumps all preview cache namespaces used by the current pipeline. PNGs generated by the previous parser path are therefore not reused as evidence for the new bridge.

## Regression state

Code-changing Windows CI run `32487492718` at feature head `897966448d72391d611ffbe6d7e6dab50850689c` passed:

```text
independent decoder/oracle: 72 tests, OK (skipped=8)
standalone C_group parser: 14 tests, OK
real game-livery opt-ins: 2 tests, OK (skipped=2)
full FH6 Assistant suite: 257 tests, OK (skipped=10)
```

New bridge regressions prove:

- structural order survives non-monotonic `source_offset` values;
- incomplete sections fail closed;
- declared/flattened count mismatch fails closed;
- high-bit raster/logo-like records do not enter the vector bridge;
- independent exact vector output is preferred without calling the legacy decoder;
- unsupported semantics invoke the explicit fallback;
- app wiring applies the bridge after legacy recovery and before renderer patches.

## Remaining M4d sign-off

The architecture handoff is implemented and regression-tested. Remaining evidence work is narrower:

- run the original Car-2997 problem sample through this exact feature head with the local FH6 install assets;
- compare the new Left preview to the known defective screenshot and confirm whether the person-obscuring polygon is gone;
- if a mismatch remains, isolate it inside the already independent renderer-layer stream rather than re-opening global order/section mapping guesses;
- add independent raster/logo black-box evidence before removing the legacy raster fallback;
- validate completed-Group mask-boundary and nested Group/mask final draw-order semantics when purpose-built evidence becomes available.
