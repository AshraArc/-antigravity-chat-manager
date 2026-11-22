#!/bin/sh
# sessionList 1-Line Remote Installer
set -e

REPO_URL="https://github.com/AshraArc/-antigravity-chat-manager.git"
INSTALL_BASE="$HOME/.local/share/sessionlist"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.gemini/antigravity-cli/plugin_data/sessionlist"
CONFIG_FILE="$CONFIG_DIR/config.json"

for dep in git python3; do
    command -v "$dep" >/dev/null 2>&1 || { echo "Error: '$dep' is required but not installed." >&2; exit 1; }
done

mkdir -p "$BIN_DIR"

if [ -d "$INSTALL_BASE/.git" ]; then
    echo "Updating existing sessionList..."
    git -C "$INSTALL_BASE" pull --quiet
else
    echo "Downloading sessionList..."
    rm -rf "$INSTALL_BASE"
    git clone --depth 1 --quiet "$REPO_URL" "$INSTALL_BASE"
fi

# Determine command prefix:
# If user passed an argument (e.g. sh -s -- ag), use it.
# Otherwise, if running interactively in terminal, prompt for custom alias with default 'ach'.
# If running non-interactively without tty, fall back to 'ach'.
DEFAULT_PREFIX="ach"
if [ -n "$1" ]; then
    CMD_PREFIX="$1"
elif [ -t 0 ] || [ -e /dev/tty ]; then
    printf "Enter preferred alias/command prefix [default: %s]: " "$DEFAULT_PREFIX"
    read USER_CMD < /dev/tty || true
    CMD_PREFIX="${USER_CMD:-$DEFAULT_PREFIX}"
else
    CMD_PREFIX="$DEFAULT_PREFIX"
fi

SCRIPT_PATH="$INSTALL_BASE/sessionlist.py"

# 1. Quick list binary: <cmd>-h
cat << EOF > "$BIN_DIR/${CMD_PREFIX}-h"
#!/bin/sh
if [ "\$#" -eq 0 ]; then
    exec python3 "$SCRIPT_PATH" --list
else
    exec python3 "$SCRIPT_PATH" "\$@"
fi
EOF
chmod +x "$BIN_DIR/${CMD_PREFIX}-h"

# 2. Interactive menu binary: <cmd>-m
cat << EOF > "$BIN_DIR/${CMD_PREFIX}-m"
#!/bin/sh
exec python3 "$SCRIPT_PATH" "\$@"
EOF
chmod +x "$BIN_DIR/${CMD_PREFIX}-m"

# 3. Direct base command
ln -sf "$BIN_DIR/${CMD_PREFIX}-m" "$BIN_DIR/$CMD_PREFIX"

# 4. Save chosen prefix to config file
mkdir -p "$CONFIG_DIR"
python3 -c "
import json, os
cfg_path = os.path.expanduser('$CONFIG_FILE')
cfg = {}
if os.path.exists(cfg_path):
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except Exception:
        pass
cfg['cli_command'] = '$CMD_PREFIX'
with open(cfg_path, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2)
" 2>/dev/null || true

echo "✔ Installed ${CMD_PREFIX}-h, ${CMD_PREFIX}-m to $BIN_DIR"

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "Note: Add $BIN_DIR to your PATH to run commands directly." ;;
esac
