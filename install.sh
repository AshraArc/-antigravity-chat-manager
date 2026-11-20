#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sessionlist.py"

mkdir -p "$INSTALL_DIR"

echo "=================================================="
echo "          sessionList Unified Installer           "
echo "=================================================="

DEFAULT_CMD="ach"
read -p "Enter preferred command name [default: $DEFAULT_CMD]: " USER_CMD
CMD_NAME="${USER_CMD:-$DEFAULT_CMD}"

TARGET_LINK="$INSTALL_DIR/$CMD_NAME"
chmod +x "$SCRIPT_PATH"
ln -sf "$SCRIPT_PATH" "$TARGET_LINK"

echo ""
echo "✔ Created executable symlink: $TARGET_LINK"

# Configure launcher on first run
python3 "$SCRIPT_PATH" --config

echo "=================================================="
echo "  ✔ sessionList Installation Complete!"
echo "=================================================="
echo "  1. In Terminal (Outside Chat):"
echo "     Run:  ach"
echo ""
echo "  2. In Antigravity (Inside Chat):"
echo "     Install plugin: agy plugin install $(dirname "$SCRIPT_PATH")"
echo "     Use: /history"
echo "=================================================="
