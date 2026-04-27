# Product Features & Capabilities

## Overview
### Feature Definition
Features are distinct, user-facing capabilities of GHCP Usage Dashboard. Each feature maps to one or more user needs defined in `Personas.md` and is traceable to use cases in `UseCases.md`.

### Feature Maturity Levels
- **Stable**: Fully implemented, tested, and documented
- **Beta**: Functional but may change based on feedback
- **Experimental**: Proof of concept, subject to removal

### Last Updated / Version Reference
Version: 0.1.0 (MVP) — April 2026

## Core Features

### Feature Category 1: Log Scanner

#### Description
Parses GitHub Copilot VS Code extension logs and telemetry cache files from the local filesystem. Extracts completions, chat turns, agent interactions, model identifiers, token counts, session IDs, timestamps, and project context.

#### Capabilities
- Recursive discovery of Copilot log files in known VS Code extension paths
- Incremental scanning — tracks file path and modification time, only processes new/changed files
- Cross-platform path resolution (Windows `%APPDATA%`, macOS `~/Library`, Linux `~/.config`)
- Graceful handling of malformed or truncated log lines (skip and warn)
- Deduplication of records by message ID

#### Supported Workflows
- `python cli.py scan` — Manual full scan
- `python cli.py scan --logs-dir /custom/path` — Scan custom directory
- Automatic scan on `dashboard` command startup

#### Limitations / Known Issues
- Copilot log format is undocumented; may break with extension updates
- Token counts for inline completions may be estimated (not all fields are always present)
- Agent mode telemetry is newer and less stable than completion/chat data

#### Related Features
- SQLite Database (stores parsed data)
- CLI Interface (triggers scan)

#### Typical Use Cases
- UC-1: Developer scans today's logs to see latest activity
- UC-2: First-time user runs scan to populate database from historical logs

---

### Feature Category 2: SQLite Database

#### Description
Persistent local storage for all parsed usage data. Single-file database at a configurable path (default: `~/.ghcp-usage/usage.db`). Uses Python's built-in `sqlite3` module.

#### Capabilities
- Schema auto-creation and migration on first run
- Tables: `sessions`, `completions`, `chat_turns`, `agent_actions`, `processed_files`
- Indexes on `session_id`, `timestamp`, `model`, `project_name` for fast queries
- `processed_files` table for incremental scan tracking (path, mtime, line count)
- Session-level aggregation (total tokens, turn counts, duration)
- Recompute session totals from turn-level data to prevent inflation on re-scans

#### Supported Workflows
- Automatic creation on first `scan`
- Database is queryable with any SQLite client for advanced analysis
- `python cli.py scan --reset` to rebuild from scratch

#### Limitations / Known Issues
- Single-user, single-writer (SQLite limitation — fine for local tool)
- No encryption at rest (data is local only; encrypt the filesystem if needed)

#### Related Features
- Log Scanner (populates the database)
- Dashboard (reads from the database)
- CLI Stats (queries the database)

---

### Feature Category 3: CLI Interface

#### Description
Command-line interface providing `scan`, `today`, `stats`, and `dashboard` commands. Follows the same ergonomic pattern as `claude-usage` CLI.

#### Capabilities
| Command | Description |
|---------|-------------|
| `scan` | Parse log files and populate/update the database |
| `today` | Print today's usage summary by model (terminal output) |
| `stats` | Print all-time statistics (sessions, tokens, costs, top projects) |
| `dashboard` | Scan + launch browser dashboard on localhost |

- `--logs-dir PATH` flag for custom log directory
- `HOST` and `PORT` environment variables for dashboard binding
- Color-coded terminal output with cost estimates
- Human-readable token formatting (e.g., "1.2M" for 1,200,000)

#### Supported Workflows
- Quick daily check: `python cli.py today`
- Deep dive: `python cli.py dashboard`
- Scripted/automated: `python cli.py scan && python cli.py stats`

#### Limitations / Known Issues
- No interactive TUI (text user interface) — output is static text
- No `--json` output flag yet (planned for v0.2)

#### Related Features
- Log Scanner (invoked by `scan` and `dashboard`)
- Dashboard (launched by `dashboard` command)

---

### Feature Category 4: Web Dashboard

#### Description
Single-page HTML/JS dashboard served on `localhost:8080` by Python's built-in `http.server`. Uses Chart.js (loaded from CDN) for interactive charts. Auto-refreshes every 30 seconds.

#### Capabilities
- **Stats Row**: Sessions, turns, input tokens, output tokens, cache read/write, estimated cost
- **Daily Token Usage Chart**: Stacked bar chart (input, output, cache read, cache creation) by day
- **Model Distribution Chart**: Doughnut chart showing token usage by model
- **Top Projects Chart**: Horizontal bar chart of top 10 projects by tokens
- **Cost by Model Table**: Sortable table with per-model cost breakdown
- **Recent Sessions Table**: Sortable, filterable list of recent sessions with duration, turns, tokens, cost
- **Cost by Project Table**: Aggregate cost per project with session/turn counts
- **Model Filter**: Checkbox filter to include/exclude specific models
- **Date Range Selector**: 7d / 30d / 90d / All time with bookmarkable URLs
- **CSV Export**: Export sessions and projects to CSV
- **Rescan Button**: Trigger database rebuild from the dashboard UI
- **Dark Theme**: Developer-friendly dark UI with accent colors

#### Supported Workflows
- Open dashboard → filter by model → select date range → analyze trends
- Export CSV for reporting
- Rescan to pick up latest activity

#### Limitations / Known Issues
- Requires internet for initial Chart.js CDN load (subsequent loads use browser cache)
- No responsive mobile layout (designed for desktop browsers)
- Maximum ~10,000 sessions before chart rendering slows

#### Related Features
- SQLite Database (data source)
- CLI Interface (launches dashboard)

---

### Feature Category 5: Cost Estimation

#### Description
Estimates API-equivalent costs based on token usage and model pricing tables. Helps developers understand the monetary value of their Copilot subscription.

#### Capabilities
- Per-model pricing table (configurable, defaults to current API pricing):
  | Model | Input/MTok | Output/MTok |
  |-------|-----------|------------|
  | GPT-4o | $2.50 | $10.00 |
  | GPT-4o-mini | $0.15 | $0.60 |
  | Claude Sonnet 4 | $3.00 | $15.00 |
  | Gemini 2.5 Pro | $1.25 | $10.00 |
  | o3-mini | $1.10 | $4.40 |
- Cost calculated at session, model, and project levels
- Models not in the pricing table shown as "n/a" (no false estimates)
- Dashboard stat card shows total estimated cost with "API pricing" disclaimer

#### Limitations / Known Issues
- These are **API prices**, not subscription prices. Copilot Individual/Business/Enterprise pricing is flat-rate.
- Cache token pricing may vary by provider
- Model routing decisions are opaque — users may not know which model was selected

#### Related Features
- Dashboard (displays cost data)
- CLI Stats (prints cost summary)

## Advanced Features

### Feature 1: VS Code Extension

#### Description
A VS Code extension (`ghcp-usage-dashboard`) that wraps the Python CLI. Allows launching the dashboard directly from VS Code without a terminal. Ships as a self-contained `.vsix` file.

#### Capabilities
- `GHCP: Open Usage Dashboard` command — spawns `python src/cli.py dashboard` as a child process, polls until ready, then opens the dashboard in a VS Code WebView panel
- `GHCP: Stop Dashboard` command — kills the Python process
- `extensionKind: ["ui"]` — forces local execution even on Remote SSH connections
- Configurable Python path, port, and auto-open on startup via VS Code settings
- Bundles Python source files inside the `.vsix` — no separate clone or `git` required

#### VS Code Settings
| Setting | Default | Description |
|---------|---------|-------------|
| `ghcpUsage.pythonPath` | `` | Path to Python 3.8+ executable. Leave empty to use system PATH |
| `ghcpUsage.port` | `8080` | Dashboard HTTP server port (1024–65535) |
| `ghcpUsage.autoOpen` | `false` | Automatically open dashboard when VS Code starts |

#### Limitations / Known Issues
- Requires Python 3.8+ to be installed separately (not bundled in the `.vsix`)
- WebView panel embeds the dashboard in an iframe — some browser-only features (e.g. CSV export triggering a download) may behave differently

#### Related Features
- CLI Interface (the extension invokes `cli.py dashboard`)
- All dashboard features are available via the extension

---

### Feature 2: GitHub API Integration (v0.2)
- Pull org-level Copilot usage metrics via `GET /orgs/{org}/copilot/usage`
- Requires GitHub PAT with `copilot` scope
- Stores API data alongside local log data in the same SQLite database
- Enables team-level views and adoption metrics

### Feature 2: Completion Acceptance Analytics (v0.2)
- Track acceptance rate per language, per project, per model
- Show "ghost text shown" vs. "accepted" vs. "partially accepted" vs. "dismissed"
- Trend line for acceptance rate over time

### Feature 3: Agent Mode Analytics (v0.2)
- Track tool calls (file edits, terminal commands, web searches)
- Files modified per agent session
- Agent session duration and token efficiency

## Feature Availability Matrix

### By User Role
| Feature | Developer | Team Lead | Admin |
|---------|-----------|-----------|-------|
| Local log scanning | ✅ | ✅ | ✅ |
| CLI commands | ✅ | ✅ | ✅ |
| Web dashboard | ✅ | ✅ | ✅ |
| Cost estimates | ✅ | ✅ | ✅ |
| CSV export | ✅ | ✅ | ✅ |
| GitHub API integration | — | ✅ | ✅ |
| Org-wide metrics | — | — | ✅ |

### By Platform
| Feature | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Log scanning | ✅ | ✅ | ✅ |
| Dashboard | ✅ | ✅ | ✅ |
| GitHub API | ✅ | ✅ | ✅ |

## Feature Dependencies

### Feature Prerequisite Map
```
Log Scanner ──→ SQLite Database ──→ CLI Stats
                                  ──→ Web Dashboard ──→ CSV Export
                                                     ──→ Cost Estimation
GitHub API Integration ──→ SQLite Database (same DB)
```

### Feature Conflicts & Incompatibilities
- `--reset` flag and incremental scanning are mutually exclusive (reset drops all data first)
- GitHub API integration requires network access; conflicts with fully air-gapped environments

## Feature Deprecation & Roadmap

### Planned Deprecations
- None (v0.1 is the first release)

### Upcoming Features
| Version | Feature |
|---------|---------|
| v0.2 | GitHub API integration, agent mode analytics, `--json` CLI output |
| v0.3 | VS Code extension wrapper, multi-user team view |
| v0.4 | Budget alerts, PDF reports, historical trend analysis |
### Replacement Features
### Migration Paths

## Feature Metrics & Usage
### Adoption Rates
### Feature Health Indicators
### Common Feature Combinations
### Feature Requests / Feedback

## Feature Performance Characteristics
### Performance Impact
### Resource Requirements
### Scalability Limits
### Concurrent Usage Limits

## Feature Documentation References
### User Guide Links
### Technical Documentation
### Video Tutorials / Demos
### Configuration Examples

## Feature Gaps & Known Limitations
### Current Limitations
### Workarounds Available
### Future Enhancements Planned
### Related Issues