#!/usr/bin/env bash
# sessionList 1-Line Remote Uninstaller
set -e

INSTALL_BASE="$HOME/.local/share/sessionlist"
BIN_DIR="$HOME/.local/bin"

echo "Uninstalling sessionList..."

# 1. Remove cloned code
rm -rf "$INSTALL_BASE"

# 2. Remove all generated aliases in ~/.local/bin/ (ach*, antig*, etc.)
rm -f "$BIN_DIR/ach" "$BIN_DIR/ach-h" "$BIN_DIR/ach-m"
rm -f "$BIN_DIR/antig" "$BIN_DIR/antig-h" "$BIN_DIR/antig-m"
rm -f "$BIN_DIR/ag" "$BIN_DIR/ag-h" "$BIN_DIR/ag-m"

# Also remove any custom prefix passed as argument (e.g. ./uninstall.sh mycmd)
if [ -n "$1" ]; then
    rm -f "$BIN_DIR/$1" "$BIN_DIR/$1-h" "$BIN_DIR/$1-m"
fi

echo "✔ Successfully uninstalled sessionList from your system."
