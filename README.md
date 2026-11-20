# Antigravity Chat Manager (`ach`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-brightgreen.svg)](https://python.org)

A fast, lightweight, and interactive terminal-based chat history browser, notebook organizer, and session launcher for **Google Antigravity CLI (`agy`)**.

---

## The Problem
When using Google Antigravity CLI, past sessions are stored in raw transcript logs under cryptic session IDs (`~/.gemini/antigravity-cli/brain/<uuid>`). If you switch between projects, study multiple topics, or close your terminal, it is difficult to:
- Find what you were talking about 3 days ago.
- Resume an older conversation without digging through transcript hashes.
- Delete old, space-consuming test chats cleanly.
- Organize conversations into subject folders (like NotebookLM or Gemini Web).

**Antigravity Chat Manager (`ach`)** solves all of this directly in your terminal.

---

## Features

- **Chronological History Feed**: Automatically parses session transcripts and sorts chats from newest to oldest.
- **Smart Date Segmentation**: Groups conversations intuitively under `[Today]`, `[Yesterday]`, `[X days ago]`, and calendar months.
- **Notebook & Group Organization**: Classify related chats into custom groups (e.g., `OS-Coursework`, `Docker`, `Backend`, `Math`).
- **Interactive Fuzzy Search**: Instant keyboard search powered by `fzf` (with automatic fallback to text search).
- **One-Key Resume**: Select any conversation number to immediately restore context via `agy --conversation <id>`.
- **Clean Terminal UI**: Refreshes in-place with zero scroll clutter, exiting cleanly without leaving zombie processes.
- **Universal CLI Compatibility**: Automatically detects whether your Antigravity launcher is named `agy` or a custom alias (e.g. `antig`, `ai`).
- **Zero Heavy Dependencies**: Built entirely with the Python 3 standard library.

---

## Quick Installation

Run the automated installer:

```bash
git clone https://github.com/<your-username>/antigravity-chat-manager.git
cd antigravity-chat-manager
chmod +x install.sh
./install.sh
```

The installer will:
1. Ask for your preferred command shortcut (defaults to `ach`).
2. Detect your Antigravity command/alias.
3. Place a symlink into `~/.local/bin/`.

*(Ensure `~/.local/bin` is in your `$PATH`)*.

---

## User Guide

### 1. Launching the Manager
Simply type:
```bash
ach
```

You will see the main menu:
```text
==========================================
         ANTIGRAVITY CHAT MANAGER         
==========================================
  [1] Recent Chats
  [2] Groups
  [3] Search
  [q] Quit
------------------------------------------
Select > 
```

---

### 2. Browsing Recent Chats (`[1]`)
Select `1` to see your past sessions categorized by date:

```text
---------------- RECENT CHATS ----------------
[Today]
  [ 1] [General] 10:15 (24) | CPU Scheduling & Gantt Charts

[Yesterday]
  [ 2] [OS] 18:30 (52) | Paging & TLB Access Time
  [ 3] [General] 14:10 (12) | Docker Container Setup

[3 days ago]
  [ 4] [Math] 09:45 (30) | Discrete Math Relations
----------------------------------------------
Actions: <num> resume, edit <num>, del <num>, b/q (back)
Recent > 
```

- **Resume a chat**: Type the number (e.g. `1`) and hit **Enter**.
- **Rename or move to a group**: Type `edit 1`.
- **Delete a single chat**: Type `del 1` (confirms with `y/N` before deleting).
- **Go back**: Type `b` or `q`.

---

### 3. Managing Groups & Notebooks (`[2]`)
Select `2` to organize your chats by subject or project:

```text
---------------- GROUPS ----------------
  [1] Docker (2 chats)
  [2] General (5 chats)
  [3] OS (4 chats)
----------------------------------------
Actions: <num> open, new, del-group <name>, b/q (back)
Group > 
```

- **Open a group**: Type the number to view only chats inside that notebook.
- **Create a new group**: Type `new` and enter the name (e.g. `Machine-Learning`).
- **Delete an entire group**: Type `del-group <name>` to remove the group and all its stored conversations in one step.

---

### 4. Fast Search (`[3]`)
Select `3` (or run `ach --search`) to instantly filter conversations across titles, prompts, dates, and group tags using interactive fuzzy search (`fzf`).

---

### Command-Line Flags
You can also run commands directly from your shell without opening the menu:

```bash
ach --search    # Jump straight to interactive search
ach --config    # Reconfigure your Antigravity command/alias
ach --help      # Show quick help options
```

---

## Configuration & Storage

- **User Preferences & Groups**: Stored cleanly under standard XDG paths at:
  `~/.config/antigravity-chat-manager/`
  - `config.json`: Stores your launcher executable/alias.
  - `metadata.json`: Stores custom titles and group assignments.
- **Original Antigravity Transcripts**: Preserved in their native paths at `~/.gemini/antigravity-cli/brain/`.

---

## Contributing
Pull requests, bug reports, and suggestions are welcome! Feel free to open an issue on GitHub.

---

## License
MIT License. See [LICENSE](LICENSE) for details.
