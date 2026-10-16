"""
square_occurrence.py - WRITE script: re-place an occurrence (typically the reference mesh's
component) so it sits square to the world axes, using the transform from mesh_align.py.
Only the occurrence placement changes; the mesh geometry is not edited.
**Ask the user before running.** Undo with fusion_mcp_update {featureType: "undo"}, or set
the occurrence's transform back to the printed "before" values.

How to fill it in:
  ALIGN_MM   = mesh_align.py's JSON "transform_mm" (4x4, row-major, mm). It maps the WORLD-frame
               export of this mesh to the squared frame. Use the world export as mesh_align's input.
  OCC_PATH   = occurrence fullPathName (from inspect_design.py "occurrences"), or None to pick
               the first occurrence whose component holds a mesh body.
  CAPTURE    = True to record the new position in the timeline (Capture Position snapshot).

The script composes new = ALIGN * current, building matrices from coordinate systems so it
does not depend on Matrix3D array ordering. It prints the before and after transforms.
Verify afterwards: re-export with export_mesh_body_stl.py COORDS="world". Its extents and
bbox should match mesh_align's "extents_after" and "bbox_after".
"""
import json
import adsk.core, adsk.fusion

ALIGN_MM = None          # e.g. [[r00,r01,r02,tx],[r10,r11,r12,ty],[r20,r21,r22,tz],[0,0,0,1]]
OCC_PATH = None
CAPTURE = True
MM2CM = 0.1


def cs(m):
    """Matrix3D -> (origin, x, y, z) as plain tuples."""
    o, x, y, z = m.getAsCoordinateSystem()[-4:]
    return [(p.x, p.y, p.z) for p in (o, x, y, z)]


def apply_R(R, v):
    return tuple(sum(R[i][j] * v[j] for j in range(3)) for i in range(3))


def main():
    if ALIGN_MM is None:
        print(json.dumps({"error": "set ALIGN_MM from mesh_align.py transform_mm"})); return
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    occ = None
    for o in design.rootComponent.allOccurrences:
        if (OCC_PATH and o.fullPathName == OCC_PATH) or (not OCC_PATH and o.component.meshBodies.count):
            occ = o; break
    if occ is None:
        print(json.dumps({"error": "occurrence not found. If the mesh lives in the root component "
                          "there is no occurrence to move: ask the user to move it into a component "
                          "(or use a Move feature on the mesh body)", "wanted": OCC_PATH}))
        return
    R = [row[:3] for row in ALIGN_MM[:3]]
    t = [ALIGN_MM[i][3] * MM2CM for i in range(3)]
    o, x, y, z = cs(occ.transform2)
    before = {"origin_mm": [v * 10 for v in o], "x": x, "y": y, "z": z}
    no = tuple(a + b for a, b in zip(apply_R(R, o), t))
    nx, ny, nz = apply_R(R, x), apply_R(R, y), apply_R(R, z)
    m = adsk.core.Matrix3D.create()
    P, V = adsk.core.Point3D.create, adsk.core.Vector3D.create
    m.setWithCoordinateSystem(P(*no), V(*nx), V(*ny), V(*nz))
    occ.transform2 = m
    captured = None
    if CAPTURE:
        try:
            design.snapshots.add()
            captured = True
        except Exception as e:
            captured = f"not captured: {e}"
    o2, x2, y2, z2 = cs(occ.transform2)
    print(json.dumps({
        "occurrence": occ.fullPathName,
        "before": before,
        "after": {"origin_mm": [round(v * 10, 4) for v in o2],
                  "x": [round(v, 6) for v in x2], "y": [round(v, 6) for v in y2],
                  "z": [round(v, 6) for v in z2]},
        "position_captured": captured,
    }, indent=1))


def run(context):
    main()

# REPL-style servers (no run() call): uncomment the next line.
# run(None)
