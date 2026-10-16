#!/usr/bin/env python3
"""
mesh_align.py - square a mesh up to the world axes the way a CAD user would model it.

Finds the part's dominant flat-face directions, then applies the SMALLEST rotation that
puts them on the X/Y/Z axes. A part tilted 8 deg gets straightened by 8 deg, but which way
is "up" and "front" (as it appears in the viewport) is kept. It then places it at a
sensible origin and writes an aligned STL plus the transform.

    .venv/bin/python mesh_align.py in.stl out_aligned.stl [--origin center-base|center|min|keep]
                                   [--then-rotate x:90,z:-90] [--json align.json]

--origin  center-base (default): X/Y centred on the origin, lowest Z on the XY plane
          center: bbox centre at origin (best for parts symmetric in all 3 axes)
          min: bbox min corner at origin.  keep: rotate about the bbox centre only
--then-rotate  extra 90-degree turns after squaring, if the user wants a different up/front
--up DIR       after squaring, turn the part so the side currently facing DIR (+x,-x,+y,-y,+z,-z
               in the squared frame) faces +Z. Use when the user says e.g. "the feet are on the
               +Y face" -> --up=-y (use "=" for negative sides).  --front=DIR then sets which side faces -Y (front view).
               ALWAYS rerun mesh_align with these (never hand-roll a transform): align.json must
               stay the single source of truth that square_occurrence.py applies in Fusion.

Use the WORLD-frame export (export_mesh_body_stl.py COORDS="world") as input when the mesh's
placement in Fusion is what the user sees. The JSON "transform_mm" (4x4, row-major,
translation in the last column, mm) maps input coords -> aligned coords. Apply it to the
Fusion occurrence with scripts/fusion/square_occurrence.py to square the reference mesh too.

Prints the correction angle per axis. Corrections under ~0.05 deg are noise; anything
from 0.5 deg to 45 deg is a real placement tilt.
"""
import argparse, itertools, json, math, sys
import numpy as np
import trimesh


def dominant_directions(mesh, ang_tol_deg=3.0):
    """Area-weighted clusters of planar facet normals, sign-folded (n and -n together)."""
    normals, areas = [], []
    for idx, n in zip(mesh.facets, mesh.facets_normal):
        normals.append(n); areas.append(mesh.area_faces[idx].sum())
    in_facet = np.zeros(len(mesh.faces), bool)
    for f in mesh.facets:
        in_facet[f] = True
    for i in np.where(~in_facet)[0]:
        normals.append(mesh.face_normals[i]); areas.append(mesh.area_faces[i])
    normals, areas = np.array(normals), np.array(areas)
    # ignore individually tiny facets: these are tessellation of curved surfaces (hole walls,
    # fillets). Hundreds of identical holes would otherwise add up to fake "flat" directions
    keep = areas >= 1e-4 * mesh.area
    normals, areas = normals[keep], areas[keep]
    order = np.argsort(-areas)
    cos_t = math.cos(math.radians(ang_tol_deg))
    clusters = []   # [sum_vector, area]
    for i in order:
        n, a = normals[i], areas[i]
        for c in clusters:
            ref = c[0] / np.linalg.norm(c[0])
            d = float(n @ ref)
            if abs(d) > cos_t:
                c[0] += np.sign(d) * n * a
                c[1] += a
                break
        else:
            clusters.append([n * a, a])
    clusters.sort(key=lambda c: -c[1])
    total = mesh.area
    return [(c[0] / np.linalg.norm(c[0]), c[1] / total) for c in clusters]


def squaring_rotation(mesh):
    dirs = dominant_directions(mesh)
    planar_frac = sum(f for _, f in dirs[:6])
    d1 = dirs[0][0] if dirs and dirs[0][1] >= 0.02 else None
    d2 = None
    for d, frac in dirs[1:]:
        if d1 is not None and abs(d @ d1) < 0.05 and frac >= 0.02:   # substantial, perpendicular
            d2 = d
            break
    method = "planar faces"
    if d1 is not None and d2 is None:
        # only one substantial flat direction (e.g. a turned part's end faces): square that
        # axis and add no spin about it - take the nearest world axis as the second direction
        k = int(np.argmax(np.abs(d1)))
        cands = [np.eye(3)[j] for j in range(3) if j != k]
        w = max(cands, key=lambda e: 1 - abs(e @ d1))
        d2 = w - (w @ d1) * d1
        method = "single flat direction + minimal spin (turned/rotational part)"
    if d1 is None:
        # mostly curved part: fall back to the oriented bounding box axes
        T, _ = trimesh.bounds.oriented_bounds(mesh)
        R_obb = T[:3, :3]
        d1, d2 = R_obb[0], R_obb[1]
        method = "oriented bounding box (few flat faces - check the result visually)"
    d2 = d2 - (d2 @ d1) * d1
    d2 /= np.linalg.norm(d2)
    d3 = np.cross(d1, d2)
    B = np.vstack([d1, d2, d3])                     # rows: part directions
    # map each part direction to the world axis it is already closest to (minimal rotation)
    best, best_score = None, -1
    for perm in itertools.permutations(range(3)):
        score = sum(abs(B[i, perm[i]]) for i in range(3))
        if score > best_score:
            best, best_score = perm, score
    T = np.zeros((3, 3))
    for i in range(2):
        T[i, best[i]] = np.sign(B[i, best[i]]) or 1.0
    T[2] = np.cross(T[0], T[1])                     # keep it a proper rotation
    R = T.T @ B                                     # R @ d_i = t_i
    tilts = {}
    for i in range(3):
        ang = math.degrees(math.acos(min(1.0, abs(float(B[i] @ T[i])))))
        tilts["XYZ"[best[i]] if i < 2 else "XYZ"[int(np.argmax(np.abs(T[2])))]] = round(ang, 3)
    total_angle = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2))))
    return R, total_angle, tilts, method, planar_frac


def parse_turns(spec):
    R = np.eye(3)
    if not spec:
        return R
    for item in spec.split(","):
        ax, deg = item.strip().lower().split(":")
        M = trimesh.transformations.rotation_matrix(math.radians(float(deg)),
                                                    np.eye(3)["xyz".index(ax)])[:3, :3]
        R = np.round(M, 12) @ R
    return R


def _dir(spec):
    spec = spec.strip().lower()
    sign = -1.0 if spec.startswith("-") else 1.0
    v = np.zeros(3); v["xyz".index(spec.lstrip("+-"))] = sign
    return v


def up_front_rotation(up, front):
    """Proper rotation (det +1) taking the `up` direction to +Z and `front` to -Y."""
    u = _dir(up) if up else np.array([0, 0, 1.0])
    if front:
        f = _dir(front)
    else:   # keep the current front if it is still horizontal, else pick one
        f = np.array([0, -1.0, 0]) if abs(u[1]) < 0.5 else np.array([0, 0, -1.0])
    if abs(u @ f) > 0.5:
        raise SystemExit("--up and --front must be different, perpendicular sides")
    src = np.array([np.cross(-f, u), -f, u])        # rows: what becomes X, Y, Z
    return src                                       # src @ s_i = e_i


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mesh"); ap.add_argument("out")
    ap.add_argument("--origin", default="center-base", choices=["center-base", "center", "min", "keep"])
    ap.add_argument("--then-rotate", default="")
    ap.add_argument("--up", help="side (+x..-z, squared frame) that should face +Z; write --up=-y for negatives")
    ap.add_argument("--front", help="side (squared frame) that should face -Y")
    ap.add_argument("--json")
    a = ap.parse_args()

    mesh = trimesh.load(a.mesh, force="mesh")
    mesh.merge_vertices()
    R, angle, tilts, method, planar_frac = squaring_rotation(mesh)
    # describe the correction as one rotation (axis + angle) - easier to read than per-axis tilts
    if angle > 1e-3:
        ax_vec = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
        n = np.linalg.norm(ax_vec)
        ax_vec = ax_vec / n if n > 1e-9 else np.array([0.0, 0.0, 1.0])
        k = int(np.argmax(np.abs(ax_vec)))
        ax_name = (("+" if ax_vec[k] > 0 else "-") + "XYZ"[k]) if abs(ax_vec[k]) > 0.99 else \
            str(np.round(ax_vec, 3).tolist())
    else:
        ax_vec, ax_name = np.array([0.0, 0.0, 1.0]), "none"
    R = parse_turns(a.then_rotate) @ R
    if a.up or a.front:
        R = up_front_rotation(a.up, a.front) @ R

    c0 = mesh.bounds.mean(0)
    M = np.eye(4); M[:3, :3] = R; M[:3, 3] = -R @ c0 + c0       # rotate about bbox centre
    out = mesh.copy(); out.apply_transform(M)
    lo, hi = out.bounds
    if a.origin == "center":
        shift = -(lo + hi) / 2
    elif a.origin == "center-base":
        shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    elif a.origin == "min":
        shift = -lo
    else:
        shift = np.zeros(3)
    Tm = np.eye(4); Tm[:3, 3] = shift
    M = Tm @ M
    out = mesh.copy(); out.apply_transform(M)
    out.export(a.out)

    # residual check: dominant directions of the result should sit on the axes
    # only judge faces that are MEANT to be square (within 20 deg of an axis); deliberately
    # angled faces (braces, chamfers, drafts) are listed separately, not counted as error
    resid, angled = 0.0, []
    for d, f in dominant_directions(out)[:12]:
        if f < 0.02:          # same threshold used to pick alignment directions
            continue
        dev = math.degrees(math.acos(min(1.0, float(np.max(np.abs(d))))))
        if dev <= 20:
            resid = max(resid, dev)
        else:
            angled.append({"normal": np.round(d, 3).tolist(), "area_pct": round(100 * f, 2),
                           "deg_from_nearest_axis": round(dev, 1)})
    rep = {
        "input": a.mesh, "output": a.out, "method": method,
        "planar_area_fraction_top6": round(planar_frac, 3),
        "correction_deg_total": round(angle, 3),
        "rotation_axis": ax_name,
        "rotation_axis_vector": np.round(ax_vec, 6).tolist(),
        "axis_tilts_deg": tilts,
        "angled_faces_ignored": angled,
        "residual_after_deg": round(resid, 4),
        "extents_before": np.round(mesh.extents, 3).tolist(),
        "extents_after": np.round(out.extents, 3).tolist(),
        "bbox_after": [np.round(out.bounds[0], 3).tolist(), np.round(out.bounds[1], 3).tolist()],
        "origin_mode": a.origin,
        "up_front": {"up": a.up, "front": a.front, "then_rotate": a.then_rotate},
        "transform_mm": np.round(M, 9).tolist(),
        "note": "transform_mm maps input -> aligned (row-major 4x4, mm). Use with "
                "scripts/fusion/square_occurrence.py to square the reference in Fusion.",
    }
    if a.json:
        json.dump(rep, open(a.json, "w"), indent=1)
    print(f"method: {method}")
    print(f"correction: rotated {rep['correction_deg_total']} deg about {ax_name}")
    print(f"extents before {rep['extents_before']} -> after {rep['extents_after']}")
    print(f"bbox after {rep['bbox_after']}  (origin mode {a.origin})")
    print(f"residual tilt of square-intended faces after alignment: {rep['residual_after_deg']} deg")
    if not (a.up or a.front or a.then_rotate):
        print("orientation: up/front kept from the current placement - CONFIRM with the user which "
              "side is the bottom (feet, base, mounting face) and rerun with --up/--front if needed")
    if angled:
        print(f"   ({len(angled)} deliberately angled face groups ignored, e.g. braces/chamfers: "
              f"{', '.join(str(a_['deg_from_nearest_axis']) + ' deg' for a_ in angled[:4])})")
    if rep["residual_after_deg"] > 0.5:
        print("!! dominant faces still not square - inspect views; part may be genuinely angled "
              "(e.g. drafted or deliberately skewed features). Ask the user.")
    if angle < 0.05:
        print("already square (correction is noise-level)")
    print(f"aligned mesh -> {a.out}" + (f"; report -> {a.json}" if a.json else ""))


if __name__ == "__main__":
    main()
