#!/bin/sh
set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/sessionlist.py"
CONFIG_DIR="$HOME/.gemini/antigravity-cli/plugin_data/sessionlist"
CONFIG_FILE="$CONFIG_DIR/config.json"

command -v python3 >/dev/null 2>&1 || { echo "Error: 'python3' is required but not installed." >&2; exit 1; }

mkdir -p "$INSTALL_DIR"

echo "=================================================="
echo "                Ach! Installer                "
echo "=================================================="

DEFAULT_CMD="ach"
printf "Enter preferred alias/command prefix [default: %s]: " "$DEFAULT_CMD"
read USER_CMD
CMD_NAME="${USER_CMD:-$DEFAULT_CMD}"

# 1. Generate quick list binary: <cmd>-h
BIN_H="$INSTALL_DIR/${CMD_NAME}-h"
cat << EOF > "$BIN_H"
#!/bin/sh
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
#!/bin/sh
exec python3 "$SCRIPT_PATH" "\$@"
EOF
chmod +x "$BIN_M"

# 3. Also symlink base command
ln -sf "$BIN_M" "$INSTALL_DIR/$CMD_NAME"

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
cfg['cli_command'] = '$CMD_NAME'
with open(cfg_path, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2)
" 2>/dev/null || true

# 5. Auto-register skills in Antigravity skill directories if they exist
SKILL_SRC="$SCRIPT_DIR/skills/sessionlist"
if [ -d "$SKILL_SRC" ]; then
    for target_dir in "$HOME/.gemini/antigravity-cli/skills" "$HOME/.agents/skills"; do
        if [ -d "$target_dir" ]; then
            dest="$target_dir/sessionlist"
            rm -rf "$dest"
            ln -sf "$SKILL_SRC" "$dest" 2>/dev/null || cp -r "$SKILL_SRC" "$dest"
            echo "✔ Registered skill in $dest"
        fi
    done
fi

echo ""
echo "✔ Created executable binaries in $INSTALL_DIR:"
echo "   - ${CMD_NAME}-h (Quick table dump)"
echo "   - ${CMD_NAME}-m (Interactive manager)"
echo "   - ${CMD_NAME}   (Direct shortcut)"

case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *) echo "Note: Add $INSTALL_DIR to your PATH to run commands directly." ;;
esac

echo "=================================================="
echo "  ✔ Ach! installation complete."
echo "=================================================="
echo "  1. In Terminal (Outside Chat):"
echo "     Run:  ${CMD_NAME}-h  (quick list)"
echo "     Run:  ${CMD_NAME}-m  (interactive menu)"
echo ""
echo "  2. In Antigravity (Inside Chat):"
echo "     Commands: /find, /recall, /history, /sessions"
echo "     Install plugin: agy plugin install \"$SCRIPT_DIR\""
echo "     Ask agent: 'show my chat history' or search with '/find <topic>'"
echo "=================================================="
