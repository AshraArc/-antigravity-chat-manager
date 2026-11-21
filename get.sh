#!/usr/bin/env bash
# sessionList 1-Line Remote Installer
set -e

REPO_URL="https://github.com/AshraArc/-antigravity-chat-manager.git"
INSTALL_BASE="$HOME/.local/share/sessionlist"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR"

echo "=================================================="
echo "      sessionList One-Line Quick Installer        "
echo "=================================================="

if [ -d "$INSTALL_BASE/.git" ]; then
    echo "Updating existing sessionList..."
    git -C "$INSTALL_BASE" pull --quiet
else
    echo "Downloading sessionList..."
    rm -rf "$INSTALL_BASE"
    git clone --depth 1 --quiet "$REPO_URL" "$INSTALL_BASE"
fi

# Determine command prefix (default: antig)
CMD_PREFIX="${1:-antig}"

SCRIPT_PATH="$INSTALL_BASE/sessionlist.py"

# 1. Quick list binary: <cmd>-h
cat << EOF > "$BIN_DIR/${CMD_PREFIX}-h"
#!/usr/bin/env bash
if [ "\$#" -eq 0 ]; then
    exec python3 "$SCRIPT_PATH" --list
else
    exec python3 "$SCRIPT_PATH" "\$@"
fi
EOF
chmod +x "$BIN_DIR/${CMD_PREFIX}-h"

# 2. Interactive menu binary: <cmd>-m
cat << EOF > "$BIN_DIR/${CMD_PREFIX}-m"
#!/usr/bin/env bash
exec python3 "$SCRIPT_PATH" "\$@"
EOF
chmod +x "$BIN_DIR/${CMD_PREFIX}-m"

# 3. Direct base command
ln -sf "$BIN_DIR/${CMD_PREFIX}-m" "$BIN_DIR/$CMD_PREFIX"

echo "✔ Successfully installed to $BIN_DIR:"
echo "   - ${CMD_PREFIX}-h  (Instant table dump)"
echo "   - ${CMD_PREFIX}-m  (Interactive dashboard)"
echo "   - ${CMD_PREFIX}    (Direct shortcut)"
echo "=================================================="
