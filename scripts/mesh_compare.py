#!/usr/bin/env python3
"""
mesh_compare.py - measure how closely a rebuilt model matches the original mesh.

    python mesh_compare.py original.stl rebuilt.stl [--tol 0.1] [--align] [--samples 20000]
                                                    [--heatmap out.ply]

Export the rebuilt body from Fusion as STL in the SAME units (mm) and SAME placement first
(see references/verification.md). Reports two-way surface deviation (mean / p95 / max),
volume and bbox difference, and where the worst deviations are so you know which feature
to fix. --align runs ICP first (use only if the rebuild was intentionally re-positioned).
Exit code 0 = p95 within tol, 1 = outside tol.
"""
import argparse, sys
import numpy as np
import trimesh


def dev(a, b, n):
    pts, _ = trimesh.sample.sample_surface_even(a, n)
    _, d, _ = trimesh.proximity.closest_point(b, pts)
    return pts, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("original"); ap.add_argument("rebuilt")
    ap.add_argument("--tol", type=float, default=0.1)
    ap.add_argument("--samples", type=int, default=20000)
    ap.add_argument("--align", action="store_true")
    ap.add_argument("--heatmap")
    a = ap.parse_args()
    A = trimesh.load(a.original, force="mesh"); B = trimesh.load(a.rebuilt, force="mesh")
    if a.align:
        T, _ = B.register(A, samples=3000)  # maps B -> A
        B.apply_transform(T)
        print("ICP applied; transform:\n", np.round(T, 4))
    ext_ratio = B.extents / np.maximum(A.extents, 1e-9)
    if np.any(np.abs(np.log10(ext_ratio)) > 0.9):
        print(f"!! extents differ by ~x{ext_ratio.round(2)}: unit mismatch (cm vs mm?)")
    pa, dA = dev(A, B, a.samples)   # original -> rebuilt: missing features
    pb, dB = dev(B, A, a.samples)   # rebuilt -> original: extra material
    def s(d): return f"mean {d.mean():.4f}  p95 {np.percentile(d,95):.4f}  max {d.max():.4f}"
    print(f"original->rebuilt (missing geometry): {s(dA)}")
    print(f"rebuilt->original (extra geometry):   {s(dB)}")
    print(f"extents  orig {A.extents.round(3)}  rebuilt {B.extents.round(3)}  diff {(B.extents-A.extents).round(3)}")
    print(f"bbox_min orig {A.bounds[0].round(3)}  rebuilt {B.bounds[0].round(3)}")
    if A.is_watertight and B.is_watertight:
        print(f"volume   orig {A.volume:.3f}  rebuilt {B.volume:.3f}  ({100*(B.volume/A.volume-1):+.2f}%)")
    for name, P, d in (("missing", pa, dA), ("extra", pb, dB)):
        bad = d > a.tol
        if bad.any():
            # cluster bad points coarsely so the agent can target features
            q = np.round(P[bad] / max(0.08 * A.extents.max(), 1e-6)).astype(int)
            keys, inv, cnt = np.unique(q, axis=0, return_inverse=True, return_counts=True)
            order = np.argsort(-cnt)[:6]
            print(f"  worst {name} regions (centroid, n_pts, max dev):")
            for k in order:
                m = inv.ravel() == k
                print(f"    {P[bad][m].mean(0).round(2)}  n={m.sum()}  max={d[bad][m].max():.3f}")
    if a.heatmap:
        _, dv, _ = trimesh.proximity.closest_point(A, B.vertices)
        c = trimesh.visual.interpolate(np.clip(dv / (3 * a.tol), 0, 1), color_map="jet")
        B.visual.vertex_colors = c; B.export(a.heatmap); print("heatmap ->", a.heatmap)
    p95 = max(np.percentile(dA, 95), np.percentile(dB, 95))
    ok = p95 <= a.tol
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'} (p95 {p95:.4f} vs tol {a.tol})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
