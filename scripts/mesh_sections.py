#!/usr/bin/env python3
"""
mesh_sections.py - labelled cross-section sheet of an STL, plus a text table of every region.
Use it to read the INSIDE of a part (rails, shelves, pockets, wall thicknesses, clear openings)
instead of writing ad-hoc section/voxel scripts.

    .venv/bin/python mesh_sections.py part_aligned.stl --cut z=6 --cut z=70 --cut y=100 \
        --cut x=60 --out sections.png [--json sections.json] [--min-size 3]

  --cut AXIS=VALUE   repeatable; world coordinates in mm (the plane AXIS=VALUE).
                     z=... is a plan view (X across, Y up the page); y=... shows X across,
                     Z up; x=... shows Y across, Z up.
  --clear AXIS=VALUE also print the clear (empty) intervals along a line in each cut, e.g.
                     --clear x=0 on a y=100 cut lists the open Z ranges along X=0. Repeatable.
  --min-size         ignore regions smaller than this in both directions (vent-hole slivers)

Output per cut: material regions (bounds, size, area) and the openings inside them
(holes / cavities with bounds), so "inner width at h=70" is read off directly.
Coordinates are world mm, same frame as the input STL. Grey = material.
"""
import argparse, json
import numpy as np
import trimesh
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

AX = "xyz"
INPLANE = {"z": (0, 1), "y": (0, 2), "x": (1, 2)}   # (horizontal, vertical) world axes per cut


def parse(spec):
    ax, _, v = spec.partition("=")
    ax = ax.strip().lower()
    if ax not in AX:
        raise SystemExit(f"bad cut '{spec}': use x=.., y=.. or z=..")
    return ax, float(v)


def section_polys(mesh, ax, val):
    n = np.zeros(3); n[AX.index(ax)] = 1
    o = np.zeros(3); o[AX.index(ax)] = val
    sec = mesh.section(plane_origin=o, plane_normal=n)
    if sec is None:
        return []
    h, v = INPLANE[ax]
    loops = []
    for P in sec.discrete:
        P = np.asarray(P)
        if len(P) < 3:
            continue
        pg = Polygon(P[:, [h, v]]).buffer(0)
        if pg.area > 1e-6:
            loops.append(pg)
    # even-odd nesting -> material regions with holes
    loops.sort(key=lambda p: -p.area)
    depth = [sum(1 for j, q in enumerate(loops) if j != i and q.area > p.area and q.contains(p.representative_point()))
             for i, p in enumerate(loops)]
    mat = None
    for p, d in zip(loops, depth):
        mat = p if mat is None else (mat.union(p) if d % 2 == 0 else mat.difference(p))
    if mat is None:
        return []
    return list(mat.geoms) if hasattr(mat, "geoms") else [mat]


def rnd(b):
    return [round(float(x), 2) for x in b]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mesh")
    ap.add_argument("--cut", action="append", required=True)
    ap.add_argument("--clear", action="append", default=[])
    ap.add_argument("--out", default="sections.png")
    ap.add_argument("--json")
    ap.add_argument("--min-size", type=float, default=3.0)
    a = ap.parse_args()
    mesh = trimesh.load(a.mesh, force="mesh")
    lo, hi = mesh.bounds
    cuts = [parse(c) for c in a.cut]
    clears = [parse(c) for c in a.clear]
    ncol = min(3, len(cuts)); nrow = -(-len(cuts) // ncol)
    fig, axs = plt.subplots(nrow, ncol, figsize=(6.2 * ncol, 5.2 * nrow), squeeze=False)
    report = []
    for k, (ax, val) in enumerate(cuts):
        h, v = INPLANE[ax]
        polys = section_polys(mesh, ax, val)
        regions = []
        for p in polys:
            x0, y0, x1, y1 = p.bounds
            if x1 - x0 < a.min_size and y1 - y0 < a.min_size:
                continue
            holes = []
            for ring in p.interiors:
                hp = Polygon(ring)
                hx0, hy0, hx1, hy1 = hp.bounds
                if hx1 - hx0 < a.min_size and hy1 - hy0 < a.min_size:
                    continue
                holes.append({"bounds": rnd(hp.bounds), "size": rnd((hx1 - hx0, hy1 - hy0))})
            regions.append({"bounds": rnd(p.bounds), "size": rnd((x1 - x0, y1 - y0)),
                            "area": round(p.area, 1), "openings": holes})
        regions.sort(key=lambda r: -r["area"])
        entry = {"cut": f"{ax.upper()}={val}", "axes": f"{AX[h].upper()} across, {AX[v].upper()} up",
                 "regions": regions}
        # clear intervals along requested lines lying in this plane
        allmat = unary_union(polys) if polys else None
        for cax, cval in clears:
            if cax == ax or cax not in (AX[h], AX[v]):
                continue
            if cax == AX[h]:   # vertical line at horizontal = cval
                line, span = LineString([(cval, lo[v] - 1), (cval, hi[v] + 1)]), (lo[v], hi[v])
                coord = 1
            else:
                line, span = LineString([(lo[h] - 1, cval), (hi[h] + 1, cval)]), (lo[h], hi[h])
                coord = 0
            solid = line.intersection(allmat) if allmat is not None else LineString()
            segs = [solid] if solid.geom_type == "LineString" else list(getattr(solid, "geoms", []))
            iv = sorted((min(s.coords[0][coord], s.coords[-1][coord]), max(s.coords[0][coord], s.coords[-1][coord]))
                        for s in segs if not s.is_empty)
            gaps, cur = [], span[0]
            for s0, s1 in iv:
                if s0 - cur > 0.05:
                    gaps.append(rnd((cur, s0)))
                cur = max(cur, s1)
            if span[1] - cur > 0.05:
                gaps.append(rnd((cur, span[1])))
            entry.setdefault("clear", []).append({
                "line": f"{cax.upper()}={cval}", "along": AX[v if coord == 1 else h].upper(),
                "solid": [rnd(s) for s in iv], "clear": gaps,
                "clear_sizes": [round(g[1] - g[0], 2) for g in gaps]})
        report.append(entry)

        g = axs[k // ncol][k % ncol]
        for p in polys:
            xs, ys = p.exterior.xy
            g.fill(xs, ys, facecolor="0.8", edgecolor="0.25", lw=0.5)
            for ring in p.interiors:
                xs, ys = ring.xy
                g.fill(xs, ys, facecolor="white", edgecolor="0.25", lw=0.5)
        for c in entry.get("clear", []):
            for g0, g1 in c["clear"]:
                cv = float(c["line"].split("=")[1])
                if c["along"] == AX[v].upper():
                    g.plot([cv, cv], [g0, g1], color="#1f77b4", lw=2)
                else:
                    g.plot([g0, g1], [cv, cv], color="#1f77b4", lw=2)
        g.set_xlim(lo[h] - 3, hi[h] + 3); g.set_ylim(lo[v] - 3, hi[v] + 3)
        g.set_aspect("equal"); g.grid(alpha=0.3, lw=0.4)
        g.set_xlabel(f"{AX[h].upper()} (mm)"); g.set_ylabel(f"{AX[v].upper()} (mm)")
        g.set_title(f"section {ax.upper()} = {val} mm", fontsize=10)
    for k in range(len(cuts), nrow * ncol):
        axs[k // ncol][k % ncol].axis("off")
    fig.tight_layout(); fig.savefig(a.out, dpi=110)

    for e in report:
        print(f"## {e['cut']}  ({e['axes']})")
        for r in e["regions"][:25]:
            op = "".join(f"\n      opening {o['size'][0]} x {o['size'][1]} at {o['bounds']}" for o in r["openings"][:8])
            print(f"  material {r['size'][0]} x {r['size'][1]}  bounds {r['bounds']}  area {r['area']}{op}")
        if len(e["regions"]) > 25:
            print(f"  ... {len(e['regions']) - 25} more regions (see --json)")
        for c in e.get("clear", []):
            print(f"  clear along {c['along']} on {c['line']}: {c['clear']}  sizes {c['clear_sizes']}")
    print(a.out)
    if a.json:
        json.dump(report, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
