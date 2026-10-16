"""
build_template.py - reference pattern for building a parametric part through the API.
Copy it, keep the helpers, replace build(). It shows the conventions the skill requires:

  * parametric design, component-first (Rule #1), everything named
  * user parameters created first; every dimension/extent driven by a parameter expression
  * sketches on ORIGIN planes, anchored to the sketch origin, fully constrained
  * one sketch per feature; holes/patterns as FEATURES (not sketch patterns); fillets last
  * deferred sketch compute while drawing; timeline grouped
  * returns a JSON report (bodies, bbox in mm, unconstrained sketches, timeline errors)

The example builds a 60 x 40 x 6 plate with four corner holes on a rectangular feature
pattern and filleted vertical corners. Internal units are cm; parameters carry units.
Entry point: run(context). REPL-style servers: uncomment run(None) at the bottom.
Run it in a NEW or disposable design, or one whose user agreed to the edit; save first.
"""
import json, traceback
import adsk.core, adsk.fusion

P = adsk.core.Point3D.create
VI = adsk.core.ValueInput


# ---------------------------------------------------------------- helpers
def param(design, name, expr, unit="mm", comment=""):
    """Create or update a user parameter (idempotent, so the script can be re-run)."""
    p = design.userParameters.itemByName(name)
    if p:
        p.expression = expr
    else:
        p = design.userParameters.add(name, VI.createByString(expr), unit, comment)
    return p


def new_component(root, name):
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = name
    return occ.component, occ


def sketch_points(sketch):
    return [sketch.sketchPoints.item(i) for i in range(sketch.sketchPoints.count)]


def pick_point(points, fn):
    """Choose a sketch point by geometry, e.g. lambda g: (g.x, g.y) min/max."""
    return min(points, key=lambda sp: fn(sp.geometry))


def dim_distance(sketch, p1, p2, orient, expr, text_pt):
    d = sketch.sketchDimensions.addDistanceDimension(p1, p2, orient, text_pt)
    d.parameter.expression = expr
    return d


H = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
V = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation


def centered_rectangle(sketch, w_expr, h_expr, w_cm, h_cm):
    """Rectangle symmetric about the sketch origin, fully constrained by 4 dimensions."""
    lines = sketch.sketchCurves.sketchLines.addTwoPointRectangle(P(-w_cm / 2, -h_cm / 2, 0), P(w_cm / 2, h_cm / 2, 0))
    pts = [lines.item(i).startSketchPoint for i in range(lines.count)]
    o = sketch.originPoint
    lo = min(pts, key=lambda s: s.geometry.x + s.geometry.y)       # bottom-left corner
    hi = max(pts, key=lambda s: s.geometry.x + s.geometry.y)       # top-right corner
    dim_distance(sketch, o, lo, H, f"({w_expr})/2", P(-w_cm / 4, -h_cm / 2 - 0.5, 0))
    dim_distance(sketch, o, lo, V, f"({h_expr})/2", P(-w_cm / 2 - 0.5, -h_cm / 4, 0))
    dim_distance(sketch, o, hi, H, f"({w_expr})/2", P(w_cm / 4, h_cm / 2 + 0.5, 0))
    dim_distance(sketch, o, hi, V, f"({h_expr})/2", P(w_cm / 2 + 0.5, h_cm / 4, 0))
    return lines


def extrude(comp, profile, dist_expr, op, name, participants=None):
    fs = comp.features.extrudeFeatures
    inp = fs.createInput(profile, op)
    inp.setDistanceExtent(False, VI.createByString(dist_expr))
    if participants:
        inp.participantBodies = participants
    f = fs.add(inp)
    f.name = name
    return f


def cut_through_all(comp, profiles, body, name):
    fs = comp.features.extrudeFeatures
    inp = fs.createInput(profiles, adsk.fusion.FeatureOperations.CutFeatureOperation)
    inp.setOneSideExtent(adsk.fusion.ThroughAllExtentDefinition.create(),
                         adsk.fusion.ExtentDirections.PositiveExtentDirection)
    inp.participantBodies = [body]
    f = fs.add(inp)
    f.name = name
    return f


def edges_parallel_to(body, axis_vec):
    col = adsk.core.ObjectCollection.create()
    for e in body.edges:
        g = e.geometry
        if g.objectType == adsk.core.Line3D.classType():
            v = g.startPoint.vectorTo(g.endPoint)
            v.normalize()
            planar = all(f.geometry.objectType == adsk.core.Plane.classType() for f in e.faces)
            if abs(v.dotProduct(axis_vec)) > 0.9999 and planar:   # skip seam edges on cylinders
                col.add(e)
    return col


def fillet(comp, edges, r_expr, name):
    fs = comp.features.filletFeatures
    inp = fs.createInput()
    try:   # current API
        inp.edgeSetInputs.addConstantRadiusEdgeSet(edges, VI.createByString(r_expr), True)
    except AttributeError:   # older builds
        inp.addConstantRadiusEdgeSet(edges, VI.createByString(r_expr), True)
    f = fs.add(inp)
    f.name = name
    return f


def report(design, comp):
    out = {"component": comp.name, "bodies": [], "unconstrained_sketches": [], "timeline_problems": []}
    for b in comp.bRepBodies:
        bb = b.boundingBox
        out["bodies"].append({"name": b.name, "solid": b.isSolid,
                              "bbox_mm": [[round(v * 10, 3) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z)],
                                          [round(v * 10, 3) for v in (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)]],
                              "volume_mm3": round(b.volume * 1000, 2)})
    for s in comp.sketches:
        if not s.isFullyConstrained:
            out["unconstrained_sketches"].append(s.name)
    tl = design.timeline
    for i in range(tl.count):
        it = tl.item(i)
        if it.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
            out["timeline_problems"].append({"index": i, "name": it.name, "msg": it.errorOrWarningMessage})
    return out


# ---------------------------------------------------------------- the part
def build(design):
    root = design.rootComponent
    tl_start = design.timeline.count

    # 1. parameters first (names = design intent)
    param(design, "plate_w", "60 mm", comment="overall width (X)")
    param(design, "plate_d", "40 mm", comment="overall depth (Y)")
    param(design, "plate_t", "6 mm", comment="thickness (Z)")
    param(design, "hole_d", "3.4 mm", comment="M3 clearance")
    param(design, "hole_inset", "8 mm", comment="hole centre from edges")
    param(design, "corner_r", "4 mm", comment="vertical corner radius")

    # 2. component first
    comp, occ = new_component(root, "Plate")

    # 3. base sketch on origin plane, symmetric about origin
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = "SK_Plate_Outline"
    sk.isComputeDeferred = True
    centered_rectangle(sk, "plate_w", "plate_d", 6.0, 4.0)
    sk.isComputeDeferred = False
    base = extrude(comp, sk.profiles.item(0), "plate_t",
                   adsk.fusion.FeatureOperations.NewBodyFeatureOperation, "EX_Plate")
    body = base.bodies.item(0)
    body.name = "Plate"

    # 4. ONE seed hole, dimensioned from the origin, then a feature pattern
    hs = comp.sketches.add(comp.xYConstructionPlane)
    hs.name = "SK_Hole_Seed"
    hs.isComputeDeferred = True
    cx, cy = -3.0 + 0.8, -2.0 + 0.8
    circ = hs.sketchCurves.sketchCircles.addByCenterRadius(P(cx, cy, 0), 0.17)
    hs.sketchDimensions.addDiameterDimension(circ, P(cx + 0.5, cy + 0.5, 0)).parameter.expression = "hole_d"
    dim_distance(hs, hs.originPoint, circ.centerSketchPoint, H, "plate_w/2 - hole_inset", P(cx / 2, cy - 0.6, 0))
    dim_distance(hs, hs.originPoint, circ.centerSketchPoint, V, "plate_d/2 - hole_inset", P(cx - 0.6, cy / 2, 0))
    hs.isComputeDeferred = False
    hole = cut_through_all(comp, hs.profiles.item(0), body, "CUT_Hole_Seed")

    pats = comp.features.rectangularPatternFeatures
    ents = adsk.core.ObjectCollection.create(); ents.add(hole)
    pin = pats.createInput(ents, comp.xConstructionAxis, VI.createByReal(2),
                           VI.createByString("plate_w - 2*hole_inset"),
                           adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
    pin.setDirectionTwo(comp.yConstructionAxis, VI.createByReal(2), VI.createByString("plate_d - 2*hole_inset"))
    pat = pats.add(pin)
    pat.name = "PAT_Holes"

    # 5. fillets LAST
    vert = edges_parallel_to(body, adsk.core.Vector3D.create(0, 0, 1))
    if vert.count:
        fillet(comp, vert, "corner_r", "FIL_Corners")

    # 6. group the timeline for this component
    tl = design.timeline
    if tl.count - tl_start > 1:
        g = tl.timelineGroups.add(tl_start, tl.count - 1)
        g.name = "Plate"
    return comp


def main():
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    try:
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        comp = build(design)
        print(json.dumps(report(design, comp), indent=1))
    except Exception:
        print(json.dumps({"error": traceback.format_exc()}))


def run(context):
    main()

# REPL-style servers (no run() call): uncomment the next line.
# run(None)
