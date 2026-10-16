# Fusion Python API: patterns and gotchas

When unsure of a signature, call the MCP's API-documentation search tool or open
`https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-A92A4B10-3781-4925-94C6-47DA85A4F65A`
(API reference). Never invent methods - check, then write.

## Essentials
```python
import adsk.core, adsk.fusion
app    = adsk.core.Application.get()
design = adsk.fusion.Design.cast(app.activeProduct)   # None if not in Design workspace
root   = design.rootComponent
design.designType = adsk.fusion.DesignTypes.ParametricDesignType
```
- **Units:** lengths in **cm**, angles in **radians**, areas cm², volumes cm³ (CAM too).
  `ValueInput.createByReal(x)` = cm/rad. `ValueInput.createByString("6 mm")` = parsed
  expression in given/default units and may reference parameters (`"plate_w/2 - 3 mm"`).
  Prefer strings for anything that should stay parametric.
- `design.unitsManager.evaluateExpression("3 in", "mm")` -> cm value; `formatInternalValue` for display.
- `Point3D.create(x, y, z)` in cm. Sketch coordinates are in **sketch space**; use
  `sketch.modelToSketchSpace(pt)` / `sketchToModelSpace` when sketching on non-XY planes or
  faces (XZ-plane sketches have their own axis directions - verify).
- Entry point for scripts: `def run(context):`. Print results (JSON) - that's what the
  agent sees. Wrap in try/except and print `traceback.format_exc()`.

## Parameters
```python
p = design.userParameters.add("wall_t", adsk.core.ValueInput.createByString("2 mm"), "mm", "wall thickness")
p = design.userParameters.itemByName("wall_t"); p.expression = "2.4 mm"
dim.parameter.expression = "wall_t*2"         # bind a sketch dimension or feature parameter
```
Feature parameters (e.g. an extrude's distance) are model parameters; set through their
ValueInput string so they reference user parameters.

## Components / occurrences
```python
occ  = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
comp = occ.component; comp.name = "Lid"
# bodies inside an occurrence in assembly context: occ.bRepBodies (proxies)
body.createForAssemblyContext(occ)            # proxy when you need world coordinates
```
Features must be created in the collection of the component that will own them
(`comp.features...`, `comp.sketches...`).

## Sketches
```python
sk = comp.sketches.add(comp.xYConstructionPlane); sk.name = "SK_Base"
sk.isComputeDeferred = True      # big speed-up while adding many curves; set False after
lines = sk.sketchCurves.sketchLines.addTwoPointRectangle(p0, p1)   # adds H/V constraints
c = sk.sketchCurves.sketchCircles.addByCenterRadius(center, r_cm)
sk.geometricConstraints.addCoincident(pt, sk.originPoint)
sk.geometricConstraints.addSymmetry(e1, e2, symLine)
d = sk.sketchDimensions.addDistanceDimension(p1, p2,
        adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, textPt)
d.parameter.expression = "pcb_w/2"
sk.sketchDimensions.addDiameterDimension(circle, textPt)
sk.project(entity)  /  sk.include(entity)     # creates a reference - use sparingly
sk.isFullyConstrained                          # check before using profiles
prof = sk.profiles.item(i)                     # order not guaranteed: pick by area/centroid
```
Profile selection: iterate `sk.profiles`, use `prof.areaProperties().area` /
`.centroid` or `prof.boundingBox` to choose; never assume index 0 when there are several.

## Features (most used)
```python
F = adsk.fusion.FeatureOperations      # NewBody / Join / Cut / Intersect / NewComponent
ext_in = comp.features.extrudeFeatures.createInput(prof_or_collection, F.NewBodyFeatureOperation)
ext_in.setDistanceExtent(False, VI.createByString("plate_t"))          # False = one side
ext_in.setSymmetricExtent(VI.createByString("w"), True)                 # True = full length
ext_in.setOneSideExtent(adsk.fusion.ThroughAllExtentDefinition.create(),
                        adsk.fusion.ExtentDirections.PositiveExtentDirection)
ext_in.setOneSideExtent(adsk.fusion.ToEntityExtentDefinition.create(face, False), dir)
ext_in.startExtent = adsk.fusion.OffsetStartDefinition.create(VI.createByString("2 mm"))
ext_in.participantBodies = [body]            # limit cuts to intended bodies
ext = comp.features.extrudeFeatures.add(ext_in); ext.name = "EX_Base"; body = ext.bodies.item(0)

rev_in = comp.features.revolveFeatures.createInput(prof, axisLineOrConstructionAxis, F.NewBodyFeatureOperation)
rev_in.setAngleExtent(False, VI.createByString("360 deg"))

hole_in = comp.features.holeFeatures.createSimpleInput(VI.createByString("hole_d"))
# or createCounterboreInput / createCountersinkInput; position with
hole_in.setPositionBySketchPoints(objCollectionOfSketchPoints)   # check direction in docs
hole_in.setDistanceExtent(VI.createByString("10 mm"))  # or setAllExtent(direction)

pat_in = comp.features.rectangularPatternFeatures.createInput(entities, comp.xConstructionAxis,
          VI.createByReal(n1), VI.createByString("pitch_x"),
          adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
pat_in.setDirectionTwo(comp.yConstructionAxis, VI.createByReal(n2), VI.createByString("pitch_y"))
circ_in = comp.features.circularPatternFeatures.createInput(entities, axis); circ_in.quantity = VI.createByReal(6)
mir_in  = comp.features.mirrorFeatures.createInput(entities, comp.yZConstructionPlane)

sh_in = comp.features.shellFeatures.createInput(objCollectionOfFacesToRemove, False)
sh_in.insideThickness = VI.createByString("wall_t")

fil_in = comp.features.filletFeatures.createInput()
fil_in.edgeSetInputs.addConstantRadiusEdgeSet(edges, VI.createByString("r"), True)  # tangent chain
ch_in = comp.features.chamferFeatures.createInput2(); ch_in.chamferEdgeSets.addEqualDistanceChamferEdgeSet(edges, VI.createByString("0.5 mm"), True)

cp_in = comp.constructionPlanes.createInput(); cp_in.setByOffset(comp.xYConstructionPlane, VI.createByString("pcb_z"))
plane = comp.constructionPlanes.add(cp_in)
```
Older code uses `fil_in.addConstantRadiusEdgeSet(...)` and `chamferFeatures.createInput(...)`;
both are deprecated - prefer the forms above, fall back if a build lacks them.

## Selecting topology robustly
Find faces/edges **by geometry, then by role**, never by index:
- planar face with normal +Z and max Z: iterate `body.faces`, `f.geometry.objectType ==
  adsk.core.Plane.classType()`, `f.geometry.normal`, `f.pointOnFace`, `f.area`.
- `edge.geometry` Line3D/Circle3D/Arc3D; `circle.radius`, `circle.center`.
- Feature outputs: `ext.endFaces`, `ext.sideFaces`, `ext.startFaces`, `fillet.faces` - these
  are the most stable handles for follow-on features.
- `entity.entityToken` + `design.findEntityByToken(token)` to re-find entities across calls.

## Timeline / health / performance
```python
tl = design.timeline
for i in range(tl.count): it = tl.item(i); it.healthState; it.errorOrWarningMessage
tl.markerPosition = i                # roll back (remember to roll forward!)
g = tl.timelineGroups.add(i0, i1); g.name = "Lid"
design.computeAll()                  # full recompute = design checker
feature.timelineObject.rollTo(True)  # roll to just before a feature to edit it
```
- `FeatureHealthStates`: Healthy / Warning / Error.
- Batch-creating many features is slow; deferred sketch compute, fewer profiles, feature
  patterns with *Identical* compute help. For heavy generated geometry consider
  `adsk.fusion.TemporaryBRepManager` (fast, history-less) + one Base Feature - only when the
  user accepts non-parametric results for that part.

## Measurement & inspection
```python
mm = app.measureManager
r = mm.measureMinimumDistance(a, b); r.value (cm), r.positionOne, r.positionTwo
mm.measureAngle(a, b).value  (rad)
obb = mm.getOrientedBoundingBox(body, lengthVec, widthVec)
body.boundingBox; body.volume; body.physicalProperties.centerOfMass; body.pointContainment(pt)
ii = design.createInterferenceInput(objCollectionOfOccurrencesOrBodies); res = design.analyzeInterference(ii)
for r in res: r.entityOne, r.entityTwo, r.interferenceBody.volume   # empty = no clashes
```
(measureMinimumDistance does not accept TemporaryBRepManager bodies.)

## Mesh bodies
```python
mb = comp.meshBodies.add(path, adsk.fusion.MeshUnits.MillimeterMeshUnit)  # insert STL/OBJ/3MF
# In a parametric design, mesh insertion may need a BaseFeature edit:
bf = comp.features.baseFeatures.add(); bf.startEdit(); comp.meshBodies.add(path, units, bf); bf.finishEdit()
# Mesh feature API (preview APIs, may change): features.meshGenerateFaceGroupsFeatures,
# features.meshConvertFeatures (MeshConvertMethodTypes Faceted / Prismatic / Organic*)
```
**Reading mesh data - verified against live Fusion (Oct 2026):**
- `meshBody.mesh` is a **`PolygonMesh`**, not a `TriangleMesh`. Its members:
  `nodeCoordinates` (list of **Point3D**, in **cm**), `nodeCoordinatesAsDouble`/`AsFloat`,
  `nodeCount`, `triangleNodeIndices`, `triangleCount`, `quadNodeIndices`, `quadCount`,
  `polygonNodeIndices`, `polygonCount`, `nodeCountPerPolygon`, `normalVectors*`,
  `triangleFaceGroupTempIds`. There is **no** `.coordinates` and **no** `.nodeIndices`.
- `TriangleMesh` (from `body.meshManager.createMeshCalculator().calculate()` on a B-rep
  body) is different: it does have `nodeIndices`.
- Coordinates are in the owning component's space. For a mesh inside a sub-component,
  apply the occurrence's `transform2`.
- `Point3D.transformBy(matrix)` changes the point **in place** and returns a bool, so
  `[p.transformBy(m) for p in pts]` gives a list of bools. `Matrix3D` has no `asMatrix`,
  `transformPoint` or `getItem`. Use `getCell(row, col)` / `asArray()` if you need values.
- `Point3D.create(x, y, z)` takes floats. Passing a Point3D raises an overload TypeError.
- **Always multiply by 10 when writing mm files.** Use `scripts/fusion/export_mesh_body_stl.py`
  rather than writing an exporter by hand. It handles all of the above and prints the
  extents in mm to cross-check.

Verify the `meshBodies.add` signature in the docs for the installed build. Fusion's Python
has no numpy/trimesh, so do heavy mesh maths agent-side.

**When an attribute error appears**, list the members of the actual object before
guessing again: `print([a for a in dir(obj) if not a.startswith("_")])`. One probe call
is cheaper than a string of trial edits.

## Export
```python
em = design.exportManager
em.execute(em.createSTEPExportOptions(path, comp))
em.execute(em.createFusionArchiveExportOptions(path))
o = em.createSTLExportOptions(body, path); o.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh; em.execute(o)
```
STL unit behaviour of `createSTLExportOptions` has varied. For verification use
`scripts/fusion/export_bodies_stl.py` (B-rep bodies) or `scripts/fusion/export_mesh_body_stl.py`
(mesh bodies). Both write mm explicitly.

## Common failure messages
- *"No target body found to cut or intersect"* -> wrong direction/extent or participant bodies.
- *Profile is not closed / no profile* -> see modelling-principles §3.
- *Compute failed* on fillet -> radius too big for adjacent faces; reduce, split edge sets,
  or move fillet later. Shell failures -> fillets smaller than wall, shell before small fillets.
- `RuntimeError: 3 : invalid argument` -> wrong type (collection vs single entity,
  ValueInput vs float) or entity from a different component context.
