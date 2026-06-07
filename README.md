# GH Agent — Setup Guide

GH Agent connects your live Grasshopper canvas to Claude Desktop (or any MCP-compatible AI client).
Claude can read your canvas, inspect errors, and read Python scripts — all from the chat window.

---

## HOW IT WORKS

```
Rhino / Grasshopper
  └── GH component  →  posts canvas data  →  mcp_server.py (port 8000)
                                                    ↕ MCP protocol (stdio)
                                              Claude Desktop
```

The GH component keeps your canvas in sync with the server.
You do all your AI conversation in Claude Desktop — no panels, no buttons, just chat.

---

## FIRST TIME SETUP

### 1. Install the MCP library
Open Command Prompt and run:
```
pip install mcp fastmcp
```

### 2. Note the full path to mcp_server.py
Example: `C:\Users\yourname\Desktop\gh-agent\mcp_server.py`
You'll need this in the next step.

### 3. Add GH Agent to Claude Desktop
Open Claude Desktop → Settings → Developer → Edit Config

This opens a file called `claude_desktop_config.json`. Add the following:
```json
{
  "mcpServers": {
    "gh-agent": {
      "command": "python",
      "args": ["C:/Users/yourname/Desktop/gh-agent/mcp_server.py"]
    }
  }
}
```
Replace the path with your actual path. Use forward slashes.
Save the file and restart Claude Desktop.

### 4. Verify the connection
In Claude Desktop, click the tools icon (hammer) in the chat input.
You should see the GH Agent tools listed: get_canvas_overview, get_nodes_with_errors, etc.

---

## SETTING UP THE GRASSHOPPER COMPONENT

1. Open Rhino 8 and Grasshopper
2. Add a **Python 3 Script** component to the canvas
3. Double-click to open the editor
4. Delete existing code and paste the contents of `gh_component.py`
5. Close the editor

### Add one input
Right-click the component → Manage Parameters → add:
- `run` (Item, Boolean)

Connect a **Toggle** or **Button** to `run`.

### The output
Connect a **Panel** to output `a` to see the sync status.

---

## USING GH AGENT

1. Make sure Claude Desktop is running and GH Agent tools are visible
2. Open your Grasshopper canvas
3. The component syncs automatically whenever it recalculates
4. Open Claude Desktop and just ask naturally:

**Example prompts:**
- "What is on my canvas right now?"
- "I have errors — what is wrong and how do I fix them?"
- "Explain what this canvas does"
- "Write a Python script that takes a list of points and returns the average"
- "I want to create a waffle structure from a surface, what components do I need?"

Claude will call the canvas tools automatically when needed.

---

## WORKS WITH OTHER AI CLIENTS

Any MCP-compatible client works with the same `mcp_server.py`:
- **Claude Desktop** ✓
- **Cursor** ✓
- **Windsurf** ✓
- **ChatGPT** ✗ (does not support MCP)

Each client handles its own API key and billing. You do not manage any API keys here.

---

## TROUBLESHOOTING

**Tools not showing in Claude Desktop**
→ Check the path in `claude_desktop_config.json` is correct and uses forward slashes
→ Restart Claude Desktop after editing the config

**"Could not reach MCP server" in GH**
→ Claude Desktop has not launched the server yet
→ Try sending a message in Claude Desktop to wake it up
→ Or run `python mcp_server.py` manually in Command Prompt to test

**Canvas not updating**
→ The GH component runs on Grasshopper's normal recalculation cycle
→ If it seems stale, press the Toggle to force a sync
