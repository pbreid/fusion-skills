# Mesh (STL/OBJ/3MF) -> parametric Fusion model

Goal: a **new, feature-based model that reproduces the mesh within a stated tolerance**
and carries the part's design intent (parameters, symmetry, patterns) - not a faceted shell.
Scope here: clean, CAD-derived meshes (exported from CAD, downloaded models), mostly
prismatic geometry. Noisy scans/organic shapes: see §7.

## 0. Choose the route

| Situation | Route |
|---|---|
| User wants **editable, parametric** geometry (default) | **A. Rebuild** - analyse mesh, model features from scratch, verify deviation |
| User just needs a solid to boolean/modify quickly, history not important | **B. Convert** - Generate Face Groups -> Convert Mesh (Prismatic), then add features on top |
| Organic surface, sculpted shape | Section-and-loft, or Form/T-spline (Design Extension); tell the user it will be approximate |

Convert Mesh facts (Autodesk docs): methods **Faceted** (one B-rep face per triangle -
heavy, ugly, but works everywhere), **Prismatic** (merges face groups into single planar/
cylindrical faces - for geometry originally made in CAD; *not available on the Personal
licence*), **Organic** (needs Design Extension). Run *Repair*, *Generate Face Groups*
(Fast first, then Accurate on detailed regions; tune angle threshold / min group size),
*Combine Face Groups* first; groups should map to real features. Operation *Parametric*
puts a Convert Mesh feature in the timeline; if Organic fails switch to *Base Feature*.
Watertight -> solid; otherwise surfaces. Complex filleted meshes often fail prismatic.
Converted bodies have **no sketches or parameters** - the dimensions are frozen. That is why
route A is the default when the user says "parametric".

## 1. Intake (always)
1. **Get the mesh onto the agent side** - analysis runs in the agent's Python, not in Fusion.
   - If the user has the original STL file, use it directly (then skip to step 2).
   - If the mesh only exists in the open Fusion design, run
     `scripts/fusion/export_mesh_body_stl.py` twice, once with `COORDS="local"` and once with
     `COORDS="world"`. Both write **mm** and print `extents_mm`. Do not write your own exporter:
     Fusion's mesh coordinates are **cm** and the PolygonMesh API has traps (see fusion-api.md).
   - **Scale gate:** the local export's extents must match the bbox from `inspect_design.py`.
     Check with `mesh_analyze.py --expect-extents X,Y,Z` (exit `SCALE MISMATCH` on ×10, ×25.4
     or ×1000). Never continue on a mismatched scale: every snapped dimension and the
     tolerance itself would be wrong.
2. **Square it up - always.** The finished model must sit square to the world axes at the
   design origin, the way anyone would model it. Its main faces go on the origin planes,
   whatever tilt the source mesh has.
   ```
   .venv/bin/python scripts/mesh_align.py part_world.stl part_aligned.stl --json align.json
   ```
   - Input: the **world** export (what the user sees), or the user's STL file.
   - It finds the dominant flat-face directions and applies the **smallest** rotation that puts
     them on the axes. An 8° placement skew is removed while the visible up and front are
     kept. It reports the correction per axis and the residual (should be ~0°).
   - Default origin: X/Y centred, base on Z=0 (`--origin center-base`). Use `--origin center` when
     the part is symmetric top-to-bottom and that plane should be a datum.
   - If the user wants a different up or front, add `--then-rotate x:90` etc. Ask when it's
     not obvious, and show the views below.
   - A residual > 0.5° means the dominant faces aren't mutually square (drafted or
     deliberately angled part). Report it and ask; don't force it.
   - **Everything downstream uses `part_aligned.stl`:** analysis, views, the build, comparison.
3. **Square views for the report.** The Fusion viewport may still show the skewed mesh, so
   render true orthographic views agent-side:
   `.venv/bin/python scripts/mesh_views.py part_aligned.stl --out views.png` (front/top/right/iso).
   Then analyse the aligned mesh:
   ```
   .venv/bin/python scripts/mesh_analyze.py part_aligned.stl --units mm --sections 7 --json part_report.json
   ```
   (the scale gate already ran on the local export, so `--expect-extents` is optional here;
   extents are the same numbers, possibly in a different axis order).
4. **STOP and ask the user before planning.** This is a hard stop, especially if the user
   invited questions. Send one short message covering:
   - units confirmed (state the measured extents back to them)
   - target **tolerance** (offer the default: 0.1 mm printed, 0.05 mm machined interfaces)
   - which features are **functional** (bores, mating faces, hole patterns, fastener sizes)
     versus cosmetic
   - intended **process/material**
   - the squared orientation: show `views.png`, state the correction applied ("removed an 8.5°
     skew about Z; 204 mm is height (Z)"), and ask if up, front and origin are right
   - whether to also square the **reference mesh** in Fusion (moves its placement only,
     undoable), so the viewport, screenshots and overlay line up. See step 7
   - anything odd the analysis found (rotation off-axis, multiple bodies, open mesh, no
     symmetry where symmetry was expected)
   Include a screenshot and the headline analysis numbers so the user can answer quickly.
   Continue only after they reply. If they're unreachable (unattended run), state the
   defaults you assumed at the top of your report.
5. Read the report (its JSON schema is in the docstring at the top of `mesh_analyze.py`; read that rather than guessing key names). Start with:
   - `body_breakdown`. "Not watertight" plus a few tiny fragments with negligible area
     percentage is tessellation debris: say so, don't treat it as several parts.
   - `cylinder_groups`. Holes are already grouped into patterns (count, Ø, axis, the walls
     they sit on, grid pitch, regular or not, `fills_grid`). Each regular group becomes **one
     seed + one pattern** (plus a mirror for the opposite wall), never individual holes.
     Choose the pattern type with the table in modeling-principles.md §5a. The build plan
     must list each pattern with its parameters (Ø, pitch, counts, seed position, suppressed
     instances).
   - For more detail at specific heights, re-run with `--section-at z=60,z=65,x=-68`
     instead of writing your own trimesh slicing (its API changes between versions).
   Then: extents/units warning, watertight/bodies, through-hole count (genus), whether it is
   axis-aligned, dominant planes, cylinders (holes/bosses/fillets with diameters and axes),
   section loops at each level, Z-levels (candidate extrude extents), symmetry.
6. Build the new component with an **identity** occurrence transform (at the design origin,
   square to the axes). **Never** copy the reference mesh's tilted placement onto the new part.
7. Optional, with the user's OK: square the reference mesh in Fusion with
   `scripts/fusion/square_occurrence.py` (paste `align.json` → `transform_mm` into `ALIGN_MM`).
   It re-places only the mesh's occurrence, composing the alignment with its current placement.
   Then the mesh overlays the new part exactly and Fusion screenshots are square. Verify by
   re-exporting the mesh with `COORDS="world"`: extents and bbox must equal mesh_align's
   `extents_after` / `bbox_after`. If the mesh sits in the root component (no occurrence),
   ask the user. The options are moving it into a component, or a Move feature on the mesh
   body (this adds a timeline item).

## 2. Recover design intent from the numbers
- **Snap to nominal**: measured 3.39-3.42 -> 3.4 (M3 clearance); 5.98 -> 6.0. Mesh
  tessellation slightly under-sizes holes and over-sizes bosses - round to the nearest
  plausible standard (ISO clearance holes M2 2.4, M2.5 2.9, M3 3.4, M4 4.5, M5 5.5;
  tapping drills M3 2.5, M4 3.3; heat-set insert holes per vendor; bearings 608 = 8/22/7).
  Common modelling grids: 0.5 or 1 mm for outlines, 0.1 mm for features.
- **Repeated values** become one parameter (all four holes Ø3.4 -> `hole_d`).
- **Regular spacings** -> pattern feature (equal pitch, circular pattern on a PCD).
- **Symmetry** -> sketch symmetric about origin / mirror feature.
- **Same section across several levels** -> one extrude spanning those levels.
- Partial cylinders tangent to planes are **fillets** (note radius); small 45° bands are chamfers.
- Draft: planes with normals a few degrees off-axis on moulded parts - model as draft
  features, not tilted sketches.
- Write the result as a **build plan table** before touching Fusion:

  | # | Feature | Sketch plane / datum | Parameters | Notes |
  |---|---|---|---|---|
  | 1 | Plate extrude | XY, centred | plate_w=60, plate_d=40, plate_t=6 | symmetric X,Y |
  | 2 | Boss extrude (join) | XY offset plate_t | boss_od=16, boss_h=8 | concentric origin |
  | 3 | Bore cut through all | XY | bore_d=8 | |
  | 4 | Corner hole + 2x2 pattern | XY | hole_d=3.4, inset=8 | |
  | 5 | Fillets | edges | r=... | last |

## 3. Bring the mesh into Fusion as a reference (recommended)
- Insert the mesh (Mesh tab > Insert Mesh, or API `meshBodies.add`) into its own component
  named `REF_Mesh`, same units and placement as analysed. Make it semi-transparent or toggle
  visibility; never model inside that component.
- For outlines that are not simple primitives, use **Create Mesh Section Sketch** (Mesh tab
  > Create) at the needed height, then in that sketch **Fit Curves to Mesh Section** (Sketch >
  Create): fit lines/arcs/circles/splines to the section line; lower spline fit tolerance for
  closer fits. Treat fitted curves as *reference*: re-draw clean geometry with constraints
  and parameters over them, or constrain the fitted curves and dimension them.
- Agent-side alternative: take the outline segments from `part_report.json` sections (already in
  world coordinates of the matching origin plane, e.g. Z sections are XY) and draw them
  directly as constrained lines/arcs.

## 4. Build
Follow modelling-principles.md and the build-plan order. Component first (`<PartName>`),
parameters first, one feature per script call, report after each (bbox in mm should match
the analysed extents as features accumulate). Use `scripts/fusion/build_template.py` helpers.
Typical prismatic recipe:
1. Base extrude from the largest section (often the bottom face outline).
2. Join/cut extrudes level by level using the Z-levels list (`To` extents or distances
   driven by parameters).
3. Holes as Hole features or cut extrudes; patterns as features.
4. Revolves for turned parts (section through the axis -> half profile on XZ/YZ).
5. Fillets/chamfers last, radii from the cylinder report.
Keep the reference mesh visible in screenshots to eyeball alignment (iso + top + front).

## 5. Verify (required before "done")
1. Export the rebuilt body to STL in mm and world coords:
   `scripts/fusion/export_bodies_stl.py` (set BODY_NAMES). Get the file to the agent side.
   **Compare like with like.** The new part sits square at the origin, so compare its export
   with **`part_aligned.stl`** (not the raw mesh). If you squared the reference mesh in Fusion
   (step 7), a fresh `COORDS="world"` export of it is equivalent. A uniform offset or small
   rotation in the result means the placement or origin choice differs, not the shape.
2. `.venv/bin/python scripts/mesh_compare.py part_aligned.stl rebuild.stl --tol 0.1` (the squared reference the analysis used)
   - p95 deviation within tolerance in **both** directions -> PASS.
   - "missing" regions = original geometry you haven't modelled; "extra" = material you added
     that isn't there. Centroids tell you which feature; fix that feature and re-run.
   - Extents ratio ~10x -> cm/mm mix-up. Uniform offset -> datum/placement error.
3. Flex test: change two or three driving parameters, confirm the timeline stays healthy,
   restore values.
4. Report: tolerance achieved (mean/p95/max), what was snapped to nominal and why, any region
   deliberately approximated.

## 6. Fast path (route B) when history doesn't matter
Mesh tab: Insert Mesh -> Repair (if needed) -> Generate Face Groups (Fast, preview, then
Accurate on detail) -> Combine Face Groups where a real face is split -> Convert Mesh
(Parametric operation, Prismatic method) -> Design tab: verify it's a solid (not orange
surface icon), then add new parametric features on top. If Prismatic is unavailable or
fails: Faceted (heavy), or Reduce/Remesh first. Preview API equivalents:
`features.meshGenerateFaceGroupsFeatures` / `features.meshConvertFeatures` (may change).

## 7. Harder inputs
- **Large meshes** (>~200k tris): decimate a copy for viewing in Fusion (Mesh > Reduce), but
  analyse the full-resolution file agent-side.
- **Fillet-heavy consumer parts**: rebuild the prismatic core first, verify, then add fillets
  one radius group at a time, re-verifying.
- **Freeform/organic regions**: several Mesh Section Sketches across the region -> Fit Curves
  (splines with few points) -> Loft with rails; or Form workspace with the mesh as reference.
  Agree a looser tolerance with the user.
- **Scans** (noise, holes): Repair/Remesh first, fit primitives with generous tolerance,
  model functional features to nominal values, accept deviation elsewhere.
- **Multiple bodies** in one STL: `bodies > 1` in the report -> one component per body.
