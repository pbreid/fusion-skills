# New part from a specification

Inputs vary: a dimensioned drawing, a sketch photo, a datasheet, a verbal description
("an L-bracket to hold a NEMA17 on 2020 extrusion"), or a reference image.

## 1. Requirements capture (short)
Extract, and ask only for what is missing and matters:
- **Function and interfaces**: what it mounts to, what mounts to it, mating datums, fasteners.
- **Critical dimensions** with sources: given by user / vendor datasheet / standard / assumed.
  Look up vendor dimensions (motor flanges, PCB mounting holes, connectors, bearings,
  extrusion slots) rather than guessing; cite them in the summary.
- **Manufacturing process**: FDM/SLA/SLS print, CNC, sheet metal, injection moulding. It
  changes wall thickness, radii, draft, hole sizing and fit clearances
  (see enclosures-assemblies.md §Fits).
- **Material, loads/environment** only if they change geometry.
- **Orientation**: which face sits on the bed / which way is up in use.
Record assumptions explicitly; carry on with sensible defaults rather than blocking on
non-critical details.

## 2. Plan
Produce a build plan table (same format as mesh-to-parametric §2): datum strategy,
parameters (name, value, unit, source), components, feature order, patterns/mirrors.
For a single part, one component. For anything with mating parts, go to
enclosures-assemblies.md and start from a skeleton.

Datum choice heuristics:
- Symmetric part: symmetry planes = origin planes.
- Part bolted to something: mounting face on XY at Z=0, bolt pattern centre at origin.
- Turned part: axis = Z (or Y) through origin; revolve a half-profile.
- Sheet metal: use the Sheet Metal rules (thickness, bend radius, K-factor) and Flange/Bend
  features; flat pattern for fabrication.

## 3. Build
- Parameters first. Sketch the **primary form** on the datum plane, symmetric/anchored,
  fully constrained, extrude/revolve.
- Add secondary features from origin-derived construction planes (offset by parameters)
  rather than sketching on generated faces where possible.
- Use the **Hole** feature for standard holes (clearance, counterbore, countersink, tapped
  with modelled or cosmetic threads) so drawings and CAM understand them.
- Pattern/mirror as features. Shell/draft. Fillets and chamfers last (and DFM radii per process).
- After each step check the report (bbox in mm vs plan) and screenshot at milestones.

### Image / photo inputs
- Get at least one known dimension for scale; ask if none is visible.
- In Fusion, *Insert > Canvas* and *Calibrate* against the known dimension; trace with few
  constrained curves (don't over-fit splines), then parameterise.
- Agent-side: estimate proportions from the image, but treat them as provisional and say so.

## 4. Verify
See verification.md: timeline health, all sketches fully constrained, key dimensions
measured, flex test of driving parameters, interference/fit checks if mating parts exist,
printability/DFM checks for the chosen process.

## 5. Deliver
Name and group the timeline, hide construction/reference bodies, set a sensible
appearance/material if asked. Ask before saving a new version. Offer exports (STEP for
other CAD/vendors, 3MF/STL for printing, F3D archive) - export only when asked.
Summary: parameters table, what was assumed, verification results.
