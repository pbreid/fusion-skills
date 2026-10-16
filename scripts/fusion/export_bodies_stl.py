"""
export_bodies_stl.py - write chosen solid bodies to a binary STL in MILLIMETRES, in
world (assembly) coordinates, so mesh_compare.py can measure them against the source mesh.
Read-only with respect to the design (it only tessellates and writes a file).

Set BODY_NAMES (empty = all visible solids) and OUT_PATH before running. OUT_PATH is on
the machine running Fusion. If the agent is on another machine, set OUT_PATH to a shared
folder, or set PRINT_BASE64 = True and decode the printed payload on the agent side
(fine for parts up to a few tens of thousands of triangles).
"""
import os, struct, tempfile, base64, json
import adsk.core, adsk.fusion

BODY_NAMES = []                    # e.g. ["Bracket"]; [] -> every visible solid body
OUT_PATH = os.path.join(tempfile.gettempdir(), "fusion_rebuild.stl")
PRINT_BASE64 = False
QUALITY = "VeryHigh"               # Low | Normal | High | VeryHigh


def main():
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    q = getattr(adsk.fusion.TriangleMeshQualityOptions, QUALITY + "QualityTriangleMesh")

    # gather bodies in assembly context (proxies carry the occurrence transform)
    bodies = [b for b in root.bRepBodies]
    for occ in root.allOccurrences:
        bodies += [b for b in occ.bRepBodies]
    bodies = [b for b in bodies if b.isSolid and b.isVisible and (not BODY_NAMES or b.name in BODY_NAMES)]
    if not bodies:
        print(json.dumps({"error": "no matching bodies", "wanted": BODY_NAMES})); return

    tris = []
    for b in bodies:
        calc = b.meshManager.createMeshCalculator()
        calc.setQuality(q)
        m = calc.calculate()
        c = m.nodeCoordinatesAsDouble
        idx = m.nodeIndices
        for i in range(0, len(idx), 3):
            tri = []
            for k in idx[i:i + 3]:
                tri.append((c[3 * k] * 10.0, c[3 * k + 1] * 10.0, c[3 * k + 2] * 10.0))  # cm -> mm
            tris.append(tri)

    buf = bytearray(b"fusion export mm".ljust(80, b" "))
    buf += struct.pack("<I", len(tris))
    for a, b_, c_ in tris:
        buf += struct.pack("<3f", 0.0, 0.0, 0.0)  # normals recomputed by readers
        for p in (a, b_, c_):
            buf += struct.pack("<3f", *p)
        buf += b"\x00\x00"
    with open(OUT_PATH, "wb") as f:
        f.write(buf)
    res = {"path": OUT_PATH, "bodies": [b.name for b in bodies], "triangles": len(tris), "units": "mm"}
    if PRINT_BASE64:
        res["stl_base64"] = base64.b64encode(bytes(buf)).decode()
    print(json.dumps(res))


def run(context):
    main()

# REPL-style servers (no run() call): uncomment the next line.
# run(None)
