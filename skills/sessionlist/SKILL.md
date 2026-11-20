---
name: sessionlist
description: Unified session history and notebook lookup for Antigravity. Trigger when the user types /history, /sessions, or asks to recall, search, or view previous chat sessions and organized groups.
---

# sessionList Skill & History Recall

`sessionList` bridges terminal session management and in-chat history recall.

## Behavior Rules for In-Chat Queries

### 1. Default Lookup ("show my chat history", "recent chats", "history")
Run with default cap of 15 recent sessions (~1 week):
```bash
python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --list
```
Format into a clean Markdown table with:
- **Period**: `[Today]`, `[Yesterday]`, `[X days ago]`, `[Month Day]`
- **Notebook / Group**: e.g., `OS-Notes`, `Docker`, `General`
- **Messages**: Number of turns
- **Topic / Preview**: First prompt or custom title
- **Session ID**: UUID for resumption

If there are more chats, mention:
*"Showing 15 most recent chats. Ask 'show me all chat histories' to see your complete archive."*

### 2. Time-Filtered Lookups ("last N days", "past N hours", "chats from today")
Filter dynamically by time window:
- For days (e.g. "show chats from last 3 days" / "past 7 days"):
  ```bash
  python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --days <N>
  ```
- For hours (e.g. "show chats from last 2 hours" / "past hour"):
  ```bash
  python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --hours <N>
  ```
Display the classified results table matching that exact time window.

### 3. Full History Lookup ("show me all chat histories", "full history", "all sessions")
Run without limits:
```bash
python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --list-all
```
Display the complete classified table across all dates.

### 4. Topic Search ("search history for <query>")
Filter past conversations by keyword or topic:
```bash
python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --search-cli "<query>"
```

### 5. Group Lookup ("show my notebooks", "show groups")
List all organized notebooks/groups and session counts:
```bash
python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --groups-cli
```
