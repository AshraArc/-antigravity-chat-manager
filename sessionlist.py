#!/usr/bin/env python3
"""
sessionList (v2.2 SQLite WAL + FTS5 & Multi-Workspace Architecture)
High-efficiency, zero-overhead session history manager for Google Antigravity CLI.
Uses SQLite WAL mode with FTS5 full-text indexing, multi-workspace directory discovery,
hardened locking, and backward-compatible TSV master mirroring.
Guaranteed fit for 80-column terminal displays.
"""

import os
import sys
import glob
import json
import re
import shutil
import sqlite3
import subprocess
try:
    import fcntl
except ImportError:
    fcntl = None
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
HISTORY_DB = os.path.join(DATA_DIR, "history.db")
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

WORKSPACES_FILE = os.path.join(DATA_DIR, "workspaces.json")

def load_workspaces():
    try:
        with open(WORKSPACES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_workspace(cid, path):
    data = load_workspaces()
    data[cid] = path
    try:
        tmp = WORKSPACES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, WORKSPACES_FILE)
    except Exception:
        pass


def detect_antigravity_root():
    """Detects primary Antigravity workspace root."""
    if os.environ.get("AGY_ROOT") and os.path.isdir(os.environ.get("AGY_ROOT")):
        return os.path.abspath(os.environ.get("AGY_ROOT"))

    antig_candidates = [
        "/mnt/a/anti-g",
        os.path.expanduser("~/anti-g"),
        os.path.join(os.path.expanduser("~"), "antigravity")
    ]
    for cand in antig_candidates:
        if os.path.isdir(cand):
            return os.path.abspath(cand)

    # Search standard config or bash profile if available
    for p in [os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.profile")]:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        m = re.search(r'export\s+(?:AGY_ROOT|ANTIGRAVITY_ROOT)=["\']?([^"\'\s]+)', line)
                        if m and os.path.isdir(m.group(1)):
                            return os.path.abspath(m.group(1))
            except Exception:
                pass

    # Look upwards from CWD for .agents or .gemini folder
    try:
        curr = os.path.abspath(os.getcwd())
        while curr and curr != os.path.dirname(curr):
            if os.path.isdir(os.path.join(curr, ".agents")) or os.path.isdir(os.path.join(curr, ".gemini")):
                return curr
            curr = os.path.dirname(curr)
    except Exception:
        pass

    return None

def infer_workspace(cid):
    """Best-effort guess of a chat's folder from the directories its tools ran in."""
    counts = {}
    fpath = os.path.join(BRAIN_DIR, cid, ".system_generated", "logs", "transcript_full.jsonl")
    if not os.path.exists(fpath):
        fpath = os.path.join(BRAIN_DIR, cid, ".system_generated", "logs", "transcript.jsonl")
    pat = re.compile(r'"(?:Cwd|cwd)":\s*"(/[^"]+)"|\bcd (/[^\s"&;\\]+)')
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                for m in pat.finditer(line):
                    d = m.group(1) or m.group(2)
                    if d and os.path.isdir(d):
                        counts[d] = counts.get(d, 0) + 1
    except Exception:
        return None
    return max(counts, key=counts.get) if counts else None

def scan_project_workspaces(root=None):
    """
    Discovers project workspaces under the given root (or default Antigravity root).
    Scans:
      - Active git repositories under root/projects
      - Direct subdirectories and nested versioned project dirs (e.g., v2.1.0/sessionList)
    """
    if not root:
        root = detect_antigravity_root()
    if not root or not os.path.isdir(root):
        return []

    projects_dir = os.path.join(root, "projects")
    if not os.path.isdir(projects_dir):
        return []

    candidates = []
    seen = set()
    ignore = {"__pycache__", "node_modules", ".git", ".idea", ".vscode"}

    # 1. Active git repositories under projects/ (depth <= 4)
    for dirpath, dirnames, filenames in os.walk(projects_dir):
        dirnames[:] = [d for d in dirnames if d not in ignore and not d.startswith(".")]
        if os.path.isdir(os.path.join(dirpath, ".git")):
            candidates.append(dirpath)
            seen.add(dirpath)

    # 2. Direct or versioned project folders under projects/
    for dirpath, dirnames, filenames in os.walk(projects_dir):
        dirnames[:] = [d for d in dirnames if d not in ignore and not d.startswith(".")]
        if dirpath != projects_dir and dirpath not in seen:
            rel = os.path.relpath(dirpath, projects_dir)
            parts = rel.split(os.sep)
            if any(dirpath.startswith(c + os.sep) for c in candidates):
                continue
            if len(parts) == 1 or (len(parts) == 2 and parts[0].startswith("v")):
                candidates.append(dirpath)
                seen.add(dirpath)

    return candidates

def get_recent_workspaces(limit=10):
    """
    Returns a list of unique existing directories used in past sessions or projects.
    Scans workspaces.json, transcript history, and active git/project repos under root.
    """
    seen = set()
    recent = []

    # 1. From saved workspaces.json
    workspaces = load_workspaces()
    for ws in reversed(list(workspaces.values())):
        if ws and os.path.isdir(ws) and ws not in seen:
            seen.add(ws)
            recent.append(ws)

    # 2. From transcript history in brain directory if workspaces.json is sparse
    for cid_folder in glob.glob(os.path.join(BRAIN_DIR, "*")):
        cid = os.path.basename(cid_folder)
        if cid not in workspaces:
            inferred = infer_workspace(cid)
            if inferred and os.path.isdir(inferred):
                save_workspace(cid, inferred)
                if inferred not in seen:
                    seen.add(inferred)
                    recent.append(inferred)

    # 3. Discovered active git repos & project folders under Antigravity Root projects
    root = detect_antigravity_root()
    if root:
        for pdir in scan_project_workspaces(root):
            if pdir not in seen and os.path.isdir(pdir):
                seen.add(pdir)
                recent.append(pdir)

    return recent[:limit]

def select_new_chat_workspace(title="Start New Antigravity Chat", prompt="Select folder [1]: ", current_ws=None):
    """
    Sequential interactive folder picker for starting or moving a chat.
    Default is Current Working Directory.
    Shows Antigravity Root if it exists and != CWD.
    Cleanly numbers all options sequentially:
      [1] Current Directory (/home/ashwath)
      [2] Antigravity Root (/mnt/a/anti-g)
      [3] /mnt/a/anti-g/projects/sessionList
      ...
      [c] Custom Folder Path
      [q] Cancel
    """
    cwd = os.path.abspath(os.getcwd())
    default_root = detect_antigravity_root()

    all_recent = get_recent_workspaces(10)
    recent_dirs = [d for d in all_recent if d != cwd and d != default_root]

    clear_screen()
    print("==================================================")
    print(f"          {title.center(38)}              ")
    print("==================================================")
    if current_ws:
        print(f"  Current workspace: {current_ws}")
        print("--------------------------------------------------")
    print(f"  [1] Current Directory (Default)")
    print(f"      -> {cwd}")

    option_map = {1: cwd}
    next_num = 2

    if default_root and default_root != cwd:
        print(f"  [{next_num}] Antigravity Root")
        print(f"      -> {default_root}")
        option_map[next_num] = default_root
        next_num += 1

    if recent_dirs:
        print("\n  Recent Project Workspaces:")
        for rdir in recent_dirs:
            print(f"  [{next_num}] {rdir}")
            option_map[next_num] = rdir
            next_num += 1

    custom_key = "c"
    print(f"\n  [{custom_key}] Custom Folder Path (type manually)")
    print("  [q] Cancel (return to menu)")
    print("--------------------------------------------------")

    choice = input(prompt).strip()

    if choice.lower() in ("q", "quit", "esc"):
        return None
    elif choice == "" or choice == "1":
        return cwd
    elif choice.isdigit():
        sel_idx = int(choice)
        if sel_idx in option_map:
            return option_map[sel_idx]
        return cwd
    elif choice.lower() == custom_key:
        p = input("Enter full folder path: ").strip()
        p = os.path.abspath(os.path.expanduser(p))
        if os.path.isdir(p):
            return p
        else:
            print(f"Error: Directory not found: {p}")
            input("Press Enter to continue...")
            return None

    return cwd

def resolve_workspace(cid):
    ws = load_workspaces().get(cid)
    if ws and os.path.isdir(ws):
        return ws
    ws = infer_workspace(cid)
    if ws:
        save_workspace(cid, ws)
        return ws
    return None

def clear_screen():
    sys.stdout.write("\033[H\033[2J\033[3J")
    sys.stdout.flush()

class FileLock:
    """Advisory file lock for safe atomic updates across multiple terminals."""
    def __init__(self, lock_path):
        self.lock_path = lock_path
        self.file_obj = None

    def __enter__(self):
        self.file_obj = open(self.lock_path, "a+")
        if fcntl:
            try:
                fcntl.flock(self.file_obj.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file_obj:
            try:
                if fcntl:
                    fcntl.flock(self.file_obj.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            finally:
                try:
                    self.file_obj.close()
                except Exception:
                    pass

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<USER_SETTINGS_CHANGE>[\s\S]*?</USER_SETTINGS_CHANGE>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\t", " ").replace("\n", " ").replace("\r", " ")
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
# SQLITE ENGINE & FULL-TEXT SEARCH (FTS5)
# ==========================================

def get_history_db_path(data_dir=None):
    base = data_dir if data_dir else DATA_DIR
    return os.path.join(base, "history.db")

def get_db_connection(db_path=None, read_only=False):
    """
    Connects to SQLite database with Antigravity connection standards:
    WAL mode, NORMAL synchronous, 5000ms busy timeout, foreign keys enabled.
    """
    path = db_path if db_path else HISTORY_DB
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    # Establish connection with 5-second busy timeout to handle concurrent readers/writers
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        # WAL (Write-Ahead-Logging) allows concurrent reads without blocking writers
        conn.execute("PRAGMA journal_mode = WAL;")
        # NORMAL sync offers durability without fsync latency on every write
        conn.execute("PRAGMA synchronous = NORMAL;")
        # Retry for up to 5000ms before throwing sqlite3.OperationalError: database is locked
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        # 4MB cache size (-4000 KiB) for fast in-memory query indexing
        conn.execute("PRAGMA cache_size = -4000;")
    except Exception:
        pass
    return conn

def init_db(conn=None, db_path=None):
    """Initializes tables, indices, and FTS5 search table."""
    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                conversation_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                relative_time TEXT,
                title TEXT NOT NULL DEFAULT '',
                group_name TEXT NOT NULL DEFAULT '',
                workspace TEXT NOT NULL DEFAULT '',
                step_count INTEGER NOT NULL DEFAULT 0,
                last_modified_time REAL NOT NULL DEFAULT 0.0
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_mtime ON sessions(last_modified_time DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_group ON sessions(group_name);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_title ON sessions(title);")

            # FTS5 Virtual Table for full-text search across titles, groups, workspaces, content
            conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                conversation_id UNINDEXED,
                title,
                group_name,
                workspace,
                content,
                tokenize = 'unicode61 remove_diacritics 2'
            );
            """)
    finally:
        if close_after:
            conn.close()

def extract_transcript_full_content(cid):
    """Extracts first user prompt, turn count, and concatenated textual content for FTS indexing."""
    cand_paths = [
        os.path.join(BRAIN_DIR, cid, ".system_generated", "logs", "transcript_full.jsonl"),
        os.path.join(BRAIN_DIR, cid, ".system_generated", "logs", "transcript.jsonl")
    ]
    tpath = None
    for p in cand_paths:
        if os.path.exists(p):
            tpath = p
            break

    first_prompt = ""
    turns = 0
    contents = []

    if tpath:
        try:
            with open(tpath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        t = entry.get("type")
                        content = clean_text(entry.get("content", ""))
                        if t == "USER_INPUT":
                            if content:
                                turns += 1
                                if not first_prompt:
                                    first_prompt = content
                                contents.append(content)
                        elif t in ("PLANNER_RESPONSE", "SYSTEM_MESSAGE"):
                            if content:
                                if not first_prompt and t == "SYSTEM_MESSAGE":
                                    first_prompt = content[:45]
                                contents.append(content)
                    except Exception:
                        pass
        except Exception:
            pass

    if not first_prompt:
        first_prompt = "(No user input recorded)"

    full_content = " ".join(contents)
    return first_prompt, turns, full_content

def update_fts_entry(conn, cid, title, group_name, workspace, content=""):
    """Atomically updates the FTS5 virtual table for a given conversation."""
    try:
        conn.execute("DELETE FROM sessions_fts WHERE conversation_id = ?;", (cid,))
        conn.execute(
            "INSERT INTO sessions_fts(conversation_id, title, group_name, workspace, content) VALUES (?, ?, ?, ?, ?);",
            (cid, title, group_name, workspace, content)
        )
    except Exception:
        pass

def migrate_tsv_to_sqlite(db_path=None, tsv_path=None):
    """
    On first run or when TSV records exist that are missing from SQLite,
    reads existing master_history.tsv records into history.db so no history is lost.
    """
    db_file = db_path if db_path else HISTORY_DB
    tsv_file = tsv_path if tsv_path else MASTER_TSV
    if not os.path.exists(tsv_file):
        return 0

    init_db(db_path=db_file)
    conn = get_db_connection(db_file)
    migrated_count = 0
    try:
        workspaces = load_workspaces()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            existing_cids = {row[0] for row in cur.execute("SELECT conversation_id FROM sessions;").fetchall()}

            tsv_records = []
            with open(tsv_file, "r", encoding="utf-8", errors="ignore") as f:
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

                    tsv_records.append((cid, mtime, msgs, group, title))

            now = datetime.now()
            # Pre-extract transcripts before opening the exclusive write transaction
            to_insert = []
            for cid, mtime, msgs, group, title in tsv_records:
                if cid not in existing_cids:
                    dt = datetime.fromtimestamp(mtime) if mtime > 0 else now
                    iso_time = dt.isoformat()
                    rel_label = get_relative_date_label(dt, now)
                    ws = workspaces.get(cid, "")
                    _, _, content = extract_transcript_full_content(cid)
                    to_insert.append((cid, iso_time, rel_label, title, group, ws, msgs, mtime, content))

            for cid, iso_time, rel_label, title, group, ws, msgs, mtime, content in to_insert:
                cur.execute("""
                    INSERT OR REPLACE INTO sessions 
                    (conversation_id, timestamp, relative_time, title, group_name, workspace, step_count, last_modified_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (cid, iso_time, rel_label, title, group, ws, msgs, mtime))

                update_fts_entry(conn, cid, title, group, ws, content)
                existing_cids.add(cid)
                migrated_count += 1
    except Exception as e:
        print(f"Error during TSV migration: {e}")
    finally:
        conn.close()

    return migrated_count

def sync_antigravity_summaries_db(conn=None):
    """
    Direct integration with Antigravity's conversation_summaries.db so all native chats
    are indexed automatically into history.db with FTS.
    """
    home = os.path.expanduser("~")
    cand_paths = [
        os.path.join(home, ".gemini", "antigravity-cli", "conversation_summaries.db"),
        os.path.join(home, ".config", "antigravity-cli", "conversation_summaries.db")
    ]
    agy_db_path = None
    for p in cand_paths:
        if os.path.isfile(p):
            agy_db_path = p
            break

    if not agy_db_path:
        return 0

    close_after = False
    if conn is None:
        init_db()
        conn = get_db_connection()
        close_after = True

    synced_count = 0
    try:
        agy_conn = sqlite3.connect(agy_db_path, timeout=5.0)
        agy_conn.row_factory = sqlite3.Row
        cur_agy = agy_conn.cursor()

        # Check if conversation_summaries table exists
        cur_agy.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_summaries';")
        if not cur_agy.fetchone():
            agy_conn.close()
            return 0

        rows = cur_agy.execute("""
            SELECT conversation_id, title, group_id, workspace_uris, step_count, last_modified_time
            FROM conversation_summaries;
        """).fetchall()

        now = datetime.now()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            existing_rows = {
                r[0]: (r[1], r[2]) for r in cur.execute("SELECT conversation_id, last_modified_time, group_name FROM sessions;").fetchall()
            }

            for r in rows:
                cid = r["conversation_id"]
                title = r["title"] or "Untitled Chat"
                group = r["group_id"] or "General"
                ws_uris_raw = r["workspace_uris"] or "[]"
                ws = ""
                try:
                    ws_list = json.loads(ws_uris_raw)
                    if isinstance(ws_list, list) and ws_list:
                        ws = ws_list[0]
                except Exception:
                    ws = ws_uris_raw

                step_count = r["step_count"] or 0
                mtime_raw = r["last_modified_time"] or 0.0
                try:
                    # mtime could be integer ms or seconds or float
                    mtime = float(mtime_raw)
                    if mtime > 1e11:  # milliseconds
                        mtime /= 1000.0
                except Exception:
                    mtime = 0.0

                if cid not in existing_rows or existing_rows[cid][0] < mtime:
                    # Retain custom group name if already assigned by user
                    if cid in existing_rows and existing_rows[cid][1] and existing_rows[cid][1] != "General":
                        group = existing_rows[cid][1]

                    dt = datetime.fromtimestamp(mtime) if mtime > 0 else now
                    iso_time = dt.isoformat()
                    rel_label = get_relative_date_label(dt, now)
                    _, _, content = extract_transcript_full_content(cid)

                    cur.execute("""
                        INSERT OR REPLACE INTO sessions 
                        (conversation_id, timestamp, relative_time, title, group_name, workspace, step_count, last_modified_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """, (cid, iso_time, rel_label, title, group, ws, step_count, mtime))

                    update_fts_entry(conn, cid, title, group, ws, content)
                    synced_count += 1

        agy_conn.close()
    except Exception:
        pass
    finally:
        if close_after:
            conn.close()

    return synced_count

# Global throttle timestamp to prevent redundant N+1 disk crawls on every command
_LAST_BRAIN_SYNC_TS = 0.0

def sync_active_sessions_to_db(conn=None, force=False):
    """
    Scans the local sandbox brain directory for active sessions.
    Throttled to run at most once every 30 seconds unless force=True.
    Indexes them directly into SQLite history.db.
    """
    global _LAST_BRAIN_SYNC_TS
    now_ts = time.time()
    if not force and (now_ts - _LAST_BRAIN_SYNC_TS < 30.0):
        return

    cand_transcripts = glob.glob(os.path.join(BRAIN_DIR, "*", ".system_generated", "logs", "transcript*.jsonl"))
    if not cand_transcripts:
        _LAST_BRAIN_SYNC_TS = now_ts
        return

    # Filter to most descriptive file per cid (prefer transcript_full.jsonl)
    cid_files = {}
    for fpath in cand_transcripts:
        cid = fpath.split(os.sep)[-4]
        if cid not in cid_files or "transcript_full" in fpath:
            cid_files[cid] = fpath

    close_after = False
    if conn is None:
        init_db()
        conn = get_db_connection()
        close_after = True

    try:
        now = datetime.now()
        workspaces = load_workspaces()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            existing_rows = {
                r[0]: (r[1], r[2], r[3]) for r in cur.execute("SELECT conversation_id, last_modified_time, group_name, title FROM sessions;").fetchall()
            }

            for cid, fpath in cid_files.items():
                mtime = os.path.getmtime(fpath)
                existing = existing_rows.get(cid)

                if not existing or existing[0] < mtime:
                    prompt, turns, content = extract_transcript_full_content(cid)
                    existing_title = existing[2] if existing and existing[2] and existing[2] != "Untitled Chat" else None
                    title = existing_title or (prompt[:45] + ("..." if len(prompt) > 45 else ""))
                    group = existing[1] if existing and existing[1] else "General"
                    ws = workspaces.get(cid) or infer_workspace(cid) or ""
                    dt = datetime.fromtimestamp(mtime)
                    iso_time = dt.isoformat()
                    rel_label = get_relative_date_label(dt, now)

                    cur.execute("""
                        INSERT OR REPLACE INTO sessions 
                        (conversation_id, timestamp, relative_time, title, group_name, workspace, step_count, last_modified_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """, (cid, iso_time, rel_label, title, group, ws, turns, mtime))

                    update_fts_entry(conn, cid, title, group, ws, content)
        _LAST_BRAIN_SYNC_TS = now_ts
    except Exception:
        pass
    finally:
        if close_after:
            conn.close()

def read_sessions(db_path=None):
    """
    Reads all sessions from SQLite database.
    Returns list of dicts: {'id', 'mtime', 'msgs', 'group', 'title', 'workspace', 'timestamp', 'relative_time'}
    """
    path = db_path if db_path else HISTORY_DB
    if not os.path.exists(path):
        return []

    conn = get_db_connection(path)
    records = []
    try:
        cur = conn.cursor()
        rows = cur.execute("""
            SELECT conversation_id, last_modified_time, step_count, group_name, title, workspace, timestamp, relative_time
            FROM sessions
            ORDER BY last_modified_time DESC;
        """).fetchall()

        for r in rows:
            records.append({
                "id": r["conversation_id"],
                "mtime": float(r["last_modified_time"] or 0.0),
                "msgs": int(r["step_count"] or 0),
                "group": r["group_name"] or "General",
                "title": r["title"] or "Untitled Chat",
                "workspace": r["workspace"] or "",
                "timestamp": r["timestamp"] or "",
                "relative_time": r["relative_time"] or ""
            })
    except Exception:
        pass
    finally:
        conn.close()
    return records

def write_session(session_dict, db_path=None):
    """
    Atomically writes or updates a single session in history.db.
    """
    path = db_path if db_path else HISTORY_DB
    init_db(db_path=path)
    conn = get_db_connection(path)
    try:
        cid = session_dict["id"]
        mtime = float(session_dict.get("mtime", time.time()))
        msgs = int(session_dict.get("msgs", 0))
        group = session_dict.get("group", "General")
        title = session_dict.get("title", "Untitled Chat")
        ws = session_dict.get("workspace", "")
        dt = datetime.fromtimestamp(mtime)
        iso_time = dt.isoformat()
        rel_label = get_relative_date_label(dt, datetime.now())
        content = session_dict.get("content", "")

        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute("""
                INSERT OR REPLACE INTO sessions 
                (conversation_id, timestamp, relative_time, title, group_name, workspace, step_count, last_modified_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (cid, iso_time, rel_label, title, group, ws, msgs, mtime))
            update_fts_entry(conn, cid, title, group, ws, content)
    finally:
        conn.close()

def search_sessions_fts(query, db_path=None):
    """
    High-performance FTS5 full-text search across titles, groups, workspaces, and content.
    Returns matched records sorted by BM25 relevance score.
    """
    path = db_path if db_path else HISTORY_DB
    if not os.path.exists(path) or not query or not query.strip():
        return []

    init_db(db_path=path)
    conn = get_db_connection(path)
    records = []
    try:
        # Sanitize query for FTS5 syntax:
        # 1. Strip characters that cause syntax issues except alphanumeric, spaces, and wildcard
        clean_q = re.sub(r'[^\w\s\*]', ' ', query).strip()
        if not clean_q:
            return []

        # 2. Disallow bare FTS boolean operators (AND, OR, NOT, NEAR) to avoid syntax error crashes
        reserved = {"AND", "OR", "NOT", "NEAR"}
        terms = []
        for t in clean_q.split():
            clean_t = t.rstrip("*")
            if not clean_t or clean_t.upper() in reserved:
                continue
            # Wrap each token in quotes with trailing wildcard for prefix matching (e.g. "term"*)
            terms.append(f'"{clean_t}"*')

        if not terms:
            return []

        fts_expr = " ".join(terms)

        cur = conn.cursor()
        # Join FTS virtual table with metadata sessions table; rank by BM25 relevance score
        rows = cur.execute("""
            SELECT s.conversation_id, s.last_modified_time, s.step_count, s.group_name, s.title, s.workspace, s.timestamp, s.relative_time
            FROM sessions_fts f
            JOIN sessions s ON f.conversation_id = s.conversation_id
            WHERE sessions_fts MATCH ?
            ORDER BY bm25(sessions_fts) ASC;
        """, (fts_expr,)).fetchall()

        now = datetime.now()
        for r in rows:
            dt = datetime.fromtimestamp(float(r["last_modified_time"] or 0.0))
            records.append({
                "id": r["conversation_id"],
                "mtime": float(r["last_modified_time"] or 0.0),
                "msgs": int(r["step_count"] or 0),
                "group": r["group_name"] or "General",
                "title": r["title"] or "Untitled Chat",
                "workspace": r["workspace"] or "",
                "timestamp": r["timestamp"] or "",
                "relative_time": r["relative_time"] or "",
                "dt": dt,
                "time_label": get_relative_date_label(dt, now),
                "exact_time": dt.strftime("%H:%M")
            })
    except Exception:
        # Fallback to LIKE if FTS expression has syntax quirk
        try:
            like_pat = f"%{query.strip()}%"
            rows = conn.execute("""
                SELECT conversation_id, last_modified_time, step_count, group_name, title, workspace, timestamp, relative_time
                FROM sessions
                WHERE title LIKE ? OR group_name LIKE ? OR workspace LIKE ?
                ORDER BY last_modified_time DESC;
            """, (like_pat, like_pat, like_pat)).fetchall()
            now = datetime.now()
            for r in rows:
                dt = datetime.fromtimestamp(float(r["last_modified_time"] or 0.0))
                records.append({
                    "id": r["conversation_id"],
                    "mtime": float(r["last_modified_time"] or 0.0),
                    "msgs": int(r["step_count"] or 0),
                    "group": r["group_name"] or "General",
                    "title": r["title"] or "Untitled Chat",
                    "workspace": r["workspace"] or "",
                    "timestamp": r["timestamp"] or "",
                    "relative_time": r["relative_time"] or "",
                    "dt": dt,
                    "time_label": get_relative_date_label(dt, now),
                    "exact_time": dt.strftime("%H:%M")
                })
        except Exception:
            pass
    finally:
        conn.close()

    return records

# Backward compatibility TSV helpers
def read_master_tsv():
    """Compatibility helper reading from SQLite history.db (or TSV fallback)."""
    records = read_sessions()
    if records:
        return records
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
    """Compatibility helper persisting to both history.db and mirror master_history.tsv."""
    init_db()
    with FileLock(LOCK_FILE):
        conn = get_db_connection()
        try:
            now = datetime.now()
            workspaces = load_workspaces()
            with conn:
                conn.execute("BEGIN IMMEDIATE;")
                cur = conn.cursor()
                for r in records:
                    cid = str(r["id"]).strip()
                    mtime = float(r["mtime"])
                    msgs = int(r["msgs"])
                    group = str(r.get("group", "General")).strip() or "General"
                    title = str(r.get("title", "Untitled Chat")).strip() or "Untitled Chat"
                    ws = str(r.get("workspace", workspaces.get(cid, "")))
                    dt = datetime.fromtimestamp(mtime) if mtime > 0 else now
                    iso_time = dt.isoformat()
                    rel_label = get_relative_date_label(dt, now)

                    cur.execute("""
                        INSERT OR REPLACE INTO sessions 
                        (conversation_id, timestamp, relative_time, title, group_name, workspace, step_count, last_modified_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """, (cid, iso_time, rel_label, title, group, ws, msgs, mtime))
                    update_fts_entry(conn, cid, title, group, ws, "")
        except Exception as e:
            print(f"Error persisting to SQLite: {e}")
        finally:
            conn.close()

        # Also keep master_history.tsv updated for plain-text mirrors/backwards compat
        tmp_path = MASTER_TSV + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                for r in records:
                    cid = str(r["id"]).replace("\t", " ").replace("\n", " ").strip()
                    mtime = r["mtime"]
                    msgs = r["msgs"]
                    group = str(r.get("group", "General")).replace("\t", " ").replace("\n", " ").replace("\r", " ").strip() or "General"
                    title = str(r.get("title", "Untitled Chat")).replace("\t", " ").replace("\n", " ").replace("\r", " ").strip() or "Untitled Chat"
                    f.write(f"{cid}\t{mtime}\t{msgs}\t{group}\t{title}\n")
            os.replace(tmp_path, MASTER_TSV)
            mirror_dir = os.path.expanduser("~/.gemini/antigravity-cli/plugin_data/sessionlist")
            if os.path.exists(mirror_dir) and mirror_dir != os.path.dirname(MASTER_TSV):
                try:
                    shutil.copy2(MASTER_TSV, os.path.join(mirror_dir, "master_history.tsv"))
                except Exception:
                    pass
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

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
    """Syncs active session transcripts and Antigravity DB to history.db."""
    init_db()
    migrate_tsv_to_sqlite()
    sync_antigravity_summaries_db()
    sync_active_sessions_to_db()

def get_all_chats():
    init_db()
    migrate_tsv_to_sqlite()
    sync_antigravity_summaries_db()
    sync_active_sessions_to_db()

    records = read_sessions()
    now = datetime.now()

    for c in records:
        dt = datetime.fromtimestamp(c["mtime"]) if c["mtime"] > 0 else now
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
# MUTATIONS & CLI ACTIONS
# ==========================================

def set_chat_title(cid, new_title):
    if not cid or not new_title:
        return
    sanitized_title = str(new_title).replace("\t", " ").replace("\n", " ").replace("\r", " ").strip()
    if not sanitized_title:
        return

    init_db()
    with FileLock(LOCK_FILE):
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute("UPDATE sessions SET title = ? WHERE conversation_id = ?;", (sanitized_title, cid))
                conn.execute("UPDATE sessions_fts SET title = ? WHERE conversation_id = ?;", (sanitized_title, cid))
        finally:
            conn.close()

        # Sync to TSV mirror
        records = read_master_tsv()
        for r in records:
            if r["id"] == cid:
                r["title"] = sanitized_title
                break
        write_master_tsv(records)

    print(f"✔ Abstracted title saved: '{sanitized_title}'")

def smart_group(group_name, ids=None, query=None, max_age_seconds=None):
    if not group_name:
        return
    sanitized_group = str(group_name).replace("\t", " ").replace("\n", " ").replace("\r", " ").strip()
    if not sanitized_group:
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
        print(f"No chats matched criteria for group '{sanitized_group}'.")
        return

    init_db()
    with FileLock(LOCK_FILE):
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE;")
                for cid in matching_ids:
                    conn.execute("UPDATE sessions SET group_name = ? WHERE conversation_id = ?;", (sanitized_group, cid))
                    conn.execute("UPDATE sessions_fts SET group_name = ? WHERE conversation_id = ?;", (sanitized_group, cid))
        finally:
            conn.close()

        records = read_master_tsv()
        for r in records:
            if r["id"] in matching_ids:
                r["group"] = sanitized_group
        write_master_tsv(records)

    print(f"✔ Successfully assigned {len(matching_ids)} session(s) to group '{sanitized_group}'.")

def get_all_data_dirs():
    """Returns all known sessionlist data directories (active and mirrors)."""
    home = os.path.expanduser("~")
    dirs = [
        DATA_DIR,
        os.path.join(home, ".gemini", "antigravity-cli", "plugin_data", "sessionlist"),
        "/mnt/a/anti-g/.agents/sessionlist_data"
    ]
    root = detect_antigravity_root()
    if root:
        dirs.append(os.path.join(root, ".agents", "sessionlist_data"))
    unique_dirs = []
    seen = set()
    for d in dirs:
        norm = os.path.abspath(d)
        if norm not in seen:
            seen.add(norm)
            unique_dirs.append(norm)
    return unique_dirs

def purge_chats_from_all_storage(cids):
    """
    Completely and thoroughly purges sessions across all Antigravity CLI storage layers:
    1. Brain directory: ~/.gemini/antigravity-cli/brain/<cid>/
    2. Conversations SQLite db: ~/.gemini/antigravity-cli/conversations/<cid>.db*
    3. Central index conversation_summaries.db:
       - conversation_summaries
       - conversations_fts
       - conversation_parents
    4. Annotations: ~/.gemini/antigravity-cli/annotations/<cid>.pbtxt
    5. SQLite history.db and sessions_fts in active and all mirror paths
    6. TSV and Workspaces across active and all mirror paths:
       - Purges cids from master_history.tsv in all data dirs
       - Purges cids from workspaces.json in all data dirs
    """
    if not cids:
        return 0
    cid_set = set(cids)
    home = os.path.expanduser("~")
    agy_cli_dir = os.path.join(home, ".gemini", "antigravity-cli")

    for cid in cid_set:
        # 1. Brain directory
        folder = os.path.join(BRAIN_DIR, cid)
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder, ignore_errors=True)
            except Exception:
                pass

        # 2. Conversations SQLite db (*.db, *.db-wal, *.db-shm)
        conv_dir = os.path.join(agy_cli_dir, "conversations")
        for f in glob.glob(os.path.join(conv_dir, f"{cid}.db*")):
            try:
                os.remove(f)
            except Exception:
                pass

        # 4. Annotations
        annot_path = os.path.join(agy_cli_dir, "annotations", f"{cid}.pbtxt")
        if os.path.exists(annot_path):
            try:
                os.remove(annot_path)
            except Exception:
                pass

    # 3. Central index conversation_summaries.db
    sum_db = os.path.join(agy_cli_dir, "conversation_summaries.db")
    if os.path.exists(sum_db):
        try:
            conn = sqlite3.connect(sum_db, timeout=5.0)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view');")
            tables = {row[0] for row in cur.fetchall()}

            for cid in cid_set:
                if "conversation_summaries" in tables:
                    try:
                        cur.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?;", (cid,))
                    except Exception:
                        pass
                if "conversations_fts" in tables:
                    try:
                        cur.execute("DELETE FROM conversations_fts WHERE conversation_id = ?;", (cid,))
                    except Exception:
                        pass
                if "conversation_parents" in tables:
                    try:
                        cur.execute("DELETE FROM conversation_parents WHERE conversation_id = ? OR parent_id = ?;", (cid, cid))
                    except Exception:
                        pass

            conn.commit()
            conn.close()
        except Exception:
            pass

    # 5. SQLite history.db and sessions_fts across active and all mirror data paths
    all_dirs = get_all_data_dirs()
    for d in all_dirs:
        db_file = os.path.join(d, "history.db")
        if os.path.exists(db_file):
            try:
                conn_h = get_db_connection(db_file)
                with conn_h:
                    conn_h.execute("BEGIN IMMEDIATE;")
                    cur_h = conn_h.cursor()
                    cur_h.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view');")
                    t_names = {row[0] for row in cur_h.fetchall()}
                    for cid in cid_set:
                        if "sessions" in t_names:
                            cur_h.execute("DELETE FROM sessions WHERE conversation_id = ?;", (cid,))
                        if "sessions_fts" in t_names:
                            cur_h.execute("DELETE FROM sessions_fts WHERE conversation_id = ?;", (cid,))
                conn_h.close()
            except Exception:
                pass

        # Clean master_history.tsv
        tsv_path = os.path.join(d, "master_history.tsv")
        if os.path.exists(tsv_path):
            try:
                lines_kept = []
                with open(tsv_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line_str = line.strip()
                        if not line_str:
                            continue
                        parts = line_str.split("\t")
                        if parts and parts[0] in cid_set:
                            continue
                        lines_kept.append(line)
                tmp_tsv = tsv_path + ".tmp"
                with open(tmp_tsv, "w", encoding="utf-8") as f:
                    f.writelines(lines_kept)
                os.replace(tmp_tsv, tsv_path)
            except Exception:
                pass

        # Clean workspaces.json
        ws_path = os.path.join(d, "workspaces.json")
        if os.path.exists(ws_path):
            try:
                with open(ws_path, "r", encoding="utf-8") as f:
                    ws_data = json.load(f)
                if isinstance(ws_data, dict):
                    modified = False
                    for cid in cid_set:
                        if cid in ws_data:
                            del ws_data[cid]
                            modified = True
                    if modified:
                        tmp_ws = ws_path + ".tmp"
                        with open(tmp_ws, "w", encoding="utf-8") as f:
                            json.dump(ws_data, f, indent=1)
                        os.replace(tmp_ws, ws_path)
            except Exception:
                pass

    return len(cid_set)

def delete_chats_multi(chats_to_delete):
    if not chats_to_delete:
        return
    print(f"\nSelected for deletion ({len(chats_to_delete)} chat{'s' if len(chats_to_delete) != 1 else ''}):")
    for idx, c in enumerate(chats_to_delete, 1):
        print(f"  [{idx}] {c['title']} (ID: {c['id'][:8]}...)")

    confirm = input(f"\nAre you sure you want to delete? (y/N): ").strip().lower()
    if confirm == "y":
        del_ids = [c["id"] for c in chats_to_delete]
        with FileLock(LOCK_FILE):
            purge_chats_from_all_storage(del_ids)
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

    title_val = new_title.replace("\t", " ").replace("\n", " ").replace("\r", " ").strip() if new_title else None
    group_val = new_group.replace("\t", " ").replace("\n", " ").replace("\r", " ").strip() if new_group else None

    if title_val or group_val:
        init_db()
        with FileLock(LOCK_FILE):
            conn = get_db_connection()
            try:
                with conn:
                    conn.execute("BEGIN IMMEDIATE;")
                    if title_val:
                        conn.execute("UPDATE sessions SET title = ? WHERE conversation_id = ?;", (title_val, cid))
                        conn.execute("UPDATE sessions_fts SET title = ? WHERE conversation_id = ?;", (title_val, cid))
                    if group_val:
                        conn.execute("UPDATE sessions SET group_name = ? WHERE conversation_id = ?;", (group_val, cid))
                        conn.execute("UPDATE sessions_fts SET group_name = ? WHERE conversation_id = ?;", (group_val, cid))
            finally:
                conn.close()

            records = read_master_tsv()
            for r in records:
                if r["id"] == cid:
                    if title_val:
                        r["title"] = title_val
                    if group_val:
                        r["group"] = group_val
                    break
            write_master_tsv(records)
        print("\n✔ Updated. Refreshing...")
        time.sleep(0.5)

def transplant_conversations(cids, new_workspace, target_db_path=None):
    """
    Transplants conversations across directories/workspaces:
    1. Validates and ensures new_workspace is absolute and existing.
    2. Updates Antigravity central index (target_db_path or ~/.gemini/antigravity-cli/conversation_summaries.db):
       - UPDATE conversation_summaries SET workspace_uris = ? WHERE conversation_id = ?
       - UPDATE conversations_fts SET workspace = ? WHERE conversation_id = ?
    3. Updates history.db across active and mirror paths:
       - UPDATE sessions SET workspace = ? WHERE conversation_id = ?
       - UPDATE sessions_fts
    4. Updates master_history.tsv
    5. Updates workspaces.json across all data paths (save_workspace).
    Returns (success_count, absolute_workspace_path).
    """
    if not cids:
        return 0, None
    if not new_workspace:
        raise ValueError("Target workspace path cannot be empty.")

    abs_ws = os.path.abspath(os.path.expanduser(str(new_workspace).strip()))
    if not os.path.isdir(abs_ws):
        raise ValueError(f"Target workspace directory does not exist: {abs_ws}")

    cid_list = list(cids)
    ws_uri_json = json.dumps(["file://" + abs_ws])

    # 1. Antigravity central index: conversation_summaries.db
    home = os.path.expanduser("~")
    sum_db_candidates = []
    if target_db_path:
        sum_db_candidates.append(target_db_path)
    if os.environ.get("AGY_SUMMARIES_DB"):
        sum_db_candidates.append(os.environ.get("AGY_SUMMARIES_DB"))
    sum_db_candidates.extend([
        os.path.join(home, ".gemini", "antigravity-cli", "conversation_summaries.db"),
        os.path.join(home, ".config", "antigravity-cli", "conversation_summaries.db")
    ])
    for sdb in sum_db_candidates:
        if os.path.isfile(sdb):
            try:
                conn_sum = sqlite3.connect(sdb, timeout=5.0)
                cur_sum = conn_sum.cursor()
                cur_sum.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view');")
                tables = {row[0] for row in cur_sum.fetchall()}
                with conn_sum:
                    for cid in cid_list:
                        if "conversation_summaries" in tables:
                            try:
                                cur_sum.execute(
                                    "UPDATE conversation_summaries SET workspace_uris = ? WHERE conversation_id = ?;",
                                    (ws_uri_json, cid)
                                )
                            except Exception:
                                pass
                        if "conversations_fts" in tables:
                            try:
                                cur_sum.execute(
                                    "UPDATE conversations_fts SET workspace = ? WHERE conversation_id = ?;",
                                    (abs_ws, cid)
                                )
                            except Exception:
                                pass
                conn_sum.close()
            except Exception:
                pass

    # 2. Update history.db and sessions_fts across all known data dirs
    all_dirs = get_all_data_dirs()
    for d in all_dirs:
        hdb = os.path.join(d, "history.db")
        if os.path.exists(hdb):
            try:
                conn_h = get_db_connection(hdb)
                with conn_h:
                    conn_h.execute("BEGIN IMMEDIATE;")
                    cur_h = conn_h.cursor()
                    cur_h.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view');")
                    t_names = {row[0] for row in cur_h.fetchall()}
                    for cid in cid_list:
                        if "sessions" in t_names:
                            cur_h.execute(
                                "UPDATE sessions SET workspace = ? WHERE conversation_id = ?;",
                                (abs_ws, cid)
                            )
                        if "sessions_fts" in t_names:
                            row = cur_h.execute(
                                "SELECT title, group_name FROM sessions WHERE conversation_id = ?;",
                                (cid,)
                            ).fetchone()
                            t = row["title"] if row else ""
                            g = row["group_name"] if row else ""
                            _, _, content = extract_transcript_full_content(cid)
                            update_fts_entry(conn_h, cid, t, g, abs_ws, content)
                conn_h.close()
            except Exception:
                pass

    # 3. Update master_history.tsv across all data dirs
    for d in all_dirs:
        tsv_path = os.path.join(d, "master_history.tsv")
        if os.path.exists(tsv_path):
            try:
                updated_lines = []
                with open(tsv_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line_str = line.strip()
                        if not line_str:
                            continue
                        parts = line_str.split("\t")
                        # master_history.tsv stores: cid, mtime, msgs, group, title
                        updated_lines.append(line)
                tmp_tsv = tsv_path + ".tmp"
                with open(tmp_tsv, "w", encoding="utf-8") as f:
                    f.writelines(updated_lines)
                os.replace(tmp_tsv, tsv_path)
            except Exception:
                pass

    # 4. Update workspaces.json across all data dirs
    for cid in cid_list:
        save_workspace(cid, abs_ws)

    return len(cid_list), abs_ws

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
    records = get_all_chats()
    db_size = os.path.getsize(HISTORY_DB) if os.path.exists(HISTORY_DB) else 0
    tsv_size = os.path.getsize(MASTER_TSV) if os.path.exists(MASTER_TSV) else 0

    print("==========================================")
    print("         Storage & Diagnostics            ")
    print("==========================================")
    print(f"  Data Directory:      {DATA_DIR}")
    print(f"  SQLite Database:     {HISTORY_DB}")
    print(f"  DB Size on Disk:     {db_size} bytes ({db_size/1024:.2f} KB)")
    print(f"  Master History TSV:  {MASTER_TSV} ({tsv_size/1024:.2f} KB)")
    print(f"  Total Chats Saved:   {len(records)} sessions")
    print(f"  Antigravity Brain:   {BRAIN_DIR}")
    print("------------------------------------------")
    get_prompt_input("Press Enter or ESC to return...")

def backup_history_log():
    clear_screen()
    if not os.path.exists(HISTORY_DB) and not os.path.exists(MASTER_TSV):
        print("No history database or TSV found to backup.")
        time.sleep(1)
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_db_name = f"history_backup_{ts}.db"
    bak_db_path = os.path.join(DATA_DIR, bak_db_name)
    bak_tsv_name = f"master_history_backup_{ts}.tsv"
    bak_tsv_path = os.path.join(DATA_DIR, bak_tsv_name)

    try:
        if os.path.exists(HISTORY_DB):
            shutil.copy2(HISTORY_DB, bak_db_path)
        if os.path.exists(MASTER_TSV):
            shutil.copy2(MASTER_TSV, bak_tsv_path)

        print("==========================================")
        print("          History Backup Created          ")
        print("==========================================")
        print(f"  SQLite DB Backup saved to:")
        print(f"  {bak_db_path}")
        print("------------------------------------------")
    except Exception as e:
        print(f"Error creating backup: {e}")

    get_prompt_input("Press Enter or ESC to return...")

def restore_history_log():
    clear_screen()
    print("==========================================")
    print("         Restore History Log (SQLite)     ")
    print("==========================================")
    
    # Look for available backups in DATA_DIR (both DB and TSV)
    db_baks = sorted(glob.glob(os.path.join(DATA_DIR, "history_backup_*.db")), reverse=True)
    tsv_baks = sorted(glob.glob(os.path.join(DATA_DIR, "master_history_backup_*.tsv")), reverse=True)
    baks = db_baks + tsv_baks
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
                if selected_bak.endswith(".db"):
                    shutil.copy2(selected_bak, HISTORY_DB)
                    # Mirror to plugin_data if applicable
                    mirror_dir = os.path.expanduser("~/.gemini/antigravity-cli/plugin_data/sessionlist")
                    if os.path.exists(mirror_dir) and mirror_dir != os.path.dirname(HISTORY_DB):
                        shutil.copy2(HISTORY_DB, os.path.join(mirror_dir, "history.db"))
                elif selected_bak.endswith(".tsv"):
                    shutil.copy2(selected_bak, MASTER_TSV)
                    migrate_tsv_to_sqlite(tsv_path=selected_bak)
            print(f"\n✔ Successfully restored master history from:")
            print(f"  {os.path.basename(selected_bak)}")
        except Exception as e:
            print(f"\nError restoring backup: {e}")
        time.sleep(1.5)

def do_export_chats(targets):
    if not targets:
        print("No chats to export.")
        return 0, ""

    export_dir = os.path.abspath(os.path.join(DATA_DIR, "..", "exported_chats"))
    os.makedirs(export_dir, exist_ok=True)

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
        time_part = c.get("exact_time", "").replace(":", "") if c.get("exact_time") else "0000"
        md_filename = f"{time_part}_{clean_slug}_{cid[:6]}.md"
        out_path = os.path.abspath(os.path.join(export_dir, md_filename))

        # Security: verify output path does not escape export directory boundary
        try:
            if os.path.commonpath([export_dir, out_path]) != export_dir:
                continue
        except Exception:
            continue

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

    return exported_count, export_dir

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

    targets = []
    if choice == "all":
        targets = chats
    elif choice.isdigit() and 1 <= int(choice) <= len(chats):
        targets = [chats[int(choice) - 1]]
    else:
        print("Invalid choice.")
        time.sleep(1)
        return

    exported_count, export_dir = do_export_chats(targets)
    print(f"\n✔ Successfully exported {exported_count} conversation(s) to:")
    print(f"  {export_dir}")
    get_prompt_input("\nPress Enter or ESC to return...")

def uninstall_sessionlist():
    clear_screen()
    print("==========================================")
    print("          Uninstall sessionList           ")
    print("==========================================")
    print("This will remove sessionList binaries and")
    print("shortcuts from ~/.local/bin/ and")
    print("~/.local/share/sessionlist/.")
    print("\nYour conversation history will remain safe.")
    print("------------------------------------------")
    confirm = get_prompt_input("Are you sure you want to uninstall? (y/N): ").strip().lower()

    if confirm != "y":
        print("\nUninstall cancelled.")
        time.sleep(1)
        return

    bin_dir = os.path.expanduser("~/.local/bin")
    install_base = os.path.expanduser("~/.local/share/sessionlist")

    # Find and delete aliases in bin_dir
    removed_files = []
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
        except Exception:
            pass

    current_alias = cfg.get("alias", "")
    prefixes = {"ach", "antig", "ag"}
    if current_alias:
        prefixes.add(current_alias)

    for p in prefixes:
        for suffix in ["", "-h", "-m"]:
            fpath = os.path.join(bin_dir, f"{p}{suffix}")
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                    removed_files.append(os.path.basename(fpath))
                except Exception:
                    pass

    # Remove install base directory if exists
    if os.path.exists(install_base):
        try:
            shutil.rmtree(install_base)
        except Exception:
            pass

    print("\n✔ Successfully uninstalled sessionList!")
    if removed_files:
        print(f"  Removed binaries: {', '.join(removed_files)}")
    print("\nThank you for using sessionList.")
    sys.exit(0)

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
        print("  [7] Uninstall sessionList")
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
        elif choice == "7":
            uninstall_sessionlist()

def _exec_agy(extra_args):
    """Clean process hand-off replacing current Python process when possible."""
    cli_cmd = detect_cli_command()
    parts = cli_cmd.split() + extra_args
    binary = parts[0]
    resolved_bin = shutil.which(binary) if not os.path.isabs(binary) else binary
    if resolved_bin and hasattr(os, "execvp"):
        try:
            os.execvp(resolved_bin, [resolved_bin] + parts[1:])
        except Exception:
            pass
    # Fallback to subprocess if execvp fails or not available
    try:
        rc = subprocess.call(parts)
    except FileNotFoundError:
        rc = 127
    sys.exit(rc or 0)

def _run_agy(extra_args):
    cli_cmd = detect_cli_command()
    parts = cli_cmd.split() + extra_args
    try:
        return subprocess.call(parts)
    except FileNotFoundError:
        return 127

def _brain_ids():
    try:
        return {d for d in os.listdir(BRAIN_DIR) if os.path.isdir(os.path.join(BRAIN_DIR, d))}
    except Exception:
        return set()

def start_new_chat():
    chosen_ws = select_new_chat_workspace()
    if not chosen_ws:
        return
    try:
        os.chdir(chosen_ws)
    except OSError as e:
        print(f"Cannot switch to {chosen_ws}: {e}")
        input("Press Enter to continue...")
        return
    clear_screen()
    print(f"Launching new Antigravity chat in {chosen_ws}...")
    _exec_agy([])

def resume_chat(cid):
    """Resume inside the chat's original folder so agy does not ask to trust a new one."""
    ws = resolve_workspace(cid)
    if not ws:
        print("\nOriginal folder of this chat is unknown.")
        ans = input(f"Folder to resume in [{os.getcwd()}]: ").strip()
        ws = os.path.expanduser(ans) if ans else os.getcwd()
        if not os.path.isdir(ws):
            print(f"Not a folder: {ws}")
            return
        save_workspace(cid, ws)
    try:
        os.chdir(ws)
    except OSError as e:
        print(f"Cannot enter {ws}: {e}")
        return
    clear_screen()
    print(f"Resuming in {ws} ...")
    _exec_agy(["--conversation", cid])

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
        print("\nCmds: <num> resume | m <num> move | e <num> edit | x <num|all> export | d <n1,n2..> del | n new | Esc/b back")
        cmd = get_prompt_input("Select > ")

        if cmd.lower() in ("b", "back", "q", "quit", "esc"):
            break
        elif cmd.lower() in ("n", "new"):
            start_new_chat()
            break
        elif cmd.lower().startswith("m ") or cmd.lower() == "m":
            part = cmd[2:].strip() if len(cmd) > 1 else ""
            if not part:
                part = get_prompt_input("Move chat number: ").strip()
            if part.isdigit() and 1 <= int(part) <= len(chats):
                target = chats[int(part) - 1]
                curr_ws = target.get("workspace") or resolve_workspace(target["id"]) or os.getcwd()
                chosen_ws = select_new_chat_workspace(
                    title=f"Move Chat #{part}: '{target['title'][:20]}'",
                    prompt="Move to [1]: ",
                    current_ws=curr_ws
                )
                if chosen_ws:
                    try:
                        count, final_ws = transplant_conversations([target["id"]], chosen_ws)
                        print(f"\n✔ Successfully moved chat #{part} to:\n  {final_ws}")
                    except Exception as e:
                        print(f"\n❌ Error moving chat: {e}")
                    time.sleep(1.0)
        elif cmd.lower().startswith("e "):
            part = cmd[2:].strip()
            if part.isdigit() and 1 <= int(part) <= len(chats):
                move_or_rename_chat(chats[int(part) - 1])
        elif cmd.lower().startswith("x ") or cmd.lower() == "x":
            part = cmd[2:].strip().lower() if len(cmd) > 1 else ""
            if not part:
                part = get_prompt_input("Export chat number or 'all': ").strip().lower()
            if part == "all":
                count, edir = do_export_chats(chats)
                print(f"\n✔ Successfully exported {count} conversation(s) to:\n  {edir}")
                input("Press Enter to continue...")
            elif part.isdigit() and 1 <= int(part) <= len(chats):
                target = chats[int(part) - 1]
                count, edir = do_export_chats([target])
                print(f"\n✔ Successfully exported '{target['title']}' to:\n  {edir}")
                input("Press Enter to continue...")
            else:
                print("Invalid export option. Usage: x <num> or x all")
                time.sleep(1)
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
    matched = search_sessions_fts(query)
    if not matched:
        # Fallback to simple title/group substring filter
        chats = get_all_chats()
        q = query.lower()
        matched = [c for c in chats if q in c["title"].lower() or q in c["group"].lower() or q in c["time_label"].lower()]
    print(f"Found {len(matched)} chat(s) matching '{query}':")
    render_terminal_table(matched)

def list_groups_cli(interactive=False):
    chats = get_all_chats()
    groups = {}
    for c in chats:
        groups.setdefault(c["group"], []).append(c)
    sorted_groups = sorted(groups.items())
    print("Groups & Notebooks:")
    for idx, (g, clist) in enumerate(sorted_groups, 1):
        print(f"  [{idx}] {g} ({len(clist)} chat{'s' if len(clist) != 1 else ''})")

    if not interactive:
        return

    print("\nCmds: m <num> move entire group | Enter/Esc back")
    cmd = get_prompt_input("Select > ").strip()
    if cmd.lower().startswith("m ") or cmd.lower() == "m":
        part = cmd[2:].strip() if len(cmd) > 1 else ""
        if not part:
            part = get_prompt_input("Group number to move: ").strip()
        if part.isdigit() and 1 <= int(part) <= len(sorted_groups):
            gname, clist = sorted_groups[int(part) - 1]
            chosen_ws = select_new_chat_workspace(
                title=f"Move Group: '{gname}' ({len(clist)} chats)",
                prompt="Move all to folder [1]: "
            )
            if chosen_ws:
                g_cids = [c["id"] for c in clist]
                try:
                    count, final_ws = transplant_conversations(g_cids, chosen_ws)
                    print(f"\n✔ Successfully moved {count} chat(s) in group '{gname}' to:\n  {final_ws}")
                except Exception as e:
                    print(f"\n❌ Error moving group: {e}")
                time.sleep(1.2)

def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--version", "-v"):
            print("Chrono (sessionList) v2.2.0 ⚡ Antigravity Session Recall (by AshraArc)")
            return
        elif arg in ("--update", "update"):
            install_base = os.path.expanduser("~/.local/share/sessionlist")
            bin_dir = os.path.expanduser("~/.local/bin")
            if os.path.exists(os.path.join(install_base, ".git")):
                print("Checking for updates...")
                try:
                    # Fetch and fast-forward cleanly
                    res = subprocess.run(["git", "-C", install_base, "pull", "--ff-only"], capture_output=True, text=True)
                    if res.returncode != 0:
                        print(f"❌ Update failed:\n{res.stderr.strip() or res.stdout.strip()}")
                        return
                    print(res.stdout.strip() if res.stdout.strip() else "✔ sessionList is already up to date.")

                    # 1. Housekeeping: prune obsolete pycache, temp files, and old backups in install base
                    for root, dirs, files in os.walk(install_base, onerror=lambda _: None):
                        for f in files:
                            if f.endswith(".tmp") or f.endswith(".pyc"):
                                try: os.remove(os.path.join(root, f))
                                except OSError: pass
                        for d in list(dirs):
                            if d == "__pycache__":
                                shutil.rmtree(os.path.join(root, d), ignore_errors=True)

                    # 2. Re-sync launcher binary wrappers in ~/.local/bin/
                    cfg_alias = detect_cli_command()
                    if cfg_alias and os.path.isdir(bin_dir):
                        script_target = os.path.join(install_base, "sessionlist.py")
                        h_path = os.path.join(bin_dir, f"{cfg_alias}-h")
                        m_path = os.path.join(bin_dir, f"{cfg_alias}-m")
                        base_path = os.path.join(bin_dir, cfg_alias)
                        try:
                            with open(h_path, "w", encoding="utf-8") as f:
                                f.write(f'#!/bin/sh\nif [ "$#" -eq 0 ]; then\n    exec python3 "{script_target}" --list\nelse\n    exec python3 "{script_target}" "$@"\nfi\n')
                            with open(m_path, "w", encoding="utf-8") as f:
                                f.write(f'#!/bin/sh\nexec python3 "{script_target}" "$@"\n')
                            os.chmod(h_path, 0o755)
                            os.chmod(m_path, 0o755)
                            if os.path.islink(base_path) or not os.path.exists(base_path):
                                try: os.remove(base_path)
                                except OSError: pass
                                os.symlink(m_path, base_path)
                        except Exception:
                            pass

                    # 3. Prune legacy unused alias symlinks from bin_dir
                    for stale in ("antig", "antig-h", "antig-m", "ag", "ag-h", "ag-m"):
                        if stale != cfg_alias and not stale.startswith(f"{cfg_alias}-"):
                            sp = os.path.join(bin_dir, stale)
                            if os.path.islink(sp):
                                try: os.remove(sp)
                                except OSError: pass
                except Exception as e:
                    print(f"Error checking updates: {e}")
            else:
                print("To update, run:")
                print("  curl -fsSL https://raw.githubusercontent.com/AshraArc/-antigravity-chat-manager/main/get.sh | sh")
            return
        elif arg == "--uninstall":
            uninstall_sessionlist()
            return
        elif arg in ("--help", "-h"):
            print("""Chrono v2.2.0 ⚡ Antigravity Instant Session Recall & FTS5 Search
Usage:
  ach [options]             Session recall CLI
  <cmd>-h [options]         Quick non-interactive table dump
  <cmd>-m                   Interactive dashboard menu

Options:
  -h, --help                Show this help message
  -v, --version             Show version information
  -l, --list                Show recent chats (default for <cmd>-h)
  -a, --all, --list-all     Show complete uncapped history
  -s, --search, --search-cli <query> Search chat titles, history and notebooks
  -x, --export <id|all>     Export session(s) directly to Markdown (.md)
  -d, --delete, --del, rm <ids...> Delete session(s) non-interactively (e.g. -d 1,2 or rm 1-3)
  --days <N>                Filter chats from the last N days (e.g. --days 7)
  -H, --hours <N>           Filter chats from the last N hours (e.g. --hours 2)
  mv <id|num> [target_dir]  Move/transplant chat to target directory (default: CWD)
  mv -g, --group <name> [target_dir] Move all chats in a group to target directory
  --groups-cli              List all notebook groups
  --set-title <id> "<title>" Set clean abstracted session title
  --update                  Check and pull latest updates
  --uninstall               Uninstall sessionList and its shortcuts
""")
            return
        elif arg in ("mv", "move"):
            # ach mv <id|num> [target_dir]
            # ach mv -g, --group <group_name> [target_dir]
            raw_args = sys.argv[2:]
            if not raw_args:
                print("Usage:")
                print("  ach mv <id|num> [target_dir]")
                print("  ach mv -g, --group <group_name> [target_dir]")
                return

            chats = get_all_chats()
            if raw_args[0] in ("-g", "--group"):
                if len(raw_args) < 2:
                    print("Error: Missing group name. Example: ach mv -g 'Projects' /path/to/target")
                    return
                gname = raw_args[1]
                target_dir = raw_args[2] if len(raw_args) > 2 else os.getcwd()
                group_chats = [c for c in chats if c["group"].lower() == gname.lower()]
                if not group_chats:
                    print(f"Error: No chats found in group '{gname}'.")
                    return
                cids = [c["id"] for c in group_chats]
                try:
                    count, final_ws = transplant_conversations(cids, target_dir)
                    print(f"✔ Successfully moved {count} chat(s) in group '{gname}' to:\n  {final_ws}")
                except Exception as e:
                    print(f"Error moving group '{gname}': {e}")
                return
            else:
                target_id = raw_args[0]
                target_dir = raw_args[1] if len(raw_args) > 1 else os.getcwd()
                cid_to_move = None
                chat_title = ""
                if target_id.isdigit():
                    idx = int(target_id)
                    if 1 <= idx <= len(chats):
                        cid_to_move = chats[idx - 1]["id"]
                        chat_title = chats[idx - 1]["title"]
                    else:
                        print(f"Error: Chat index {idx} out of range (1-{len(chats)}).")
                        return
                else:
                    matched = [c for c in chats if c["id"].startswith(target_id)]
                    if matched:
                        cid_to_move = matched[0]["id"]
                        chat_title = matched[0]["title"]
                    else:
                        print(f"Error: No chat found matching identifier '{target_id}'.")
                        return
                try:
                    count, final_ws = transplant_conversations([cid_to_move], target_dir)
                    print(f"✔ Successfully moved '{chat_title}' to:\n  {final_ws}")
                except Exception as e:
                    print(f"Error moving chat '{target_id}': {e}")
                return
        elif arg in ("--export", "-x"):
            target_arg = sys.argv[2] if len(sys.argv) > 2 else "all"
            chats = get_all_chats()
            targets = []
            if target_arg.lower() == "all":
                targets = chats
            elif target_arg.isdigit():
                idx = int(target_arg)
                if 1 <= idx <= len(chats):
                    targets = [chats[idx - 1]]
                else:
                    print(f"Error: Chat index {idx} out of range (1-{len(chats)}).")
                    return
            else:
                # Try matching by CID
                matched = [c for c in chats if c["id"].startswith(target_arg)]
                if matched:
                    targets = [matched[0]]
                else:
                    print(f"Error: No chat found matching identifier '{target_arg}'.")
                    return
            count, edir = do_export_chats(targets)
            print(f"✔ Successfully exported {count} conversation(s) to:\n  {edir}")
            return
        elif arg in ("--delete", "--del", "-d", "rm"):
            raw_args = sys.argv[2:] if len(sys.argv) > 2 else []
            if not raw_args:
                print("Error: Missing session ID(s) to delete. Example: -d 1,2 or rm 1-3")
                return
            chats = get_all_chats()
            tokens = []
            for item in raw_args:
                tokens.extend(re.split(r"[\s,]+", item.strip()))
            selected = []
            for t in tokens:
                if not t:
                    continue
                m = re.match(r"^(\d+)-(\d+)$", t)
                if m:
                    start, end = int(m.group(1)), int(m.group(2))
                    if start > end:
                        start, end = end, start
                    for idx in range(start, end + 1):
                        if 1 <= idx <= len(chats):
                            target = chats[idx - 1]
                            if target not in selected:
                                selected.append(target)
                elif t.isdigit():
                    idx = int(t)
                    if 1 <= idx <= len(chats):
                        target = chats[idx - 1]
                        if target not in selected:
                            selected.append(target)
                else:
                    for c in chats:
                        if c["id"].startswith(t) and c not in selected:
                            selected.append(c)
            if selected:
                del_ids = [c["id"] for c in selected]
                with FileLock(LOCK_FILE):
                    purge_chats_from_all_storage(del_ids)
                print(f"✔ Deleted {len(selected)} chat(s).")
            else:
                print(f"No chats matched '{' '.join(raw_args)}'.")
            return
        elif arg in ("--list", "-l"):
            render_terminal_table(get_all_chats(), limit=15)
            return
        elif arg in ("--all", "--list-all", "-a"):
            render_terminal_table(get_all_chats(), limit=None)
            return
        elif arg in ("--days",):
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
        elif arg in ("--search", "-s", "--search-cli"):
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
        print("          Chrono ⚡ Antigravity           ")
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
                    matched = search_sessions_fts(q)
                    if not matched:
                        matched = [c for c in get_all_chats() if q.lower() in c["title"].lower() or q.lower() in c["group"].lower() or q.lower() in c["time_label"].lower()]
                    if 1 <= int(sub) <= len(matched):
                        resume_chat(matched[int(sub) - 1]["id"])
                        break
        elif choice == "3":
            list_groups_cli(interactive=True)
        elif choice in ("4", "s", "set", "settings"):
            settings_view()

if __name__ == "__main__":
    main()
