#!/bin/sh
# Ach! 1-Line Remote Uninstaller
set -e

INSTALL_BASE="$HOME/.local/share/ach"
BIN_DIR="$HOME/.local/bin"
CONFIG_FILE="$HOME/.gemini/antigravity-cli/plugin_data/sessionlist/config.json"

echo "Uninstalling Ach!..."

# 1. Remove cloned code (both current and legacy)
rm -rf "$INSTALL_BASE" "$HOME/.local/share/sessionlist"

# 2. Read custom alias from config if present
if [ -f "$CONFIG_FILE" ] && command -v python3 >/dev/null 2>&1; then
    CONFIG_CMD="$(python3 -c "
import json, os
try:
    with open(os.path.expanduser('$CONFIG_FILE'), 'r', encoding='utf-8') as f:
        cfg = json.load(f)
        cmd = cfg.get('cli_command', '')
        if cmd:
            print(cmd)
except Exception:
    pass
" 2>/dev/null || true)"
    if [ -n "$CONFIG_CMD" ]; then
        rm -f "$BIN_DIR/$CONFIG_CMD" "$BIN_DIR/$CONFIG_CMD-h" "$BIN_DIR/$CONFIG_CMD-m"
    fi
fi

# 3. Remove standard generated aliases in ~/.local/bin/ (ach*, antig*, etc.)
rm -f "$BIN_DIR/ach" "$BIN_DIR/ach-h" "$BIN_DIR/ach-m"
rm -f "$BIN_DIR/antig" "$BIN_DIR/antig-h" "$BIN_DIR/antig-m"
rm -f "$BIN_DIR/ag" "$BIN_DIR/ag-h" "$BIN_DIR/ag-m"

# Also remove any custom prefix passed as argument (e.g. ./uninstall.sh mycmd)
if [ -n "$1" ]; then
    rm -f "$BIN_DIR/$1" "$BIN_DIR/$1-h" "$BIN_DIR/$1-m"
fi

# 4. Offer clean removal of config directory
CONFIG_DIR="$HOME/.gemini/antigravity-cli/plugin_data/sessionlist"
if [ -d "$CONFIG_DIR" ]; then
    rm -rf "$CONFIG_DIR"
fi

echo "✔ Successfully uninstalled Ach! from your system."
