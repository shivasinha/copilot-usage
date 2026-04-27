# GHCP Usage Dashboard — Quick Start

## Overview

A local dashboard for tracking your VS Code GitHub Copilot usage — chat sessions, token counts, model breakdowns, premium request quota, and estimated costs. Zero dependencies, zero telemetry, everything stays on your machine.

---

## Prerequisites

- **Python 3.8+** (no pip packages required)
- **VS Code** with GitHub Copilot extension installed and active
- A web browser (Chrome, Firefox, Edge, Safari)

---

## Installation

### Option A — VS Code Extension (recommended)

Install the `.vsix` file directly:

```
code --install-extension ghcp-usage-dashboard-0.1.0.vsix --force
```

Then use the Command Palette: `GHCP: Open Usage Dashboard`.

### Option B — Python CLI (no VS Code required)

```bash
git clone <repo-url>
cd ghcp-usage
```

No build step, no virtual environment, no dependencies.

---

## Usage

### Windows (PowerShell)
```powershell
python src/cli.py dashboard
```

### macOS / Linux
```bash
python3 src/cli.py dashboard
```

This will:
1. Scan your local VS Code Copilot log files
2. Build a SQLite database at `~/.ghcp-usage/usage.db`
3. Open your browser at `http://localhost:8080`

### Other commands
```bash
python src/cli.py scan             # Incremental scan only (no browser)
python src/cli.py today            # Today's usage by model in terminal
python src/cli.py stats            # All-time aggregates by model in terminal
python src/cli.py scan --reset     # Wipe DB and re-scan from scratch
```

### Custom host / port
```powershell
$env:PORT = "9000"; python src/cli.py dashboard   # Windows PowerShell
```
```bash
PORT=9000 python3 src/cli.py dashboard            # macOS / Linux
```

---

## How Data Is Captured

Two sources run in parallel and are automatically deduplicated:

**JSONL Scanner (default, always on)**
- Reads VS Code's `workspaceStorage/<id>/chatSessions/*.jsonl` log files
- Covers all sessions including SSH remote connections
- Accurate token counts for all models
- Scans on startup and every 30 seconds in the background

**mitmproxy (optional, local VS Code only)**
- Intercepts live HTTPS calls to the Copilot API
- Real-time capture (no waiting for log files)
- Requires separate setup (see `setup-proxy-global.ps1`)
- Useful when log files are unavailable or for immediate capture

---

## Project Structure

```
ghcp-usage/
├── src/
│   ├── cli.py          # CLI entry point
│   ├── scanner.py      # VS Code JSONL log parser
│   ├── dashboard.py    # HTTP server + single-page dashboard
│   ├── db.py           # SQLite schema and connection management
│   ├── pricing.py      # Per-model API cost estimates
│   ├── quota.py        # Monthly premium request quota tracking
│   └── settings.py     # Persistent settings (~/.ghcp-usage/settings.json)
├── docs/               # Product requirements, architecture, data model
├── .github/            # Copilot agents and workspace instructions
└── Readme.md
```

Database location: `~/.ghcp-usage/usage.db`

---

## Dashboard Settings

Click the **⚙** gear icon in the top-right header. Settings persist across restarts.

| Setting | Default | Notes |
|---------|---------|-------|
| Data Refresh Interval | 30s | Controls UI auto-refresh and background scan rate. Min 10s. |
| Monthly Premium Request Limit | 100 | Base for quota bar %. Copilot Individual/Business default. |
| Data Source | Both | `Both` = proxy + JSONL; `JSONL only` = local logs; `Proxy only` = live interception |
| Price Overrides | — | JSON map of model substrings to `[input $/MTok, output $/MTok]` |

---

## Timezone

All timestamps and daily chart groupings use **IST (UTC+5:30)**.

---

## Privacy

All data stays on your machine. The tool reads local VS Code log files and writes to a local SQLite database. Nothing is sent to GitHub, OpenAI, Anthropic, or any external service.

---

## Key Implementation Rules

- Zero runtime dependencies — Python stdlib only
- All SQL queries use parameterised placeholders
- All dynamic HTML uses `esc()` to prevent XSS
- Deduplication via `UNIQUE INDEX` on `message_id` — proxy and JSONL data never double-count


## Quick Start / Getting Started

No `pip install`, no virtual environment, no build step.

### Windows
```powershell
git clone https://github.com/youruser/ghcp-usage
cd ghcp-usage
python cli.py dashboard
```

### macOS / Linux
```bash
git clone https://github.com/youruser/ghcp-usage
cd ghcp-usage
python3 cli.py dashboard
```

This will:
1. Scan your local Copilot logs
2. Build a SQLite database
3. Open your browser to `http://localhost:8080`

## Key Features

- **Log Scanner** — Parses VS Code GitHub Copilot extension logs from the local filesystem
- **CLI Commands** — `scan`, `today`, `stats`, `dashboard` for terminal and browser access
- **Web Dashboard** — Interactive charts (Chart.js), model filters, date range selectors, sortable tables
- **Cost Estimates** — Maps token usage to API pricing (GPT-4o, Claude Sonnet 4, Gemini, o3-mini, etc.)
- **CSV Export** — Export session and project data for reporting
- **Privacy-First** — All data stays local. Zero telemetry. Zero cloud sync.

## Prerequisites

- **Python 3.8+** (no pip packages required)
- **VS Code** with GitHub Copilot extension installed and used
- A web browser (Chrome, Firefox, Safari, Edge)

## Installation

```bash
git clone https://github.com/youruser/ghcp-usage
cd ghcp-usage
```

That's it. No build step, no dependencies.

## Basic Usage / Quick Example

```bash
# Scan Copilot log files and populate the database
python cli.py scan

# Show today's usage summary by model (in terminal)
python cli.py today

# Show all-time statistics (in terminal)
python cli.py stats

# Scan + open browser dashboard at http://localhost:8080
python cli.py dashboard

# Custom host and port
$env:HOST = "0.0.0.0"; $env:PORT = "9000"; python cli.py dashboard  # Windows PowerShell
HOST=0.0.0.0 PORT=9000 python3 cli.py dashboard                     # macOS/Linux

# Scan a custom log directory
python cli.py scan --logs-dir /path/to/logs
```

The scanner is incremental — it tracks each file's path and modification time, so re-running `scan` is fast and only processes new or changed files.

## Project Structure

```
ghcp-usage/
├── cli.py              # CLI entry point: scan, today, stats, dashboard
├── scanner.py          # Parses Copilot logs, writes to SQLite database
├── dashboard.py        # HTTP server + single-page HTML/JS dashboard
├── tests/              # Test suite (pytest)
│   ├── test_scanner.py
│   ├── test_cli.py
│   └── test_dashboard.py
├── docs/               # Screenshots and documentation assets
├── .github/
│   └── workflows/
│       └── ci.yml      # GitHub Actions CI pipeline
├── README.md           # This file
├── LICENSE             # MIT License
├── ProductOverview.md  # Product requirements documentation
├── Personas.md         # User personas
├── Domain.md           # Domain knowledge & glossary
├── Features.md         # Feature specifications
├── UseCases.md         # Use case documentation
├── Architecture.md     # System architecture
├── TechStack.md        # Technology stack details
├── DataModel.md        # Database schema & data models
├── API.md              # API documentation
├── SecurityReq.md      # Security requirements
├── PerfReq.md          # Performance requirements
├── QualityStd.md       # Quality standards
└── AcceptanceCriteria.md # Acceptance criteria (Gherkin)
```

## Documentation

| Document | Description |
|----------|-------------|
| [ProductOverview.md](ProductOverview.md) | Product vision, value props, roadmap |
| [Personas.md](Personas.md) | User personas and roles |
| [Domain.md](Domain.md) | Domain glossary and business context |
| [Features.md](Features.md) | Feature specifications |
| [UseCases.md](UseCases.md) | Use cases with step-by-step workflows |
| [Architecture.md](Architecture.md) | System architecture and data flow |
| [TechStack.md](TechStack.md) | Technology stack and rationale |
| [DataModel.md](DataModel.md) | SQLite schema and query patterns |
| [API.md](API.md) | Dashboard API and GitHub API integration |
| [SecurityReq.md](SecurityReq.md) | Security requirements and threat model |
| [PerfReq.md](PerfReq.md) | Performance targets and benchmarks |
| [QualityStd.md](QualityStd.md) | Quality standards and NFRs |
| [AcceptanceCriteria.md](AcceptanceCriteria.md) | Gherkin acceptance criteria |

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Make changes (ensure tests pass: `pytest tests/`)
4. Commit with conventional commits (`feat:`, `fix:`, `docs:`)
5. Open a pull request

**Key rules:**
- Zero runtime dependencies (Python stdlib only)
- All SQL queries must use parameterized placeholders
- All dynamic HTML content must use the `esc()` function
- Tests must pass on Windows, macOS, and Linux

## Support & Feedback

- **Issues**: Open a GitHub issue for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions and ideas

## License

MIT License — see [LICENSE](LICENSE)

## Team / Contact Information

Created as an open-source project inspired by [phuryn/claude-usage](https://github.com/phuryn/claude-usage).