# sessionList

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-brightgreen.svg)](https://python.org)

Unified session manager and history recall for **Google Antigravity CLI (`agy`)**.

Use **`sessionList`** in two ways:
1. **Outside Chat (Terminal CLI)**: An interactive, clean terminal manager to browse chronological history, group chats into notebooks, fuzzy search, resume, and delete sessions.
2. **Inside Chat (Antigravity Plugin)**: A native `/history` slash command to recall past conversations and notebook topics on the fly without leaving your conversation.

---

## Features

- **Unified Memory & Storage**: The same notebooks, custom titles, and session history are shared seamlessly between the terminal CLI and in-chat slash commands.
- **Chronological History Feed**: Automatically parsed from session transcripts, sorted from newest to oldest.
- **Relative Date Segmentation**: Cleanly groups chats under `[Today]`, `[Yesterday]`, `[X days ago]`, and calendar months.
- **Notebooks & Groups**: Group related sessions into subjects (e.g. `OS-Coursework`, `Docker`, `Math`).
- **Fuzzy Search**: Instant `fzf`-powered search across titles, prompts, and groups.
- **One-Key Resume**: Select any session number to seamlessly launch `agy --conversation <id>`.
- **In-Chat Slash Commands**: Access past sessions right inside Antigravity using `/history` or `/sessions`.
- **Zero Heavy Dependencies**: Pure Python 3 standard library.

---

## Installation

### 1. Terminal CLI Setup
```bash
git clone https://github.com/AshraArc/sessionList.git
cd sessionList
chmod +x install.sh
./install.sh
```

### 2. Antigravity In-Chat Plugin Setup
To enable the `/history` slash command inside Antigravity:
```bash
agy plugin install /path/to/sessionList
# or directly from GitHub:
agy plugin install https://github.com/AshraArc/sessionList
```

---

## Usage

### In Terminal (Outside Chat):
Simply run:
```bash
ach
```

```text
==========================================
               sessionList                
==========================================
  [1] Recent Chats
  [2] Groups
  [3] Search
  [q] Quit
------------------------------------------
Select > 
```

- `<num>`: Resume session in Antigravity
- `edit <num>`: Rename session or assign to a notebook group
- `del <num>`: Delete session and clean up disk space
- `del-group <name>`: Delete an entire notebook and all contained sessions

### In Chat (Inside Antigravity):
While chatting with Antigravity, simply type:
- `/history`: List recent sessions with message counts, dates, and session IDs.
- `/history search <query>`: Search past topics and conversations.
- `/history groups`: Display organized notebooks.

---

## Author
**AshraArc** • [GitHub Repository](https://github.com/AshraArc/sessionList)

## License
MIT License
