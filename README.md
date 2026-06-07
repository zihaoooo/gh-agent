# GH Agent

GH Agent connects a live Grasshopper canvas to Claude Desktop (or any MCP-compatible AI client). Claude can read your canvas, inspect errors, and write Python scripts — all from the chat window.

End users: download the installer from the [Releases](https://github.com/zihaoooo/gh-agent/releases) page.

---

## How it works

```
Rhino / Grasshopper
  └── GHAgentComponent.cs  ──POST /canvas──▶  mcp_server.py :8000
                            ◀──GET /commands──  (HTTP, localhost only)
                                                      │
                                               MCP stdio protocol
                                                      │
                                              Claude Desktop
```

Three processes, two channels:

1. **The GH component** (`plugin/`) is a compiled `.gha` that runs inside Grasshopper. It serializes the canvas on a 5-second timer and POSTs the data to a local HTTP server. It also polls `/commands` every 2 seconds to receive and execute actions queued by Claude (e.g. adding a component, injecting a Python script).

2. **The MCP server** (`server/mcp_server.py`) runs two things in one process: a small `HTTPServer` on port 8000 (background thread) that accepts canvas data and serves command queues, and a `FastMCP` stdio server that Claude Desktop connects to. The HTTP layer is the bridge between Grasshopper and MCP.

3. **Claude Desktop** connects to `mcp_server.py` via MCP stdio and calls tools to read or modify the canvas. No API keys or browser extension needed — just the MCP config.

---

## Repo structure

```
gh-agent/
├── plugin/
│   ├── GHAgentComponent.cs   — Grasshopper component: canvas serializer + command executor
│   ├── GHAgentInfo.cs        — plugin metadata (name, version, icon)
│   └── GHAgent.csproj        — .NET build config, targets Rhino 8 SDK
├── server/
│   ├── mcp_server.py         — MCP server + HTTP bridge + tool definitions + component library
│   └── configure.py          — CLI helper: detects Python, writes claude_desktop_config.json
├── installer/
│   └── setup.iss             — Inno Setup script: bundles .gha, mcp_server.py, configure.py
├── assets/
│   └── icon.ico
└── dist/                     — gitignored; built artifacts go here
```

---

## MCP tools

| Tool | Type | Description |
|---|---|---|
| `get_canvas_overview` | read | All nodes: type, name, nickname, error flag |
| `get_nodes_with_errors` | read | Only nodes with errors + messages |
| `get_node_error` | read | Full error message for a single node |
| `get_node_details` | read | Full JSON for a single node including position and script |
| `get_python_script` | read | Source code of a Python 3 Script component |
| `get_component_library` | read | Curated list of addable components with descriptions |
| `add_component` | write | Queues a component-add command; placed near a reference node |
| `write_python_script` | write | Queues a script-inject command into a Python 3 Script component |

Write tools work via the command queue: Claude pushes a command, the GH component picks it up within 2 seconds on its poll cycle.

---

## Building

**Plugin (C#)**

Requires Rhino 8 and the Grasshopper SDK. Build with Visual Studio or `dotnet build`:

```
cd plugin
dotnet build -c Release
```

Output: `plugin/bin/Release/net48/GHAgent.gha`

**Installer**

Requires [Inno Setup 6](https://jrsoftware.org/isinfo.php). Open `installer/setup.iss` and run Build → Compile. The `.exe` lands in `dist/`.

The installer: copies `GHAgent.gha` to the Grasshopper Libraries folder, copies `mcp_server.py` and `configure.py` to `%APPDATA%\GHAgent\`, runs `configure.py pip` to install `mcp` and `fastmcp`, then runs `configure.py install` to write `claude_desktop_config.json`.

---

## Extending the component library

`COMPONENT_LIBRARY` in `mcp_server.py` is the only place that needs editing to add new addable components. Each entry needs a `gh_name` that matches what Grasshopper's `ComponentServer` recognizes. The `.gha` does not need to be recompiled.

---

## License

MIT
