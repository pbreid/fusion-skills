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
1. Get the file onto the agent side (path in the workspace) - analysis runs in the agent's
   Python, not inside Fusion.
2. Ask/confirm **units** (STL has none; mm is the usual default) and the **target tolerance**
   (default: 0.1 mm for printed parts, 0.05 mm for machined interfaces). Ask what the part is
   for and which features are functional (bores, mating faces, hole pattern) - those get exact
   nominal values; cosmetic ones may be approximated.
3. Run:
   ```
   python scripts/mesh_analyze.py part.stl --units mm --sections 7 --json part_report.json
   ```
   Read: extents/units warning, watertight/bodies, through-hole count (genus), whether it is
   axis-aligned, dominant planes, cylinders (holes/bosses/fillets with diameters and axes),
   section loops at each level, Z-levels (candidate extrude extents), symmetry.
4. If not axis-aligned: align it (rotate so principal faces lie on origin planes, translate
   so a datum - e.g. base face and symmetry centre - sits at the origin). Record the
   transform; reconstruct in the aligned frame and compare against the aligned mesh.

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
2. `python scripts/mesh_compare.py part.stl rebuild.stl --tol 0.1`
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
