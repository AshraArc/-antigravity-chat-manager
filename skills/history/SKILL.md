---
name: history
description: Displays conversation history, searches past Antigravity chats, lists notebook groups, and provides instructions to resume sessions. Trigger when the user asks for /history, chat history, previous chats, or to find past conversations.
---

# History Slash Command & Skill

This skill allows the agent to inspect, search, and report previous Antigravity conversations and organized notebook groups directly inside the active chat.

## Usage Modes

When the user types `/history` or asks about past conversations:

### 1. `/history` (Recent Chats Overview)
Run the helper script to fetch recent conversations:
```bash
python3 /mnt/a/anti-g/projects/antigravity-chat-manager/antig_manager.py --list
```
Format the output into a clean, readable Markdown table:
- **Date / Period**: `Today`, `Yesterday`, `X days ago`
- **Group / Notebook**: e.g. `OS-Notes`, `Docker`, `General`
- **Messages**: Number of turns
- **Topic / Preview**: First prompt or custom title
- **Session ID**: The UUID needed to resume

Provide the command to resume:
```bash
agy --conversation <session-id>
```

### 2. `/history search <keyword>`
Filter conversations matching the user's topic:
```bash
python3 /mnt/a/anti-g/projects/antigravity-chat-manager/antig_manager.py --search-cli "<keyword>"
```
Display matching conversations and provide one-click resumption instructions.

### 3. `/history groups`
List all notebook categories and count of conversations in each group:
```bash
python3 /mnt/a/anti-g/projects/antigravity-chat-manager/antig_manager.py --groups-cli
```
Explain how to manage them in terminal using `ach` or `antig-h`.
