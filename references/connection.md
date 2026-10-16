# Connecting to Fusion

Researched October 2026. Re-check if tools look different - Autodesk's MCP uses dynamic tooling.

## The three official Autodesk Fusion MCP servers

| Server | Where it runs | Use it for |
|---|---|---|
| **Autodesk Fusion MCP** (desktop) | Local, inside the running Fusion client; Streamable HTTP; no auth; desktop only (not the web client) | **Default for this skill** - real-time modelling in the user's open design |
| Autodesk Fusion Data MCP | Autodesk cloud | Hubs, projects, folders, permissions, metadata - not geometry |
| Autodesk Fusion Compute MCP (public beta, Sept 2026) | Autodesk cloud Fusion sessions; endpoint `https://developer.api.autodesk.com/da/v3/mcp/fusion` | Headless/parallel agents without the desktop. Needs Autodesk account, active Fusion licence and a Fusion Team hub. Beta limits: 2 concurrent sessions, 1 h max, 15 min idle stop; sessions are temporary - save to Fusion Team or export before ending. Exposes the TypeScript API behind one `execute` tool. |

### Enabling the desktop MCP
1. Fusion: *Preferences > General > API* -> tick **Fusion MCP Server**, note the port (default `27182`).
2. Client config (any Streamable-HTTP MCP client - OMP, Claude Code, Cursor, VS Code, Claude Desktop):
   ```json
   { "mcpServers": { "fusion": { "url": "http://127.0.0.1:27182/mcp" } } }
   ```
   Some clients want the bare `http://127.0.0.1:27182`; try both. Claude Code:
   `claude mcp add --transport http fusion http://127.0.0.1:27182/mcp`.
   Claude Desktop also has an official Autodesk Fusion connector in its directory.
3. Fusion must be running **before** the client connects.

### What the desktop MCP gives you (verified live, Oct 2026)
Server identifies as **"MCP Server Adapter" 1.0.0**. Tool names may change between Fusion
builds, so list them at connect time. On the build tested, they were:

| Tool | Arguments | Use |
|---|---|---|
| `fusion_mcp_read` | `queryType` (required) + query-specific args | Design queries; `queryType: "screenshot"` with `direction` (confirmed values: `iso-top-right`, `front`, `top`, `right`; plain `iso` is rejected; `fusion_mcp.py directions` lists all), `width`, `height` returns a base64 PNG; `queryType: "apiDocumentation"` with `searchPattern` (plus optional `apiCategory`, `filter`) searches the API docs |
| `fusion_mcp_execute` | `featureType: "script"`, `object: {script: "<python source>", readOnly: true\|false}` | Run a Fusion Python script. The key is **`script`**, not `code` |
| `fusion_mcp_update` | `featureType: "undo" \| "redo"` | Undo/redo |
| `fusion_mcp_electronics_read` | | Electronics documents only |

Check the exact enums with `tools/list` (`inputSchema`). Guessed values such as
`operation: "document_summary"` fail validation.

**Script results come back as a JSON envelope inside the text content:**
`{"message": "<everything the script printed>", "success": true}` or
`{"error": "<Python traceback>", "success": false}`. Print JSON from scripts and parse it
twice: the envelope, then `message`. Scripts define `def run(context):`; module-level code
also runs. `readOnly` is an adapter hint, not a sandbox.

**Protocol details (for clients without native MCP support):**
- POST JSON-RPC to `http://127.0.0.1:27182/mcp` with
  `Accept: application/json, text/event-stream`. Responses may be SSE (`event:`/`data:` lines).
- `initialize` returns an **`Mcp-Session-Id` response header**. Send it on every later
  request, including `notifications/initialized` (answered 202). Without it you get
  HTTP 400 `{"error": "Missing MCP-Session-Id header"}`.
- **Don't hand-roll this each session.** Use `scripts/fusion_mcp.py` (stdlib only):
  ```bash
  python3 scripts/fusion_mcp.py tools --schema
  python3 scripts/fusion_mcp.py run scripts/fusion/inspect_design.py          # read-only
  python3 scripts/fusion_mcp.py run my_build_step.py --write
  python3 scripts/fusion_mcp.py screenshot --direction iso-top-right --out shot.png
  python3 scripts/fusion_mcp.py docs "PolygonMesh"
  ```
  or `from fusion_mcp import FusionMCP; f = FusionMCP(); f.run_script(src, read_only=False)`.
  `run_script` raises on `success: false` with Fusion's traceback and returns parsed JSON stdout.
- Better still, register the server natively in the agent (OMP / Claude Code MCP config)
  so the tools appear as first-class tool calls.

Autodesk's sample add-in (github.com/AutodeskFusion360/FusionMCPSample) uses different names
(`execute_api_script`, `get_screenshot`, `get_api_documentation`), which is another reason
to read `tools/list` rather than assume.

Autodesk's guidance for agents: start with a minimal working version, test early with
heavier inputs (agents miss performance options such as deferred compute unless asked),
correct one behaviour at a time, use screenshots as requirements, ask the agent to test
through the MCP, and save before running modification scripts.

## Locality problem (agent not on the Fusion machine)

The desktop MCP binds to localhost. Fusion runs on Windows/macOS only. If the coding
agent runs elsewhere (Linux box, devcontainer, remote server):
- Run the agent (or just the MCP client) on the Fusion machine, or
- Tunnel it: `ssh -L 27182:127.0.0.1:27182 user@fusion-pc` from the agent host, or
- Use the community **faust-machines/fusion360-mcp-server**, which supports LAN binding
  (`FUSION_MCP_HOST=0.0.0.0` on the Fusion host; `uvx fusion360-mcp-server --mode socket
  --host <fusion-ip>` on the agent host). Its socket has **no auth** - trusted LAN only.
Files written by Fusion scripts land on the Fusion machine; plan file transfer (shared
folder, or base64 in the script output for small payloads).

**Windows + WSL** (agent in WSL, Fusion on the Windows host) works well. `127.0.0.1:27182`
is usually reachable from WSL2 with mirrored networking. If it isn't, use the Windows host
IP or enable mirrored mode. Files exchange through `C:\Users\Public\`, which WSL sees as
`/mnt/c/Users/Public/`. Fusion scripts write there and the agent copies from there.

## Community fallbacks (if the official MCP is unavailable)

| Project | Notes |
|---|---|
| faust-machines/fusion360-mcp-server | `uvx fusion360-mcp-server --mode socket` + add-in on TCP 9876. ~89 typed tools (sketch, extrude, revolve, loft, shell, holes, patterns, sheet metal, joints, parameters, measure, interference, import_mesh, STL/STEP/F3D export, CAM) plus `execute_code`. Notes: one operation per call - batching crashes the add-in; 30 s timeout; logs to `~/fusion360mcp.log`; all units cm. |
| prim-design/fusion-mcp | stdio server + TCP add-in, 51 tools, `execute_python` escape hatch, main-thread dispatch via CustomEvent. |
| AuraFriday Fusion-360-MCP-Server | Via MCP-Link server; generic API-path execution + Python; on the Autodesk App Store. |
| hitsmaxft/fusion-mcp-client | CLI/library *for the official endpoint*: `snapshot`, guarded `run --write --expect-document`, `screenshot`, `bundle` export. Useful pattern: refuse writes if document id/version changed. |

Typed tools are fine for simple steps, but for anything that needs constraints, parameter
expressions or exact references, write an API script (`execute_code`/script tool) using
`scripts/fusion/build_template.py` helpers.

## Pre-flight checklist
- [ ] Fusion running, Design workspace active, the intended document is in front.
- [ ] Inspect snapshot taken; document saved (or user confirms it's a scratch doc).
- [ ] Licence check: **Fusion for Personal Use** limits you to 10 active editable documents
      and lacks some features (notably *prismatic* Convert Mesh). Ask which licence if a
      workflow depends on it.
- [ ] Decide where exported files go and how the agent will read them.
