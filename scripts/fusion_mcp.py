#!/usr/bin/env python3
"""
fusion_mcp.py - minimal stdlib client for Autodesk's official Fusion MCP (Streamable HTTP).
Use it when the agent harness has no native MCP connection to Fusion (e.g. OMP calling
over HTTP from WSL), instead of hand-writing the JSON-RPC handshake each session.

Protocol as observed against live Fusion (server "MCP Server Adapter" 1.0.0, Oct 2026):
  * POST JSON-RPC to http://127.0.0.1:27182/mcp, Accept: application/json, text/event-stream
  * `initialize` returns an Mcp-Session-Id header; every later request must send it
    (otherwise HTTP 400 "Missing MCP-Session-Id header"); then send notifications/initialized
  * Tools: fusion_mcp_read {queryType,...}, fusion_mcp_execute {featureType:"script",
    object:{script, readOnly}}, fusion_mcp_update {featureType: undo|redo},
    fusion_mcp_electronics_read. Tool text is a JSON envelope:
    {"message": <script stdout>, "success": true} or {"error": <traceback>, "success": false}

CLI:
  fusion_mcp.py tools [--schema] [--json]   list tools (--json = machine-readable)
  fusion_mcp.py directions                  valid screenshot directions
  fusion_mcp.py read '{"queryType":"..."}'  raw read call
  fusion_mcp.py run script.py [--write]     execute a Fusion script (read-only unless --write)
  fusion_mcp.py screenshot [--direction iso-top-right] [--out shot.png] [--width 1200 --height 900]
  fusion_mcp.py docs "PolygonMesh"          API documentation query (args vary; see --schema)
Env: FUSION_MCP_URL (default http://127.0.0.1:27182/mcp)
"""
import argparse, base64, json, os, sys, urllib.error, urllib.request

URL = os.environ.get("FUSION_MCP_URL", "http://127.0.0.1:27182/mcp")


class FusionMCP:
    def __init__(self, url=URL, timeout=300):
        self.url, self.timeout, self.sid, self._id = url, timeout, None, 0
        r = self._post({"jsonrpc": "2.0", "id": self._next(), "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                   "clientInfo": {"name": "fusion360-skill", "version": "1"}}})
        self.server = (r or {}).get("result", {}).get("serverInfo")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _next(self):
        self._id += 1
        return self._id

    def _post(self, body):
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.sid:
            h["Mcp-Session-Id"] = self.sid
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self.sid = r.headers.get("Mcp-Session-Id") or self.sid
                raw = r.read().decode()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:500]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"cannot reach Fusion MCP at {self.url}: {e.reason}. Is Fusion running "
                               "with Preferences > General > API > Fusion MCP Server enabled?")
        if not raw:
            return None
        if raw.lstrip().startswith(("event:", "data:")):
            data = [l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
            return json.loads(data[-1]) if data else None
        return json.loads(raw)

    def rpc(self, method, params=None):
        r = self._post({"jsonrpc": "2.0", "id": self._next(), "method": method, "params": params or {}})
        if "error" in r:
            raise RuntimeError(f"JSON-RPC error: {r['error']}")
        return r["result"]

    def tools(self):
        return self.rpc("tools/list")["tools"]

    def call(self, name, args):
        """Returns (envelope_or_text, raw_content_list)."""
        res = self.rpc("tools/call", {"name": name, "arguments": args})
        content = res.get("content", [])
        text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
        try:
            env = json.loads(text) if text else {}
        except json.JSONDecodeError:
            env = {"message": text}
        return env, content

    def run_script(self, source, read_only=True):
        """Execute a Fusion Python script (must define run(context)). Returns stdout.
        Raises on failure with Fusion's traceback. If stdout is JSON it is parsed."""
        env, _ = self.call("fusion_mcp_execute",
                           {"featureType": "script", "object": {"script": source, "readOnly": read_only}})
        if not env.get("success", "error" not in env):
            raise RuntimeError("Fusion script failed:\n" + str(env.get("error", env)))
        out = env.get("message", "")
        try:
            return json.loads(out)
        except (json.JSONDecodeError, TypeError):
            return out

    def read(self, **args):
        env, content = self.call("fusion_mcp_read", args)
        return env, content

    def enum_values(self, tool, prop):
        """Allowed values for a property anywhere in a tool's input schema (from tools/list)."""
        found = set()

        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == prop and isinstance(v, dict) and "enum" in v:
                        found.update(v["enum"])
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        for t in self.tools():
            if t["name"] == tool:
                walk(t.get("inputSchema", {}))
        return sorted(found)

    def screenshot(self, out, direction="iso-top-right", width=1200, height=900):
        """Valid directions on the tested build include iso-top-right, front, top, right
        (plain "iso" is rejected). On a validation error the allowed list is fetched and shown."""
        _, content = self.read(queryType="screenshot", direction=direction, width=width, height=height)
        for c in content:
            if c.get("data"):
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(base64.b64decode(c["data"]))
                return out
        text = " ".join(c.get("text", "") for c in content)
        if "direction" in text and "enum" in text:
            allowed = self.enum_values("fusion_mcp_read", "direction")
            raise RuntimeError(f"invalid direction '{direction}'. Allowed: {', '.join(allowed) or '(see tools --schema)'}")
        raise RuntimeError(f"no image in screenshot result: {text[:300]}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tools"); t.add_argument("--schema", action="store_true")
    t.add_argument("--json", action="store_true", help="machine-readable tools/list output")
    r = sub.add_parser("read"); r.add_argument("args")
    x = sub.add_parser("run"); x.add_argument("script"); x.add_argument("--write", action="store_true")
    s = sub.add_parser("screenshot"); s.add_argument("--direction", default="iso-top-right",
        help="e.g. iso-top-right, front, top, right (run 'directions' for the full list)")
    s.add_argument("--out", default="fusion_shot.png"); s.add_argument("--width", type=int, default=1200)
    s.add_argument("--height", type=int, default=900)
    sub.add_parser("directions", help="list valid screenshot directions")
    d = sub.add_parser("docs"); d.add_argument("pattern"); d.add_argument("--extra", default="{}",
                                                                         help="extra JSON args")
    a = ap.parse_args()
    f = FusionMCP()
    if a.cmd == "tools" and a.json:
        print(json.dumps(f.tools(), indent=1))
    elif a.cmd == "directions":
        print("\n".join(f.enum_values("fusion_mcp_read", "direction")))
    elif a.cmd == "tools":
        for tool in f.tools():
            print(f"== {tool['name']}\n{tool.get('description', '')[:400]}")
            if a.schema:
                print(json.dumps(tool.get("inputSchema", {}), indent=1))
    elif a.cmd == "read":
        env, content = f.read(**json.loads(a.args))
        print(json.dumps(env, indent=1)[:20000])
    elif a.cmd == "run":
        out = f.run_script(open(a.script).read(), read_only=not a.write)
        print(json.dumps(out, indent=1) if not isinstance(out, str) else out)
    elif a.cmd == "screenshot":
        print(f.screenshot(a.out, a.direction, a.width, a.height))
    elif a.cmd == "docs":
        env, content = f.read(queryType="apiDocumentation", searchPattern=a.pattern, **json.loads(a.extra))
        # results may arrive as extra content items rather than in the envelope message
        print(json.dumps(env, indent=1)[:5000])
        for c in content[1:]:
            print(c.get("text") or json.dumps(c)[:5000])


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(e, file=sys.stderr); sys.exit(1)
