# sessionList

The power-user companion CLI for Google Antigravity: FTS5 Full-Text Search, Complete Multi-Layer Purge, Markdown Export & Sequential Workspace Selector.

> **Note:** Antigravity provides a built-in picker (`/resume` inside a chat) for searching, renaming, deleting one at a time, and resuming conversations. `sessionList` does not try to replace it. It serves as the dedicated power-user companion covering what the picker does not: **FTS5 deep content search (searching inside conversation messages & code blocks, not just titles), true multi-layer batch purge, top-level Markdown note exports, sequential folder selection for new chats, and catalog backups**—all directly from a plain terminal.

Created by **AshraArc**.

Run it from any terminal:
- **`<cmd>-h`**: instant, non-interactive table of your recent chats, deep CLI search, batch deletion, and direct export.
- **`<cmd>-m`**: interactive dashboard menu with FTS5 search, multi-layer batch purge, top-level markdown export, notebook groups, and folder selector.

(`<cmd>` is the prefix you pick at install, `ach` by default.)

---


---

## How sessionList Integrates with Antigravity CLI (`agy`)

`sessionList` is engineered to hook cleanly into Antigravity's native storage architecture rather than fighting or replacing it:

```
┌──────────────────────────────────────────────────────────────┐
│                    Developer Shell (Terminal)                │
│             ach -l  |  ach -s  |  ach -d  |  ach -x          │
└──────────────────────────────┬───────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
   ┌───────────────────────────┐ ┌───────────────────────────┐
   │    sessionList SQLite     │ │   Antigravity Central     │
   │  history.db (WAL + FTS5)  │ │ conversation_summaries.db │
   └────────────┬──────────────┘ └────────────┬──────────────┘
                │                             │
                │     Direct SQLite Sync      │
                ├─────────────────────────────┤
                ▼                             ▼
   ┌─────────────────────────────────────────────────────────┐
   │            Antigravity Runtime Persistence              │
   │  • ~/.gemini/antigravity-cli/conversations/<uuid>.db    │
   │  • ~/.gemini/antigravity-cli/brain/<uuid>/logs/         │
   │  • Original Project Directory (No Folder Trust Errors)   │
   └─────────────────────────────────────────────────────────┘
```

### 1. Direct SQLite & FTS5 Synchronization
- **Native Discovery**: `sessionList` directly reads Antigravity's `~/.gemini/antigravity-cli/conversation_summaries.db`, automatically discovering chats as soon as they are created in `agy`.
- **FTS5 Full-Text Indexing**: Syncs transcript messages into an SQLite `FTS5` virtual table so you can search the exact words, errors, and code blocks discussed across all conversations.

### 2. Multi-Layer Purge vs Built-in `/resume`
- When you delete a chat in `sessionList` (`ach -d 1,2` or `d 1-3`):
  1. Executes clean SQL deletions in `conversation_summaries.db` (`conversation_summaries`, `conversations_fts`, `conversation_parents`).
  2. Deletes the per-session database `conversations/<uuid>.db*`.
  3. Deletes raw brain logs and annotations.
  4. Removes the record from `history.db`.
- **The Result**: Unlike manual file deletion, the session vanishes **permanently and cleanly from Antigravity's built-in `/resume` picker** with zero ghost entries.

### 3. Workspace-Aware Resume (No Untrusted Folder Warnings)
- Antigravity links chats to specific project roots. When resuming across folders, `agy` often halts with security warnings (*"Do you trust this folder?"*).
- `sessionList` tracks the original directory where the chat was created. When you select a session, it automatically switches (`cd <workspace>`) before handing off execution via `os.execvp`, ensuring instant resume without security friction.

### 4. Non-Interactive CLI Pipelining
- Antigravity's `/resume` is an interactive TUI only. `sessionList` adds UNIX scripting capabilities:
  - `ach -l`: Quick formatted table dump to standard output.
  - `ach -x <id|all>`: Scriptable export to Markdown for CI or documentation notes.
  - `ach -d <ids>`: Bulk cleanup in automated scripts.

## Key Features

- **SQLite WAL Engine + FTS5 Full-Text Search**:
  High-concurrency SQLite storage backed by Write-Ahead Logging (WAL) and an FTS5 virtual table. Deep search indexes not just conversation titles, but the actual message transcripts and code snippets across your chat history.
- **Complete Multi-Layer Purge (`d n1,n2..` / `--delete`)**:
  Deleting chats completely removes them across all Antigravity CLI storage layers—including transcript directories (`brain/<cid>/`), conversation databases (`conversations/<cid>.db*`), annotations, and Antigravity's central index `conversation_summaries.db` (`conversation_summaries`, `conversations_fts`, `conversation_parents`). Once deleted, sessions vanish permanently from `/resume`.
- **Top-Level Markdown Export (`x <num>`, `x all` / `--export`)**:
  Export any chat or all chats to clean, readable Markdown notes with full speaker labels, timestamps, and tool outputs directly from the top-level chat table (`x 1`, `x all`) or via CLI (`--export 1`, `--export all`).
- **Sequential Workspace Selector (`[n]`)**:
  Starting a new chat (`n`) opens a numbered, sequential folder picker showing your Current Working Directory (Default `[1]`), Antigravity Root (`[2]`), recently active project repositories, and a custom folder path prompt (`[c]`).
- **Plain-Terminal Power & CLI Flags**:
  Search, list, export, and delete chats non-interactively via flags: `--search-cli`, `--export`, `--delete`, `--days`, `--hours`, `--all`.
- **Catalog Archiver (Backup & Restore)**:
  Timestamped backups of the master chat database with one-step recovery.
- **Notebook Groups & Titles (`e <num>`)**:
  Rename chats and organize them into notebook categories for quick project grouping.
- **Workspace-Aware Resume**:
  Resuming a chat switches to its original directory first so `agy` never halts to ask for untrusted workspace permissions.

---

## Quick Install

Run this single command in your terminal to install immediately:

```bash
curl -fsSL https://raw.githubusercontent.com/AshraArc/-antigravity-chat-manager/main/get.sh | sh
```

> **Prefer a custom command prefix like `ag` or `ach`?**
> ```bash
> curl -fsSL https://raw.githubusercontent.com/AshraArc/-antigravity-chat-manager/main/get.sh | sh -s -- ag
> ```

---

## Installation & Setup

### Option 1: 1-Line Quick Install (Recommended)
Paste the command above into your terminal. It installs `ach-h` (instant table dump & CLI actions) and `ach-m` (interactive dashboard) directly into `~/.local/bin/`.

### Option 2: Manual Clone & Setup (`install.sh`)
```bash
git clone https://github.com/AshraArc/-antigravity-chat-manager.git
cd -antigravity-chat-manager
./install.sh
```

---

## Uninstallation

To remove `sessionList` and all its terminal shortcuts completely:

```bash
curl -fsSL https://raw.githubusercontent.com/AshraArc/-antigravity-chat-manager/main/uninstall.sh | sh
```

Or if you have the repo cloned locally:
```bash
./uninstall.sh
```

---

## Usage Guide

### Command-Line Interface (CLI Flags)

`sessionList` supports direct non-interactive CLI flags for automations, scripting, and shell workflows:

```bash
# Instant table view
ach-h                      # Show 15 most recent sessions
ach-h --all                # Show complete uncapped history
ach-h --days 7             # Filter sessions from past 7 days
ach-h --hours 2            # Filter sessions from past 2 hours

# Deep FTS5 Full-Text Search via CLI
ach-h --search-cli "query" # Search inside conversation titles, messages, and code blocks

# Direct Markdown Export
ach-h --export 1           # Export chat #1 to Markdown (.md)
ach-h --export all         # Export all chats to Markdown notes

# Direct Multi-Layer Batch Deletion
ach-h --delete 1,3,4       # Completely purge chats #1, #3, and #4 across all storage layers
```

### Interactive Management Menu (`ach-m`)

Launch the dashboard:
```bash
ach-m
```

```text
==========================================
               sessionList                
==========================================
  [1] All Chats
  [2] Search & Resume
  [3] Groups & Notebooks
  [4] Settings
  [q] Quit (or press ESC)
------------------------------------------
Select > 
```

**Inside All Chats**:
```text
Cmds: <num> resume | x <num> export MD | d <n1,n2..> del | e <num> edit | n new | Esc/b back
Select > 
```
- `<num>`: Resume selected session in its original workspace.
- `x <num>` / `x all`: Export chat (or all chats) directly to clean Markdown notes without entering submenus.
- `d <n1,n2..>`: Delete one or multiple sessions (e.g. `d 1,3,4` or `d 1 3 4`) with multi-layer purge across SQLite and `conversation_summaries.db`.
- `e <num>`: Edit chat title or assign it to a notebook group.
- `n`: Launch a new Antigravity session using the sequential folder selector.
- `ESC` or `b`: Return to previous menu.

**Inside Search & Resume (`[2]`)**:
- Deep FTS5 query search scans conversation messages, user prompts, and code blocks in addition to titles.
- Press `Enter` to resume any matched chat directly in its workspace.

**New Chat Folder Selector (`[n]` / `n`)**:
```text
==================================================
          Start New Antigravity Chat              
==================================================
  [1] Current Directory (Default)
      -> /mnt/a/anti-g/projects/sessionList
  [2] Antigravity Root
      -> /mnt/a/anti-g
  
  Recent Project Workspaces:
  [3] /mnt/a/anti-g/projects/api-service
  [4] /mnt/a/anti-g/projects/frontend

  [c] Custom Folder Path (type manually)
  [q] Cancel (return to menu)
--------------------------------------------------
Select folder [1]:
```

**Inside Settings (`[4] Settings`)**:
- `[1] CLI Alias & Shortcuts`: In-place alias renaming (`ag`, `antig`, `ai`, `agy`) with automatic shortcut generation.
- `[2] Default Time Window Filter`: Choose default view (*All time*, *Past 7 days*, *Past 30 days*).
- `[3] Export Chats to Markdown (.md)`: Exports conversations to human-readable markdown notes in `.agents/exported_chats/`.
- `[4] Backup Master History`: Creates timestamped backups of `history.db`.
- `[5] Restore Master History from Backup`: One-click recovery if database is ever corrupted or deleted.
- `[6] Storage & Diagnostics Info`: Real-time inspection of SQLite WAL database status, storage paths, chat counts, and file sizes.
- `[7] Uninstall sessionList`: Clean removal of all shortcuts and binary installations.

---

## File Hierarchy & Architecture

```text
sessionList/ (Repository Root)
├── sessionlist.py              # Core engine: SQLite WAL + FTS5, TUI, folder selector, export & multi-layer purge
├── install.sh                  # Interactive installer: sets up shortcuts in ~/.local/bin
├── get.sh                      # 1-line curl-to-sh remote bootstrap installer
├── uninstall.sh                # Clean uninstaller: removes shortcuts and alias links
├── plugin.json                 # Antigravity plugin manifest
├── README.md                   # Documentation, positioning & usage guide
├── docs/                       # Web landing page & documentation assets
│   └── index.html              # Landing page and interactive terminal preview
├── .gitignore                  # Git hygiene rules
└── skills/
    └── sessionlist/
        └── SKILL.md            # Agent skill prompt definition (zero-token fast path)

Runtime Storage (Created automatically in user's workspace / environment):
├── .agents/
│   ├── sessionlist_data/
│   │   ├── history.db          # SQLite WAL database (sessions table + sessions_fts index)
│   │   ├── history.db-wal      # SQLite Write-Ahead Log
│   │   ├── history.db-shm      # SQLite shared memory index
│   │   ├── config.json         # Saved launcher alias and user preferences
│   │   └── workspaces.json     # Chat ID to workspace path mapping for context-aware resume
│   └── exported_chats/         # Markdown exports of full conversation notes (*.md)
└── ~/.local/bin/               # User binary directory (in system $PATH)
    ├── <prefix>-h              # Quick table dump, CLI search, export & delete launcher (e.g. ach-h, ag-h)
    └── <prefix>-m              # Interactive dashboard launcher (e.g. ach-m, ag-m)
```

---

## License

MIT License. Created by **AshraArc**.
