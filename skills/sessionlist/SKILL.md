---
name: sessionlist
description: Unified session history and notebook lookup for Antigravity. Trigger when the user types /history, /sessions, or asks to recall, search, or view previous chat sessions and organized groups.
---

# sessionList Skill & Slash Command

`sessionList` bridges terminal session management and in-chat history recall.

## Slash Commands & In-Chat Triggers

When the user asks for `/history`, `/sessions`, or previous chat lookups:

### 1. `/history` or `/sessions`
Display recent conversations organized by chronological period:
```bash
python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --list
```
Format into a clean Markdown table with:
- **Period**: `[Today]`, `[Yesterday]`, `[X days ago]`
- **Group**: e.g., `OS-Notes`, `Docker`, `General`
- **Messages**: Number of turns
- **Title / Summary**: First prompt or custom title
- **Session ID**: UUID

### 2. `/history search <query>`
Filter past conversations by keyword or topic:
```bash
python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --search-cli "<query>"
```

### 3. `/history groups`
List all organized notebooks/groups and session counts:
```bash
python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --groups-cli
```

### 4. Terminal Launcher Note
Remind the user that they can also manage, rename, categorize, or delete sessions outside chat directly in their terminal using the unified CLI:
```bash
sessionlist
```
