#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/sessionlist.py"

mkdir -p "$INSTALL_DIR"

echo "=================================================="
echo "          sessionList Unified Installer           "
echo "=================================================="

DEFAULT_CMD="ach"
read -p "Enter preferred alias/command prefix [default: $DEFAULT_CMD]: " USER_CMD
CMD_NAME="${USER_CMD:-$DEFAULT_CMD}"

# 1. Generate quick list binary: <cmd>-h
BIN_H="$INSTALL_DIR/${CMD_NAME}-h"
cat << EOF > "$BIN_H"
#!/usr/bin/env bash
if [ "\$#" -eq 0 ]; then
    exec python3 "$SCRIPT_PATH" --list
else
    exec python3 "$SCRIPT_PATH" "\$@"
fi
EOF
chmod +x "$BIN_H"

# 2. Generate interactive menu binary: <cmd>-m
BIN_M="$INSTALL_DIR/${CMD_NAME}-m"
cat << EOF > "$BIN_M"
#!/usr/bin/env bash
exec python3 "$SCRIPT_PATH" "\$@"
EOF
chmod +x "$BIN_M"

# 3. Also symlink base command
ln -sf "$BIN_M" "$INSTALL_DIR/$CMD_NAME"

echo ""
echo "✔ Created executable binaries in $INSTALL_DIR:"
echo "   - ${CMD_NAME}-h (Quick table dump)"
echo "   - ${CMD_NAME}-m (Interactive manager)"
echo "   - ${CMD_NAME}   (Direct shortcut)"

echo "=================================================="
echo "  ✔ sessionList Installation Complete!"
echo "=================================================="
echo "  1. In Terminal (Outside Chat):"
echo "     Run:  ${CMD_NAME}-h  (quick list)"
echo "     Run:  ${CMD_NAME}-m  (interactive menu)"
echo ""
echo "  2. In Antigravity (Inside Chat):"
echo "     Install plugin: agy plugin install \"$SCRIPT_DIR\""
echo "     Ask agent: 'show my chat history' or 'history of past 7 days'"
echo "=================================================="
