"""
inspect_design.py - READ-ONLY snapshot of the active Fusion design, printed as JSON.
Run inside Fusion via the MCP's script-execution tool (read-only mode where offered).

Entry point: run(context) - the official Fusion MCP calls it. For REPL-style servers
(e.g. faust-machines `execute_code`) uncomment the `run(None)` line at the bottom.
Lengths are converted to mm for readability.
"""
import json
import adsk.core, adsk.fusion

CM2MM = 10.0


def bbox_mm(bb):
    return {"min": [round(v * CM2MM, 3) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z)],
            "max": [round(v * CM2MM, 3) for v in (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)]}


def main():
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        print(json.dumps({"error": "active product is not a Fusion design (switch to the Design workspace)"}))
        return
    doc = app.activeDocument
    um = design.unitsManager
    out = {
        "document": doc.name,
        "saved": doc.isSaved, "modified": doc.isModified,
        "version": doc.dataFile.versionNumber if doc.dataFile else None,
        "design_type": "parametric" if design.designType == adsk.fusion.DesignTypes.ParametricDesignType else "direct",
        "default_length_units": um.defaultLengthUnits,
        "user_parameters": [
            {"name": p.name, "expression": p.expression, "unit": p.unit, "comment": p.comment}
            for p in design.userParameters],
        "components": [], "occurrences": [], "timeline_problems": [], "mesh_bodies": [],
    }
    for comp in design.allComponents:
        c = {"name": comp.name, "bodies": [], "sketches": []}  # bbox values are in this component's LOCAL frame
        for b in comp.bRepBodies:
            c["bodies"].append({
                "name": b.name, "solid": b.isSolid, "visible": b.isVisible,
                "faces": b.faces.count, "bbox_mm": bbox_mm(b.boundingBox),
                "volume_mm3": round(b.volume * 1000, 3) if b.isSolid else None})
        for s in comp.sketches:
            c["sketches"].append({"name": s.name, "fully_constrained": s.isFullyConstrained,
                                  "profiles": s.profiles.count,
                                  "plane": s.referencePlane.name if hasattr(s.referencePlane, "name") else None})
        for m in comp.meshBodies:
            out["mesh_bodies"].append({"component": comp.name, "name": m.name,
                                       "triangles": m.mesh.triangleCount if m.mesh else None,
                                       "bbox_mm": bbox_mm(m.boundingBox)})
        out["components"].append(c)
    for occ in design.rootComponent.allOccurrences:
        xf = occ.transform2
        t = xf.translation
        rot = None
        try:
            axes = xf.getAsCoordinateSystem()[-3:]
            vecs = [[round(v.x, 5), round(v.y, 5), round(v.z, 5)] for v in axes]
            rotated = any(abs(vecs[i][j] - (1 if i == j else 0)) > 1e-6 for i in range(3) for j in range(3))
            rot = {"rotated": rotated, "x_axis": vecs[0], "y_axis": vecs[1], "z_axis": vecs[2]}
        except Exception as e:
            rot = {"error": str(e)}
        out["occurrences"].append({"path": occ.fullPathName, "component": occ.component.name,
                                   "grounded": occ.isGrounded,
                                   "is_referenced": occ.isReferencedComponent,
                                   "offset_mm": [round(v * CM2MM, 3) for v in (t.x, t.y, t.z)],
                                   "rotation": rot})
    if out["design_type"] == "parametric":
        tl = design.timeline
        out["timeline_count"] = tl.count
        for i in range(tl.count):
            item = tl.item(i)
            if item.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
                out["timeline_problems"].append({
                    "index": i, "name": item.name,
                    "state": "error" if item.healthState == adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState else "warning",
                    "message": item.errorOrWarningMessage})
    print(json.dumps(out, indent=1))
    return out


def run(context):
    main()

# REPL-style servers (no run() call): uncomment the next line.
# run(None)
