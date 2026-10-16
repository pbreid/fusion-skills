#!/usr/bin/env python3
"""
mesh_views.py - render square orthographic views (front/top/right/iso) of an STL, agent-side.
Use it on the aligned mesh, so the report shows true front, top and side views even
while the Fusion viewport still has the part tilted.

    .venv/bin/pip install matplotlib
    .venv/bin/python mesh_views.py aligned.stl --out views.png [--max-faces 60000]

Feature markers: --mark "X,Y,Z:label" (repeatable) draws a labelled red dot in every view.
Use it whenever you ask the user about specific features ("A = Ø56 dome") so they can see
what you mean. Take coordinates from the analyzer report (cylinder base_point, plane positions).

Convention: front = looking along +Y (sees X horizontal, Z up), top = looking down -Z,
right = looking along -X. Axes are labelled in mm with equal aspect.
"""
import argparse
import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

VIEWS = {  # name: (elev, azim)
    "front (-Y side)": (0, -90),
    "top": (90, -90),
    "right (+X side)": (0, 0),
    "iso": (25, -55),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mesh"); ap.add_argument("--out", default="views.png")
    ap.add_argument("--max-faces", type=int, default=60000)
    ap.add_argument("--mark", action="append", default=[], metavar="X,Y,Z:LABEL",
                    help="label a feature in every view, e.g. --mark '0,-71,150:A Ø56 dome' "
                         "(repeatable). Use when asking the user about specific features.")
    a = ap.parse_args()
    import os
    if os.path.isdir(a.out) or a.out.endswith(("/", os.sep)):
        os.makedirs(a.out, exist_ok=True)
        a.out = os.path.join(a.out, "views.png")
    elif not os.path.splitext(a.out)[1]:
        a.out += ".png"
    m = trimesh.load(a.mesh, force="mesh")
    if len(m.faces) > a.max_faces:
        idx = np.argsort(-m.area_faces)[:a.max_faces]   # keep the largest faces
        m = trimesh.Trimesh(m.vertices, m.faces[idx], process=False)
    marks = []
    for spec in a.mark:
        xyz, _, label = spec.partition(":")
        marks.append(([float(v) for v in xyz.split(",")], label.strip() or "?"))
    tris = m.vertices[m.faces]
    light = np.array([0.4, -0.6, 0.7]); light /= np.linalg.norm(light)
    shade = 0.35 + 0.65 * np.abs(m.face_normals @ light)
    colors = np.c_[np.tile(shade[:, None], (1, 3)) * [0.55, 0.65, 0.8], np.ones(len(shade))]
    lo, hi = m.bounds
    c, r = (lo + hi) / 2, (hi - lo).max() / 2
    fig = plt.figure(figsize=(14, 11))
    for k, (name, (elev, azim)) in enumerate(VIEWS.items()):
        ax = fig.add_subplot(2, 2, k + 1, projection="3d")
        ax.add_collection3d(Poly3DCollection(tris, facecolors=colors, edgecolors="none",
                                             linewidths=0, rasterized=True))
        ax.set_proj_type("ortho")
        ax.view_init(elev=elev, azim=azim)
        for setlim, i in ((ax.set_xlim, 0), (ax.set_ylim, 1), (ax.set_zlim, 2)):
            setlim(c[i] - r, c[i] + r)
        ax.set_box_aspect((1, 1, 1))
        ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")
        depth = {"front (-Y side)": ax.yaxis, "top": ax.zaxis, "right (+X side)": ax.xaxis}.get(name)
        if depth is not None:                       # hide the axis pointing at the viewer
            depth.set_ticklabels([]); depth.label.set_visible(False)
        for mk in marks:
            (x, y, z), label = mk
            ax.scatter([x], [y], [z], color="#d62728", s=40, depthshade=False, zorder=10)
            ax.text(x, y, z, "  " + label, color="#d62728", fontsize=9, fontweight="bold", zorder=11,
                    bbox=dict(facecolor="white", alpha=0.75, edgecolor="none", pad=1))
        ax.set_title(f"{name}   extents {np.round(hi - lo, 1).tolist()} mm", fontsize=9)
    fig.tight_layout()
    fig.savefig(a.out, dpi=110)
    print(a.out)


if __name__ == "__main__":
    main()
