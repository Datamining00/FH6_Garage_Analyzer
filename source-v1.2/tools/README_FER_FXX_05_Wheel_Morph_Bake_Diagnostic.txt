FER_FXX_05 four-way wheel morph bake diagnostic
================================================

Purpose
-------
Generate four read-only comparison GLBs from the same FH6 vehicle ZIP:

1. baseline  - no weighted wheel morph
2. diameter  - selector 0 only
3. width     - selector 1 only
4. combined  - selector 0 + selector 1

The source ZIP is opened read-only and SHA-256 is checked before and after conversion.
Outputs are written under:

%LOCALAPPDATA%\FH6 Assistant\Diagnostics\<vehicle>_wheel_morph_bake_<timestamp>

After each conversion, the existing structure-only neutral wheel visibility pass is
applied. WheelStyle motion/blur primitives identified by the previously verified
MeshBlob signature are marked hidden before AABB measurement. The comparison report
therefore measures visible/static WheelStyle geometry rather than motion geometry.

FER_FXX_05 candidate stock inputs
---------------------------------
Front: 245 mm, 19 in
Rear:  345 mm, 19 in

These values are currently treated as a diagnostic candidate derived from the public
ForzaLiveryStudio wheel_sizes.json game-DB extraction. They have not yet been
independently cross-verified against the user's local FH6 RealDB.

The converter computes the published ForzaTech rim weights directly:

diameter = (wheel_diameter_in - 10) / 14
width    = (1 - tire_width_mm / 1000) / 0.9
scale_x  = 1

No tire morph, arbitrary X-axis shrink, per-vehicle geometry correction, or source
archive modification is performed.

Verified FXX morph evidence
---------------------------
The latest FER_FXX_05 W3 report resolves the actual signed base-vertex addressing:

Front weighted wheel mesh example:
  minIndex = 2749
  IndexedVertexOffset = -2749
  resolved morph vertex start = 0

Rear weighted wheel mesh example:
  minIndex = 3212
  IndexedVertexOffset = -3212
  resolved morph vertex start = 0

The actual FH6 morph selector profiles also show:

selector 0: X delta = 0; Y/Z radial deltas present
selector 1: X axial delta present; Y/Z deltas = 0

Together with the published ForzaTech rim tuple order, this strongly corroborates
selector 0 as wheel-diameter/radial morph and selector 1 as wheel-width/axial morph.

Usage
-----
1. Keep the distributed package intact. It contains:
   - Kfps.ChassisConverter.exe
   - run_wheel_morph_bake_diagnostic.py
   - Run_FER_FXX_05_Wheel_Morph_Bake_Diagnostic.cmd
   - fh6garage/preview3d/wheel_visibility.py and its structural parser dependency
2. Double-click Run_FER_FXX_05_Wheel_Morph_Bake_Diagnostic.cmd.
3. Select FER_FXX_05.zip when prompted.
4. Wait for the four conversions to finish.
5. Return these files for analysis:
   - wheel_morph_four_way_report.json
   - *_wheel_combined.glb
   - optionally the baseline/diameter/width GLBs for visual comparison

The JSON report records per-visible-WheelStyle-instance AABB spans and center shifts
for all four modes, the neutral visibility result, converter morph counters, and source
SHA-256 verification.
