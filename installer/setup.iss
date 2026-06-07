; GH Agent — Inno Setup Installer Script
; Compile this with Inno Setup 6 to produce GHAgent_Setup.exe

[Setup]
AppName=GH Agent
AppVersion=1.0
AppPublisher=GH Agent
AppPublisherURL=https://yourwebsite.com
AppSupportURL=https://yourwebsite.com
UninstallDisplayName=GH Agent

DefaultDirName={userappdata}\GH Agent
DisableDirPage=yes

DefaultGroupName=GH Agent
DisableProgramGroupPage=yes

OutputDir=dist
OutputBaseFilename=GHAgent_Setup
SetupIconFile=assets\icon.ico

Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
WizardSizePercent=120


[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"


[Messages]
WelcomeLabel1=Welcome to GH Agent
WelcomeLabel2=GH Agent connects your Grasshopper canvas to Claude Desktop, giving you AI assistance directly inside your design workflow.%n%nThis wizard will:%n  • Install the GH Agent server%n  • Add the GH Agent component to Grasshopper%n  • Configure Claude Desktop automatically%n%nClick Next to continue.
FinishedHeadingLabel=GH Agent is ready
FinishedLabel=Installation complete.%n%nNext steps:%n%n1. Restart Rhino — the GH Agent component will appear in your toolbar%n2. Open Claude Desktop%n3. Visit yourwebsite.com to get the GH Agent Project%n%nDrop the GH Agent component on your canvas and start chatting.


[Files]
; MCP server
Source: "mcp_server.py";      DestDir: "{app}";                               Flags: ignoreversion

; Config helper
Source: "configure.py";       DestDir: "{app}";                               Flags: ignoreversion

; Grasshopper plugin
Source: "plugin\GHAgent.gha"; DestDir: "{userappdata}\Grasshopper\Libraries"; Flags: ignoreversion

; README
Source: "README.md";          DestDir: "{app}";                               Flags: ignoreversion


[Icons]
Name: "{group}\GH Agent Files";     Filename: "{app}"
Name: "{group}\Repair GH Agent";    Filename: "{app}\repair.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall GH Agent"; Filename: "{uninstallexe}"


[Run]
; Install Python dependencies via configure.py (uses the same Python detection as install)
Filename: "python"; \
  Parameters: """{app}\configure.py"" pip"; \
  StatusMsg: "Installing Python dependencies..."; \
  Flags: runhidden waituntilterminated

; Write Claude Desktop config
Filename: "python"; \
  Parameters: """{app}\configure.py"" install"; \
  StatusMsg: "Configuring Claude Desktop..."; \
  Flags: runhidden waituntilterminated


[UninstallRun]
Filename: "python"; \
  Parameters: """{app}\configure.py"" uninstall"; \
  Flags: runhidden waituntilterminated; \
  RunOnceId: "UnconfigureClaude"

Filename: "cmd.exe"; \
  Parameters: "/c del ""{userappdata}\Grasshopper\Libraries\GHAgent.gha"""; \
  Flags: runhidden waituntilterminated; \
  RunOnceId: "RemoveGHA"


[Code]
function IsPythonInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('python', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
            and (ResultCode = 0);
end;

function IsClaudeDesktopInstalled(): Boolean;
begin
  Result :=
    FileExists(ExpandConstant('{localappdata}\Programs\claude-desktop\Claude.exe')) or
    FileExists(ExpandConstant('{localappdata}\AnthropicClaude\Claude.exe')) or
    FileExists(ExpandConstant('{userappdata}\Programs\claude-desktop\Claude.exe'));
end;

function IsRhinoInstalled(): Boolean;
var
  RhinoPath: String;
begin
  RhinoPath := 'C:\Program Files\Rhino 8\System\Rhino.exe';
  Result := FileExists(RhinoPath);
end;

function InitializeSetup(): Boolean;
var
  Msg: String;
  MissingItems: Boolean;
begin
  Result       := True;
  MissingItems := False;
  Msg          := 'The following required software was not found:' + #13#10 + #13#10;

  if not IsPythonInstalled() then
  begin
    Msg := Msg + '  • Python 3 — download from python.org' + #13#10;
    MissingItems := True;
  end;

  if not IsRhinoInstalled() then
  begin
    Msg := Msg + '  • Rhino 8 — download from rhino3d.com' + #13#10;
    MissingItems := True;
  end;

  if MissingItems then
  begin
    MsgBox(Msg + #13#10 + 'Please install the items above and run this setup again.', mbError, MB_OK);
    Result := False;
    Exit;
  end;

  if not IsClaudeDesktopInstalled() then
  begin
    if MsgBox(
      'Claude Desktop was not found on this computer.' + #13#10 + #13#10 +
      'GH Agent requires Claude Desktop to work. If you have not installed it yet, ' +
      'download it from claude.ai/download and run this setup again.' + #13#10 + #13#10 +
      'If you know Claude Desktop is already installed, you can continue anyway.' + #13#10 + #13#10 +
      'Continue with installation?',
      mbConfirmation, MB_YESNO
    ) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  RepairBat: String;
  Lines: TArrayOfString;
begin
  if CurStep = ssPostInstall then
  begin
    // Write repair.bat — used by the Start Menu shortcut
    // Uses bare "python" so it picks up whatever Python is current at repair time
    RepairBat := ExpandConstant('{app}\repair.bat');
    SetArrayLength(Lines, 9);
    Lines[0] := '@echo off';
    Lines[1] := 'echo GH Agent Repair';
    Lines[2] := 'echo ---------------';
    Lines[3] := 'python "%~dp0configure.py" repair';
    Lines[4] := 'if %errorlevel% neq 0 (';
    Lines[5] := '  echo. & echo Repair failed. Make sure Python is installed from python.org. & pause';
    Lines[6] := ') else (';
    Lines[7] := '  echo. & echo Done! Restart Claude Desktop for changes to take effect. & pause';
    Lines[8] := ')';
    SaveStringsToFile(RepairBat, Lines, False);
  end;
end;
