# Enclosures and assemblies

## 1. Assembly strategy
- **Top-down (skeleton / master sketch)** for anything designed together - an enclosure
  around a PCB, a lid and base, a bracket set. One layout drives every part, so changing
  `pcb_w` moves every wall, boss and cut-out.
- **Bottom-up** for reusable or bought parts (fasteners, motors, modules): insert as
  components/linked designs, break the link for catalogue parts right after insert.
- Fusion supports a hybrid: skeleton at the assembly level + one component per part.

Structure:
```
Assembly (root)
  SK_Skeleton / construction planes (pcb plane, split plane, wall planes)  [root, or a "Skeleton" component]
  + PCB (imported STEP or simple placeholder box with keep-out bodies)
  + Base   (sketches + body)
  + Lid    (sketches + body)
  + Hardware (screws, inserts - linked or broken-link library parts)
```
Rule #1 applies: activate the component before creating its sketches/features. In-context
references from a component to the skeleton are fine (that's the point) - reference the
skeleton sketch and construction planes, **not** another part's faces where possible.

## 2. Electronics enclosure recipe
1. **Inputs**: PCB outline and thickness, mounting hole positions/diameter, tallest component
   height (top and bottom side), connector positions/sizes/mating-plug clearance, buttons/
   LEDs/displays, cable entry, IP rating / Ex constraints if any, process (FDM vs moulded).
   Best source: the ECAD export (Fusion Electronics PCB -> 3D, or STEP from KiCad/Altium).
   Bring the PCB in as its own component; build keep-out bodies for connectors (include the
   mating plug and finger room).
2. **Parameters** (example, FDM defaults):
   `pcb_w, pcb_d, pcb_t, pcb_clear = 0.5 mm` (gap PCB edge to wall), `wall_t = 2.0 mm`,
   `floor_t = 2.0 mm`, `standoff_h` (= clearance for bottom-side parts + 1 mm),
   `top_clear` (tallest part + 1-2 mm), `boss_od = 2.5*screw_d` (moulded) or insert OD + 2*1.6 mm (FDM),
   `lid_gap = 0.2 mm`, `lip_h = 2 mm`, `corner_r`.
   Inner box = PCB + 2*pcb_clear; outer = inner + 2*wall_t; height from standoff_h, pcb_t, top_clear.
3. **Skeleton**: PCB plane (offset from base floor by `floor_t + standoff_h`), split plane
   between base and lid, outline sketch of the inner cavity on origin, symmetric.
4. **Shell**: extrude the outer outline to full height as one body, fillet vertical
   edges, then Shell (inside thickness `wall_t`) removing the top face - or extrude walls
   from an offset outline. Split Body at the split plane into base and lid, then move
   each body into its component (or create the bodies directly in their components).
5. **Lid/base interface**: lip and groove (lip width ~ wall_t/2, `lid_gap` clearance per
   side), or screws into bosses at the corners; sealing groove if needed (gasket per vendor).
6. **Standoffs/bosses** at PCB hole positions from the skeleton sketch; hole for the chosen
   fastener (self-tapping pilot, heat-set insert hole per insert vendor, or nut trap).
   Add gussets/ribs to tall bosses; core bosses on moulded parts.
7. **Cut-outs**: sketch on construction planes at the wall, projected from the connector
   keep-out bodies or dimensioned from the PCB datum; add clearance (0.3-0.5 mm per side
   for FDM). Labels/vents as features (vent patterns as feature patterns).
8. **Assemble**: joints to position; check interference; section analysis through bosses
   and the lid interface.

## 3. Design rules
Injection-moulded plastics (DFM sources: Fictiv/Protolabs-style guidance as summarised by
Fabcon; confirm with the moulder):
- Uniform wall, typically 1.2-3.0 mm (1.5-2.5 mm common for enclosures); change thickness
  gradually.
- Draft 0.5-3 deg (>= 1 deg polished, ~3 deg textured; ribs/bosses ~0.5 deg).
- Ribs 40-60 % of wall (up to ~75 % on non-cosmetic faces), height <= 3x wall, root radius.
- Bosses: OD ~ 2-2.5x screw diameter, wall <= ~60 % of nominal wall, cored, gusseted.
- Internal radius ~0.5x wall, external = internal + wall; no sharp internal corners.
- Snap-fits: cantilever sized by allowable strain; ~0.3 mm close-fit gaps; 1-2 deg draft;
  root fillet ~0.5x thickness; avoid undercuts that need side actions.

FDM 3D printing (calibrate with a test coupon - printers differ):
- Walls >= 2 perimeters x line width; 1.6-2.5 mm is a robust default for enclosures.
- Clearances per side: sliding/moving 0.15-0.3 mm, snug/push 0.1-0.15 mm, press fit
  0-0.05 mm (tune by test print). Holes print undersize - add 0.1-0.2 mm or drill/ream.
- Use **heat-set inserts** for M2-M4 threads (hole size from insert vendor, not screw
  size); M5+ can be printed or use inserts. Nut traps: +0.2 mm across flats, +0.3 mm depth.
- Avoid overhangs > ~45-50 deg without support; chamfer (not fillet) downward-facing
  edges on the bed side; teardrop or diamond horizontal holes; split parts so the
  cosmetic face is up and functional holes are vertical.
- Minimum feature ~1 mm wide/deep for embossed text.
CNC: internal corner radius >= tool radius (add dog-bones for mating square parts), avoid
deep narrow pockets (> 4x tool diameter), standard drill sizes, design datums for workholding.
Sheet metal: constant thickness, bend radius >= thickness, relief cuts, holes >= thickness
from bends.

## 4. Fits (put values in parameters)
| Fit | FDM start (per side) | Machined |
|---|---|---|
| Free sliding / rotating | 0.2-0.3 mm | H9/d9 class or ~0.05-0.1 mm |
| Snug, hand assembly | 0.1-0.15 mm | H7/h6 |
| Press | 0-0.05 mm (test!) | H7/p6 |
| Lid lip in groove | 0.2 mm | 0.1 mm |
Model nominal geometry and apply clearance through a parameter so it can be tuned after a test print.

## 5. Joints, constraints and grounding
- Positioning order: ground (or ground-to-parent) **one** base component, then joint
  everything to it.
- **Joints** (rigid, revolute, slider, cylindrical, pin-slot, planar, ball): fast, use snap
  points / joint origins; the first selection moves to the second.
- **As-built joints**: when parts were already modelled in place (top-down) - they keep current
  positions. Ideal for skeleton-built enclosures.
- **Rigid group**: lock several components together quickly (an as-built rigid joint for >2
  components); use instead of ground inside sub-assemblies, because *Ground is not carried
  across Insert* while rigid groups/as-built joints are.
- **Assembly constraints** (added 2025): progressive mate-style constraints for complex
  geometry or when snap points are awkward; can coexist with joints. Test by dragging.
- Joint origins: create explicit joint origins on construction geometry for repeatable,
  edit-safe placement. Use joint limits for motion ranges; motion links for coupled motion.
- Subassemblies are not rigid in the parent by default - lock with as-built rigid joint to the
  parent origin or a rigid group.
- Moving a component without a joint creates a pending snapshot - Capture Position only on
  purpose.

## 6. Assembly verification
- Interference analysis across all components (expect only intentional press fits).
- Section analysis through every boss/screw, the lid seam, and connector cut-outs.
- Check assembly sequence: can the PCB go in, can screws be driven, can the lid close,
  can cables be plugged with the lid on.
- Drive joints through their range and re-check interference.
- Flex: change `pcb_w`, `top_clear`, `wall_t` and confirm everything follows with no
  timeline errors.
