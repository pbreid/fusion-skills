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

### What the desktop MCP gives you
Tool names are discovered at connection time. Observed capabilities: query the active
document/design, execute Fusion **Python** API scripts in the live session (with a
read-only option - an adapter hint, not a sandbox), viewport **screenshots** from named
directions (current, top, front, iso...), and search of current **API documentation**.
Autodesk's own sample (github.com/AutodeskFusion360/FusionMCPSample) uses the tool names
`execute_api_script`, `get_screenshot`, `get_api_documentation`. Scripts follow the add-in
convention `def run(context): ...`; output via `print`.

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
