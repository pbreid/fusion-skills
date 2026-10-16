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
   `http://127.0.0.1:27182/mcp`, enabled in Fusion *Preferences > General > API*). On current
   builds the tools are `fusion_mcp_read` (`queryType`: screenshot, apiDocumentation, ...),
   `fusion_mcp_execute` (`featureType: "script"`, `object: {script, readOnly}`) and
   `fusion_mcp_update` (undo/redo). Confirm with `tools/list` and read the input schemas;
   don't guess argument names or enums.
2. **No native MCP tools in your harness?** Don't hand-roll JSON-RPC. Use
   `scripts/fusion_mcp.py` (session header, envelope parsing and screenshots are handled):
   `python3 scripts/fusion_mcp.py run scripts/fusion/inspect_design.py`.
   Unreachable or missing: read `references/connection.md` (setup, WSL/remote use, fallbacks).
3. Run `scripts/fusion/inspect_design.py` (read-only) to snapshot: document, saved state,
   units, design type, parameters, components, bodies, meshes, timeline errors.
   Never start editing a document you have not inspected.
4. Agent-side Python: create a venv once **in the working folder, not inside the skill
   folder** (`python3 -m venv .venv && .venv/bin/pip install trimesh numpy scipy shapely rtree
   networkx`). System pip is often blocked (PEP 668), and `python` may not exist, so use
   `python3` or `.venv/bin/python`. Add `matplotlib` for `mesh_views.py`. Keep exports, reports and screenshots in the working
   folder too.

## 1. Route the request

| User wants | Read | Then |
|---|---|---|
| Mesh (STL/OBJ/3MF) -> parametric model | `references/mesh-to-parametric.md` | export with `export_mesh_body_stl.py` (mm, scale gate), **square it with `mesh_align.py`**, render views with `mesh_views.py`, analyse with `mesh_analyze.py`, **stop and ask intake questions**, rebuild square at the origin, verify with `mesh_compare.py` |
| New part from dimensions / sketch / photo / description | `references/part-from-spec.md` | design-intent plan -> parameters -> build |
| Enclosure, PCB housing, multi-part assembly, joints, 3D-print/CNC fits | `references/enclosures-assemblies.md` | skeleton/master sketch -> components -> joints |
| Edit an existing design | `references/modeling-principles.md` §Editing | inspect, change the driving parameter or earliest sketch |
| Anything | `references/fusion-api.md` before writing API code; `references/verification.md` before saying "done" |

`references/modeling-principles.md` is the core rulebook (design intent, Rule #1, sketch and
reference stability). Load it for any modelling task. `references/resources.md` lists the
sources these rules came from, for when you need to look something up.

## 2. Non-negotiables

- **Ask before you plan.** After inspecting and analysing, and before any build plan or
  geometry, send the user one short message with what you found and the questions that
  change the model: units, tolerance, functional features, process, orientation. If the
  user asked "do you have questions?", this step is mandatory. Then wait for the answer.
- **Plan before geometry.** Write a short build plan first: datum/origin choice, user
  parameters (names, values, units), components, feature order, which features are
  patterned/mirrored. Show it to the user when the part is non-trivial or ambiguous.
- **Parametric, component-first.** Design type parametric. Create (and activate) a component
  before its sketches and bodies. Bodies never sit beside components at the same level.
- **Parameters drive everything** that a human might change. Name them for intent
  (`wall_t`, `pcb_w`, `clearance`), set units explicitly, derive secondaries with expressions.
- **Sketches:** on origin planes or origin-derived construction planes, anchored to the
  sketch origin, constraints before dimensions, fully constrained (`isFullyConstrained`).
  One purpose per sketch. Use construction lines for logic. Avoid projecting edges.
- **Features:** base feature first, then adds/cuts, holes, then patterns/mirrors (as features,
  not sketch patterns), then draft/shell, **fillets and chamfers last**.
- **Square to the world axes, always.** New parts are built at the design origin with their main
  faces on the origin planes, whatever tilt the source mesh or reference has. Never copy a
  tilted placement onto a new component. Use `mesh_align.py` for meshes.
- **Repeated features are never modelled one by one.** Use a seed + rectangular, circular or
  path pattern, or a mirror, with counts and pitch in parameters, Identical compute for large
  counts, and suppressed instances for gaps. See modeling-principles.md §5a.
- **Name** every component, body, sketch and key feature; group timeline runs.
- **Small steps, verify each.** One logical feature per script call; after each, check the
  returned report (bodies, bbox in mm, timeline health) and take a screenshot at milestones.
  Some servers crash on batched multi-operation calls.
- **Units:** the API works in **cm and radians** internally, including mesh coordinates.
  Pass parameter expressions as strings with units (`"6 mm"`, `"plate_w/2"`) via
  `ValueInput.createByString`; raw floats are cm. Every file you export for analysis must be
  in mm. Cross-check its extents against the `inspect_design` bbox before using it.
- **Use the skill's scripts before writing your own.** Need a slice at a specific height?
  Use `mesh_analyze.py --section-at z=60,x=-68`. Need hole patterns? Read
  `cylinder_groups`. Need report keys? Read the schema in the script's docstring. Need
  tool arguments? Run `fusion_mcp.py tools --json` or `directions`. If an API call fails with
  an AttributeError, probe `dir(obj)` once rather than guessing repeatedly.
- **Only report what you measured.** Say "not verified" rather than asserting something you
  haven't checked (for example "the shell is closed in Fusion").
- **Safety:** save (or confirm the document is disposable) before any write script. Use the
  read-only flag for inspection. Never delete user geometry, break links, or switch to direct
  modelling without asking. If a write times out, inspect before retrying - it may have applied.

## 3. Workflow skeleton

```
inspect -> analyse -> ASK (one message, then wait) -> plan (params, datums, feature order)
-> build in small scripted steps (report after each) -> verify (verification.md)
-> flex test (change key parameters, confirm no timeline errors, restore)
-> tidy (names, groups, visibility) -> ask before save/version -> summarise
```

The final summary to the user lists: parameters created (name = value), components/bodies,
verification results (e.g. mesh deviation p95, interference check), assumptions made, and
anything left for them to decide.

## 4. Scripts in this skill

- `scripts/fusion_mcp.py` - stdlib client for the official Fusion MCP over HTTP (handshake,
  session header, envelope parsing, `run`, `screenshot`, `directions`, `tools --json`, `docs`).
  Use it as a CLI or import it.
- `scripts/mesh_analyze.py` - offline (agent-side Python) mesh analysis: bbox, units sanity,
  planes, holes/bosses/fillets with axes and diameters, world-aligned cross-sections, symmetry.
  `--expect-extents X,Y,Z` aborts on a scale mismatch; `--scale` rescales; `--section-at z=60,x=-68`
  slices at exact positions. Also reports `cylinder_groups` (hole patterns with count and grid
  pitch) and `body_breakdown` (real bodies vs tessellation fragments).
- `scripts/mesh_align.py` - square a mesh to the world axes with the smallest rotation (keeps up
  and front), set the origin, write the aligned STL and `transform_mm`.
- `scripts/mesh_views.py` - square orthographic front/top/right/iso renders of an STL (needs matplotlib).
- `scripts/mesh_compare.py` - two-way deviation between source mesh and rebuilt STL, PASS/FAIL
  against a tolerance, and where the worst regions are.
- `scripts/fusion/inspect_design.py` - read-only JSON snapshot of the active design.
- `scripts/fusion/build_template.py` - the house pattern for API builds (parameters,
  component-first, constrained sketches, feature pattern, fillets last, report). Copy its helpers.
- `scripts/fusion/export_bodies_stl.py` - tessellate B-rep bodies to a mm STL in world coords for comparison.
- `scripts/fusion/export_mesh_body_stl.py` - write an imported **mesh** body to a mm STL, in the local
  or world frame (handles PolygonMesh, cm→mm, occurrence transform), and print its extents.
- `scripts/fusion/square_occurrence.py` - (write, ask first) re-place the reference mesh's occurrence
  so it sits square, using mesh_align's transform. Moves the placement only, not the geometry.

Fusion-side scripts expose `run(context)` (official MCP convention). For REPL-style servers,
uncomment the final `run(None)` line. `inspect_design.py` and `export_mesh_body_stl.py` use API
members verified against live Fusion. `build_template.py` and `export_bodies_stl.py` follow
the documentation but are not yet live-tested, so fix any error with the docs tool or a
`dir()` probe.
