"""
GH Agent — Claude Desktop Configuration Helper
"""

import json
import os
import sys
import subprocess


def get_config_path() -> str:
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Claude", "claude_desktop_config.json")


def get_server_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")


def get_python_path() -> str:
    try:
        result = subprocess.run(
            ["where", "python"],
            capture_output=True,
            text=True
        )
        paths = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]

        # Filter out the Windows App Store stub
        real_paths = [p for p in paths if "WindowsApps" not in p]

        if real_paths:
            return real_paths[0].replace("\\", "/")

        # Fallback: check common install locations, newest first
        common = [
            os.path.expandvars(rf"%LOCALAPPDATA%\Programs\Python\Python3{minor}\python.exe")
            for minor in range(14, 8, -1)  # 3.14 down to 3.9
        ]
        common += [
            rf"C:\Python3{minor}\python.exe"
            for minor in range(14, 8, -1)
        ]
        for path in common:
            if os.path.exists(path):
                return path.replace("\\", "/")

    except Exception:
        pass

    print("ERROR: No valid Python installation found. Please install Python from python.org.")
    sys.exit(1)


def read_config(config_path: str) -> dict:
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def write_config(config_path: str, config: dict):
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def pip_install():
    python_path = get_python_path()
    print(f"Installing dependencies using {python_path} ...")
    result = subprocess.run(
        [python_path, "-m", "pip", "install", "mcp", "fastmcp", "--quiet"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print("✓ Dependencies installed")
    else:
        print(f"ERROR: pip install failed\n{result.stderr}")
        sys.exit(1)


def install():
    config_path = get_config_path()
    server_path = get_server_path()
    python_path = get_python_path()

    config = read_config(config_path)

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    config["mcpServers"]["gh-agent"] = {
        "command": python_path,
        "args": [server_path.replace("\\", "/")]
    }

    write_config(config_path, config)
    print(f"✓ Configured")
    print(f"  Python:  {python_path}")
    print(f"  Server:  {server_path}")


def repair():
    """Re-run pip install and reconfigure Claude Desktop. Run this after upgrading Python."""
    pip_install()
    install()


def uninstall():
    config_path = get_config_path()

    if not os.path.exists(config_path):
        print("No config found")
        return

    config = read_config(config_path)

    if "mcpServers" in config and "gh-agent" in config["mcpServers"]:
        del config["mcpServers"]["gh-agent"]
        write_config(config_path, config)
        print("✓ GH Agent removed")
    else:
        print("Nothing to remove")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: configure.py install | uninstall | pip | repair")
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "install":
        install()
    elif action == "uninstall":
        uninstall()
    elif action == "pip":
        pip_install()
    elif action == "repair":
        repair()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
