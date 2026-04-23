# Data Gathering — How It Works

## Source

VS Code GitHub Copilot chat logs — **JSONL files** at:

| Platform | Path |
|---|---|
| Windows | `%APPDATA%\Code\User\workspaceStorage\<workspace-id>\chatSessions\<session-uuid>.jsonl` |
| macOS | `~/Library/Application Support/Code/User/workspaceStorage/…` |
| Linux | `~/.config/Code/User/workspaceStorage/…` |

---

## Scan Workflow (`scanner.py`)

1. **Resolve storage root** — from `--logs-dir` flag or the OS default path above.
2. **Build workspace map** — reads `workspace.json` in each workspace folder hash; maps hash → human project name (e.g. `code/ghcp-usage`).
3. **Discover files** — finds all `chatSessions/*.jsonl` under every workspace folder.
4. **Skip unchanged files** — compares each file's `path + mtime` against the `processed_files` table; unchanged files are skipped entirely.
5. **Parse JSONL** — each file contains many incremental-update lines; all requests are collected and **deduplicated by `requestId`** (last write wins).
6. **Extract per-turn data** from each request:
   - `requestId` → `message_id` (dedup key)
   - `modelId` → model name (strips `copilot/` prefix)
   - `timestamp` → normalised ISO 8601 UTC
   - **Input tokens** (priority order):
     1. `result.metadata.renderedUserMessage` — the fully-rendered payload (system prompt + history + context) that VS Code sent to the model, stored for completed requests. Most accurate.
     2. `message.text` + `variableData.variables[*].value` + cumulative session history accumulation — used when the rendered payload is absent.
   - **Output tokens**: extracted from `response[]` items — covers markdown text (`kind=null`), thinking blocks (`kind=thinking`), file edits (`kind=textEditGroup`, `edits[*][*].text`), and progress messages (`kind=progressTaskSerialized`). All estimated at ÷4 chars/token.
   - `accepted`, `tool_name`, `cwd`, `language` → all `NULL` for chat sessions
7. **INSERT OR IGNORE** turns into the DB (dedup enforced by `message_id` partial unique index).
8. **Recompute session aggregates** — a single SQL `INSERT OR REPLACE` recomputes the `sessions` table entirely from `turns` to prevent inflation on re-scans.

---

## Database Tables

| Table | Purpose |
|---|---|
| `turns` | One row per chat request. Contains model, timestamps, estimated tokens, `message_id`. |
| `sessions` | Aggregated per session-UUID. Derived from `turns` on every scan. |
| `processed_files` | Tracks `path + mtime` of scanned JSONL files for incremental updates. |

---

## Key Limitations / Assumptions

| Topic | Detail |
|---|---|
| **Token counts** | Estimated (1 token ≈ 4 chars). Input uses `renderedUserMessage` when available (most accurate), otherwise `message.text` + `variableData` + cumulative history. Output includes markdown, thinking blocks, and file edits (`textEditGroup`). System prompt tokens not stored in VS Code logs are not counted. |
| **Completions / accepts** | Inline ghost-text completion events (accepts/rejects) are **not stored locally** by VS Code — they are sent to GitHub telemetry only and cannot be recovered from local logs. Always `NULL`. |
| **Accepted / completions** | Always `NULL` for chat sessions — only inline completion events would populate these. |
| **Cost estimates** | Computed at query time by `pricing.py` from estimated tokens and `PRICING_TABLE`. |
| **Incremental re-scan** | Only new/modified files are re-processed (mtime check). A full reset requires `--reset`. |
| **Deduplication** | Turn-level: `message_id` unique index. Session-level: aggregates fully recomputed each run. |

---

## Scan Triggers

| How | When |
|---|---|
| `python src/cli.py scan` | Manual CLI scan |
| `python src/cli.py dashboard` | Auto-scans on startup before opening the browser |
| `POST /api/rescan` (dashboard) | Triggered by the **Rescan** button in the browser UI |
