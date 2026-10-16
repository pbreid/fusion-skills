#!/usr/bin/env python3
"""
mesh_analyze.py - offline analysis of a (clean, CAD-derived) STL/OBJ/3MF to plan a
parametric Fusion rebuild. Runs in the AGENT's Python, not inside Fusion
(Fusion's embedded Python has no numpy/trimesh).

    python3 -m venv .venv && .venv/bin/pip install trimesh numpy scipy shapely rtree networkx
    .venv/bin/python mesh_analyze.py part.stl [--units mm] [--json out.json] [--sections 5]
        [--axis auto|x|y|z] [--tol 0.05] [--expect-extents 156,204,142.5] [--scale 10]

Reports:
  * units sanity, bbox, volume, watertightness, genus (through-hole count hint)
  * principal axes & whether the part is already axis-aligned
  * dominant planar faces (normal, offset, area) -> candidate sketch planes / extents
  * cylindrical regions (axis, radius, length, hole vs boss) -> holes, bosses, fillets
  * cross-section outlines at several heights along the build axis -> sketch profiles,
    with straight runs and arcs detected and dimensions snapped to nice values
  * symmetry planes
All lengths are reported in the mesh's units (default mm). Fusion API uses cm.

--json report schema (read this instead of guessing keys):
  file, units, triangles, bbox_min[3], bbox_max[3], extents[3], watertight, winding_consistent,
  bodies, volume, genus_through_holes_hint, area, units_warning, axis_aligned_to_world,
  oriented_bbox_extents[3], alignment_advice?, section_axis ("X"|"Y"|"Z"), levels_along_axis[],
  planes[]:    {normal[3], offset, area, area_pct, axis_aligned ("+Z"... or null), world_position ("Z=6.0")}
  cylinders[]: {kind (hole|boss|fillet/partial-concave|fillet/partial-convex), radius, diameter,
                axis[3], axis_aligned ("X"|"Y"|"Z"|null), base_point[3], length, sweep_deg, faces}
  sections[]:  {at (position along section_axis), area, plane_2d_axes ("XY"...), same_as_previous,
                loops[]: {loop (outer|inner), type (circle|rectangle|polyline), center[2]|null,
                          diameter|null, bounds[4] (minu,minv,maxu,maxv), size[2], n_segments,
                          segments[]|null: {from[2], to[2], len}}}   (segments capped at 40/loop)
  symmetry:    {X|Y|Z: {mid, symmetric, p95_dev, threshold}}   (deterministic sampling; overall
               shape only - small asymmetric features such as one-sided holes can still pass)
  body_breakdown: {count, significant, fragments, fragment_area_pct, list[]: {triangles, area_pct,
                   watertight, volume, bbox_min, bbox_max}}
  cylinder_groups[]: {kind (hole|boss|fillet), diameter, axis, count, lengths[],
                   stations_along_axis[], <X|Y|Z>_values: {n, min, max, pitch, regular,
                   gaps[[after_value, n_missing]], values[],
                   design_hint: {blocks[{start,n,span}], block_pitch[], suggest}}, centres[[x,y,z]],
                   grid_cells_per_station, fills_grid}    <- use this for hole patterns
               (regular=true with gaps = a pitch grid with missing rows/columns, e.g. two blocks)
  sections_at[]: same shape as sections[] plus axis, from --section-at
"""
import argparse, json, math, sys
from collections import defaultdict

import numpy as np
import trimesh

NICE = [0.05, 0.1, 0.2, 0.25, 0.5, 1.0]


def snap(v, step):
    return round(round(v / step) * step, 6) if step else v


def nice_snap(v, tol):
    """Snap to the coarsest 'nice' increment that stays within tol."""
    for step in reversed(NICE):
        s = round(v / step) * step
        if abs(s - v) <= tol:
            return round(s, 4)
    return round(v, 4)


def planar_groups(mesh, ang_tol=1.0, off_tol=0.02, min_frac=0.002, skip=frozenset()):
    """Group coplanar facets (ignoring faces claimed by curved regions). Sorted by area."""
    groups = []
    total = mesh.area
    for idx, normal, origin in zip(mesh.facets, mesh.facets_normal, mesh.facets_origin):
        if skip and skip.intersection(idx.tolist()):
            continue
        area = mesh.area_faces[idx].sum()
        groups.append((normal, float(np.dot(normal, origin)), area))
    # also single triangles that are not part of a facet (large flat tris)
    in_facet = np.zeros(len(mesh.faces), bool)
    for f in mesh.facets:
        in_facet[f] = True
    for i in np.where(~in_facet)[0]:
        if i in skip:
            continue
        if mesh.area_faces[i] / total > min_frac:
            n = mesh.face_normals[i]
            groups.append((n, float(np.dot(n, mesh.triangles_center[i])), mesh.area_faces[i]))
    merged = []
    cos_tol = math.cos(math.radians(ang_tol))
    for n, d, a in groups:
        for m in merged:
            if np.dot(m["n"], n) > cos_tol and abs(m["d"] - d) < off_tol:
                m["area"] += a
                break
        else:
            merged.append({"n": n, "d": d, "area": a})
    merged = [m for m in merged if m["area"] / total > min_frac]
    merged.sort(key=lambda m: -m["area"])
    out = []
    for m in merged:
        n = m["n"]
        ax = int(np.argmax(np.abs(n)))
        aligned = abs(n[ax]) > 0.9998
        out.append({
            "normal": [round(float(x), 4) for x in n],
            "offset": round(m["d"], 4),
            "area": round(float(m["area"]), 3),
            "area_pct": round(100 * m["area"] / total, 2),
            "axis_aligned": ("+" if n[ax] > 0 else "-") + "XYZ"[ax] if aligned else None,
            "world_position": f"{'XYZ'[ax]}={round(m['d'] * np.sign(n[ax]), 4)}" if aligned else None,
        })
    return out


def cylinder_regions(mesh, min_faces=8, rad_tol=0.03):
    """Find curved regions whose normals are all perpendicular to one axis and fit a circle.
    Works for holes, bosses, fillets (partial cylinders)."""
    adj = mesh.face_adjacency
    ang = mesh.face_adjacency_angles
    # candidate faces: not part of a big planar facet (>2 tris). Curved surfaces tessellate
    # into strips of 1-2 triangle facets.
    planar = np.zeros(len(mesh.faces), bool)
    for f in mesh.facets:
        if len(f) > 2:
            planar[f] = True
    ok = ~planar[adj[:, 0]] & ~planar[adj[:, 1]] & (ang < np.radians(40))
    import networkx as nx
    g = nx.Graph()
    g.add_edges_from(adj[ok])
    results = []
    for comp in nx.connected_components(g):
        comp = np.fromiter(comp, int)
        if len(comp) < min_faces:
            continue
        normals = mesh.face_normals[comp]
        # axis = direction most perpendicular to all normals (smallest singular vector)
        _, s, vt = np.linalg.svd(normals - 0 * normals.mean(0))
        axis = vt[-1]
        if s[-1] / max(s[0], 1e-9) > 0.15:   # normals not coplanar -> not a cylinder (sphere/freeform)
            continue
        if s[1] / max(s[0], 1e-9) < 0.05:    # all normals parallel -> it's a plane, not a cylinder
            continue
        pts = mesh.triangles_center[comp]
        # project onto plane perpendicular to axis
        u = np.cross(axis, [1, 0, 0] if abs(axis[0]) < 0.9 else [0, 1, 0]); u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        P = np.c_[pts @ u, pts @ v]
        # algebraic circle fit
        A = np.c_[2 * P, np.ones(len(P))]
        b = (P ** 2).sum(1)
        c, *_ = np.linalg.lstsq(A, b, rcond=None)
        cx, cy = c[0], c[1]
        r = math.sqrt(max(c[2] + cx ** 2 + cy ** 2, 0))
        # vertices give better radius than triangle centres
        verts = mesh.vertices[np.unique(mesh.faces[comp])]
        Pv = np.c_[verts @ u, verts @ v]
        rv = np.linalg.norm(Pv - [cx, cy], axis=1)
        r = float(np.median(rv))
        if r <= 0 or rv.std() / r > rad_tol:
            continue
        # normalise axis direction first so base_point is always the min end along +axis
        ax_i = int(np.argmax(np.abs(axis)))
        if axis[ax_i] < 0:
            axis = -axis
        center3 = cx * u + cy * v
        h = verts @ axis
        center3 = center3 - axis * (center3 @ axis) + axis * h.min()
        # hole vs boss: normals point toward axis for a hole
        radial = (pts - (center3 + np.outer((pts - center3) @ axis, axis)))
        inward = np.mean(np.sum(radial * normals, 1) < 0)
        # angular coverage
        th = np.sort(np.degrees(np.arctan2(Pv[:, 1] - cy, Pv[:, 0] - cx)))
        th = np.unique(np.round(th, 2))
        gaps = np.diff(np.r_[th, th[0] + 360]) if len(th) > 1 else np.array([360.0])
        max_gap = float(gaps.max())
        # a full circle tessellated with n segments has max gap ~360/n; allow up to 60 deg
        sweep = int(round(360 - max_gap)) if max_gap > 60 else 360
        ax = ax_i
        results.append({
            "kind": ("hole" if inward > 0.5 else "boss") if sweep >= 340 else
                    ("fillet/partial-concave" if inward > 0.5 else "fillet/partial-convex"),
            "radius": round(r, 4),
            "diameter": round(2 * r, 4),
            "axis": [round(float(x), 4) for x in axis],
            "axis_aligned": "XYZ"[ax] if abs(axis[ax]) > 0.9998 else None,
            "base_point": [round(float(x), 4) for x in center3],
            "length": round(float(h.max() - h.min()), 4),
            "sweep_deg": sweep,
            "faces": int(len(comp)),
            "_face_ids": comp.tolist(),
        })
    results.sort(key=lambda d: (d["kind"], -d["radius"]))
    return results


def _pitch(vals):
    """Unique positions, base pitch, and whether they sit on that pitch (allowing gaps).
    Returns (values, pitch, regular, gaps) where gaps lists [after_value, missing_count]."""
    u = np.unique(np.round(vals, 1))
    if len(u) < 2:
        return u.tolist(), None, True, []
    d = np.diff(u)
    base = float(np.min(d))
    near = d[np.abs(d - base) < max(0.08 * base, 0.15)]
    pitch = float(np.mean(near)) if len(near) else base
    k = d / pitch
    on_grid = bool(np.all(np.abs(k - np.round(k)) < 0.08))
    gaps = [[float(u[i]), int(round(k[i])) - 1] for i in range(len(d)) if round(k[i]) > 1]
    return u.tolist(), round(pitch, 3), on_grid, gaps


def _design_hint(vals, pitch, gaps):
    """Designers usually specify round numbers. If the pitch is odd but the span of each block
    is round, the pattern was defined as 'n instances over a span' (Fusion Extent type)."""
    if pitch is None or len(vals) < 3:
        return None
    # split into blocks at gaps
    blocks, start = [], 0
    for i in range(1, len(vals)):
        if vals[i] - vals[i - 1] > 1.5 * pitch:
            blocks.append(vals[start:i]); start = i
    blocks.append(vals[start:])
    info = [{"start": round(b[0], 3), "n": len(b), "span": round(b[-1] - b[0], 3)} for b in blocks]
    def roundish(x, step=0.5, tol=0.03):
        return abs(x - round(x / step) * step) < tol
    hint = {"blocks": info}
    pitch_round = roundish(pitch, 0.1, 0.008)          # CAD-derived meshes are precise
    if not pitch_round and all(roundish(b["span"]) for b in info if b["n"] > 1):
        hint["suggest"] = ("extent: " + " + ".join(f"{b['n']} over {round(b['span'] * 2) / 2:g}" for b in info)
                           + " (pitch is a derived value - use Extent distance type)")
    elif pitch_round:
        hint["suggest"] = f"spacing: pitch {round(pitch * 10) / 10:g}"
    if len(info) > 1:
        bp = [round(info[i + 1]["start"] - info[i]["start"], 3) for i in range(len(info) - 1)]
        hint["block_pitch"] = bp
        if len(set(b["n"] for b in info)) == 1 and max(bp) - min(bp) < 0.1:
            extra = (f"{len(info)} identical blocks at {bp[0]:g} -> pattern the block pattern "
                     f"(pattern of a pattern)")
            hint["suggest"] = f"{hint['suggest']}; {extra}" if hint.get("suggest") else extra
    return hint


def cylinder_groups(cyls):
    """Group cylinders by kind, diameter and axis; report count and grid pitch.
    Turns hundreds of hole records into 'Ø5 hole x280, X axis, grid 20x14 @ 7.4 x 6.7'."""
    groups = {}
    for c in cyls:
        kind = c["kind"].split("/")[0]
        key = (kind, round(c["diameter"], 1), c["axis_aligned"] or tuple(np.round(c["axis"], 2)))
        groups.setdefault(key, []).append(c)
    out = []
    for (kind, dia, ax), cs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        P = np.array([c["base_point"] for c in cs])
        g = {"kind": kind, "diameter": dia, "axis": ax if isinstance(ax, str) else list(ax),
             "count": len(cs), "lengths": sorted({round(c["length"], 2) for c in cs})[:6]}
        if isinstance(ax, str):
            ai = "XYZ".index(ax)
            stations = _pitch(P[:, ai])[0]             # walls/levels the holes sit on
            g["stations_along_axis"] = stations[:12]
            for k in (0, 1, 2):
                if k == ai:
                    continue
                vals, pitch, regular, gaps = _pitch(P[:, k])
                g["%s_values" % "XYZ"[k]] = {"n": len(vals), "min": vals[0], "max": vals[-1],
                                            "pitch": pitch, "regular": regular,
                                            "gaps": gaps, "values": vals[:200],
                                            "design_hint": _design_hint(vals, pitch, gaps)}
            g["centres"] = np.round(P, 2).tolist()[:1000]   # base points (min end along axis)
            n_grid = np.prod([g["%s_values" % "XYZ"[k]]["n"] for k in (0, 1, 2) if k != ai])
            g["grid_cells_per_station"] = int(n_grid)
            g["fills_grid"] = bool(len(cs) == n_grid * max(len(stations), 1))
        out.append(g)
    return out


def body_breakdown(mesh):
    parts = mesh.split(only_watertight=False)
    total = sum(p.area for p in parts) or 1.0
    rows = sorted(({"triangles": int(len(p.faces)), "area_pct": round(100 * p.area / total, 3),
                    "watertight": bool(p.is_watertight),
                    "volume": round(abs(float(p.volume)), 2) if p.is_watertight else None,
                    "bbox_min": np.round(p.bounds[0], 2).tolist(),
                    "bbox_max": np.round(p.bounds[1], 2).tolist()} for p in parts),
                  key=lambda r: -r["area_pct"])
    significant = [r for r in rows if r["area_pct"] >= 0.5]
    return {"count": len(rows), "significant": len(significant),
            "fragments": len(rows) - len(significant),
            "fragment_area_pct": round(sum(r["area_pct"] for r in rows if r["area_pct"] < 0.5), 3),
            "list": rows[:12]}


def describe_section(path2d, tol):
    """Break a 2D section into lines/arcs with snapped dimensions."""
    out = []
    for poly in path2d.polygons_full:
        coords = np.array(poly.exterior.coords)
        loops = [("outer", coords)] + [("inner", np.array(i.coords)) for i in poly.interiors]
        for kind, c in loops:
            ring = c
            # straight-segment extraction via Douglas-Peucker
            from shapely.geometry import LineString
            ls = LineString(ring).simplify(tol)
            pts = np.array(ls.coords)
            segs = []
            for a, b in zip(pts[:-1], pts[1:]):
                L = np.linalg.norm(b - a)
                segs.append({"from": [round(float(x), 3) for x in a], "to": [round(float(x), 3) for x in b],
                             "len": nice_snap(float(L), tol)})
            minx, miny, maxx, maxy = (poly.bounds if kind == "outer" else
                                      (c[:, 0].min(), c[:, 1].min(), c[:, 0].max(), c[:, 1].max()))
            # circle test
            ctr = c[:-1].mean(0)
            rr = np.linalg.norm(c[:-1] - ctr, axis=1)
            is_circle = len(c) > 12 and rr.std() < tol
            out.append({
                "loop": kind,
                "type": "circle" if is_circle else ("rectangle" if len(segs) == 4 else "polyline"),
                "center": [round(float(x), 3) for x in ctr] if is_circle else None,
                "diameter": nice_snap(2 * float(rr.mean()), tol) if is_circle else None,
                "bounds": [round(float(x), 3) for x in (minx, miny, maxx, maxy)],
                "size": [nice_snap(float(maxx - minx), tol), nice_snap(float(maxy - miny), tol)],
                "segments": None if is_circle else segs[:40],
                "n_segments": 0 if is_circle else len(segs),
            })
    return out


def sections(mesh, axis_idx, n, tol, positions=None):
    lo, hi = mesh.bounds[0][axis_idx], mesh.bounds[1][axis_idx]
    span = hi - lo
    normal = np.zeros(3); normal[axis_idx] = 1
    res = []
    prev_sig = None
    ts = positions if positions is not None else np.linspace(lo + 0.02 * span, hi - 0.02 * span, n)
    for t in ts:
        sec = mesh.section(plane_origin=normal * t, plane_normal=normal)
        if sec is None:
            res.append({"at": round(float(t), 3), "area": 0.0, "plane_2d_axes": None,
                        "same_as_previous": False, "loops": [], "note": "no intersection"})
            continue
        # world-aligned 2D frame so loop coordinates read directly as sketch coordinates
        # on the matching origin plane: Z->(X,Y), Y->(X,Z), X->(Y,Z)
        u, v = [(1, 2), (0, 2), (0, 1)][axis_idx]
        M = np.zeros((4, 4)); M[0, u] = 1; M[1, v] = 1; M[2, axis_idx] = 1; M[2, 3] = -t; M[3, 3] = 1
        p2, T = sec.to_2D(to_2D=M)
        desc = describe_section(p2, tol)
        sig = tuple((d["type"], tuple(d["size"])) for d in desc)
        res.append({"at": round(float(t), 3), "area": round(float(p2.area), 3),
                    "plane_2d_axes": "XYZ"[u] + "XYZ"[v],
                    "same_as_previous": sig == prev_sig, "loops": desc})
        prev_sig = sig
    return res


def symmetry(mesh, tol):
    """Test mirror symmetry about the bbox mid-planes."""
    out = {}
    c = mesh.bounds.mean(0)
    rng = np.random.default_rng(0)                    # deterministic: same answer every run
    w = mesh.area_faces / mesh.area_faces.sum()
    idx = rng.choice(len(mesh.faces), size=min(1500, len(mesh.faces)), p=w)
    sample = mesh.triangles_center[idx]
    thresh = max(tol * 2, 0.002 * float(mesh.extents.max()))
    for i, name in enumerate("XYZ"):
        m = sample.copy(); m[:, i] = 2 * c[i] - m[:, i]
        _, d, _ = trimesh.proximity.closest_point(mesh, m)   # unsigned surface distance
        p95 = float(np.percentile(d, 95))
        out[name] = {"mid": round(float(c[i]), 4), "symmetric": bool(p95 < thresh),
                     "p95_dev": round(p95, 4), "threshold": round(thresh, 4)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mesh")
    ap.add_argument("--units", default="mm", help="units the file is authored in (STL has none)")
    ap.add_argument("--json", nargs="?", const="-", help="write full report to this path; "
                    "'--json' alone or '--json -' prints ONLY the JSON to stdout (no text summary)")
    ap.add_argument("--sections", type=int, default=5)
    ap.add_argument("--axis", default="auto", help="section/build axis: auto|x|y|z")
    ap.add_argument("--tol", type=float, default=0.05, help="geometric tolerance in mesh units")
    ap.add_argument("--expect-extents", help="X,Y,Z extents (mm) reported by Fusion (inspect_design "
                    "bbox) - aborts on a scale mismatch, e.g. a cm-valued STL")
    ap.add_argument("--scale", type=float, default=1.0, help="multiply coordinates first (10 = cm->mm)")
    ap.add_argument("--section-at", help="extra sections at exact positions, e.g. z=60,z=65.5,x=-68 "
                    "(use instead of hand-written trimesh slicing)")
    a = ap.parse_args()

    mesh = trimesh.load(a.mesh, force="mesh")
    mesh.merge_vertices()
    if a.scale != 1.0:
        mesh.apply_scale(a.scale)
    if a.expect_extents:
        want = np.sort(np.array([float(v) for v in a.expect_extents.split(",")]))
        got = np.sort(mesh.extents)
        ratio = float(np.median(want / np.maximum(got, 1e-12)))
        if abs(ratio - 1) > 0.02:
            hint = (" -> looks like cm; re-export in mm or pass --scale 10" if abs(ratio - 10) < 0.5 else
                    " -> looks like m; pass --scale 1000" if abs(ratio - 1000) < 20 else
                    " -> looks like inches; pass --scale 25.4" if abs(ratio - 25.4) < 0.5 else "")
            print(f"!! SCALE MISMATCH: mesh extents {np.round(got, 3).tolist()} vs expected "
                  f"{want.tolist()} (ratio {ratio:.3f}){hint}. Aborting - fix units before analysing.")
            sys.exit(2)
    rep = {"file": a.mesh, "units": a.units}
    ext = mesh.extents
    rep["triangles"] = int(len(mesh.faces))
    rep["bbox_min"] = np.round(mesh.bounds[0], 4).tolist()
    rep["bbox_max"] = np.round(mesh.bounds[1], 4).tolist()
    rep["extents"] = np.round(ext, 4).tolist()
    rep["watertight"] = bool(mesh.is_watertight)
    rep["winding_consistent"] = bool(mesh.is_winding_consistent)
    bb = body_breakdown(mesh)
    rep["bodies"] = bb["count"]
    rep["body_breakdown"] = bb
    if mesh.is_watertight:
        rep["volume"] = round(float(mesh.volume), 3)
        rep["genus_through_holes_hint"] = int(round((2 - mesh.euler_number) / 2))
    rep["area"] = round(float(mesh.area), 3)
    mx = float(ext.max())
    rep["units_warning"] = (
        "largest extent < 2 -> file may be in metres or inches; confirm before modelling" if mx < 2 else
        "largest extent > 3000 -> file may be in microns or scaled; confirm" if mx > 3000 else
        None if a.expect_extents else
        "scale not cross-checked: pass --expect-extents from inspect_design (Fusion's mesh API is in cm)")

    # principal axes
    try:
        obb_T, obb_ext = trimesh.bounds.oriented_bounds(mesh)
        R = np.linalg.inv(obb_T)[:3, :3]
        aligned = bool(np.all(np.max(np.abs(R), axis=0) > 0.999))
    except Exception:
        aligned, obb_ext = None, None
    rep["axis_aligned_to_world"] = aligned
    if obb_ext is not None:
        rep["oriented_bbox_extents"] = np.round(obb_ext, 4).tolist()
    if aligned is False:
        rep["alignment_advice"] = ("Part is rotated relative to world axes. Square it first: "
                                   "mesh_align.py in.stl aligned.stl --json align.json")

    rep["cylinders"] = cylinder_regions(mesh)
    claimed = frozenset(i for c in rep["cylinders"] for i in c.pop("_face_ids"))
    rep["planes"] = planar_groups(mesh, off_tol=a.tol, skip=claimed)[:30]
    # alignment judged from dominant features (OBB is ambiguous for round parts)
    big = [p for p in rep["planes"] if p["area_pct"] > 3] + rep["cylinders"]
    if big:
        aligned = all(f["axis_aligned"] for f in big)
        rep["axis_aligned_to_world"] = aligned
        if aligned:
            rep.pop("alignment_advice", None)
        else:
            rep["alignment_advice"] = ("Dominant faces/axes are not on world axes. Square it first: "
                                       "mesh_align.py in.stl aligned.stl --json align.json, then "
                                       "analyse aligned.stl.")
    axis_idx = {"x": 0, "y": 1, "z": 2}.get(a.axis.lower())
    if axis_idx is None:
        # build axis = the axis-aligned direction carrying the most planar area (typical extrude dir)
        score = np.zeros(3)
        for p in rep["planes"]:
            score[int(np.argmax(np.abs(p["normal"])))] += p["area"]
        axis_idx = int(np.argmax(score))
    rep["section_axis"] = "XYZ"[axis_idx]
    rep["sections"] = sections(mesh, axis_idx, a.sections, a.tol)
    rep["cylinder_groups"] = cylinder_groups(rep["cylinders"])
    if a.section_at:
        extra = []
        for item in a.section_at.split(","):
            ax, val = item.strip().lower().split("=")
            extra += sections(mesh, "xyz".index(ax), 0, a.tol, positions=[float(val)])
            extra[-1]["axis"] = ax.upper()
        rep["sections_at"] = extra
    try:
        rep["symmetry"] = symmetry(mesh, a.tol)
    except Exception as e:
        rep["symmetry"] = f"skipped: {e}"

    # distinct heights along section axis = candidate extrude extents
    hs = sorted({p["offset"] * np.sign(p["normal"][axis_idx]) for p in rep["planes"]
                 if p["axis_aligned"] and p["axis_aligned"][1] == "XYZ"[axis_idx]})
    rep["levels_along_axis"] = [round(float(h), 4) for h in hs]

    txt = json.dumps(rep, indent=1, default=float)
    if a.json == "-":
        print(txt)
        return
    if a.json:
        open(a.json, "w").write(txt)
    # concise console summary
    print(f"# {a.mesh}  ({rep['triangles']} tris, units assumed {a.units})")
    print(f"extents {rep['extents']}  bbox_min {rep['bbox_min']}  watertight={rep['watertight']}"
          f"  bodies={rep['bodies']}  through-holes≈{rep.get('genus_through_holes_hint')}")
    if bb["fragments"]:
        print(f"   bodies: {bb['significant']} significant + {bb['fragments']} tiny fragments "
              f"({bb['fragment_area_pct']}% of area) - fragments are tessellation debris; "
              f"'not watertight' may come from them alone")
    if rep["units_warning"]:
        print("!!", rep["units_warning"])
    if aligned is False:
        print("!!", rep["alignment_advice"])
    print(f"\n## top planes (facing, position, area%)")
    for p in rep["planes"][:12]:
        where = p["world_position"] or f"d={p['offset']}"
        print(f"  {(p['axis_aligned'] or str(p['normal'])):<6} {where:<14} {p['area_pct']}%")
    print(f"\n## cylinder groups (kind, Ø, axis, count, grid)")
    for g in rep["cylinder_groups"][:15]:
        grid = ""
        if isinstance(g["axis"], str):
            dims = [f"{k[0]}:{v['n']}@{v['pitch']}"
                    + ("" if v["regular"] else "(irregular)")
                    + ("".join(f" gap after {a_} (-{n_})" for a_, n_ in v["gaps"]) if v["gaps"] else "")
                    for k, v in g.items() if k.endswith("_values")]
            grid = f" stations {g['stations_along_axis'][:4]} grid {' '.join(dims)}"
        print(f"  {g['kind']:<7} Ø{g['diameter']:<6} {str(g['axis']):<4} x{g['count']:<4} len {g['lengths'][:3]}{grid}")
        for k, v in g.items():
            if k.endswith("_values") and v.get("design_hint") and v["design_hint"].get("suggest") and g["count"] >= 4:
                print(f"      {k[0]} intent: {v['design_hint']['suggest']}")
    print(f"\n## cylindrical regions (first 25 of {len(rep['cylinders'])}; full list in --json)")
    for c in rep["cylinders"][:25]:
        print(f"  {c['kind']:<22} Ø{c['diameter']:<8} axis {c['axis_aligned'] or c['axis']} "
              f"at {c['base_point']} len {c['length']} sweep {c['sweep_deg']}°")
    print(f"\n## levels along {rep['section_axis']}: {rep['levels_along_axis']}")
    print(f"## sections along {rep['section_axis']}")
    for s in rep["sections"]:
        tag = " (same as previous)" if s["same_as_previous"] else ""
        print(f"  @{s['at']}: area {s['area']}{tag}")
        if not s["same_as_previous"]:
            for l in s["loops"]:
                extra = f"Ø{l['diameter']} at {l['center']}" if l["type"] == "circle" else \
                        f"{l['n_segments']} segs size {l['size']}"
                print(f"     {l['loop']:<5} {l['type']:<9} {extra}")
    for s_ in rep.get("sections_at", []):
        print(f"\n## section {s_['axis']}={s_['at']}: area {s_['area']} {s_.get('note', '')}")
        for l in s_["loops"]:
            extra = f"Ø{l['diameter']} at {l['center']}" if l["type"] == "circle" else \
                    f"{l['n_segments']} segs size {l['size']} bounds {l['bounds']}"
            print(f"     {l['loop']:<5} {l['type']:<9} {extra}")
    if isinstance(rep["symmetry"], dict):
        print("\n## symmetry about bbox mid-planes (p95 dev):",
              {k: f"{v['symmetric']} ({v['p95_dev']})" for k, v in rep["symmetry"].items()})
    if a.json:
        print(f"\nfull report -> {a.json}")


if __name__ == "__main__":
    main()
