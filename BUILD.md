# GH Agent — How to Build the Installer

This guide explains how to compile the Grasshopper component (`.gha`) and package
everything into `GHAgent_Setup.exe` using Inno Setup 6.

---

## What you need

1. **.NET SDK 7** (targets Rhino 8) — to build the `.gha` from `plugin/`
2. **Inno Setup 6** — free, https://jrsoftware.org/isdl.php — to compile the installer
3. The repo source (this folder)

---

## Repo layout

```
gh-agent/
  plugin/
    GHAgent.csproj         <- .NET build config (outputs GHAgent.gha)
    GHAgentComponent.cs
    GHAgentInfo.cs
  server/
    mcp_server.py
    configure.py
  installer/
    setup.iss              <- Inno Setup script
  assets/
    icon.ico
  README.md
  build.bat                <- one-shot: builds .gha then installer
  dist/                    <- installer output lands here (gitignored)
```

---

## Build

**One-shot:** run `build.bat` from the repo root. It builds the `.gha` (Release)
then compiles the installer; `GHAgent_Setup.exe` lands in `dist/`.

**Manual:**
1. `dotnet build "plugin\GHAgent.csproj" -c Release`
   Make sure the output `GHAgent.gha` ends up at `plugin\GHAgent.gha`
   (this is what `setup.iss` packages).
2. Open `installer\setup.iss` in Inno Setup, or run
   `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\setup.iss`.
3. Find `GHAgent_Setup.exe` in `dist/`.

> **Path note (must fix before first build):** `installer/setup.iss` was carried over
> from the old flat layout and its `Source:` lines still point at files as if they sit
> next to the `.iss` (`mcp_server.py`, `configure.py`, `README.md`). In this layout those
> live in `server/` and the repo root. Either add `SourceDir=..` under `[Setup]` and
> rewrite the `Source:` paths (`server\mcp_server.py`, `server\configure.py`, `README.md`,
> `plugin\GHAgent.gha`), or stage the files into one folder before compiling.

Before tagging a release, also update in `setup.iss`:
- `AppVersion`
- `AppPublisherURL` / `AppSupportURL` (currently `https://yourwebsite.com`)
- the `yourwebsite.com` references in the welcome/finish page text

---

## What the installer does

**Install:**
1. Checks Python is installed — errors and stops if not
2. Checks Claude Desktop is installed — warns if not found
3. Copies `mcp_server.py` + `configure.py` to `%APPDATA%\GH Agent\`
4. Copies `GHAgent.gha` to `%APPDATA%\Grasshopper\Libraries\`
5. Runs `configure.py pip` → `pip install mcp fastmcp`
6. Runs `configure.py install` → writes the MCP entry into `claude_desktop_config.json`

**Uninstall:**
1. `configure.py uninstall` → removes the entry from `claude_desktop_config.json`
2. Deletes the GH Agent files and the installed `.gha`
3. Removes Start Menu shortcuts

---

## Updating for a new version

If you change `mcp_server.py` or the component:
1. Bump `AppVersion` in `setup.iss`
2. Rebuild → new `GHAgent_Setup.exe`
3. Upload it to the GitHub **Releases** page (the README links users there)

---

## Notes

- Installs to `%APPDATA%` — no admin rights required
- Windows 10 / 11; Mac would need a separate packaging approach
