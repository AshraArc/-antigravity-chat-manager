---
name: sessionlist
description: High-efficiency session history and notebook lookup for Antigravity. Trigger on /history, /sessions, or natural language requests for chat history.
---

# sessionList Skill

Direct, zero-token overhead session history recall from `master_history.tsv`.

## FAST PATH (Standard In-Chat History)

Whenever the user asks for chat history (e.g. `/history`, `show my chats`, `history of past 7 days`):
1. **Execute the CLI tool directly**:
   - Recent chats: `python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --list`
   - Filter by days: `python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --days <N>`
   - Filter by hours: `python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --hours <N>`
   - Keyword search: `python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --search-cli "<query>"`
   - All history: `python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --all`
2. **CLEAN TOOL SUMMARY**:
   - Always set `toolSummary` to a clean short phrase (e.g. `History lookup`, `Session history`).
3. **ZERO-TOKEN FAST OUTPUT**:
   - The CLI tool outputs a pre-aligned table formatted strictly for an 80-column terminal.
   - Output the tool result DIRECTLY inside a code block or verbatim. DO NOT re-tokenize or summarize.

## ASYNC CHAT TITLING (Turn 1 or 2)
On turn 1 or turn 2 of a session, if the current session still has a raw/default title, run in the background:
`python3 /mnt/a/anti-g/projects/sessionList/sessionlist.py --set-title <current_cid> "<Clean 2-to-4 Word Title>"`
