#!/usr/bin/env python3
"""
sessionList (v2.1 Plain-Text Master Log Architecture)
High-efficiency, zero-overhead session history manager for Google Antigravity CLI.
Uses line-delimited TSV master_history.tsv for sub-millisecond atomic append and read.
Guaranteed fit for 80-column terminal displays.
"""

import os
import sys
import glob
import json
import re
import shutil
import subprocess
import fcntl
import time
from datetime import datetime, timedelta

def get_data_dir():
    # 1. Environment variable override
    if os.environ.get("SESSIONLIST_DATA_DIR") and os.path.isdir(os.environ.get("SESSIONLIST_DATA_DIR")):
        return os.environ.get("SESSIONLIST_DATA_DIR")

    # 2. Look upwards from CWD for active workspace root containing .agents or .gemini
    try:
        curr = os.path.abspath(os.getcwd())
        while curr and curr != os.path.dirname(curr):
            agents_dir = os.path.join(curr, ".agents")
            if os.path.isdir(agents_dir):
                target = os.path.join(agents_dir, "sessionlist_data")
                try:
                    os.makedirs(target, exist_ok=True)
                    test = os.path.join(target, ".write_test")
                    with open(test, "w") as f: f.write("1")
                    os.remove(test)
                    return target
                except Exception:
                    pass
            curr = os.path.dirname(curr)
    except Exception:
        pass

    # 3. Dynamic lookup relative to this script file
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cand_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
        cand_agents = os.path.join(cand_root, ".agents", "sessionlist_data")
        if os.path.isdir(os.path.dirname(cand_agents)):
            try:
                os.makedirs(cand_agents, exist_ok=True)
                test = os.path.join(cand_agents, ".write_test")
                with open(test, "w") as f: f.write("1")
                os.remove(test)
                return cand_agents
            except Exception:
                pass
    except Exception:
        pass

    # 4. Standard persistent fallbacks across Linux, macOS, WSL
    home = os.path.expanduser("~")
    fallbacks = [
        os.path.join(home, ".gemini", "antigravity-cli", "plugin_data", "sessionlist"),
        os.path.join(home, ".config", "sessionlist"),
        os.path.join(home, ".cache", "sessionlist"),
        "/tmp/sessionlist"
    ]
    for p in fallbacks:
        try:
            os.makedirs(p, exist_ok=True)
            test_file = os.path.join(p, ".write_test")
            with open(test_file, "w") as f: f.write("1")
            os.remove(test_file)
            return p
        except Exception:
            continue
    return "/tmp"

DATA_DIR = get_data_dir()
MASTER_TSV = os.path.join(DATA_DIR, "master_history.tsv")
LOCK_FILE = os.path.join(DATA_DIR, "history.lock")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
GROUPS_FILE = os.path.join(DATA_DIR, "groups.txt")

def get_brain_dir():
    # Detects where Antigravity stores raw session transcripts on this system
    if os.environ.get("AGY_BRAIN_DIR") and os.path.isdir(os.environ.get("AGY_BRAIN_DIR")):
        return os.environ.get("AGY_BRAIN_DIR")

    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".gemini", "antigravity-cli", "brain"),
        os.path.join(home, ".config", "antigravity-cli", "brain"),
        os.path.join(home, ".antigravity", "brain"),
        os.path.join(os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local", "share")), "antigravity-cli", "brain")
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return os.path.join(home, ".gemini", "antigravity-cli", "brain")

BRAIN_DIR = get_brain_dir()

def clear_screen():
    sys.stdout.write("\033[H\033[2J\033[3J")
    sys.stdout.flush()

class FileLock:
    """Kernel advisory file lock for safe atomic updates across multiple terminals."""
    def __init__(self, lock_path):
        self.lock_path = lock_path
        self.file_obj = None

    def __enter__(self):
        self.file_obj = open(self.lock_path, "w+")
        fcntl.flock(self.file_obj.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file_obj:
            try:
                fcntl.flock(self.file_obj.fileno(), fcntl.LOCK_UN)
                self.file_obj.close()
            except Exception:
                pass

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<USER_SETTINGS_CHANGE>[\s\S]*?</USER_SETTINGS_CHANGE>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def get_relative_date_label(dt, now):
    today_start = datetime(now.year, now.month, now.day)
    yesterday_start = today_start - timedelta(days=1)

    if dt >= today_start:
        return "Today"
    elif dt >= yesterday_start:
        return "Yesterday"
    else:
        days_ago = (today_start - datetime(dt.year, dt.month, dt.day)).days
        if days_ago <= 20:
            return f"{days_ago} days ago"
        else:
            return dt.strftime("%b %d")

# ==========================================
# PLAIN-TEXT MASTER LOG ENGINE (TSV)
# ==========================================

def read_master_tsv():
    """Reads all sessions from TSV file in <0.2ms."""
    if not os.path.exists(MASTER_TSV):
        return []
    records = []
    try:
        with open(MASTER_TSV, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 5:
                    cid, mtime_str, msgs_str, group, title = parts[0], parts[1], parts[2], parts[3], parts[4]
                elif len(parts) == 4:
                    cid, mtime_str, msgs_str, group = parts[0], parts[1], parts[2], parts[3]
                    title = "Untitled Chat"
                elif len(parts) >= 2:
                    cid, mtime_str = parts[0], parts[1]
                    msgs_str, group, title = "1", "General", "Untitled Chat"
                else:
                    continue

                try:
                    mtime = float(mtime_str)
                except ValueError:
                    mtime = 0.0
                try:
                    msgs = int(msgs_str)
                except ValueError:
                    msgs = 1

                records.append({
                    "id": cid,
                    "mtime": mtime,
                    "msgs": msgs,
                    "group": group,
                    "title": title
                })
    except Exception:
        pass
    return records

def write_master_tsv(records):
    """Atomically replaces master_history.tsv in <0.5ms."""
    tmp_path = MASTER_TSV + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            for r in records:
                cid = r["id"]
                mtime = r["mtime"]
                msgs = r["msgs"]
                group = r["group"].replace("\t", " ")
                title = r["title"].replace("\t", " ").replace("\n", " ")
                f.write(f"{cid}\t{mtime}\t{msgs}\t{group}\t{title}\n")
        os.replace(tmp_path, MASTER_TSV)
        # Mirror backup to plugin_data so both antigravity default locations stay identical
        mirror_dir = os.path.expanduser("~/.gemini/antigravity-cli/plugin_data/sessionlist")
        if os.path.exists(mirror_dir) and mirror_dir != os.path.dirname(MASTER_TSV):
            try:
                shutil.copy2(MASTER_TSV, os.path.join(mirror_dir, "master_history.tsv"))
            except Exception:
                pass
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        print(f"Error persisting TSV: {e}")

def parse_transcript_data(fpath):
    first_prompt = ""
    user_turns = 0
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "USER_INPUT":
                        cleaned = clean_text(entry.get("content", ""))
                        if cleaned:
                            user_turns += 1
                            if not first_prompt:
                                first_prompt = cleaned
                except Exception:
                    pass
    except Exception:
        pass

    if not first_prompt:
        first_prompt = "(No user input recorded)"

    return first_prompt, user_turns

def sync_active_session_to_tsv():
    """
    Scans the local sandbox brain directory for this container's active session.
    Appends or updates its record in master_history.tsv.
    Takes <1ms when up to date.
    """
    pattern = os.path.join(BRAIN_DIR, "*", ".system_generated", "logs", "transcript.jsonl")
    disk_files = glob.glob(pattern)
    if not disk_files:
        return

    with FileLock(LOCK_FILE):
        records = read_master_tsv()
        rec_map = {r["id"]: r for r in records}
        dirty = False

        for fpath in disk_files:
            cid = fpath.split(os.sep)[-4]
            mtime = os.path.getmtime(fpath)
            existing = rec_map.get(cid)

            if not existing:
                prompt, turns = parse_transcript_data(fpath)
                title = prompt[:45] + ("..." if len(prompt) > 45 else "")
                new_rec = {
                    "id": cid,
                    "mtime": mtime,
                    "msgs": turns,
                    "group": "General",
                    "title": title
                }
                records.append(new_rec)
                rec_map[cid] = new_rec
                dirty = True
            elif existing["mtime"] < mtime:
                prompt, turns = parse_transcript_data(fpath)
                existing["mtime"] = mtime
                existing["msgs"] = turns
                dirty = True

        if dirty:
            write_master_tsv(records)

def get_all_chats():
    sync_active_session_to_tsv()
    records = read_master_tsv()
    now = datetime.now()

    for c in records:
        dt = datetime.fromtimestamp(c["mtime"])
        c["dt"] = dt
        c["time_label"] = get_relative_date_label(dt, now)
        c["exact_time"] = dt.strftime("%H:%M")

    records.sort(key=lambda x: x["mtime"], reverse=True)
    return records

# ==========================================
# FAST OUTPUT FORMATTER (Guaranteed <= 78 cols)
# ==========================================

def render_terminal_table(chats, limit=None):
    if not chats:
        print("No recorded chat sessions found.")
        return

    displayed = chats if limit is None else chats[:limit]
    
    print("-" * 76)
    print(f"{'#':<3} {'Period':<10} {'Time':<6} {'Group':<10} {'Msgs':<5} {'Title':<36}")
    print("-" * 76)

    current_period = None
    for idx, c in enumerate(displayed, 1):
        period = c["time_label"]
        time_str = c["exact_time"]
        group = (c["group"][:8] + "..") if len(c["group"]) > 10 else c["group"]
        msgs = str(c["msgs"])
        
        # Max 36 chars for title to strictly fit within 76 columns total
        raw_title = c["title"]
        title = (raw_title[:33] + "...") if len(raw_title) > 36 else raw_title

        print(f"{idx:<3} {period:<10} {time_str:<6} {group:<10} {msgs:<5} {title:<36}")

    print("-" * 76)
    if limit is not None and len(chats) > limit:
        print(f"Showing {limit} of {len(chats)} sessions. To see all, run with --all.")

# ==========================================
# MUTATIONS & CLI ACTIONS
# ==========================================

def set_chat_title(cid, new_title):
    if not cid or not new_title:
        return
    with FileLock(LOCK_FILE):
        records = read_master_tsv()
        updated = False
        for r in records:
            if r["id"] == cid:
                r["title"] = new_title.strip()
                updated = True
                break
        if updated:
            write_master_tsv(records)
            print(f"✔ Abstracted title saved: '{new_title.strip()}'")

def smart_group(group_name, ids=None, query=None, max_age_seconds=None):
    if not group_name:
        return
    chats = get_all_chats()
    now_ts = datetime.now().timestamp()
    matching_ids = set()

    for c in chats:
        match = True
        if max_age_seconds is not None and (now_ts - c["mtime"]) > max_age_seconds:
            match = False
        if query and (query.lower() not in c["title"].lower() and query.lower() not in c["group"].lower()):
            match = False
        if ids and c["id"] not in ids:
            match = False
        if match:
            matching_ids.add(c["id"])

    if not matching_ids:
        print(f"No chats matched criteria for group '{group_name}'.")
        return

    with FileLock(LOCK_FILE):
        records = read_master_tsv()
        for r in records:
            if r["id"] in matching_ids:
                r["group"] = group_name
        write_master_tsv(records)
        print(f"✔ Successfully assigned {len(matching_ids)} session(s) to group '{group_name}'.")

def delete_chats_multi(chats_to_delete):
    if not chats_to_delete:
        return
    print(f"\nSelected for deletion ({len(chats_to_delete)} chat{'s' if len(chats_to_delete) != 1 else ''}):")
    for idx, c in enumerate(chats_to_delete, 1):
        print(f"  [{idx}] {c['title']} (ID: {c['id'][:8]}...)")

    confirm = input(f"\nAre you sure you want to delete? (y/N): ").strip().lower()
    if confirm == "y":
        del_ids = {c["id"] for c in chats_to_delete}
        for c in chats_to_delete:
            folder = os.path.join(BRAIN_DIR, c["id"])
            if os.path.exists(folder):
                try:
                    shutil.rmtree(folder)
                except Exception:
                    pass
        with FileLock(LOCK_FILE):
            records = read_master_tsv()
            records = [r for r in records if r["id"] not in del_ids]
            write_master_tsv(records)
        print(f"\n✔ Deleted {len(chats_to_delete)} chat(s). Refreshing...")
        time.sleep(0.5)

def delete_single_chat(chat):
    delete_chats_multi([chat])

def detect_cli_command():
    """
    Robust Multi-Tier Resolution:
    1. If user passed/configured a custom command, verify it actually exists and works.
    2. If invalid or missing, fall back to official 'agy' or 'antigravity'.
    3. Check PATH and standard installation directories (~/.local/bin/agy).
    Never crashes with FileNotFoundError.
    """
    candidates = []

    # 1. Environment variable override
    if os.environ.get("AGY_CMD"):
        candidates.append(os.environ.get("AGY_CMD"))

    # 2. Saved user config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                if cfg.get("cli_command"):
                    candidates.append(cfg["cli_command"])
        except Exception:
            pass

    # 3. Standard binaries & common aliases
    candidates.extend(["agy", "antigravity", "ag", "antig"])

    # 4. Standard path locations
    home = os.path.expanduser("~")
    candidates.extend([
        os.path.join(home, ".local", "bin", "agy"),
        os.path.join(home, "bin", "agy"),
        "/usr/local/bin/agy",
        "/usr/bin/agy"
    ])

    for cmd in candidates:
        if not cmd:
            continue
        parts = cmd.split()
        binary = parts[0]
        # If absolute or relative path that exists
        if os.path.isfile(binary) and os.access(binary, os.X_OK):
            return cmd
        # If binary found in system PATH
        if shutil.which(binary):
            return cmd

    # Final fallback default
    return "agy"

def get_prompt_input(prompt_text):
    """
    Reads input supporting standard typing, Enter, and instant Esc button detection.
    If Esc is pressed at any point, immediately returns 'esc'.
    """
    if not sys.stdin.isatty():
        try:
            return input(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            return "esc"

    import termios
    import tty

    sys.stdout.write(prompt_text)
    sys.stdout.flush()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    chars = []

    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            # ESC key detection (ASCII 27)
            if ch == "\x1b":
                # Check if it's a lone ESC press or arrow key escape sequence
                # Set non-blocking read for next 0.05s
                import select
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if not r:
                    # Pure lone ESC key pressed!
                    return "esc"
                else:
                    # Arrow key or sequence - discard sequence
                    sys.stdin.read(2)
                    continue
            elif ch in ("\r", "\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                break
            elif ch in ("\x03", "\x04"):  # Ctrl+C or Ctrl+D
                return "esc"
            elif ch in ("\x08", "\x7f"):  # Backspace
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            else:
                chars.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return "".join(chars).strip()

def move_or_rename_chat(chat):
    cid = chat["id"]
    print(f"\nEdit chat #{chat.get('index', '')}: {chat['title']}")
    new_title = input(f"New title [Enter to keep: '{chat['title']}']: ").strip()
    new_group = input(f"Assign to group [Enter to keep: '{chat['group']}']: ").strip()

    with FileLock(LOCK_FILE):
        records = read_master_tsv()
        updated = False
        for r in records:
            if r["id"] == cid:
                if new_title:
                    r["title"] = new_title
                if new_group:
                    r["group"] = new_group
                updated = True
                break
        if updated:
            write_master_tsv(records)
            print("\n✔ Updated. Refreshing...")
            time.sleep(0.5)

def configure_alias_interactive():
    clear_screen()
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
        except Exception:
            pass

    current_alias = cfg.get("cli_command", "agy")
    print("==========================================")
    print("           CLI Alias & Shortcuts          ")
    print("==========================================")
    print(f"  Current Launcher Alias: '{current_alias}'")
    print(f"  Active Shortcuts:       {current_alias}-h (list), {current_alias}-m (menu)")
    print("------------------------------------------")
    print("Enter new alias name (e.g. 'ag', 'antig', 'ai', 'agy')")
    print("Or press Enter / ESC to keep current.")
    print("------------------------------------------")
    new_alias = get_prompt_input("New Alias > ")

    if not new_alias or new_alias == "esc" or new_alias == current_alias:
        return

    cfg["cli_command"] = new_alias
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    bin_cand = os.path.abspath(os.path.join(script_dir, "..", "bin"))
    if not os.path.isdir(bin_cand):
        bin_cand = "/mnt/a/anti-g/bin"

    setup_script = os.path.join(bin_cand, "setup_alias.sh")
    if os.path.exists(setup_script):
        try:
            subprocess.run([setup_script, new_alias], check=True, stdout=subprocess.DEVNULL)
            print(f"\n✔ Successfully switched alias to '{new_alias}'!")
            print(f"   - Quick list:        {new_alias}-h")
            print(f"   - Interactive menu:  {new_alias}-m")
        except Exception:
            print(f"\n✔ Updated config to '{new_alias}'.")
    else:
        print(f"\n✔ Updated config to '{new_alias}'.")

    time.sleep(1.2)

def configure_time_window():
    clear_screen()
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
        except Exception:
            pass

    cur_days = cfg.get("default_days", 0)
    cur_str = f"Past {cur_days} days" if cur_days > 0 else "All time (No limit)"

    print("==========================================")
    print("        Default Time Window Filter        ")
    print("==========================================")
    print(f"  Current Default: {cur_str}")
    print("------------------------------------------")
    print("  [1] All time (Show all chats)")
    print("  [2] Past 7 days")
    print("  [3] Past 14 days")
    print("  [4] Past 30 days")
    print("  [5] Custom number of days")
    print("  [b] Cancel / ESC")
    print("------------------------------------------")
    ch = get_prompt_input("Select > ").lower()

    if ch in ("b", "back", "esc"):
        return
    elif ch == "1":
        cfg["default_days"] = 0
    elif ch == "2":
        cfg["default_days"] = 7
    elif ch == "3":
        cfg["default_days"] = 14
    elif ch == "4":
        cfg["default_days"] = 30
    elif ch == "5":
        raw = get_prompt_input("Enter days (e.g. 3): ")
        if raw.isdigit():
            cfg["default_days"] = int(raw)
        else:
            return

    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        print("\n✔ Saved default time filter.")
    except Exception as e:
        print(f"Error saving: {e}")
    time.sleep(0.8)

def show_storage_info():
    clear_screen()
    records = read_master_tsv()
    size_bytes = os.path.getsize(MASTER_TSV) if os.path.exists(MASTER_TSV) else 0

    print("==========================================")
    print("         Storage & Diagnostics            ")
    print("==========================================")
    print(f"  Data Directory:      {DATA_DIR}")
    print(f"  Master History TSV:  {MASTER_TSV}")
    print(f"  Total Chats Saved:   {len(records)} sessions")
    print(f"  File Size on Disk:   {size_bytes} bytes ({size_bytes/1024:.2f} KB)")
    print(f"  Antigravity Brain:   {BRAIN_DIR}")
    print("------------------------------------------")
    get_prompt_input("Press Enter or ESC to return...")

def backup_history_log():
    clear_screen()
    if not os.path.exists(MASTER_TSV):
        print("No master_history.tsv found to backup.")
        time.sleep(1)
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_name = f"master_history_backup_{ts}.tsv"
    bak_path = os.path.join(DATA_DIR, bak_name)

    try:
        shutil.copy2(MASTER_TSV, bak_path)
        print("==========================================")
        print("          History Backup Created          ")
        print("==========================================")
        print(f"  Backup saved to:")
        print(f"  {bak_path}")
        print("------------------------------------------")
    except Exception as e:
        print(f"Error creating backup: {e}")

    get_prompt_input("Press Enter or ESC to return...")

def restore_history_log():
    clear_screen()
    print("==========================================")
    print("         Restore History Log (TSV)        ")
    print("==========================================")
    
    # Look for available backups in DATA_DIR
    baks = sorted(glob.glob(os.path.join(DATA_DIR, "master_history_backup_*.tsv")), reverse=True)
    if not baks:
        print("  No previous backups found in:")
        print(f"  {DATA_DIR}")
        print("------------------------------------------")
        get_prompt_input("Press Enter or ESC to return...")
        return

    print("Available backups:")
    for idx, b in enumerate(baks[:10], 1):
        bname = os.path.basename(b)
        size = os.path.getsize(b)
        print(f"  [{idx}] {bname} ({size} bytes)")
    print("------------------------------------------")
    print("Enter number to restore, or ESC/b to cancel")
    choice = get_prompt_input("Select > ")

    if choice.isdigit() and 1 <= int(choice) <= len(baks):
        selected_bak = baks[int(choice) - 1]
        try:
            with FileLock(LOCK_FILE):
                shutil.copy2(selected_bak, MASTER_TSV)
                # Mirror to plugin_data if applicable
                mirror_dir = os.path.expanduser("~/.gemini/antigravity-cli/plugin_data/sessionlist")
                if os.path.exists(mirror_dir) and mirror_dir != os.path.dirname(MASTER_TSV):
                    shutil.copy2(MASTER_TSV, os.path.join(mirror_dir, "master_history.tsv"))
            print(f"\n✔ Successfully restored master history from:")
            print(f"  {os.path.basename(selected_bak)}")
        except Exception as e:
            print(f"\nError restoring backup: {e}")
        time.sleep(1.5)

def export_chat_to_markdown():
    clear_screen()
    chats = get_all_chats()
    if not chats:
        print("No chats found to export.")
        time.sleep(1)
        return

    print("==========================================")
    print("        Export Conversation to MD         ")
    print("==========================================")
    for idx, c in enumerate(chats[:15], 1):
        print(f"  [{idx:2d}] {c['time_label']:<10} {c['title'][:36]}")
    print("------------------------------------------")
    print("Options: <num> export chat | 'all' export all | ESC back")
    choice = get_prompt_input("Select > ").strip().lower()

    if choice in ("b", "back", "q", "quit", "esc", ""):
        return

    export_dir = os.path.abspath(os.path.join(DATA_DIR, "..", "exported_chats"))
    os.makedirs(export_dir, exist_ok=True)

    targets = []
    if choice == "all":
        targets = chats
    elif choice.isdigit() and 1 <= int(choice) <= len(chats):
        targets = [chats[int(choice) - 1]]
    else:
        print("Invalid choice.")
        time.sleep(1)
        return

    exported_count = 0
    for c in targets:
        cid = c["id"]
        # Find transcript
        cand_paths = [
            os.path.join(BRAIN_DIR, cid, ".system_generated", "logs", "transcript.jsonl"),
            os.path.join(BRAIN_DIR, cid, ".system_generated", "logs", "transcript_full.jsonl")
        ]
        tpath = None
        for p in cand_paths:
            if os.path.exists(p):
                tpath = p
                break

        clean_slug = re.sub(r"[^\w\-_\. ]", "_", c["title"]).strip().replace(" ", "_")[:35]
        if not clean_slug:
            clean_slug = "chat"
        md_filename = f"{c['exact_time'].replace(':', '')}_{clean_slug}_{cid[:6]}.md"
        out_path = os.path.join(export_dir, md_filename)

        md_lines = [
            f"# {c['title']}\n",
            f"- **Session ID**: `{cid}`",
            f"- **Group**: {c['group']}",
            f"- **Date**: {c['time_label']} at {c['exact_time']}",
            f"- **Messages Recorded**: {c['msgs']}\n",
            "---\n\n"
        ]

        if tpath:
            try:
                with open(tpath, "r", encoding="utf-8", errors="ignore") as f:
                    turn = 1
                    for line in f:
                        try:
                            entry = json.loads(line)
                            t = entry.get("type")
                            src = entry.get("source")
                            content = entry.get("content", "")
                            cleaned = clean_text(content)

                            if t == "USER_INPUT" and cleaned:
                                md_lines.append(f"### Turn {turn} (User)\n\n{cleaned}\n\n")
                                turn += 1
                            elif t == "PLANNER_RESPONSE" and cleaned:
                                md_lines.append(f"**Assistant**:\n\n{cleaned}\n\n")
                        except Exception:
                            pass
            except Exception as e:
                md_lines.append(f"*(Error parsing transcript: {e})*\n")
        else:
            md_lines.append("*(Transcript file not found on disk for this sandbox)*\n")

        with open(out_path, "w", encoding="utf-8") as f:
            f.writelines(md_lines)
        exported_count += 1

    print(f"\n✔ Successfully exported {exported_count} conversation(s) to:")
    print(f"  {export_dir}")
    get_prompt_input("\nPress Enter or ESC to return...")

def settings_view():
    while True:
        clear_screen()
        print("==========================================")
        print("                 Settings                 ")
        print("==========================================")
        print("  [1] CLI Alias & Shortcuts (Rename)")
        print("  [2] Default Time Window Filter")
        print("  [3] Export Chats to Markdown (.md)")
        print("  [4] Backup Master History (TSV)")
        print("  [5] Restore Master History from Backup")
        print("  [6] Storage & Diagnostics Info")
        print("  [b] Back / ESC")
        print("------------------------------------------")
        choice = get_prompt_input("Select > ").lower()

        if choice in ("b", "back", "q", "quit", "esc"):
            break
        elif choice == "1":
            configure_alias_interactive()
        elif choice == "2":
            configure_time_window()
        elif choice == "3":
            export_chat_to_markdown()
        elif choice == "4":
            backup_history_log()
        elif choice == "5":
            restore_history_log()
        elif choice == "6":
            show_storage_info()

def start_new_chat():
    cli_cmd = detect_cli_command()
    clear_screen()
    print("Launching new Antigravity chat session...")
    parts = cli_cmd.split()
    cmd_binary = parts[0]
    args = parts
    try:
        os.execvp(cmd_binary, args)
    except FileNotFoundError:
        subprocess.call(cli_cmd, shell=True, executable="/bin/bash")
        sys.exit(0)

def resume_chat(cid):
    cli_cmd = detect_cli_command()
    clear_screen()
    parts = cli_cmd.split()
    cmd_binary = parts[0]
    args = parts + ["--conversation", cid]
    try:
        os.execvp(cmd_binary, args)
    except FileNotFoundError:
        subprocess.call(f"{cli_cmd} --conversation {cid}", shell=True, executable="/bin/bash")
        sys.exit(0)

# ==========================================
# INTERACTIVE TERMINAL VIEWS (ach)
# ==========================================

def all_chats_view():
    while True:
        clear_screen()
        chats = get_all_chats()
        for idx, c in enumerate(chats, 1):
            c["index"] = idx
        print("==========================================")
        print("                All Chats                 ")
        print("==========================================")
        render_terminal_table(chats, limit=None)
        print("\nCmds: <num> resume | e <num> edit | d <n1,n2..> del | n new | Esc/b back")
        cmd = get_prompt_input("Select > ")

        if cmd.lower() in ("b", "back", "q", "quit", "esc"):
            break
        elif cmd.lower() in ("n", "new"):
            start_new_chat()
            break
        elif cmd.lower().startswith("e "):
            part = cmd[2:].strip()
            if part.isdigit() and 1 <= int(part) <= len(chats):
                move_or_rename_chat(chats[int(part) - 1])
        elif cmd.lower().startswith("d ") or cmd.lower().startswith("del ") or cmd.lower().startswith("d,") or cmd.lower().startswith("del,"):
            raw_input = re.sub(r"^(del|d)[\s,]*", "", cmd, flags=re.I).strip()
            tokens = re.split(r"[\s,]+", raw_input)
            selected = []
            for t in tokens:
                if t.isdigit():
                    idx = int(t)
                    if 1 <= idx <= len(chats):
                        target = chats[idx - 1]
                        if target not in selected:
                            selected.append(target)
            if selected:
                delete_chats_multi(selected)
            else:
                print("Invalid chat numbers. Usage: d 1,2,4")
                input("Press Enter...")
        elif cmd.isdigit() and 1 <= int(cmd) <= len(chats):
            resume_chat(chats[int(cmd) - 1]["id"])

def search_chats_cli(query):
    chats = get_all_chats()
    q = query.lower()
    matched = [c for c in chats if q in c["title"].lower() or q in c["group"].lower() or q in c["time_label"].lower()]
    print(f"Found {len(matched)} chat(s) matching '{query}':")
    render_terminal_table(matched)

def list_groups_cli():
    chats = get_all_chats()
    groups = {}
    for c in chats:
        groups.setdefault(c["group"], []).append(c)
    print("Groups & Notebooks:")
    for idx, (g, clist) in enumerate(sorted(groups.items()), 1):
        print(f"  [{idx}] {g} ({len(clist)} chat{'s' if len(clist) != 1 else ''})")

def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--help", "-h"):
            print("""sessionList (v2.1 Master Log)
Usage:
  ach                 Interactive terminal manager
  ach --list          Fast direct list of recent chats
  ach --all           Show complete history
  ach --days <N>      Filter by last N days (e.g. --days 7)
  ach --hours <N>     Filter by last N hours (e.g. --hours 2)
  ach --search-cli <q> Search titles & groups
  ach --groups-cli    List all notebook groups
  ach --set-title <id> "<title>" Set clean abstracted title
""")
            return
        elif arg == "--list":
            render_terminal_table(get_all_chats(), limit=15)
            return
        elif arg in ("--all", "--list-all"):
            render_terminal_table(get_all_chats(), limit=None)
            return
        elif arg in ("--days", "-d"):
            days = float(sys.argv[2]) if len(sys.argv) > 2 else 7.0
            now_ts = datetime.now().timestamp()
            chats = [c for c in get_all_chats() if (now_ts - c["mtime"]) <= (days * 86400)]
            render_terminal_table(chats)
            return
        elif arg in ("--hours", "-H"):
            hours = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
            now_ts = datetime.now().timestamp()
            chats = [c for c in get_all_chats() if (now_ts - c["mtime"]) <= (hours * 3600)]
            render_terminal_table(chats)
            return
        elif arg == "--search-cli":
            q = sys.argv[2] if len(sys.argv) > 2 else ""
            search_chats_cli(q)
            return
        elif arg == "--groups-cli":
            list_groups_cli()
            return
        elif arg == "--set-title":
            cid = sys.argv[2] if len(sys.argv) > 2 else ""
            t = sys.argv[3] if len(sys.argv) > 3 else ""
            set_chat_title(cid, t)
            return
        elif arg == "--group-window":
            gname = sys.argv[2] if len(sys.argv) > 2 else ""
            unit = sys.argv[3].lower() if len(sys.argv) > 3 else "--hours"
            val = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
            sec = val * 86400 if "day" in unit else val * 3600
            q = sys.argv[6] if len(sys.argv) > 6 and sys.argv[5] == "--match" else None
            smart_group(gname, max_age_seconds=sec, query=q)
            return
        elif arg == "--group-ids":
            gname = sys.argv[2] if len(sys.argv) > 2 else ""
            ids = sys.argv[3:] if len(sys.argv) > 3 else []
            smart_group(gname, ids=ids)
            return

    while True:
        clear_screen()
        print("==========================================")
        print("               sessionList                ")
        print("==========================================")
        print("  [1] All Chats")
        print("  [2] Search & Resume")
        print("  [3] Groups & Notebooks")
        print("  [4] Settings")
        print("  [q] Quit (or press ESC)")
        print("------------------------------------------")
        choice = get_prompt_input("Select > ").lower()

        if choice in ("q", "quit", "exit", "esc"):
            clear_screen()
            break
        elif choice == "1":
            all_chats_view()
        elif choice == "2":
            q = get_prompt_input("Search query: ")
            if q and q != "esc":
                search_chats_cli(q)
                print("\nOptions: <num> resume | n new chat | Enter/Esc return")
                sub = get_prompt_input("Select > ").lower()
                if sub in ("n", "new"):
                    start_new_chat()
                    break
                elif sub.isdigit():
                    matched = [c for c in get_all_chats() if q.lower() in c["title"].lower() or q.lower() in c["group"].lower() or q.lower() in c["time_label"].lower()]
                    if 1 <= int(sub) <= len(matched):
                        resume_chat(matched[int(sub) - 1]["id"])
                        break
        elif choice == "3":
            list_groups_cli()
            get_prompt_input("\nPress Enter or Esc to continue...")
        elif choice in ("4", "s", "set", "settings"):
            settings_view()

if __name__ == "__main__":
    main()
