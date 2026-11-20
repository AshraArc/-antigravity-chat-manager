#!/usr/bin/env python3
"""
Antigravity Chat Manager (ACM)
Portable, interactive chat history browser, notebook organizer, and session launcher
for Google Antigravity CLI (agy) and user-defined aliases.
"""

import os
import sys
import glob
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta

# User configuration paths
CONFIG_DIR = os.path.expanduser("~/.config/antigravity-chat-manager")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
METADATA_FILE = os.path.join(CONFIG_DIR, "metadata.json")
BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity-cli/brain")

def clear_screen():
    sys.stdout.write("\033[H\033[2J\033[3J")
    sys.stdout.flush()

def get_config_dir():
    # Priority: ~/.config/antigravity-chat-manager -> ~/.cache/antigravity-chat-manager -> /tmp
    preferred = os.path.expanduser("~/.config/antigravity-chat-manager")
    try:
        os.makedirs(preferred, exist_ok=True)
        return preferred
    except OSError:
        fallback = os.path.expanduser("~/.cache/antigravity-chat-manager")
        try:
            os.makedirs(fallback, exist_ok=True)
            return fallback
        except OSError:
            tmp = "/tmp/antigravity-chat-manager"
            os.makedirs(tmp, exist_ok=True)
            return tmp

def load_config():
    cfg_dir = get_config_dir()
    cfg_file = os.path.join(cfg_dir, "config.json")
    default_cfg = {"cli_command": ""}
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r") as f:
                cfg = json.load(f)
                return {**default_cfg, **cfg}
        except Exception:
            return default_cfg
    return default_cfg

def save_config(cfg):
    cfg_dir = get_config_dir()
    cfg_file = os.path.join(cfg_dir, "config.json")
    try:
        with open(cfg_file, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")

def detect_cli_command(force_reconfigure=False):
    """
    Detects how the user launches Antigravity CLI:
    1. Check config file
    2. Check environment variable AGY_CMD
    3. Check PATH for 'agy'
    4. Check common locations (~/.local/bin/agy, etc.)
    5. Fallback: prompt the user and save
    """
    cfg = load_config()
    cmd = cfg.get("cli_command", "").strip()

    if cmd and not force_reconfigure:
        return cmd

    # Check env var
    env_cmd = os.environ.get("AGY_CMD", "").strip()
    if env_cmd:
        cfg["cli_command"] = env_cmd
        save_config(cfg)
        return env_cmd

    # Auto-detection: check if 'agy' binary is in PATH
    if shutil.which("agy"):
        detected = "agy"
    elif os.path.exists(os.path.expanduser("~/.local/bin/agy")):
        detected = os.path.expanduser("~/.local/bin/agy")
    elif os.path.exists(os.path.expanduser("~/.gemini/antigravity-cli/bin/agy")):
        detected = os.path.expanduser("~/.gemini/antigravity-cli/bin/agy")
    else:
        detected = "agy"

    if force_reconfigure or not cmd:
        print("\n--- Antigravity CLI Setup ---")
        print(f"Detected default launcher: '{detected}'")
        user_choice = input(f"Enter the command/alias you use to run Antigravity [{detected}]: ").strip()
        final_cmd = user_choice if user_choice else detected
        cfg["cli_command"] = final_cmd
        save_config(cfg)
        print(f"✔ Saved launcher command: '{final_cmd}'\n")
        return final_cmd

    return cmd

def load_metadata():
    cfg_dir = get_config_dir()
    meta_file = os.path.join(cfg_dir, "metadata.json")
    if os.path.exists(meta_file):
        try:
            with open(meta_file, "r") as f:
                return json.load(f)
        except Exception:
            return {"chats": {}, "groups": ["General"]}
    return {"chats": {}, "groups": ["General"]}

def save_metadata(data):
    cfg_dir = get_config_dir()
    meta_file = os.path.join(cfg_dir, "metadata.json")
    try:
        with open(meta_file, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving metadata: {e}")

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<USER_REQUEST>", "", text)
    text = re.sub(r"</USER_REQUEST>", "", text)
    text = re.sub(r"<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>", "", text)
    text = re.sub(r"<SYSTEM_MESSAGE>[\s\S]*?</SYSTEM_MESSAGE>", "", text)
    text = " ".join(text.split())
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

def get_all_chats():
    data = load_metadata()
    chats_meta = data.get("chats", {})
    convos = []
    now = datetime.now()

    pattern = os.path.join(BRAIN_DIR, "*", ".system_generated", "logs", "transcript.jsonl")
    files = glob.glob(pattern)

    for fpath in files:
        cid = fpath.split(os.sep)[-4]
        mtime = os.path.getmtime(fpath)
        dt = datetime.fromtimestamp(mtime)
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
            continue

        c_info = chats_meta.get(cid, {})
        group = c_info.get("group", "General")
        custom_title = c_info.get("title", "")

        title = custom_title if custom_title else (first_prompt[:45] + ("..." if len(first_prompt) > 45 else ""))
        if not title:
            title = "(Empty conversation)"

        time_label = get_relative_date_label(dt, now)

        convos.append({
            "id": cid,
            "mtime": mtime,
            "dt": dt,
            "time_label": time_label,
            "exact_time": dt.strftime("%H:%M"),
            "msgs": user_turns,
            "group": group,
            "title": title,
            "folder": os.path.dirname(os.path.dirname(os.path.dirname(fpath)))
        })

    convos.sort(key=lambda x: x["mtime"], reverse=True)
    return convos

def resume_chat(cid):
    cli_cmd = detect_cli_command()
    clear_screen()
    # Support both full binary paths and custom alias wrappers
    parts = cli_cmd.split()
    cmd_binary = parts[0]
    args = parts + ["--conversation", cid]

    try:
        os.execvp(cmd_binary, args)
    except FileNotFoundError:
        # If user gave an alias that is only a shell function, invoke via bash -ic
        subprocess.call(f"{cli_cmd} --conversation {cid}", shell=True, executable="/bin/bash")
        sys.exit(0)

def delete_single_chat(chat):
    confirm = input(f"Delete chat '{chat['title']}'? (y/N): ").strip().lower()
    if confirm == "y":
        try:
            if os.path.exists(chat["folder"]):
                shutil.rmtree(chat["folder"])
            data = load_metadata()
            if chat["id"] in data.get("chats", {}):
                del data["chats"][chat["id"]]
                save_metadata(data)
        except Exception as e:
            print(f"Error deleting: {e}")

def create_group():
    gname = input("Enter new group name: ").strip()
    if not gname:
        return
    data = load_metadata()
    existing = [g.lower() for g in data.get("groups", [])]
    if gname.lower() in existing:
        return
    data.setdefault("groups", []).append(gname)
    save_metadata(data)

def delete_group(group_name):
    if group_name.lower() == "general":
        input("Cannot delete default 'General' group. Press Enter...")
        return

    data = load_metadata()
    all_chats = get_all_chats()
    group_chats = [c for c in all_chats if c["group"].lower() == group_name.lower()]

    print(f"This will delete group '{group_name}' and all {len(group_chats)} chat(s) in it.")
    confirm = input("Are you sure? (y/N): ").strip().lower()
    if confirm == "y":
        for c in group_chats:
            if os.path.exists(c["folder"]):
                shutil.rmtree(c["folder"])
            if c["id"] in data.get("chats", {}):
                del data["chats"][c["id"]]

        data["groups"] = [g for g in data.get("groups", []) if g.lower() != group_name.lower()]
        save_metadata(data)

def move_or_rename_chat(chat):
    data = load_metadata()
    cid = chat["id"]
    if cid not in data["chats"]:
        data["chats"][cid] = {}

    print(f"\nEdit chat: {chat['title']}")
    new_title = input(f"New title [press Enter to keep: '{chat['title']}']: ").strip()
    new_group = input(f"Assign to group [press Enter to keep: '{chat['group']}']: ").strip()

    if new_title:
        data["chats"][cid]["title"] = new_title
    if new_group:
        data["chats"][cid]["group"] = new_group
        existing = [g.lower() for g in data.get("groups", [])]
        if new_group.lower() not in existing:
            data.setdefault("groups", []).append(new_group)

    save_metadata(data)

def search_chats():
    convos = get_all_chats()
    if not convos:
        clear_screen()
        print("No chats found.")
        input("Press Enter...")
        return

    has_fzf = subprocess.call(["which", "fzf"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    if has_fzf and sys.stdin.isatty():
        lines = [f"{c['id']} | [{c['time_label']}] [{c['group']}] ({c['msgs']} msgs) | {c['title']}" for c in convos]
        proc = subprocess.Popen(
            ["fzf", "--reverse", "--header=Select chat to resume (Esc to cancel):", "--delimiter=\\|", "--with-nth=2.."],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
        )
        out, _ = proc.communicate(input="\n".join(lines))
        if proc.returncode == 0 and out.strip():
            selected_id = out.strip().split("|")[0].strip()
            resume_chat(selected_id)
    else:
        clear_screen()
        query = input("Search query: ").strip().lower()
        matches = [c for c in convos if query in c["title"].lower() or query in c["group"].lower() or query in c["time_label"].lower()]
        if not matches:
            print("No matching chats.")
            input("Press Enter...")
            return

        print("\nResults:")
        for idx, c in enumerate(matches, 1):
            print(f"  [{idx}] [{c['time_label']}] [{c['group']}] - {c['title']}")
        choice = input("\nEnter number to resume (or Enter to cancel): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            resume_chat(matches[int(choice) - 1]["id"])

def group_view():
    while True:
        clear_screen()
        data = load_metadata()
        chats = get_all_chats()
        all_group_names = set(data.get("groups", ["General"]))

        groups = {g: [] for g in all_group_names}
        for c in chats:
            groups.setdefault(c["group"], []).append(c)

        print("---------------- GROUPS ----------------")
        sorted_groups = sorted(groups.keys())
        for idx, g in enumerate(sorted_groups, 1):
            count = len(groups[g])
            print(f"  [{idx}] {g} ({count} chat{'s' if count != 1 else ''})")
        print("----------------------------------------")
        print("Actions: <num> open, new, del-group <name>, b/q (back)")
        cmd = input("Group > ").strip()

        if cmd.lower() in ("b", "back", "q", "quit", "exit", ""):
            break
        elif cmd.lower() in ("new", "create", "new-group"):
            create_group()
        elif cmd.lower().startswith("del-group "):
            gname = cmd.split(maxsplit=1)[1].strip()
            delete_group(gname)
        elif cmd.isdigit() and 1 <= int(cmd) <= len(sorted_groups):
            selected_group = sorted_groups[int(cmd) - 1]
            inside_group_view(selected_group)

def inside_group_view(group_name):
    while True:
        clear_screen()
        chats = [c for c in get_all_chats() if c["group"] == group_name]
        print(f"--- Group: {group_name} ---")
        if not chats:
            print("  (No chats in this group)")
            input("\nPress Enter to go back...")
            return

        current_label = None
        for idx, c in enumerate(chats, 1):
            if c["time_label"] != current_label:
                current_label = c["time_label"]
                print(f"\n[{current_label}]")
            print(f"  [{idx}] {c['exact_time']} ({c['msgs']} msgs) | {c['title']}")

        print("\n" + "-" * 35)
        print("Actions: <num> resume, edit <num>, del <num>, b/q (back)")
        cmd = input(f"{group_name} > ").strip()

        if cmd.lower() in ("b", "back", "q", "quit", "exit", ""):
            break

        parts = cmd.split()
        act = parts[0].lower()

        if act == "del" and len(parts) > 1 and parts[1].isdigit():
            i = int(parts[1]) - 1
            if 0 <= i < len(chats):
                delete_single_chat(chats[i])
        elif act == "edit" and len(parts) > 1 and parts[1].isdigit():
            i = int(parts[1]) - 1
            if 0 <= i < len(chats):
                move_or_rename_chat(chats[i])
        elif act.isdigit() and 1 <= int(act) <= len(chats):
            resume_chat(chats[int(act) - 1]["id"])

def recent_chats_view():
    while True:
        clear_screen()
        chats = get_all_chats()
        if not chats:
            print("No chats found.")
            input("Press Enter...")
            return

        print("---------------- RECENT CHATS ----------------")
        current_label = None
        for idx, c in enumerate(chats, 1):
            if c["time_label"] != current_label:
                current_label = c["time_label"]
                print(f"\n[{current_label}]")
            print(f"  [{idx:2d}] [{c['group']}] {c['exact_time']} ({c['msgs']:2d}) | {c['title']}")
        print("\n----------------------------------------------")
        print("Actions: <num> resume, edit <num>, del <num>, b/q (back)")
        cmd = input("Recent > ").strip()

        if cmd.lower() in ("b", "back", "q", "quit", "exit", ""):
            break

        parts = cmd.split()
        act = parts[0].lower()

        if act == "del" and len(parts) > 1 and parts[1].isdigit():
            i = int(parts[1]) - 1
            if 0 <= i < len(chats):
                delete_single_chat(chats[i])
        elif act == "edit" and len(parts) > 1 and parts[1].isdigit():
            i = int(parts[1]) - 1
            if 0 <= i < len(chats):
                move_or_rename_chat(chats[i])
        elif act.isdigit() and 1 <= int(act) <= len(chats):
            resume_chat(chats[int(act) - 1]["id"])

def print_help():
    print("""
sessionList - Antigravity Chat History Manager

Usage:
  ach                  Launch interactive terminal session manager
  ach --search         Directly trigger fuzzy/text search across past chats
  ach --list           Output plain text list of chats (default cap: 15)
  ach --all            Output complete chat archive
  ach --days <N>       Filter chats from the last N days (e.g. --days 7)
  ach --hours <N>      Filter chats from the last N hours (e.g. --hours 2)
  ach --groups-cli     Output list of groups (for in-chat / CLI)
  ach --search-cli <q> Search chats via command line
  ach --config         Reconfigure your Antigravity launcher command or alias
  ach --help           Show this help message
""")

def list_chats_cli(limit=15, max_age_seconds=None):
    chats = get_all_chats()
    if not chats:
        print("No chats found.")
        return

    now_ts = datetime.now().timestamp()
    if max_age_seconds is not None:
        filtered = [c for c in chats if (now_ts - c["mtime"]) <= max_age_seconds]
        if not filtered:
            print("No chats found within the specified time range.")
            return
        chats = filtered
        limit = None  # Show all matching within that time filter

    total_chats = len(chats)
    displayed_chats = chats if limit is None else chats[:limit]

    current_label = None
    for idx, c in enumerate(displayed_chats, 1):
        if c["time_label"] != current_label:
            current_label = c["time_label"]
            print(f"\n[{current_label}]")
        print(f"  [{idx:2d}] [{c['group']}] {c['exact_time']} ({c['msgs']:2d} msgs) | {c['title']} | ID: {c['id']}")

    if limit is not None and total_chats > limit:
        print(f"\nShowing {limit} most recent sessions. To see all {total_chats} chats, ask: 'show me all chat histories'")

def list_groups_cli():
    data = load_metadata()
    chats = get_all_chats()
    all_group_names = set(data.get("groups", ["General"]))
    groups = {g: [] for g in all_group_names}
    for c in chats:
        groups.setdefault(c["group"], []).append(c)

    print("Groups & Notebooks:")
    for idx, g in enumerate(sorted(groups.keys()), 1):
        count = len(groups[g])
        print(f"  [{idx}] {g} ({count} chat{'s' if count != 1 else ''})")

def search_chats_cli(query):
    convos = get_all_chats()
    matches = [c for c in convos if query.lower() in c["title"].lower() or query.lower() in c["group"].lower()]
    if not matches:
        print(f"No chats matching '{query}'.")
        return
    print(f"Found {len(matches)} chat(s) matching '{query}':")
    for idx, c in enumerate(matches, 1):
        print(f"  [{idx}] [{c['time_label']}] [{c['group']}] {c['title']} | ID: {c['id']}")

def bulk_group_by_time(group_name, max_age_seconds):
    if not group_name:
        print("Group name cannot be empty.")
        return

    data = load_metadata()
    chats = get_all_chats()
    now_ts = datetime.now().timestamp()
    matching = [c for c in chats if (now_ts - c["mtime"]) <= max_age_seconds]

    if not matching:
        print("No chats found within the specified time window to group.")
        return

    for c in matching:
        cid = c["id"]
        if cid not in data["chats"]:
            data["chats"][cid] = {}
        data["chats"][cid]["group"] = group_name

    existing = [g.lower() for g in data.get("groups", [])]
    if group_name.lower() not in existing:
        data.setdefault("groups", []).append(group_name)

    save_metadata(data)
    print(f"✔ Successfully grouped {len(matching)} chat(s) into '{group_name}'.")

def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("-h", "--help"):
            print_help()
            return
        elif arg in ("--config", "-c"):
            detect_cli_command(force_reconfigure=True)
            return
        elif arg in ("--search", "-s"):
            search_chats()
            return
        elif arg == "--list":
            # Default cap: 15 recent sessions (or ~1 week)
            list_chats_cli(limit=15)
            return
        elif arg in ("--list-all", "--all"):
            list_chats_cli(limit=None)
            return
        elif arg in ("--days", "-d"):
            days = float(sys.argv[2]) if len(sys.argv) > 2 else 7.0
            list_chats_cli(max_age_seconds=days * 86400)
            return
        elif arg in ("--hours", "-H"):
            hours = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
            list_chats_cli(max_age_seconds=hours * 3600)
            return
        elif arg == "--group-window":
            # Syntax: --group-window <group_name> --hours <N> OR --days <N>
            gname = sys.argv[2] if len(sys.argv) > 2 else ""
            unit = sys.argv[3].lower() if len(sys.argv) > 3 else "--hours"
            val = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
            sec = val * 86400 if "day" in unit else val * 3600
            bulk_group_by_time(gname, sec)
            return
        elif arg == "--groups-cli":
            list_groups_cli()
            return
        elif arg == "--search-cli":
            q = sys.argv[2] if len(sys.argv) > 2 else ""
            search_chats_cli(q)
            return

    while True:
        clear_screen()
        print("==========================================")
        print("               sessionList                ")
        print("==========================================")
        print("  [1] Recent Chats")
        print("  [2] Groups")
        print("  [3] Search")
        print("  [q] Quit")
        print("------------------------------------------")
        choice = input("Select > ").strip().lower()

        if choice in ("q", "quit", "exit"):
            clear_screen()
            break
        elif choice == "1":
            recent_chats_view()
        elif choice == "2":
            group_view()
        elif choice == "3":
            search_chats()

if __name__ == "__main__":
    main()
