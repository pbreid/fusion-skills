"""
export_mesh_body_stl.py - write a MESH body (imported STL/OBJ/3MF) to a binary STL in
MILLIMETRES and world coordinates, so the agent can analyse it with mesh_analyze.py.
(For solid/B-rep bodies use export_bodies_stl.py.)

API facts verified against live Fusion (Oct 2026):
  * meshBody.mesh is a PolygonMesh: nodeCoordinates (Point3D list, **cm**),
    nodeCoordinatesAsDouble, triangleNodeIndices, triangleCount, quadNodeIndices, quadCount.
    There is no `.coordinates` or `.nodeIndices` on PolygonMesh.
  * Point3D.transformBy(matrix) transforms IN PLACE and returns a bool.
  * Use the occurrence's transform2 for mesh bodies inside a sub-component.

Set MESH_NAME (None = first mesh body found) and OUT_PATH (on the Fusion machine;
on Windows+WSL, C:\\Users\\Public\\ is reachable from WSL as /mnt/c/Users/Public/).
Prints JSON including the extents in mm - check them against inspect_design's bbox.
COORDS="local" (default) exports in the mesh component's own frame and reports the
occurrence transform separately. If that transform is rotated, build the new component in
this local frame on origin planes, then give its occurrence the same transform.
Entry point run(context); REPL-style servers: uncomment run(None) at the bottom.
"""
import json, math, os, struct, tempfile
import adsk.core, adsk.fusion

MESH_NAME = None
OUT_PATH = os.path.join(tempfile.gettempdir(), "fusion_mesh_ref.stl")
# "local": the mesh component's own frame (default - this is the frame to analyse and
#          build in; it matches inspect_design's bbox and is usually the original CAD frame)
# "world": after the occurrence transform (what you see in the viewport)
COORDS = "local"
CM2MM = 10.0


def describe_transform(m):
    """Translation (mm), axis vectors and a 'rotated' flag for an occurrence Matrix3D."""
    t = m.translation
    out = {"translation_mm": [round(t.x * CM2MM, 4), round(t.y * CM2MM, 4), round(t.z * CM2MM, 4)]}
    try:
        res = m.getAsCoordinateSystem()          # (origin, xAxis, yAxis, zAxis)
        axes = res[-3:]
        out["x_axis"], out["y_axis"], out["z_axis"] = [
            [round(v.x, 6), round(v.y, 6), round(v.z, 6)] for v in axes]
        ident = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        out["rotated"] = any(abs(a - b) > 1e-6 for got, want in
                             zip((out["x_axis"], out["y_axis"], out["z_axis"]), ident)
                             for a, b in zip(got, want))
    except Exception as e:                        # report, don't fail the export
        out["axes_error"] = str(e)
    try:
        out["matrix_row_major"] = [round(v, 6) for v in m.asArray()]
    except Exception:
        pass
    return out


def main():
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent

    # find the mesh body and the occurrence (if any) that places it
    target, xf = None, None
    for mb in root.meshBodies:
        if MESH_NAME in (None, mb.name):
            target = mb
            break
    if target is None:
        for occ in root.allOccurrences:
            for mb in occ.component.meshBodies:
                if MESH_NAME in (None, mb.name):
                    target, xf = mb, occ.transform2
                    break
            if target:
                break
    if target is None:
        print(json.dumps({"error": "no mesh body found", "wanted": MESH_NAME}))
        return

    mesh = target.mesh
    pts = list(mesh.nodeCoordinates)              # Point3D, cm (local to the component)
    if xf is not None and COORDS == "world":
        for p in pts:
            p.transformBy(xf)                     # in place; returns bool
    P = [(p.x * CM2MM, p.y * CM2MM, p.z * CM2MM) for p in pts]

    tris = []
    ti = mesh.triangleNodeIndices
    for i in range(0, len(ti), 3):
        tris.append((ti[i], ti[i + 1], ti[i + 2]))
    qi = mesh.quadNodeIndices if mesh.quadCount else []
    for i in range(0, len(qi), 4):                # split quads (OBJ/3MF) into two triangles
        a, b, c, d = qi[i:i + 4]
        tris += [(a, b, c), (a, c, d)]
    skipped_polys = mesh.polygonCount if hasattr(mesh, "polygonCount") else 0

    lo = [min(p[k] for p in P) for k in range(3)]
    hi = [max(p[k] for p in P) for k in range(3)]
    with open(OUT_PATH, "wb") as f:
        f.write(b"fusion mesh export mm".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            pa, pb, pc = P[a], P[b], P[c]
            u = [pb[k] - pa[k] for k in range(3)]
            v = [pc[k] - pa[k] for k in range(3)]
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            L = math.sqrt(sum(x * x for x in n)) or 1.0
            f.write(struct.pack("<12fH", n[0] / L, n[1] / L, n[2] / L, *pa, *pb, *pc, 0))

    print(json.dumps({
        "path": OUT_PATH, "mesh_body": target.name, "triangles": len(tris), "units": "mm",
        "coords": COORDS,
        "world_transform_applied": xf is not None and COORDS == "world",
        "occurrence_transform": describe_transform(xf) if xf is not None else None,
        "extents_mm": [round(hi[k] - lo[k], 3) for k in range(3)],
        "bbox_min_mm": [round(v, 3) for v in lo],
        "untriangulated_polygons_skipped": skipped_polys,
    }))


def run(context):
    main()

# REPL-style servers (no run() call): uncomment the next line.
# run(None)
