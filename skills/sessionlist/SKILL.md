---
name: sessionlist
description: Unified session history and notebook lookup for Antigravity. Trigger when the user types /history, /sessions, asks to view or search chat history, or asks to group/organize past sessions.
---

# sessionList Skill

Bridges terminal session management (`ach`) and in-chat history actions.

## Command Reference

Run `sessionlist.py` located at `/mnt/a/anti-g/projects/sessionList/sessionlist.py`:

1. **List Recent Chats** (Default cap: 15):
   `python3 .../sessionlist.py --list`

2. **List All Chats** (No cap):
   `python3 .../sessionlist.py --list-all`

3. **Time-Filtered Chats**:
   `python3 .../sessionlist.py --days <N>` or `--hours <N>`

4. **Topic / Keyword Search**:
   `python3 .../sessionlist.py --search-cli "<query>"`

5. **List Notebook Groups**:
   `python3 .../sessionlist.py --groups-cli`

6. **Abstraction Filter (Smart Titling)**:
   When displaying chats, ALWAYS apply the AI Abstraction Filter:
   - For any chat with a raw/unpolished prompt (e.g. starting with "hey i...", "can you..."), distill it into a clean, 2-to-5 word title (e.g. "Ryzen AI NPU Evaluation", "Docker WSL Setup").
   - Persist the abstracted title so the terminal CLI benefits: `python3 .../sessionlist.py --set-title <cid> "<Clean Title>"`

7. **Smart Grouping**:
   - Filter by time & topic: `python3 .../sessionlist.py --group-window "<Group>" --hours <N> --match "<query>"`
   - Specific session IDs: `python3 .../sessionlist.py --group-ids "<Group>" <id1> <id2>`

Format table output cleanly with: Period, Group, Message count, Abstracted Title, and Session ID.
