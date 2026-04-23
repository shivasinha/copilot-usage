# GHCP Usage Dashboard

## Overview

A local dashboard for tracking your VS Code GitHub Copilot usage — completions, chat sessions, agent interactions, token counts, model breakdowns, and estimated costs. Inspired by [claude-usage](https://github.com/phuryn/claude-usage). Works on Copilot Individual, Business, and Enterprise plans.

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