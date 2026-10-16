# Modelling principles (general CAD + Fusion-specific)

Distilled from Autodesk's sketching/parametric guidance, the AU class "Fusion 360 - Modeling
Tips from the Experts" (Peter Doering, Expert Elite & Jeff Strater, Fusion sketch/modelling
architect), Onshape's *Mastering 3D Modeling* robustness guide, and assembly classes by the
Fusion product team. See resources.md.

## 1. Design intent first
A parametric model is a recipe that will be replayed with different numbers. Before drawing,
decide *what should stay true when things change*:
- What are the **datums**? (mounting face, symmetry planes, a bore axis, PCB origin.) Put
  them on the origin planes. Model at real size, in the right orientation (Z up = print/use
  orientation unless the user says otherwise).
- What are the **driving dimensions** (the ones a human will change) vs derived ones?
  Driving -> user parameters. Derived -> expressions (`boss_od = 2.5 * screw_d`).
- What is **symmetric**? Model half/quarter and mirror, or sketch symmetric about origin.
- What is **patterned**? Model one seed, pattern as a feature.
- Test intent at the end by flexing the key parameters (flex test).

## 2. Fusion Rule #1: component first
"When in doubt, before doing anything, create a component and make sure it's activated."
`Component (activated) -> Sketch -> Body -> Features -> Assemble`
- Activated component filters the timeline, owns its sketches/construction/joint origins,
  and exports with full history via *Save copy as*.
- Joints, drawings, BOM, isolate and colour cycling work on **components**, not bodies.
- Assembly structure: each component holds its own sketch + body; a skeleton/master sketch
  may sit at assembly level beside sub-components. Never loose bodies beside components.
- Valid alternatives: *skeletal* (one layout sketch -> several bodies -> convert to components
  ASAP) and *single-part file* (a standalone part meant to be inserted elsewhere needs no
  extra component).
- Multi-body is fine **inside** a component for tool bodies/booleans; one finished body per
  component as a rule.
- Do not use "Delete all features after marker" while a component is activated - it applies
  to the whole timeline.

## 3. Sketch rules
- Sketch on **origin planes** or construction planes defined from origin geometry; only
  sketch on a model face when the feature truly belongs to that face, knowing it creates a
  dependency.
- Anchor to the sketch origin (Fusion adds a fixed origin point; geometry snapped to it is
  locked - use *Delete Coincident* if that was unintended).
- **Constraints before dimensions.** Horizontal/vertical first, then symmetry, coincident,
  tangent, equal, then size. Use symmetry constraints instead of mirrored dimensions -
  missing orientation constraints are the main cause of flipping dimensions.
- **Fully constrained** (black, `sketch.isFullyConstrained`) before using it for features.
- **Many small sketches** beat one big sketch: faster solve, fewer failures. One feature, one sketch.
- Use **construction geometry** for logic (symmetry axes, spacing, reference circles) and to
  keep profile count low - fewer, simpler profiles are faster and more stable.
- Prefer **feature fillets** over sketch fillets, **feature patterns** over sketch patterns.
- You rarely need Trim: Fusion can extrude any closed sub-region.
- Closed-profile failures: endpoints not coincident, overlapping/duplicate lines,
  construction used as real geometry. Debug: show profiles, zoom corners, AutoConstrain,
  or add test lines to see where regions appear.
- Splines: as few fit points as possible; use tangent handles, not dozens of traced points.
- Every Fusion sketch can hold 3D curves (no separate 3D sketch).

## 4. References and stability (why models break)
Most errors come from a reference that cannot be found after an upstream edit.
Stability ranking, best to worst:
1. **Origin planes/axes/point** - never fail.
2. Construction geometry defined only from origin geometry.
3. Sketch geometry referenced from another sketch (stable unless you delete the source curve).
4. **Body** references > **face** > **edge** > **vertex** (an edge needs two faces resolved, a vertex three).
Construction geometry built from a face is only as stable as that face.

What breaks references:
- Deleting and recreating sketch curves (new IDs) - **edit, don't delete**. *Break Curve* also issues new IDs.
- Upstream edits that consume a referenced face/edge.
- Inserting features before a reference.
- Projected edges of features that later change (especially fillet edges). Project sparingly;
  prefer dimensioning to projected origin geometry.
- Auto-project while sketching silently creates references - avoid / project explicitly.

Timeline states: **red = error** (feature failed); **yellow = warning** - often computed from
*cached* geometry and no longer associative. Treat warnings as bugs. *Compute All* is a
design checker: run it before declaring done.

Fixing: roll the marker back before the first failure, fix it first (later errors often
vanish), step forward one feature at a time, re-attach references. Broken projected curve:
Break Link, re-project, then constrain the new projection collinear/coincident with the old
curve (keeps downstream IDs).

## 5. Feature order
1. Base feature (largest/primary form; usually an extrude or revolve from the main datum).
2. Primary adds and cuts (bosses, pockets, ribs).
3. Holes (Hole feature for standard holes: counterbore/countersink/tapped/cosmetic threads).
4. Patterns and mirrors (feature patterns; choose compute option *Identical* when instances
   are the same, *Adjust* when they must respond to local geometry).
5. Shell / draft.
6. Fillets and chamfers last (they consume edges everything else depends on).
Order in the timeline = order of intent, not order of creation; reorder when it helps.
The timeline is a time machine: a sketch cannot reference geometry created after it.

## 5a. Repeated features (holes, vents, ribs, bosses, slots)
**Never model repeated features one by one.** Model one seed and pattern it as a feature,
or mirror it. Forty identical holes are one Hole feature plus one pattern, with every
number in a parameter. Hand-placed copies break the moment the pitch, panel size or count
changes, and they bloat the timeline.

**Decide the pattern type from the data.** For meshes, use `cylinder_groups` in the analyzer
report: count, pitch per axis, `regular`, `fills_grid`, and `stations_along_axis` (which walls).

| What you see | Model it as |
|---|---|
| Regular rows × columns (`regular: true` on both axes) | One seed + **rectangular pattern**, two directions |
| Same grid on two opposite walls (two stations, symmetric) | Pattern on one wall + **mirror** feature across the symmetry plane. Alternatively, one seed cut that pierces both walls (Through All or To Object), but only if nothing else lies on that line; set **participant bodies** so internal ribs aren't cut |
| Staggered / hex grid | Two rectangular patterns of two seeds, the second offset by half a pitch, or one pattern whose seed is a pair of holes |
| Holes on a PCD / around an axis | One seed + **circular pattern** (quantity, total angle, symmetric if needed) |
| Along a curve or edge | **Pattern on path** |
| `fills_grid: false` (positions missing, e.g. behind a boss or a cut-out) | Full rectangular pattern, then **suppress instances**, or let a later solid feature fill them if that is the design intent. Prefer suppression when the gaps are few and fixed; prefer a bounded field when the gaps follow another feature's outline |
| Irregular spacing, a few instances | Separate features or several sketch points on one Hole feature, each dimensioned. Don't force a pattern |
| A whole perforated *region* (vent field inside a boundary) | Seed + pattern sized to the region, or a dedicated vent generator if the field must clip to an arbitrary outline |

**Parameterise the pattern so it follows the design.**
- Use `vent_d`, `vent_pitch_y`, `vent_pitch_z`, `vent_n_y`, `vent_n_z`, and the seed position
  from a datum (`vent_y0`, `vent_z0`). Dimension the seed from origin or skeleton geometry, not
  from model edges.
- Where the field should fill a panel, derive the count:
  `vent_n_y = floor((panel_h - 2*vent_margin) / vent_pitch_y) + 1`, and centre the field with
  the seed offset `(panel_h - (vent_n_y - 1)*vent_pitch_y) / 2`. Changing the panel size then
  re-flows the grid. Fusion expressions support `floor`, `ceil` and `round`.
- Use **Spacing** distance type when the pitch is the design value. Use **Extent** when the
  overall span is the design value and the pitch is derived.
- **Recover which one the designer used from the numbers.** Designers type round numbers. An
  odd pitch whose span is round (7.421 = 141/19, 6.667 = 40/6) means "n instances over a span",
  so use Extent with `vent_rows = 20`, `vent_span = 141`. A round pitch (7.5) means Spacing.
  `mesh_analyze.py` reports this as `design_hint.suggest` per axis. Never parameterise a derived
  pitch like 7.421 as the driving value.
- **Blocks of a grid** (identical groups separated by a larger gap): pattern the seed into one
  block, then pattern that pattern feature by the block pitch (`vent_block_pitch`,
  `vent_blocks`). Suppressing instances is the fallback for irregular gaps.

**Performance with large counts.**
- Hundreds of instances: set compute option **Identical** when every instance meets the same
  geometry, as with holes through a flat wall. It is far faster. Use **Adjust** only when
  instances must react to varying geometry, such as holes ending on a curved face.
- Pattern the **feature** (the cut), not the body.
- Keep the seed sketch tiny: one circle, dimensioned.
- Create large patterns late, just before fillets, and suppress them while editing upstream
  geometry if recompute gets slow.

**Seeds and fillets.** Edge fillets or chamfers on patterned holes go on the **seed** before
patterning (pattern both features together), or are patterned with it. Never fillet hundreds
of instance edges afterwards.

**Verify patterns explicitly.**
- Instance count in the model equals the analyzer count.
- First and last instance positions are measured against the source.
- No instance breaks into a rib or edge.
- Flex test: change the pitch and the panel size, and confirm the grid re-flows without
  timeline errors.

## 6. Parameters
- Create **user parameters first**; names lower_snake, intent-revealing, with units and a
  comment. Group by prefix (`pcb_`, `wall_`, `boss_`).
- Derive with expressions; avoid circular references; don't mix hard-coded values with
  parameterised ones for the same intent.
- Model exact fits, then apply a `clearance`/`tolerance` parameter.
- Configurations (configured designs): configure user parameters, feature parameters,
  suppression and inserted configured components in a configuration table - use for real
  product variants, not for every tweak. Text parameters exist for labels/engravings.

## 7. Timeline hygiene
- Name everything (sketches `SK_...`, features `EX_/CUT_/FIL_/PAT_...`, bodies by part).
- Keep each component's operations contiguous; enable component colour swatches.
- Group meaningful runs of features ("Lid snap hooks"), not one group per component.
- Capture Position only when position-dependent modelling needs it; otherwise reset moves.

## 8. Linked (external) components
Insert from the data panel = linked. Link only when the part is reused, will change, and the
assembly must follow. Develop in context first; *Save copy as* when mature. Off-the-shelf parts
(fasteners, McMaster/vendor STEP): break the link immediately after insert, before saving.
User parameters of a linked component are not accessible from the parent.

## 9. Editing an existing design
1. Inspect: parameters, timeline health, which sketch drives the region in question.
2. Change the **driving parameter or earliest sketch dimension**, not a downstream patch.
3. Prefer a local change; if broader change is needed, say which dependency forces it and
   preserve mating datums.
4. Re-run Compute All, compare before/after bbox, volume and key dimensions, screenshot.

## 10. When parametric is the wrong tool
Organic/freeform shapes: Form (T-spline) workspace, then convert and continue parametrically
(convert to components immediately). Imported STEP with no history: turn on design history
and add features on top, or use direct edits (Press Pull, Replace Face, Offset Face)
sparingly. Do not switch the whole design to direct modelling without asking - it discards
history.
