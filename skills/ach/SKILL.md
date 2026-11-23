---
name: ach
description: High-efficiency session history and notebook lookup for Antigravity with Ach! (SQLite WAL + FTS5 full-text recall). Trigger on /history, /sessions, /find, /recall, search, or natural language requests for chat history and past transcript content.
---

# Ach! (ach) Skill

Direct, zero-token overhead session history recall and past transcript content search from `history.db` (SQLite WAL + FTS5 full-text engine).

## Tool Resolution
Run the command using the installed CLI binary if available (`ach`), or via `python3 ach.py`:
- Binary: `ach`
- Or script: `python3 ach.py` (or specify path to local installation)

## FAST PATH (Standard In-Chat History)

Whenever the user asks for chat history (e.g. `/history`, `/sessions`, `show my chats`, `history of past 7 days`):
1. **Execute the CLI tool directly**:
   - Recent chats: `ach --list` (or `python3 ach.py --list`)
   - Filter by days: `ach --days <N>` (or `python3 ach.py --days <N>`)
   - Filter by hours: `ach --hours <N>` (or `python3 ach.py --hours <N>`)
   - All history: `ach --all` (or `python3 ach.py --all`)
2. **CLEAN TOOL SUMMARY**:
   - Always set `toolSummary` to a clean short phrase (e.g. `History lookup`, `Session history`).
3. **ZERO-TOKEN FAST OUTPUT**:
   - The CLI tool outputs a pre-aligned table formatted strictly for an 80-column terminal.
   - Output the tool result DIRECTLY inside a code block or verbatim. DO NOT re-tokenize or summarize.

## FULL-TEXT SEARCH & RECALL (/find, /recall)

Whenever the user searches past transcripts, queries prior discussions, or uses `/find <query>` / `/recall <query>`:
1. **Execute FTS5 search directly**:
   - Recipe: `ach -s "<query>"` (or `python3 ach.py -s "<query>"`)
   - Also accepts `--search-cli "<query>"`.
2. **CLEAN TOOL SUMMARY**:
   - Set `toolSummary` to a short phrase (e.g. `Session search`, `Transcript recall`).
3. **OUTPUT**:
   - Return matched sessions and contextual snippets directly to the user.

## ASYNC CHAT TITLING (Turn 1 or 2)
On turn 1 or turn 2 of a session, if the current session still has a raw/default title, run in the background:
`ach --set-title <current_cid> "<Clean 2-to-4 Word Title>"` (or `python3 ach.py --set-title <current_cid> "<Clean 2-to-4 Word Title>"`)
