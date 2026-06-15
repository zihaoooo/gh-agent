@echo off
REM Build GH Agent: compile the .gha, then the installer.
REM Run from the repo root.

echo Building .gha...
dotnet build "plugin\GHAgent.csproj" -c Release
if errorlevel 1 (
    echo Build failed. Aborting.
    pause
    exit /b 1
)

echo Staging .gha for the installer...
copy /Y "plugin\bin\Release\net7.0-windows\GHAgent.gha" "plugin\GHAgent.gha"
if errorlevel 1 (
    echo Could not stage GHAgent.gha. Aborting.
    pause
    exit /b 1
)

echo Compiling installer...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer\setup.iss"
if errorlevel 1 (
    echo Installer compile failed.
    pause
    exit /b 1
)

echo Done. Installer is in dist\
pause
