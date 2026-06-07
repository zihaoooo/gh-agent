"""
GH Agent — MCP Server
Exposes Grasshopper canvas tools to any MCP-compatible AI client (Claude Desktop, Cursor, etc.)

HOW IT WORKS:
- Claude Desktop connects to this process via stdio (MCP protocol)
- The GH component posts canvas data to a small HTTP server running in the background (port 8000)
- The GH component polls /commands every 2 seconds and executes any queued commands
- Claude can then call the tools below to read your live canvas or add/edit components

SETUP (Claude Desktop):
Add this to your claude_desktop_config.json:
{
  "mcpServers": {
    "gh-agent": {
      "command": "python",
      "args": ["C:/path/to/mcp_server.py"]
    }
  }
}
"""

import threading
import json
import uuid
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from mcp.server.fastmcp import FastMCP


# ─────────────────────────────────────────────
# SHARED STATE
# Canvas data posted by the GH component lives here.
# Command queue is polled by the GH component every 2 seconds.
# ─────────────────────────────────────────────

canvas_state = {}
command_queue = deque()
command_results = {}
state_lock = threading.Lock()


# ─────────────────────────────────────────────
# COMPONENT LIBRARY
# Curated list of Grasshopper components Claude can add to the canvas.
# gh_name must match what Grasshopper's ComponentServer recognizes.
# Extend this list to support more components without touching the .gha.
# ─────────────────────────────────────────────

COMPONENT_LIBRARY = {
    "voronoi": {
        "display_name": "Voronoi",
        "gh_name": "Voronoi",
        "description": "Creates a 2D Voronoi diagram from points. Good for planting patterns, cell-based site analysis.",
        "category": "Mesh"
    },
    "contour_evenly_spaced": {
        "display_name": "Contour (Evenly Spaced)",
        "gh_name": "Contour",
        "description": "Cuts a surface or mesh with evenly spaced parallel planes. Use for topographic contours at regular intervals, e.g. every 1 meter. Inputs: Shape, Direction, Distance.",
        "category": "Surface"
    },
    "delaunay_mesh": {
        "display_name": "Delaunay Mesh",
        "gh_name": "Delaunay Mesh",
        "description": "Creates a triangulated mesh from points using Delaunay triangulation. Good for terrain modeling from survey points.",
        "category": "Mesh"
    },
    "populate_2d": {
        "display_name": "Populate 2D",
        "gh_name": "Populate 2D",
        "description": "Scatters points randomly within a region. Good for randomized planting layouts.",
        "category": "Vector"
    },
    "populate_geometry": {
        "display_name": "Populate Geometry",
        "gh_name": "Populate Geometry",
        "description": "Scatters points on a surface or mesh. Good for planting on terrain.",
        "category": "Vector"
    },
    "rectangular_grid": {
        "display_name": "Rectangular Grid",
        "gh_name": "Square Grid",
        "description": "Creates a rectangular grid of cells and points. Good for regular planting grids and paving layouts.",
        "category": "Vector"
    },
    "hexagonal_grid": {
        "display_name": "Hexagonal Grid",
        "gh_name": "Hexagonal",
        "description": "Creates a hexagonal grid. Good for honeycomb paving and ecological planting patterns.",
        "category": "Vector"
    },
    "offset_curve": {
        "display_name": "Offset Curve",
        "gh_name": "Offset Curve",
        "description": "Offsets a curve by a distance. Good for setbacks, buffers, and path widths.",
        "category": "Curve"
    },
    "divide_curve": {
        "display_name": "Divide Curve",
        "gh_name": "Divide Curve",
        "description": "Divides a curve into equal segments and returns the points. Good for placing trees or lights along a path.",
        "category": "Curve"
    },
    "perp_frames": {
        "display_name": "Perpendicular Frames",
        "gh_name": "Perp Frames",
        "description": "Creates perpendicular frames along a curve. Good for road cross-sections and path profiles.",
        "category": "Curve"
    },
    "extrude": {
        "display_name": "Extrude",
        "gh_name": "Extrude",
        "description": "Extrudes a curve or surface along a vector. Good for walls, raised planters, and building masses.",
        "category": "Surface"
    },
    "boundary_surface": {
        "display_name": "Boundary Surface",
        "gh_name": "Boundary Surfaces",
        "description": "Creates a flat surface from a closed planar curve. Good for paving areas and planting beds.",
        "category": "Surface"
    },
    "area": {
        "display_name": "Area",
        "gh_name": "Area",
        "description": "Calculates the area and centroid of a surface or closed curve. Good for site area calculations.",
        "category": "Surface"
    },
    "move": {
        "display_name": "Move",
        "gh_name": "Move",
        "description": "Moves geometry by a vector. Good for shifting elements in X, Y, or Z.",
        "category": "Transform"
    },
    "scale": {
        "display_name": "Scale",
        "gh_name": "Scale",
        "description": "Scales geometry from a center point. Good for resizing site elements.",
        "category": "Transform"
    },
    "series": {
        "display_name": "Series",
        "gh_name": "Series",
        "description": "Generates a sequence of numbers with a start, step, and count. Good for evenly spaced elevation values.",
        "category": "Sets"
    },
    "range": {
        "display_name": "Range",
        "gh_name": "Range",
        "description": "Divides a domain into equally spaced values. Good for normalized ranges and gradient inputs.",
        "category": "Sets"
    },
    "number_slider": {
        "display_name": "Number Slider",
        "gh_name": "Number Slider",
        "description": "An interactive slider for controlling a number value. The most common parametric control.",
        "category": "Params"
    },
    "panel": {
        "display_name": "Panel",
        "gh_name": "Panel",
        "description": "Displays data or holds a text or number value. Good for notes and inspecting output.",
        "category": "Params"
    },
}


# ─────────────────────────────────────────────
# HTTP SERVER (port 8000)
# Receives canvas data from the GH component.
# Serves pending commands to the GH component.
# Runs in a background thread — invisible to the user.
# ─────────────────────────────────────────────

class CanvasHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/canvas":
            self._handle_canvas()
        elif self.path == "/command_result":
            self._handle_command_result()
        else:
            self._respond(404, {"error": "Not found"})

    def do_GET(self):
        if self.path == "/commands":
            self._handle_get_commands()
        else:
            self._respond(404, {"error": "Not found"})

    def _handle_canvas(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            with state_lock:
                canvas_state["nodes"] = body.get("nodes", [])
            self._respond(200, {"status": "ok", "node_count": len(canvas_state["nodes"])})
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _handle_get_commands(self):
        with state_lock:
            pending = list(command_queue)
            command_queue.clear()
        self._respond(200, pending)

    def _handle_command_result(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            with state_lock:
                command_results[body.get("command_id", "")] = body
            self._respond(200, {"status": "ok"})
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def start_canvas_server():
    server = HTTPServer(("127.0.0.1", 8000), CanvasHandler)
    server.serve_forever()

threading.Thread(target=start_canvas_server, daemon=True).start()


# ─────────────────────────────────────────────
# MCP SERVER
# Claude Desktop connects here via stdio.
# Tools below are discovered and called automatically.
# ─────────────────────────────────────────────

mcp = FastMCP("GH Agent")


# ── READ TOOLS ────────────────────────────────

@mcp.tool()
def get_canvas_overview() -> str:
    """
    Get a summary of all components currently on the Grasshopper canvas.
    Use this first to understand what is on the canvas before diving deeper.
    """
    if not canvas_state:
        return "No canvas data available. Make sure the GH component is on the canvas and has run at least once."
    nodes = canvas_state.get("nodes", [])
    if not nodes:
        return "Canvas is empty."
    lines = []
    for node in nodes:
        error_flag = " ⚠️ ERROR" if node.get("has_error") else ""
        lines.append(
            f"- [{node['type']}] {node['name']} (nickname: {node['nickname']}) | ID: {node['id']}{error_flag}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_nodes_with_errors() -> str:
    """
    Get only the nodes that currently have errors on the canvas.
    Use this when debugging to quickly identify what is broken.
    """
    nodes = canvas_state.get("nodes", [])
    error_nodes = [n for n in nodes if n.get("has_error")]
    if not error_nodes:
        return "No errors found on the canvas."
    lines = []
    for node in error_nodes:
        lines.append(f"- [{node['type']}] {node['name']} | ID: {node['id']}")
        for msg in node.get("messages", []):
            lines.append(f"  Error: {msg}")
    return "\n".join(lines)


@mcp.tool()
def get_node_error(node_id: str) -> str:
    """
    Get the specific error message for a single node.
    Use this after get_nodes_with_errors to read the full error detail.

    Args:
        node_id: The unique GUID of the node (visible in get_nodes_with_errors output)
    """
    nodes = canvas_state.get("nodes", [])
    for node in nodes:
        if node["id"] == node_id:
            if node.get("has_error"):
                return "\n".join(node.get("messages", ["Unknown error"]))
            return "No errors found on this node."
    return "Node not found. Check the node ID."


@mcp.tool()
def get_node_details(node_id: str) -> str:
    """
    Get full details about a specific node: type, position, and any script.
    Use this when you need to understand exactly what a component is doing.

    Args:
        node_id: The unique GUID of the node
    """
    nodes = canvas_state.get("nodes", [])
    for node in nodes:
        if node["id"] == node_id:
            return json.dumps(node, indent=2)
    return "Node not found. Check the node ID."


@mcp.tool()
def get_python_script(node_id: str) -> str:
    """
    Get the Python source code inside a Python 3 Script component.
    Use this when the user asks you to read, fix, or improve a script.

    Args:
        node_id: The unique GUID of the Python 3 Script component
    """
    nodes = canvas_state.get("nodes", [])
    for node in nodes:
        if node["id"] == node_id:
            script = node.get("script")
            if script:
                return script
            return "No script found. This may not be a Python 3 Script component."
    return "Node not found. Check the node ID."


# ── WRITE TOOLS ───────────────────────────────

@mcp.tool()
def get_component_library() -> str:
    """
    Get the full list of Grasshopper components that can be added to the canvas.
    Always call this before add_component so you can pick the right key and
    explain the options to the user when similar ones exist (e.g. two Contour types).
    """
    lines = []
    for key, comp in COMPONENT_LIBRARY.items():
        lines.append(
            f"- key: \"{key}\"\n"
            f"  name: {comp['display_name']}\n"
            f"  category: {comp['category']}\n"
            f"  description: {comp['description']}"
        )
    return "\n\n".join(lines)


@mcp.tool()
def add_component(component_key: str, near_node_id: str = "") -> str:
    """
    Add a Grasshopper component to the canvas.

    Before calling this:
    1. Call get_component_library to see available components and pick the right key.
    2. Call get_canvas_overview to find a near_node_id — place the new component
       near the node the user is asking about.
    3. Explain to the user what you are adding and why, especially when similar
       options exist (like two Contour components).

    The component will be placed 220 units to the right of near_node_id.
    If no near_node_id is provided, it is placed at a default canvas position.

    Args:
        component_key: The key from get_component_library (e.g. "voronoi", "contour_evenly_spaced")
        near_node_id:  Optional. GUID of a node to place the new component next to.
    """
    if component_key not in COMPONENT_LIBRARY:
        available = ", ".join(COMPONENT_LIBRARY.keys())
        return f"Unknown component key '{component_key}'. Available keys: {available}"

    comp = COMPONENT_LIBRARY[component_key]
    command_id = str(uuid.uuid4())

    with state_lock:
        command_queue.append({
            "type": "add_component",
            "command_id": command_id,
            "gh_name": comp["gh_name"],
            "gh_category": comp["category"],
            "display_name": comp["display_name"],
            "near_node_id": near_node_id,
        })

    return (
        f"Command queued: adding '{comp['display_name']}' to the canvas. "
        f"It will appear within 2 seconds. Command ID: {command_id}"
    )


@mcp.tool()
def write_python_script(node_id: str, code: str) -> str:
    """
    Write Python code directly into a Python 3 Script component on the canvas.

    Before calling this:
    1. Call get_canvas_overview to confirm the node_id is a Python3Component.
    2. Show the code to the user in chat and explain what it does.
    3. Only inject after the user confirms.

    Args:
        node_id: The GUID of the Python 3 Script component.
        code:    The complete Python script to write into the component.
    """
    command_id = str(uuid.uuid4())
    with state_lock:
        command_queue.append({
            "type": "set_script",
            "command_id": command_id,
            "node_id": node_id,
            "code": code,
        })
    return (
        f"Command queued: writing script into component {node_id}. "
        f"It will update within 2 seconds. Command ID: {command_id}"
    )


# ─────────────────────────────────────────────
# ENTRY POINT
# Claude Desktop launches this as a subprocess
# and communicates via stdio
# ─────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
