# Milestone 4d renderer trace — evidence-driven integration

Status: **IN PROGRESS — TWO BOUNDED RUNTIME CORRECTIONS APPLIED; ORIGINAL CAR-2997 LEFT-SIDE OCCLUSION NOT YET SIGNED OFF**

This note records the first renderer-connection pass after the independent decoder and controlled FLS semantic work. It deliberately separates facts proven by controlled or real corpus evidence from hypotheses about the original visual defect.

No global layer reversal is introduced. `source_offset` remains provenance only. No Left/Right section-name swap is introduced from the FLS UI-side convention.

## Runtime chain traced

The current FH6 Assistant preview path is:

```text
app.py
  -> apply_livery_decoder_recovery_patch()
  -> apply_livery_baseline_behavior_patch()
  -> livery_preview.decode_livery_preview()
  -> pinned KFPS decode_forza_source()
  -> group by source_section
  -> render_typecode_layers_canvas(section layers)
  -> exact vehicle projection for that section
  -> display-only section rotation
```

The pinned KFPS tree flattener walks Group children recursively in structural DFS order. The renderer consumes the resulting layer list in list order: an ordinary later layer paints over an earlier layer, while an encountered mask acts at that point in the sequence.

Controlled FLS pair 5 independently proves the same paint rule for flat direct siblings: stored child order is back-to-front paint order. It does **not** establish that raw byte offset is a general z-order key for nested Group scenes.

## Correction A — preserve decoder structural order

Before this pass, `livery_baseline_behavior_patch.normalize_decoded_layer_order()` sorted every section by ascending `source_offset` whenever offsets were complete and unique.

That policy is not supported for nested Group scenes and conflicts with the independent decoder contract, which preserves structural DFS child order and treats `source_offset` as provenance only.

The wrapper now leaves the decoder's layer order unchanged and records:

```text
fh6assistant_layer_order_policy = decoder_structural_dfs
```

Regression tests explicitly use intentionally non-monotonic source offsets and require the original structural order to survive unchanged.

This is a correctness fix to the runtime contract. It is **not yet evidence that source-offset sorting caused the original Car-2997 Left-side visual occlusion**; no causal claim is made until that exact scene is re-rendered or directly compared at the affected nested region.

## Correction B — chromatic `01 02` mask in verified-flat sections

Controlled FLS pair 5 proves that, for direct Shape siblings, a physical `01 02` lead on the following Shape carries trailing mask state for the immediately preceding direct Shape **independent of predecessor color**.

The pinned legacy flatten path suppresses non-authoritative record masks when the predecessor carries chromatic color data. The local flat-section recovery path now repairs only the bounded case for which structure has already been proven:

```text
verified flat root
+ direct 32-byte Shape children
+ following child lead = 01 02
=> immediately previous direct Shape mask = true
```

After the pinned conversion, the recovered previous layer is normalized to:

```text
mask = true
data[6] = 1
fh6assistant_mask_evidence = verified_flat_0102_previous_direct_shape
```

No nested Group-boundary state is inferred. No section-terminal state is inferred by this recovery path.

For the Car-2997 independent scene, the four currently confirmed mask source offsets are all achromatic Shapes, so this correction is a real general runtime bug fix but **does not by itself explain the known Car-2997 Left-side occlusion**.

## Car 2997 runtime discrepancy still present in prior diagnostics

The prior pinned-runtime differential for `Livery_2997_20260817150058` reports:

```text
legacy patched runtime total: 9085
independent exact scene total: 9086

legacy Left:  2988
exact Left:   2989
legacy Right: 2964
exact Right:  2964
```

The independent decoder has exact 11-section byte coverage, no unknown spans, and declared/parsed leaf equality. Therefore the old renderer input path was missing one Left leaf relative to the independently validated scene.

The same prior differential also contains large semantic/parser divergences around section boundaries and transformed groups. Those historical comparisons are useful diagnostics, but they compare different decoder implementations and are not themselves sufficient to identify the exact occluding polygon.

## High-value nested transform landmarks

The independent Car-2997 Left scene provides corpus-validated nested/reflected landmarks near the late artwork region, including:

```text
source_offset 194176
shape_id 124
parent_path (3, 14, 0)
effective transform approximately:
  x  = 165.8598436178
  y  = -19.3278817261
  sx = 0.2054017781
  sy = 0.2054018211
  rotation = 112.9000778198

source_offset 194336
shape_id 124
parent_path (3, 14, 5)
effective transform approximately:
  x  = 153.2265189475
  y  = -18.2161875276
  sx = -0.0497239419
  sy = 0.1314831851
  rotation = 28.6999435425
```

These are better candidates for renderer-path differential checks than global layer reversal or source-offset sorting because they exercise nested Group composition and reflection directly.

## Left/Right convention

Controlled FLS pair 6 proves an FLS UI-facing side convention:

```text
FLS UI Right <-> serialized/internal Left slot 3
FLS UI Left  <-> serialized/internal Right slot 4
```

The serialized/internal section order remains stable and is retained by the independent decoder. The current FH6 Assistant projection path also maps internal Left/Right by their serialized names. Pair 6 therefore does **not** justify swapping application section names; it only prevents using the FLS UI label as a direct serialized-side oracle.

## Current conclusion

Applied and regression-tested:

1. remove unsupported `source_offset` z-order normalization;
2. preserve decoder structural DFS order into the renderer;
3. repair chromatic direct-sibling `01 02` masks only in structurally verified flat recovery;
4. keep Group-boundary mask state fail-closed;
5. keep serialized Left/Right section mapping unchanged.

Still required before M4d sign-off:

- directly compare the legacy renderer input and independent semantics in the affected Car-2997 nested Left region;
- identify the one missing legacy Left leaf and determine whether it is visually relevant;
- validate nested Group/mask final draw order with a purpose-built oracle if the real-sample comparison remains ambiguous;
- re-render the original problem sample and confirm whether the person-obscuring polygon is gone.
