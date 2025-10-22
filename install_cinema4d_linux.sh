#!/bin/bash
# Cinema 4D MCP Installer for Linux
# Run this script to install: chmod +x install_cinema4d_linux.sh && ./install_cinema4d_linux.sh

set -e

echo "============================================"
echo "Cinema 4D MCP Installer for Linux"
echo "============================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check Python
echo "[1/5] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Install Python 3.10+ using your package manager:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "  Fedora: sudo dnf install python3 python3-pip"
    echo "  Arch: sudo pacman -S python python-pip"
    read -p "Press Enter to exit..."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Found Python $PYTHON_VERSION"

# Install Python dependencies
echo ""
echo "[2/5] Installing Python dependencies..."
python3 -m pip install --upgrade pip --user
python3 -m pip install -e . --user
echo "Dependencies installed successfully!"

# Find Cinema 4D plugins folder
echo ""
echo "[3/5] Locating Cinema 4D plugins folder..."

# Check common Cinema 4D versions
C4D_VERSIONS=("2026" "2025" "2024" "R26" "R25")
C4D_PLUGINS_DIR=""

for version in "${C4D_VERSIONS[@]}"; do
    POSSIBLE_PATH="$HOME/.maxon/Cinema 4D $version/plugins"
    if [ -d "$POSSIBLE_PATH" ]; then
        C4D_PLUGINS_DIR="$POSSIBLE_PATH"
        echo "Found Cinema 4D $version plugins folder"
        break
    fi
done

if [ -z "$C4D_PLUGINS_DIR" ]; then
    echo "WARNING: Could not automatically locate Cinema 4D plugins folder."
    echo "Please manually copy c4d_plugin.py to your Cinema 4D plugins folder:"
    echo "~/.maxon/Cinema 4D <version>/plugins/"
    echo ""
    read -p "Enter the path to your Cinema 4D plugins folder (or press Enter to skip): " MANUAL_PATH
    if [ -n "$MANUAL_PATH" ]; then
        C4D_PLUGINS_DIR="$MANUAL_PATH"
    fi
fi

# Copy plugin file
if [ -n "$C4D_PLUGINS_DIR" ]; then
    echo ""
    echo "[4/5] Installing Cinema 4D plugin..."
    mkdir -p "$C4D_PLUGINS_DIR"
    cp "$SCRIPT_DIR/c4d_plugin.py" "$C4D_PLUGINS_DIR/"
    echo "Plugin installed to: $C4D_PLUGINS_DIR"
else
    echo "[4/5] Skipping plugin installation (manual install required)"
fi

# Configure Claude Desktop
echo ""
echo "[5/5] Configuring Claude Desktop..."

# Try different possible Claude config locations
CLAUDE_CONFIGS=(
    "$HOME/.config/Claude/claude_desktop_config.json"
    "$HOME/.config/claude/claude_desktop_config.json"
)

CLAUDE_CONFIG=""
for config in "${CLAUDE_CONFIGS[@]}"; do
    CLAUDE_DIR=$(dirname "$config")
    if [ -d "$CLAUDE_DIR" ] || mkdir -p "$CLAUDE_DIR" 2>/dev/null; then
        CLAUDE_CONFIG="$config"
        break
    fi
done

if [ -z "$CLAUDE_CONFIG" ]; then
    echo "WARNING: Could not locate Claude Desktop config directory."
    echo "Please manually configure Claude Desktop by adding to config:"
    echo ""
    echo '{
  "mcpServers": {
    "cinema4d": {
      "command": "python3",
      "args": ["'$SCRIPT_DIR'/main_c4d.py"]
    }
  }
}'
    echo ""
else
    CLAUDE_DIR=$(dirname "$CLAUDE_CONFIG")
    mkdir -p "$CLAUDE_DIR"

    # Check if config exists
    if [ -f "$CLAUDE_CONFIG" ]; then
        echo "Claude Desktop config already exists."
        echo "Backing up to claude_desktop_config.json.backup"
        cp "$CLAUDE_CONFIG" "$CLAUDE_CONFIG.backup"
    fi

    # Create or update config
    MAIN_C4D_PATH="$SCRIPT_DIR/main_c4d.py"

    cat > "$CLAUDE_CONFIG" << EOF
{
  "mcpServers": {
    "cinema4d": {
      "command": "python3",
      "args": ["$MAIN_C4D_PATH"]
    }
  }
}
EOF

    echo "Claude Desktop configured successfully!"
fi

# Success message
echo ""
echo "============================================"
echo "Installation Complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "1. Restart Cinema 4D if it's running"
echo "2. In Cinema 4D, go to Plugins → Cinema 4D MCP"
echo "3. Click 'Connect to MCP'"
echo "4. Restart Claude Desktop"
echo "5. Start using Cinema 4D with Claude!"
echo ""
echo "The MCP server will start automatically when Claude Desktop launches."
echo ""
echo "For troubleshooting, see README_CINEMA4D.md"
echo ""
read -p "Press Enter to exit..."
