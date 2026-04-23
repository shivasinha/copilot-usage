# System Architecture

## Architecture Overview

GHCP Usage Dashboard follows a **three-layer pipeline architecture**: Scan → Store → Present. It mirrors the design of [claude-usage](https://github.com/phuryn/claude-usage) adapted for GitHub Copilot's data sources.

The system is a single-process Python application with no external service dependencies. It reads local files, writes to a local SQLite database, and serves a local HTTP dashboard. Optionally, it calls the GitHub REST API for org-level metrics.

## High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Developer Machine                         │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │  VS Code +   │    │   scanner.py │    │   dashboard.py    │  │
│  │  Copilot Ext │───▶│              │───▶│                   │  │
│  │  (log files) │    │  Parse JSONL │    │  HTTP Server      │  │
│  └──────────────┘    │  + telemetry │    │  + Single-Page    │  │
│                      │              │    │    HTML/JS App     │  │
│  ┌──────────────┐    │              │    │                   │  │
│  │ GitHub API   │───▶│              │    │  Chart.js (CDN)   │  │
│  │ (optional)   │    └──────┬───────┘    └────────┬──────────┘  │
│  └──────────────┘           │                     │              │
│                      ┌──────▼─────────────────────▼──────┐      │
│                      │         usage.db (SQLite)          │      │
│                      │  sessions | completions | turns    │      │
│                      │  agent_actions | processed_files   │      │
│                      └───────────────────────────────────┘      │
│                                                                  │
│  ┌──────────────┐                                               │
│  │   cli.py     │──── scan / today / stats / dashboard          │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

## Component Model

### Core Components

| Component | File | Responsibility |
|-----------|------|---------------|
| **Scanner** | `scanner.py` | Discover, parse, and deduplicate Copilot log files. Insert/update records in SQLite. |
| **Dashboard** | `dashboard.py` | Serve HTTP API (`/api/data`, `/api/rescan`) and the single-page HTML/JS dashboard. |
| **CLI** | `cli.py` | Entry point. Route commands (`scan`, `today`, `stats`, `dashboard`). Format terminal output. |

### Supporting Components

| Component | Responsibility |
|-----------|---------------|
| **SQLite Database** | Persistent storage. Auto-created with schema migrations. |
| **Chart.js (CDN)** | Client-side chart rendering. No server-side dependency. |
| **Browser** | Renders the dashboard. Opened automatically by `cli.py dashboard`. |

### External Integrations

| Integration | Protocol | Auth | Status |
|-------------|----------|------|--------|
| GitHub Copilot Usage API | HTTPS REST | PAT with `copilot` scope | Planned (v0.2) |
| Chart.js CDN | HTTPS | None | Stable |

## Architectural Patterns & Principles

1. **Zero-Dependency**: Only Python stdlib. No `pip install`, no `node_modules`, no build step.
2. **Local-First**: All data stays on the developer's machine. No cloud sync, no external telemetry.
3. **Incremental Processing**: Scanner tracks processed files (path, mtime, line count). Re-runs skip unchanged files.
4. **Single-File Database**: SQLite requires no server, no configuration, no ports.
5. **Embedded Dashboard**: HTML/CSS/JS is a Python string in `dashboard.py` — no separate frontend build.
6. **Idempotent Operations**: Running `scan` multiple times produces the same result (dedup by message ID, recompute totals).

## Layered Architecture

### Presentation Layer
- **Web Dashboard**: Single-page app embedded in `dashboard.py`. HTML served on `GET /`. Data fetched via `GET /api/data`. Rescan triggered via `POST /api/rescan`.
- **CLI Output**: Formatted terminal tables with color and alignment. Human-readable token formatting.

### Business Logic Layer
- **Scanner Logic** (`scanner.py`):
  - File discovery (recursive glob for `*.jsonl` / `*.log` in known paths)
  - JSONL parsing with error tolerance (skip malformed lines)
  - Session metadata extraction (session ID, project, timestamps, git branch)
  - Turn extraction (model, tokens, tool name, message ID)
  - Deduplication (last record per message ID wins)
  - Session aggregation (sum tokens/turns from individual records)
- **Cost Calculation** (`dashboard.py` client-side JS + `cli.py` server-side Python):
  - Model → pricing table lookup
  - Cost = (input_tokens × input_price + output_tokens × output_price) / 1,000,000
  - Unknown models → "n/a"
- **Data Aggregation** (`dashboard.py`):
  - Daily rollups by model
  - Session filtering by model + date range
  - Project-level aggregation from sessions

### Data Access Layer
- **SQLite via `sqlite3` module**: Direct SQL queries, `conn.row_factory = sqlite3.Row` for dict-like access.
- **Schema Management**: `init_db()` creates tables with `IF NOT EXISTS`, adds columns with `ALTER TABLE` for upgrades.
- **Processed Files Tracking**: `processed_files` table with `(path, mtime, lines)` for incremental scanning.

### Infrastructure Layer
- **HTTP Server**: Python's `http.server.HTTPServer` + `BaseHTTPRequestHandler`. Single-threaded, localhost-only.
- **File System**: Cross-platform path resolution via `pathlib.Path`. Handles Windows/macOS/Linux differences.
- **Browser Launch**: `webbrowser.open()` with 1-second delay after server start.

## Data Flow

### System Flows

#### Scan Flow
```
1. cli.py receives "scan" command
2. scanner.scan() called with log directories
3. For each directory:
   a. Glob for *.jsonl files
   b. Check processed_files table for (path, mtime)
   c. Skip if unchanged; process if new or modified
   d. Parse file → extract sessions + turns
   e. Upsert sessions, insert turns (dedup by message_id)
   f. Record file as processed
4. Recompute session totals from turns table
5. Print summary
```

#### Dashboard Flow
```
1. cli.py receives "dashboard" command
2. Run scan (same as above)
3. Start HTTPServer on HOST:PORT
4. Open browser in background thread
5. Browser requests GET /
6. Server returns HTML (embedded in dashboard.py)
7. Browser JS calls GET /api/data
8. Server queries SQLite, returns JSON
9. Browser renders charts + tables
10. Every 30s: JS re-fetches /api/data, updates UI
```

### Request/Response Cycles

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/` | GET | — | HTML dashboard page |
| `/api/data` | GET | — | JSON: `{ all_models, daily, sessions_all, generated_at }` |
| `/api/rescan` | POST | — | JSON: `{ new, updated, skipped, turns, sessions }` |

## Scalability & Performance Considerations

- **Log volume**: Typical developer generates 10–100 log files/month. Scanner handles thousands efficiently.
- **Database size**: SQLite handles millions of rows. Typical usage stays under 100MB.
- **Dashboard rendering**: Chart.js handles ~10,000 data points smoothly. Beyond that, date range filtering limits visible data.
- **Memory**: Scanner processes files one at a time. No full-dataset memory requirement.
- **Concurrency**: Single-threaded HTTP server is sufficient for localhost single-user access.

## Security Architecture

- **No authentication**: Localhost-only server. No remote access by default.
- **No data transmission**: All data stays local. No telemetry, no phone-home.
- **GitHub API token**: Stored in environment variable (not in config files). Used only for optional API calls over HTTPS.
- **Input validation**: JSONL parsing uses `json.loads()` — no `eval()`. SQL uses parameterized queries (no injection).
- **XSS prevention**: Dashboard uses `esc()` function (creates text node) for all dynamic content.

## Deployment Architecture

```
Developer machine (single-process, no containers):
  python cli.py dashboard
    → scanner.py reads logs from filesystem
    → writes to ~/.ghcp-usage/usage.db
    → dashboard.py serves on localhost:8080
    → browser renders dashboard
```

No Docker, no cloud, no infrastructure. Clone and run.

## Technology Constraints & Trade-offs

| Constraint | Rationale | Trade-off |
|-----------|-----------|-----------|
| Python stdlib only | Zero-install friction | No `requests` (use `urllib`), no `click` (manual arg parsing) |
| Embedded HTML in Python | Single-file dashboard, no build step | Harder to maintain large HTML templates |
| SQLite (not PostgreSQL) | Zero-config, no server process | Single-writer, no concurrent remote access |
| Chart.js from CDN | No npm/bundler needed | Requires internet for first load (cached after) |
| Single-threaded HTTP | Simplicity | Cannot handle concurrent requests (fine for localhost) |

## Future Architecture Evolution

| Phase | Change |
|-------|--------|
| v0.2 | Add `github_api.py` module for REST API integration. Add `config.py` for token/path management. |
| v0.3 | Optional VS Code extension wrapper (TypeScript) that invokes Python CLI. |
| v0.4 | Consider replacing embedded HTML with a separate `static/` directory for maintainability. |

## Related Architecture Decisions (Link to ADRs)
- ADR-001: Use SQLite over JSON file storage (query performance, ACID compliance)
- ADR-002: Embed HTML in Python over separate static files (single-file simplicity)
- ADR-003: Use Chart.js CDN over bundled JS (no build tools required)
- ADR-004: Python stdlib only over adding pip dependencies (zero-install principle)