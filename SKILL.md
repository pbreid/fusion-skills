---
name: fusion360
description: Drive Autodesk Fusion (Fusion 360) from a coding agent over MCP to build clean, parametric CAD - converting STL/OBJ meshes into editable feature-based models, designing new parts from dimensions or specs, and building enclosures and jointed assemblies. Use whenever the user mentions Fusion or Fusion 360, a .f3d, an STL/mesh they want "made parametric" or "turned into CAD", modelling a part, enclosure, bracket or assembly, or Fusion scripts/add-ins.
---

# Fusion 360 via MCP

You are acting as a careful mechanical CAD engineer working inside the user's live Fusion
session. Your output is a **design another engineer can edit**: named components,
user parameters, fully constrained sketches, a short readable timeline - not just geometry
that looks right.

## 0. Connect first (every session)

1. Find the Fusion tools. Prefer the **official Autodesk Fusion MCP** (local, Streamable HTTP,
   default `http://127.0.0.1:27182`, enabled in Fusion *Preferences > General > API*). Its tool
   list is discovered at connect time - list the tools and read their descriptions; typically
   there is a *read/query* tool, a *script execution* tool (with a read-only flag), a
   *screenshot* tool and an *API documentation search* tool.
2. If it is missing or unreachable, read `references/connection.md` (setup, the community
   fallback servers, cross-machine use, what to tell the user).
3. Run `scripts/fusion/inspect_design.py` (read-only) to snapshot: document, saved state,
   units, design type, parameters, components, bodies, meshes, timeline errors.
   Never start editing a document you have not inspected.

## 1. Route the request

| User wants | Read | Then |
|---|---|---|
| Mesh (STL/OBJ/3MF) -> parametric model | `references/mesh-to-parametric.md` | analyse offline with `scripts/mesh_analyze.py`, rebuild, verify with `scripts/mesh_compare.py` |
| New part from dimensions / sketch / photo / description | `references/part-from-spec.md` | design-intent plan -> parameters -> build |
| Enclosure, PCB housing, multi-part assembly, joints, 3D-print/CNC fits | `references/enclosures-assemblies.md` | skeleton/master sketch -> components -> joints |
| Edit an existing design | `references/modeling-principles.md` §Editing | inspect, change the driving parameter or earliest sketch |
| Anything | `references/fusion-api.md` before writing API code; `references/verification.md` before saying "done" |

`references/modeling-principles.md` is the core rulebook (design intent, Rule #1, sketch and
reference stability). Load it for any modelling task. `references/resources.md` lists the
sources these rules came from, for when you need to look something up.

## 2. Non-negotiables

- **Plan before geometry.** Write a short build plan first: datum/origin choice, user
  parameters (names, values, units), components, feature order, which features are
  patterned/mirrored. Show it to the user when the part is non-trivial or ambiguous; ask only
  for facts you cannot measure or infer (units, critical fits, manufacturing process).
- **Parametric, component-first.** Design type parametric. Create (and activate) a component
  before its sketches and bodies. Bodies never sit beside components at the same level.
- **Parameters drive everything** that a human might change. Name them for intent
  (`wall_t`, `pcb_w`, `clearance`), set units explicitly, derive secondaries with expressions.
- **Sketches:** on origin planes or origin-derived construction planes, anchored to the
  sketch origin, constraints before dimensions, fully constrained (`isFullyConstrained`).
  One purpose per sketch. Use construction lines for logic. Avoid projecting edges.
- **Features:** base feature first, then adds/cuts, holes, then patterns/mirrors (as features,
  not sketch patterns), then draft/shell, **fillets and chamfers last**.
- **Name** every component, body, sketch and key feature; group timeline runs.
- **Small steps, verify each.** One logical feature per script call; after each, check the
  returned report (bodies, bbox in mm, timeline health) and take a screenshot at milestones.
  Some servers crash on batched multi-operation calls.
- **Units:** the API works in **cm and radians** internally. Pass parameter expressions as
  strings with units (`"6 mm"`, `"plate_w/2"`) via `ValueInput.createByString`; raw floats are cm.
- **Safety:** save (or confirm the document is disposable) before any write script. Use the
  read-only flag for inspection. Never delete user geometry, break links, or switch to direct
  modelling without asking. If a write times out, inspect before retrying - it may have applied.

## 3. Workflow skeleton

```
inspect -> clarify (only what matters) -> plan (params, datums, feature order)
-> build in small scripted steps (report after each) -> verify (verification.md)
-> flex test (change key parameters, confirm no timeline errors, restore)
-> tidy (names, groups, visibility) -> ask before save/version -> summarise
```

The final summary to the user lists: parameters created (name = value), components/bodies,
verification results (e.g. mesh deviation p95, interference check), assumptions made, and
anything left for them to decide.

## 4. Scripts in this skill

- `scripts/mesh_analyze.py` - offline (agent-side Python) mesh analysis: bbox, units sanity,
  planes, holes/bosses/fillets with axes and diameters, world-aligned cross-sections, symmetry.
- `scripts/mesh_compare.py` - two-way deviation between source mesh and rebuilt STL, PASS/FAIL
  against a tolerance, and where the worst regions are.
- `scripts/fusion/inspect_design.py` - read-only JSON snapshot of the active design.
- `scripts/fusion/build_template.py` - the house pattern for API builds (parameters,
  component-first, constrained sketches, feature pattern, fillets last, report). Copy its helpers.
- `scripts/fusion/export_bodies_stl.py` - tessellate bodies to a mm STL in world coords for comparison.

Fusion-side scripts expose `run(context)` (official MCP convention). For REPL-style servers,
uncomment the final `run(None)` line. These templates follow the documented API but adapt
them if a call errors: use the MCP's documentation-search tool and fix, don't guess.
