#!/usr/bin/env bash
# sessionList 1-Line Remote Installer
set -e

PRIMARY_REPO="https://github.com/AshraArc/ach-cli.git"
FALLBACK_REPO="https://github.com/AshraArc/-antigravity-chat-manager.git"
INSTALL_BASE="$HOME/.local/share/sessionlist"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR"

if [ -d "$INSTALL_BASE/.git" ]; then
    echo "Updating existing sessionList..."
    git -C "$INSTALL_BASE" pull --quiet || {
        echo "Pull failed, attempting remote update..."
        git -C "$INSTALL_BASE" remote set-url origin "$PRIMARY_REPO" 2>/dev/null || true
        git -C "$INSTALL_BASE" pull --quiet 2>/dev/null || true
    }
else
    echo "Downloading sessionList..."
    rm -rf "$INSTALL_BASE"
    if ! git clone --depth 1 --quiet "$PRIMARY_REPO" "$INSTALL_BASE" 2>/dev/null; then
        echo "Primary repo failed, falling back to backup repository URL..."
        git clone --depth 1 --quiet "$FALLBACK_REPO" "$INSTALL_BASE"
    fi
fi

# Determine command prefix:
# If user passed an argument (e.g. bash -s -- ag), use it.
# Otherwise, if running interactively in terminal, prompt for custom alias with default 'ach'.
# If running non-interactively without tty, fall back to 'ach'.
DEFAULT_PREFIX="ach"
if [ -n "$1" ]; then
    CMD_PREFIX="$1"
elif [ -t 0 ] || [ -e /dev/tty ]; then
    read -p "Enter preferred alias/command prefix [default: $DEFAULT_PREFIX]: " USER_CMD < /dev/tty || true
    CMD_PREFIX="${USER_CMD:-$DEFAULT_PREFIX}"
else
    CMD_PREFIX="$DEFAULT_PREFIX"
fi

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

# 4. Clean up legacy / stale aliases if CMD_PREFIX changed
for legacy in "antig" "ag"; do
    if [ "$CMD_PREFIX" != "$legacy" ]; then
        rm -f "$BIN_DIR/${legacy}" "$BIN_DIR/${legacy}-h" "$BIN_DIR/${legacy}-m"
    fi
done

# 5. Clean up old temporary files, broken symlinks, and legacy python caches in install base
if [ -d "$INSTALL_BASE" ]; then
    find "$INSTALL_BASE" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$INSTALL_BASE" -type f -name "*.tmp" -delete 2>/dev/null || true
fi

# 6. Auto-register skills in Antigravity skill directories if they exist
SKILL_SRC="$INSTALL_BASE/skills/sessionlist"
if [ -d "$SKILL_SRC" ]; then
    TARGET_SKILL_DIRS=(
        "$HOME/.gemini/antigravity-cli/skills"
        "$HOME/.agents/skills"
    )
    for target_dir in "${TARGET_SKILL_DIRS[@]}"; do
        if [ -d "$target_dir" ]; then
            dest="$target_dir/sessionlist"
            rm -rf "$dest"
            ln -sf "$SKILL_SRC" "$dest" 2>/dev/null || cp -r "$SKILL_SRC" "$dest"
            echo "✔ Registered skill in $dest"
        fi
    done
fi

echo "✔ Installed ${CMD_PREFIX}-h, ${CMD_PREFIX}-m to $BIN_DIR"
