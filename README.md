# sessionList

Unified session manager and history recall for **Google Antigravity CLI (`agy`)**.

Created by **AshraArc**.

Use **`sessionList`** across two environments:
1. **Terminal Interface (`ach`)**: Interactive session manager to view chronological history, create subject notebooks, perform fuzzy search, resume, and clean up past sessions.
2. **In-Chat Plugin (`/history` or plain prompts)**: Native conversational recall allowing the agent to list, filter, search, and group past sessions during active chats.

---

## Key Features

- **Chronological History Feed**: Automatically parsed from local transcript logs and sorted from newest to oldest.
- **Smart Date Segmentation**: Grouped under `[Today]`, `[Yesterday]`, `[X days ago]`, and calendar months.
- **AI Abstraction Filter**: Automatically distills raw, verbose user prompts into clean 2-to-5 word topic summaries and persists them across both terminal and chat views.
- **Subject Notebooks & Groups**: Categorize related sessions into custom subjects (e.g., `OS-Coursework`, `Docker`, `Math`).
- **Flexible Time-Window Filters**: Filter sessions by past hours (`--hours <N>`) or days (`--days <N>`).
- **Smart Grouping**: Group chats matching specific topics and time ranges in one step.
- **Interactive Fuzzy Search**: Instant keyboard navigation powered by `fzf` (with standard text fallback).
- **Sub-100ms Performance**: Zero external heavy dependencies; built purely with standard Python 3.

---

## Installation

### 1. Terminal Command Setup (`ach`)
```bash
git clone https://github.com/AshraArc/sessionList.git
cd sessionList
chmod +x install.sh
./install.sh
```
Follow the one-time prompt to configure your launcher shortcut (`ach`).

### 2. Antigravity In-Chat Plugin Setup
To enable the `/history` skill inside your Antigravity conversations:
```bash
agy plugin install /path/to/sessionList
# or directly from your GitHub repository:
agy plugin install https://github.com/AshraArc/sessionList
```

---

## Usage Guide

### A. Terminal Interface (`ach`)

Launch the interactive manager:
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

#### Terminal Shortcuts:
- `<number>`: Resume selected session in Antigravity (`agy --conversation <id>`).
- `edit <number>`: Rename session title or assign to a notebook group.
- `del <number>`: Permanently delete a single session.
- `del-group <name>`: Delete an entire notebook group and all its sessions.
- `b` or `q`: Return to previous menu or exit cleanly.

#### Command-Line Flags:
```bash
ach --search                            # Open instant fuzzy search
ach --list                              # Display 15 most recent sessions
ach --all                               # Display complete conversation archive
ach --days 7                            # View sessions from the last 7 days
ach --hours 2                           # View sessions from the past 2 hours
ach --group-window "OS" --hours 2 --match "memory"   # Group matching chats
ach --help                              # Display all available flags
```

---

### B. In-Chat Natural Language Commands

While chatting in Antigravity, you can use either `/history` or natural English prompts:

| What you want to do | Example Prompt |
| :--- | :--- |
| **View recent sessions** | `/history` or `"show my chat history"` |
| **View full archive** | `"show me all chat histories"` |
| **Filter by time window** | `"show chats from the last 3 days"` or `"past 2 hours"` |
| **Search past discussions** | `/history search docker` or `"search history for paging"` |
| **View notebooks / groups** | `/history groups` or `"show my notebooks"` |
| **Smart group by time + topic**| `"group the docker chats from today into DevOps"` |

---

## Storage Architecture

All preferences, titles, and group assignments are stored under standard XDG paths:
- `~/.config/antigravity-chat-manager/metadata.json`: Stores custom titles and notebook classifications.
- `~/.config/antigravity-chat-manager/config.json`: Stores your custom Antigravity command/alias.
- `~/.gemini/antigravity-cli/brain/`: Native session transcript storage (preserved).

---

## License

MIT License. See [LICENSE](LICENSE) for details.
