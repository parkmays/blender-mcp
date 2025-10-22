@echo off
REM Cinema 4D MCP Installer for Windows
REM Double-click this file to install

echo ============================================
echo Cinema 4D MCP Installer for Windows
echo ============================================
echo.

cd /d "%~dp0"

REM Check Python
echo [1/5] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10 or later from python.org
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo Found Python %PYTHON_VERSION%

REM Install Python dependencies
echo.
echo [2/5] Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -e .
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo Dependencies installed successfully!

REM Find Cinema 4D plugins folder
echo.
echo [3/5] Locating Cinema 4D plugins folder...

set C4D_PLUGINS_DIR=
set "C4D_VERSIONS=2026 2025 2024 R26 R25"

for %%v in (%C4D_VERSIONS%) do (
    set "POSSIBLE_PATH=%APPDATA%\Maxon\Cinema 4D %%v\plugins"
    if exist "!POSSIBLE_PATH!" (
        set "C4D_PLUGINS_DIR=!POSSIBLE_PATH!"
        echo Found Cinema 4D %%v plugins folder
        goto :found_c4d
    )
)

:found_c4d

if "%C4D_PLUGINS_DIR%"=="" (
    echo WARNING: Could not automatically locate Cinema 4D plugins folder.
    echo.
    echo Please manually copy c4d_plugin.py to your Cinema 4D plugins folder:
    echo %APPDATA%\Maxon\Cinema 4D ^<version^>\plugins\
    echo.
    set /p "C4D_PLUGINS_DIR=Enter the path to your Cinema 4D plugins folder (or press Enter to skip): "
)

REM Copy plugin file
if not "%C4D_PLUGINS_DIR%"=="" (
    echo.
    echo [4/5] Installing Cinema 4D plugin...
    if not exist "%C4D_PLUGINS_DIR%" mkdir "%C4D_PLUGINS_DIR%"
    copy /Y "%~dp0c4d_plugin.py" "%C4D_PLUGINS_DIR%\"
    if errorlevel 1 (
        echo ERROR: Failed to copy plugin file
        pause
        exit /b 1
    )
    echo Plugin installed to: %C4D_PLUGINS_DIR%
) else (
    echo [4/5] Skipping plugin installation (manual install required)
)

REM Configure Claude Desktop
echo.
echo [5/5] Configuring Claude Desktop...

set "CLAUDE_CONFIG=%APPDATA%\Claude\claude_desktop_config.json"
set "CLAUDE_DIR=%APPDATA%\Claude"

REM Create Claude config directory if it doesn't exist
if not exist "%CLAUDE_DIR%" mkdir "%CLAUDE_DIR%"

REM Check if config exists
if exist "%CLAUDE_CONFIG%" (
    echo Claude Desktop config already exists.
    echo Backing up to claude_desktop_config.json.backup
    copy /Y "%CLAUDE_CONFIG%" "%CLAUDE_CONFIG%.backup"
)

REM Create or update config
set "MAIN_C4D_PATH=%~dp0main_c4d.py"
set "MAIN_C4D_PATH=%MAIN_C4D_PATH:\=/%"

(
echo {
echo   "mcpServers": {
echo     "cinema4d": {
echo       "command": "python",
echo       "args": ["%MAIN_C4D_PATH%"]
echo     }
echo   }
echo }
) > "%CLAUDE_CONFIG%"

echo Claude Desktop configured successfully!

REM Success message
echo.
echo ============================================
echo Installation Complete!
echo ============================================
echo.
echo Next steps:
echo 1. Restart Cinema 4D if it's running
echo 2. In Cinema 4D, go to Plugins -^> Cinema 4D MCP
echo 3. Click 'Connect to MCP'
echo 4. Restart Claude Desktop
echo 5. Start using Cinema 4D with Claude!
echo.
echo The MCP server will start automatically when Claude Desktop launches.
echo.
echo For troubleshooting, see README_CINEMA4D.md
echo.
pause
