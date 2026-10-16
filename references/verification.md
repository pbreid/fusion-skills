# Verification - before saying "done"

"Looks right in a screenshot" is not verification. Run the checks that apply and report results.

## Model health (always)
- [ ] `design.computeAll()` then timeline scan: zero errors, zero warnings (warnings mean
      cached, non-associative geometry).
- [ ] Every sketch used by a feature is fully constrained (`isFullyConstrained`).
- [ ] Bodies are solids (`isSolid`), expected count per component, no stray bodies/surfaces.
- [ ] Parametric design type; parameters named, with units and comments; no hard-coded
      duplicates of a parameterised value.
- [ ] Names on components, bodies, sketches, key features; timeline grouped.
`scripts/fusion/inspect_design.py` covers most of this in one read-only call.

## Dimensions
- [ ] Bounding box (mm) matches the spec / source mesh extents.
- [ ] Measure critical features with `measureManager.measureMinimumDistance` / circle
      radii from edge geometry: hole sizes, hole pitch, wall thickness, boss heights.
- [ ] Volume plausible (mesh rebuild: within ~1 % of source unless intentionally changed).

## Mesh rebuilds
- [ ] `export_bodies_stl.py` -> `mesh_compare.py --tol <agreed>`: PASS both directions.
- [ ] Report mean / p95 / max deviation and which nominal snaps were applied.

## Flex test (robustness)
- [ ] Change 2-3 driving parameters (e.g. +20 % width, different hole count/pitch) ->
      recompute -> no errors, geometry follows intent (holes stay inset, symmetry holds).
- [ ] Restore original values; confirm return to the same bbox/volume.

## Assemblies
- [ ] Exactly one grounded component per level (or rigid-group / as-built locks).
- [ ] `design.analyzeInterference`: no unintended overlaps.
- [ ] Joints driven through their range without clashes.
- [ ] Section views through fasteners, seams and cut-outs inspected (screenshot).

## Manufacturability (by process)
- FDM: min wall, overhangs, bed face, hole orientation, insert hole sizes, clearances as parameters.
- Moulding: draft present on pull-direction faces, uniform wall, rib/boss ratios, no undercuts.
- CNC: internal radii >= tool radius, reachable features, standard holes.
- Sheet metal: flat pattern generates, bend reliefs, hole-to-bend distances.

## Visual review
Screenshots: iso, front, top, and one section through the critical feature. For mesh
rebuilds, show reference mesh and rebuild overlaid. Compare silhouettes to any reference image.

## Hand-off
- Ask before saving a new version / Save As; give a meaningful version description.
- Exports only on request: STEP (exchange), 3MF/STL (print, mm), F3D (archive with history).
- Summary: parameters table, components/bodies, checks run with numbers, assumptions, open items.
