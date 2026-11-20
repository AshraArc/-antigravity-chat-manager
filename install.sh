#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/antig_manager.py"

mkdir -p "$INSTALL_DIR"

echo "=================================================="
echo "    Antigravity Chat Manager (ACM) Installer     "
echo "=================================================="

# Prompt for preferred command name
DEFAULT_ALIAS="ach"
read -p "Enter preferred command name [default: $DEFAULT_ALIAS]: " USER_CMD
CMD_NAME="${USER_CMD:-$DEFAULT_ALIAS}"

TARGET_LINK="$INSTALL_DIR/$CMD_NAME"
chmod +x "$SCRIPT_PATH"
ln -sf "$SCRIPT_PATH" "$TARGET_LINK"

echo ""
echo "✔ Created symlink: $TARGET_LINK"

# Configure Antigravity executable / alias on first run
python3 "$SCRIPT_PATH" --config

echo "=================================================="
echo "  ✔ Installation Complete!"
echo "=================================================="
echo "  To browse and resume your chats anytime, type:"
echo ""
echo "      $CMD_NAME"
echo ""
echo "  (Ensure $INSTALL_DIR is in your PATH)"
echo "=================================================="
