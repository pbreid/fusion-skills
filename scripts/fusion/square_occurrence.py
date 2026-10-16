"""
square_occurrence.py - WRITE script: re-place the reference mesh so it sits square to the world
axes, using the transform from mesh_align.py. Only placement changes; the mesh geometry is not
edited. **Ask the user before running.** Undo with fusion_mcp_update {featureType: "undo"}.

How it works (verified failure mode, Oct 2026): Fusion refuses to set transform2 on a nested
occurrence that it hands back in assembly context ("3 : invalid argument value"). So the script
moves the **top-level occurrence** that contains the mesh. Because
world(mesh) = T_top * inner, applying ALIGN to T_top squares the mesh exactly. By default it
refuses if that top-level occurrence contains anything else (other bodies or components),
so unrelated parts are never moved by accident. Set ALLOW_SIBLINGS = True to override.

Settings (use fusion_mcp.py run ... --set NAME=VALUE):
  ALIGN_MM        mesh_align.py JSON "transform_mm" (4x4 row-major, mm), computed from the
                  WORLD-frame export of this mesh
  MESH_NAME       mesh body name, or None for the first mesh body found
  CAPTURE         True to record the position in the timeline (Capture Position)
  ALLOW_SIBLINGS  False (default) = refuse if the top-level occurrence holds other geometry

Verify afterwards: export_mesh_body_stl.py with COORDS="world". Extents and bbox must equal
mesh_align's extents_after / bbox_after.
"""
import json
import adsk.core, adsk.fusion

ALIGN_MM = None
MESH_NAME = None
CAPTURE = True
ALLOW_SIBLINGS = False
MM2CM = 0.1


def cs(m):
    """Matrix3D -> (origin, x, y, z) tuples. getAsCoordinateSystem returns 4 values in Python."""
    o, x, y, z = m.getAsCoordinateSystem()[-4:]
    return [(p.x, p.y, p.z) for p in (o, x, y, z)]


def apply_R(R, v):
    return tuple(sum(R[i][j] * v[j] for j in range(3)) for i in range(3))


def find_mesh_occurrence(design):
    for occ in design.rootComponent.allOccurrences:          # proxies, world context
        for mb in occ.component.meshBodies:
            if MESH_NAME in (None, mb.name):
                return occ, mb
    return None, None


def top_level(occ):
    while occ.assemblyContext is not None:
        occ = occ.assemblyContext
    return occ


def other_content(top, mesh_occ, mesh_body):
    """Names of anything in `top` other than the target mesh body and its owning chain."""
    found = []
    def walk(comp, owner_is_target_chain):
        for b in comp.bRepBodies:
            found.append("body:" + b.name)
        for m in comp.meshBodies:
            if m.name != mesh_body.name:
                found.append("mesh:" + m.name)
        for o in comp.occurrences:
            walk(o.component, True)
    walk(top.component, True)
    return found


def main():
    if ALIGN_MM is None:
        print(json.dumps({"error": "set ALIGN_MM from mesh_align.py transform_mm"})); return
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    occ, mb = find_mesh_occurrence(design)
    if occ is None:
        print(json.dumps({"error": "no mesh body inside an occurrence. If it is in the root "
                          "component there is nothing to move: ask the user to move it into a "
                          "component (or use a Move feature on the mesh body)", "wanted": MESH_NAME}))
        return
    top = top_level(occ)
    others = other_content(top, occ, mb)
    if others and not ALLOW_SIBLINGS:
        print(json.dumps({"error": "the top-level occurrence holding the mesh also contains other "
                          "geometry; moving it would move those too. Ask the user, then rerun "
                          "with --set ALLOW_SIBLINGS=True if acceptable.",
                          "top_level_occurrence": top.fullPathName, "other_content": others[:20]}))
        return

    R = [row[:3] for row in ALIGN_MM[:3]]
    t = [ALIGN_MM[i][3] * MM2CM for i in range(3)]
    o, x, y, z = cs(top.transform2)                          # top-level: transform2 is world
    before = {"origin_mm": [round(v * 10, 4) for v in o], "x": x, "y": y, "z": z}
    no = tuple(a + b for a, b in zip(apply_R(R, o), t))
    nx, ny, nz = apply_R(R, x), apply_R(R, y), apply_R(R, z)
    m = adsk.core.Matrix3D.create()
    P, V = adsk.core.Point3D.create, adsk.core.Vector3D.create
    m.setWithCoordinateSystem(P(*no), V(*nx), V(*ny), V(*nz))
    top.transform2 = m
    captured = None
    if CAPTURE:
        try:
            design.snapshots.add()
            captured = True
        except Exception as e:
            captured = f"not captured: {e}"
    o2, x2, y2, z2 = cs(top.transform2)
    print(json.dumps({
        "moved_occurrence": top.fullPathName,
        "mesh_occurrence": occ.fullPathName,
        "nested": occ.assemblyContext is not None,
        "before": before,
        "after": {"origin_mm": [round(v * 10, 4) for v in o2],
                  "x": [round(v, 6) for v in x2], "y": [round(v, 6) for v in y2],
                  "z": [round(v, 6) for v in z2]},
        "position_captured": captured,
        "next": "verify: export_mesh_body_stl.py COORDS=world; extents/bbox must match align.json",
    }, indent=1))


def run(context):
    main()

# REPL-style servers (no run() call): uncomment the next line.
# run(None)
