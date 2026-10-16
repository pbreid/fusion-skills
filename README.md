# fusion360 — an agent skill for parametric CAD in Autodesk Fusion

A skill for AI coding agents (OMP, Claude Code, Cursor, Codex and other agents that load
`SKILL.md`-style skills) that lets them drive **Autodesk Fusion (Fusion 360)** over the Model
Context Protocol and produce clean, editable, parametric CAD.

The skill pairs a connection guide with distilled CAD and Fusion best practice, so the agent
models like a careful mechanical engineer. It builds named components, user parameters and
fully constrained sketches in a short, readable timeline, and it verifies its own work.

It covers three workflows:

| Workflow | What the agent does |
|---|---|
| **Mesh → parametric** | It analyses an STL/OBJ/3MF offline, recovers design intent (nominal sizes, patterns, symmetry), rebuilds the part feature by feature, then measures the deviation against the source mesh. |
| **New part from a spec** | It turns dimensions, datasheets, sketches or descriptions into a build plan, then into a parametric part. |
| **Enclosures and assemblies** | It builds skeleton-driven enclosures around a PCB. It applies DFM rules for printing and moulding, sets fits as parameters, and assembles parts with joints, rigid groups and interference checks. |

---

## Repository layout

```
fusion360/
├── SKILL.md                         Entry point: connection steps, routing table, non-negotiable rules
├── README.md                        This file
├── references/
│   ├── connection.md                Official vs community Fusion MCP servers, setup, remote/LAN use, licence caveats
│   ├── modeling-principles.md       Core rulebook: design intent, Rule #1, sketches, reference stability, feature order
│   ├── fusion-api.md                Fusion Python API patterns, units, selection, timeline, measurement, export, errors
│   ├── mesh-to-parametric.md        Mesh rebuild workflow (and when to use Convert Mesh instead)
│   ├── part-from-spec.md            Requirements → plan → build → verify for new parts
│   ├── enclosures-assemblies.md     Top-down enclosures, DFM rules, fit table, joints/constraints/grounding
│   ├── verification.md              Checklist the agent must pass before saying "done"
│   └── resources.md                 Sources the rules were distilled from, plus learning channels
└── scripts/
    ├── mesh_analyze.py              Agent-side mesh analysis (planes, holes/bosses, sections, symmetry)
    ├── mesh_align.py                Squares a mesh to the world axes (smallest rotation) and sets the origin
    ├── mesh_views.py                Square orthographic front/top/right/iso renders of an STL
    ├── mesh_compare.py              Two-way deviation between source mesh and rebuild, PASS/FAIL
    ├── fusion_mcp.py                Stdlib client for the official Fusion MCP (CLI or import)
    └── fusion/                      Scripts executed *inside* Fusion via the MCP
        ├── inspect_design.py        Read-only JSON snapshot of the active design
        ├── build_template.py        Reference build pattern (parameters, constrained sketches, patterns, fillets, report)
        ├── export_bodies_stl.py     Tessellates solid bodies to a millimetre STL in world coordinates
        ├── export_mesh_body_stl.py  Writes an imported mesh body to a millimetre STL (local frame by default, or world)
        └── square_occurrence.py     Re-places the reference mesh so it sits square (placement only; asks first)
```

### How the skill is structured

`SKILL.md` stays short and is always loaded when the skill triggers. It tells the agent how to
connect, then routes it to the reference file for the task at hand, so detailed material only
enters context when it's needed (progressive disclosure). The scripts do deterministic work
(geometry analysis, measurement, export) that the model should not attempt "by eye".

---

## Requirements

**Fusion side**
- Autodesk Fusion desktop (Windows or macOS), running, with the Design workspace active.
- The **Autodesk Fusion MCP Server** enabled: *Preferences → General → API → Fusion MCP Server*.
  Note the port; the default is `27182`.
- Licence note: Fusion for Personal Use limits you to 10 active editable documents and does
  not include *Prismatic* Convert Mesh. The default rebuild workflow doesn't need it.

**Agent side**
- An MCP client that supports Streamable HTTP (OMP, Claude Code, Cursor, VS Code, Claude Desktop).
- Python 3.10+ for the mesh scripts. Use a virtual environment: Debian/Ubuntu and WSL block
  system-wide `pip install` (PEP 668), and `python` may not exist (use `python3`):
  ```bash
  cd ~/remodel          # your working folder, not the skill folder
  python3 -m venv .venv
  .venv/bin/pip install trimesh numpy scipy shapely rtree networkx matplotlib
  ```
  Then run scripts by full path, for example
  `.venv/bin/python ~/.agents/skills/fusion360/scripts/mesh_analyze.py part.stl ...`.
  Keeping the venv out of the skill folder keeps the skill small and the repo clean.
  Fusion's embedded Python doesn't include numpy or trimesh. That's why mesh analysis runs
  on the agent side. `fusion_mcp.py` needs only the standard library.

---

## Installation

1. **Add the skill to your agent.** Copy or clone the `fusion360/` folder into the agent's
   skills directory:
   - Claude Code: `~/.claude/skills/fusion360/` (user-wide) or `.claude/skills/fusion360/` (per project)
   - OMP and other agents: the skills folder that agent reads `SKILL.md` files from

2. **Connect the agent to Fusion.** Add the MCP server to your client config:
   ```json
   { "mcpServers": { "fusion": { "url": "http://127.0.0.1:27182/mcp" } } }
   ```
   Some clients expect the bare `http://127.0.0.1:27182` instead. For Claude Code:
   ```bash
   claude mcp add --transport http fusion http://127.0.0.1:27182/mcp
   ```
   Start Fusion **before** the client connects.

3. **If the agent isn't on the Fusion machine.** The official server only listens on
   localhost. Either forward the port:
   ```bash
   ssh -L 27182:127.0.0.1:27182 user@fusion-pc
   ```
   or use the community `faust-machines/fusion360-mcp-server`, which can bind to the LAN.
   It has no authentication, so use it on trusted networks only. See `references/connection.md`.

   **Windows + WSL** (agent in WSL, Fusion on Windows): `127.0.0.1:27182` is normally
   reachable from WSL2. Exchange files through `C:\Users\Public\`, which is
   `/mnt/c/Users/Public/` inside WSL.

4. **If your agent can't register MCP servers natively**, it can drive Fusion through the
   bundled client instead:
   ```bash
   python3 scripts/fusion_mcp.py tools --schema
   python3 scripts/fusion_mcp.py run scripts/fusion/inspect_design.py          # read-only
   python3 scripts/fusion_mcp.py run my_step.py --write                        # modifies the design
   python3 scripts/fusion_mcp.py screenshot --direction iso-top-right --out shot.png
   ```

5. **Smoke test.** Ask the agent to "inspect the open Fusion design". It should run
   `scripts/fusion/inspect_design.py` in read-only mode and report the document, units,
   parameters, components and timeline health.

---

## Usage

Invoke the skill by name or just describe the job; the skill triggers on Fusion, STL→CAD,
enclosure and assembly requests. Example prompts:

- *"Use the fusion360 skill to turn `bracket.stl` into a parametric model. It's in mm, and the
  holes are M3 clearance. Target 0.1 mm deviation."*
- *"Design an FDM enclosure for this PCB (STEP attached) with heat-set inserts, a USB-C
  cut-out on the short side and a lid with a 0.2 mm lip clearance."*
- *"Make the wall thickness and PCB clearance parameters in the open design and flex-test them."*

What the agent will do (see `SKILL.md` §3):

```
inspect → analyse → ask you (then wait) → plan (parameters, datums, feature order)
→ build in small scripted steps → verify → flex test → tidy → ask before saving → summarise
```

The final summary lists the parameters created, the bodies and components, the verification
numbers, assumptions, and open items.

---

## Scripts

### `scripts/mesh_analyze.py` (runs on the agent side)
```bash
.venv/bin/python scripts/mesh_analyze.py part.stl --units mm --sections 7 \
    --expect-extents 156,204,142.5 --json part_report.json
# options: --axis auto|x|y|z   --tol 0.05   --scale 10 (cm → mm)
```
`--section-at z=60,x=-68` adds sections at exact positions. The report also includes
`cylinder_groups`, which turns hundreds of hole records into lines like "Ø5 hole ×560, X
axis, grid Y:20@7.4 Z:14@6.7", and `body_breakdown`, which separates real bodies from
tessellation slivers.

`--expect-extents` takes the bbox from `inspect_design.py`. If the file is scaled wrong (for
example a cm-valued export), the script stops with `SCALE MISMATCH` and suggests the fix,
instead of producing a report that's 10× off.

It reports:
- Extents with a units sanity warning, watertightness and body count.
- A through-hole estimate from the mesh genus.
- Whether the part is aligned to world axes.
- Dominant planes as world positions (`Z=6.0`).
- Cylindrical regions classified as hole, boss or fillet, with diameter, axis, base point and length.
- Cross-section loops at several levels in world coordinates of the matching origin plane, with
  circles and rectangles detected.
- Candidate extrude levels and mirror symmetry.

### `scripts/mesh_align.py` (runs on the agent side)
```bash
.venv/bin/python scripts/mesh_align.py part_world.stl part_aligned.stl --json align.json \
    [--origin center-base|center|min|keep] [--then-rotate x:90]
```
Squares a part to the world axes the way you'd model it. It finds the dominant flat-face
directions and applies the **smallest** rotation that puts them on X/Y/Z. An 8° placement
skew is removed, but the visible up and front are kept. Turned parts with only one flat
direction get that axis squared with no added spin. Default origin is X/Y centred with the
base on Z=0. It reports the correction per axis and the residual tilt (should be ~0°), and
writes `transform_mm` for `square_occurrence.py`. Tested on a DGX-shaped part with a
90° + 10° placement (10.0° removed, 0.0° residual), on square parts (0° change), and on a
tilted turned part (7.0° removed, no spurious spin).

### `scripts/mesh_views.py` (runs on the agent side)
```bash
.venv/bin/python scripts/mesh_views.py part_aligned.stl --out views.png
```
Four orthographic views (front, top, right, iso) with mm axes, rendered from the aligned
mesh. The report gets true square views even while the Fusion viewport still shows the
part skewed.

### `scripts/mesh_compare.py` (runs on the agent side)
```bash
.venv/bin/python scripts/mesh_compare.py original.stl rebuild.stl --tol 0.1 [--align] [--heatmap dev.ply]
```
It reports two-way surface deviation: *missing* geometry (in the original but not the rebuild)
and *extra* geometry (the reverse), as mean, p95 and max. It also compares extents and volume,
flags cm/mm mismatches, and lists the centroids of the worst regions so you know which feature
to fix. The exit code is `0` for PASS and `1` for FAIL.

### `scripts/fusion_mcp.py` (runs on the agent side)
A standard-library client for the official endpoint. Commands: `tools [--schema] [--json]`,
`run script.py [--write] [--set NAME=VALUE ...]`, `screenshot --direction ...`, `directions`, `read '<json>'`,
`docs "<pattern>"`. It does the `initialize` handshake,
keeps the `Mcp-Session-Id` header, parses the `{"message", "success"}` result envelope,
raises with Fusion's traceback on failure, and decodes screenshots to PNG. Set
`FUSION_MCP_URL` to override the default `http://127.0.0.1:27182/mcp`.

### `scripts/fusion/*.py` (runs inside Fusion via the MCP's script tool)
| Script | Writes to the design? | Purpose |
|---|---|---|
| `inspect_design.py` | No | Prints JSON: document state, units, parameters, components, bodies (bbox in mm), sketches and their constraint status, mesh bodies, occurrences, timeline errors and warnings. |
| `build_template.py` | **Yes** | A worked example: a 60×40×6 plate with a 2×2 hole pattern and filleted corners. It shows the conventions, and its helpers are meant to be copied: idempotent `param()`, `new_component()`, `centered_rectangle()`, `extrude()`, `cut_through_all()`, `fillet()`, `report()`. Run it in a new or scratch design. |
| `export_bodies_stl.py` | No (it writes a file) | Writes the selected solid bodies as a binary STL in **mm**, in world coordinates. It can also print the STL as base64 when the agent can't see Fusion's filesystem. |
| `square_occurrence.py` | **Yes (placement only)** | Applies mesh_align's `transform_mm` to the reference mesh's occurrence so it sits square at the origin, overlaying the new part. Builds the matrix from coordinate systems (no array-order ambiguity), prints before and after, and optionally captures position. Undoable. Ask the user first. |
| `export_mesh_body_stl.py` | No (it writes a file) | Writes an imported **mesh** body (the STL you want to rebuild) as a binary STL in **mm**, and prints its extents and the occurrence transform. `COORDS="local"` (default) uses the mesh component's own frame for analysis and building; `COORDS="world"` is for comparing against `export_bodies_stl.py` output. Fusion's mesh API returns cm; this script converts. |

All three expose `run(context)`, which is the convention the official MCP uses. For REPL-style
servers such as faust-machines `execute_code`, uncomment the `run(None)` line at the bottom.

---

## Testing status

| Component | Status |
|---|---|
| `mesh_analyze.py`, `mesh_compare.py` | Tested on synthetic parts: a prismatic bracket with a boss, bore and hole pattern, an X-axis turned spacer, and a rotated block. All features were recovered at the correct world coordinates, and a deliberate 0.2 mm bore error was detected and localised. The scale check catches a cm-valued file. |
| `fusion_mcp.py` | Tested against a mock server that reproduces the live protocol (session header, SSE responses, result envelope, screenshot payload). |
| `inspect_design.py` | **Run against live Fusion** (first real test, Oct 2026): worked first time. |
| `export_mesh_body_stl.py` | **Run against live Fusion** (second test): correct mm output first time. That run exposed the rotated-occurrence case, which is now handled. |
| `mesh_align.py`, `mesh_views.py` | Tested on synthetic parts (see above). |
| `square_occurrence.py` | Written against documented API (`getAsCoordinateSystem`, `setWithCoordinateSystem`, `transform2`, `snapshots.add`); **not yet run live**. Verify with a world re-export as described in the workflow. |
| `build_template.py`, `export_bodies_stl.py` | Syntax-checked and written against the documented API, **not yet run live**. Expect small fixes (deprecated names, hole/extrude direction). |
| Official MCP tools | Verified live: `fusion_mcp_read`, `fusion_mcp_execute`, `fusion_mcp_update` and `fusion_mcp_electronics_read` on server "MCP Server Adapter" 1.0.0. Names may change between Fusion builds, so the skill still tells the agent to check `tools/list`. |

### Changelog
- **First live test fixes.**
  - Added the `export_mesh_body_stl.py` mesh exporter and the `fusion_mcp.py` client.
  - Added `--expect-extents` and `--scale` to `mesh_analyze.py`.
  - Corrected the PolygonMesh, `transformBy` and Matrix3D notes in `fusion-api.md`.
  - Documented the real tool schemas, the result envelope and the WSL setup.
  - Made the intake questions a hard stop before planning.
  - Added venv setup.
- **Fourth live test fixes.**
  - New `fusion_mcp.py run --set NAME=VALUE` configures Fusion scripts from the command line. It uses the Python parser, so docstrings are never touched.
  - Scripts now ship executable.
  - `mesh_analyze.py --json` alone prints JSON to stdout.
  - Grid detection now handles gaps (for example two blocks of vents with a missing band) and reports `values`, `gaps` and `centres`.
  - `mesh_views.py --out` accepts a folder or a name without an extension.
  - `SKILL.md` now has an exact command recipe for the mesh workflow.
- **Squaring up.**
  - New `mesh_align.py`: smallest-rotation squaring to the world axes, origin placement, transform output.
  - New `mesh_views.py`: square orthographic renders.
  - New `square_occurrence.py`: squares the reference mesh in Fusion.
  - The workflow now always builds the new part square at the origin with an identity
    placement, and no longer copies a tilted placement.
  - Comparison is made against the aligned mesh.
- **Third live test fixes.**
  - Hole detection now works on coarsely tessellated holes. They were being labelled as fillets.
  - New `cylinder_groups` output reports hole patterns with count and grid pitch.
  - New `body_breakdown` output separates real bodies from tessellation fragments.
  - Symmetry results are now repeatable between runs.
  - New `--section-at` option slices at exact positions.
  - `fusion_mcp.py` gained `tools --json` and `directions`, and lists the valid screenshot directions when a value is rejected.
  - Venv and working files now go in the working folder, not the skill folder.
  - New rule: only report what was measured.
- **Second live test fixes.**
  - The mesh exporter now defaults to the mesh component's **local frame** and reports the occurrence transform, including a `rotated` flag.
  - `inspect_design.py` now reports occurrence rotation as well as offset.
  - The mesh workflow tells the agent to build in the local frame and match the occurrence placement, instead of sketching on a tilted world frame.

Please open an issue or PR with fixes from live runs.

---

## Key rules the skill enforces (summary)

- **Parametric and component-first** ("Rule #1"): create and activate a component before its
  sketches and bodies. Bodies never sit beside components.
- **User parameters drive everything** a human might change, with intent-revealing names and
  explicit units.
- **Sketches** go on origin or origin-derived planes, anchored to the origin. Constraints come
  before dimensions, every sketch is fully constrained, and each sketch has one purpose.
  Projections are avoided.
- **Feature order:** base feature → adds and cuts → holes → feature patterns and mirrors →
  shell and draft → **fillets and chamfers last**.
- **Stable references:** origin > construction from origin > sketch > body > face > edge > vertex.
  Timeline warnings count as bugs.
- **API units are cm and radians.** Parameter expressions are passed as strings (`"6 mm"`, `"plate_w/2"`).
- **Safety:** inspect first and save first. Run one operation per call and verify after each.
  Never delete user geometry or switch to direct modelling without asking. If a write times
  out, inspect before retrying.

The full reasoning and sources are in `references/`.

---

## Sources

The guidance is distilled from Autodesk's official Fusion MCP documentation and blog posts
(2026), the Fusion API reference, the AU class *"Fusion 360 – Modeling Tips from the Experts"*
(Peter Doering and Jeff Strater), AU assembly classes, Onshape's *Mastering 3D Modeling*, DFM
guidance for plastic enclosures, and FDM tolerance guides. Full list in
[`references/resources.md`](references/resources.md).

## Disclaimer

This is not an Autodesk product. Autodesk, Fusion and Fusion 360 are trademarks of
Autodesk, Inc. Generated geometry, fits and DFM values are starting points. Verify critical
dimensions, and test-print or prototype before relying on a part.
