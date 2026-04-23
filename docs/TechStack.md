# Technology Stack

## Overview & Rationale

GHCP Usage Dashboard is designed for **zero-install simplicity**. The entire tool runs on Python 3.8+ standard library with no third-party packages. The web dashboard uses Chart.js loaded from a CDN. This mirrors the proven approach of [claude-usage](https://github.com/phuryn/claude-usage).

**Guiding principle**: If it requires `pip install`, it's not in the MVP.

## Frontend / UI Layer

### Framework(s)
- **None** — Plain HTML5 + vanilla JavaScript embedded as a Python string in `dashboard.py`
- No React, Vue, or Svelte. No bundler. No build step.

### Libraries & Dependencies
| Library | Version | Source | Purpose |
|---------|---------|--------|---------|
| Chart.js | 4.4.0 | CDN (`cdn.jsdelivr.net`) | Interactive charts (bar, doughnut, line) |

### Version Constraints
- Chart.js 4.x (UMD build, loaded via `<script>` tag)
- ES6+ JavaScript (all modern browsers)

### Development Tools
- Browser DevTools for dashboard debugging
- No linting/formatting toolchain for frontend (embedded in Python string)

## Backend / Application Layer

### Primary Language(s)
- **Python 3.8+** — minimum version to ensure broad compatibility
- Target: Python 3.10–3.12 for development and testing

### Frameworks & Libraries
| Module | Source | Purpose |
|--------|--------|---------|
| `sqlite3` | stdlib | Database access |
| `http.server` | stdlib | HTTP server for dashboard |
| `json` | stdlib | JSON parsing (JSONL logs, API responses) |
| `pathlib` | stdlib | Cross-platform file path handling |
| `glob` | stdlib | Recursive file discovery |
| `datetime` | stdlib | Timestamp parsing and formatting |
| `os` / `sys` | stdlib | Environment variables, platform detection |
| `webbrowser` | stdlib | Auto-open browser on dashboard launch |
| `threading` | stdlib | Background browser launch thread |
| `urllib.request` | stdlib | GitHub API HTTP calls (v0.2, replaces `requests`) |
| `collections` | stdlib | `defaultdict` for aggregation |

### Runtime Environment
- CPython 3.8+ (standard Python distribution)
- No virtual environment required
- No `pyproject.toml`, `setup.py`, or `requirements.txt`

### Message Queue / Event System
- Not applicable — single-process, synchronous architecture

## Data Layer

### Database(s)
| Database | Type | Purpose |
|----------|------|---------|
| SQLite 3 | Embedded relational | All usage data storage |

- **Location**: `~/.ghcp-usage/usage.db` (configurable via `DB_PATH`)
- **Access**: Python `sqlite3` module (built-in)
- **Concurrency**: Single-writer (WAL mode for read concurrency if needed)
- **Size**: Typically < 50MB for individual use; < 500MB for large orgs

### Cache System(s)
- **Browser cache**: Chart.js CDN file cached by browser
- **processed_files table**: Serves as a scan cache (skip unchanged files)
- No Redis, Memcached, or in-memory cache

### Data Migration Tools
- **Schema auto-migration**: `init_db()` uses `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ADD COLUMN` with `try/except` for forward-compatible upgrades
- No Alembic, no Flyway, no migration files

## Infrastructure & DevOps

### Cloud Platform(s)
- **None** — purely local tool. No cloud infrastructure.

### Container Technology
- **None** — no Docker, no containers. Clone and run.
- Optional: Dockerfile may be provided for convenience (not required)

### Orchestration
- Not applicable

### CI/CD Pipeline
- **GitHub Actions** for automated testing:
  - Python test suite (`pytest`)
  - Multi-platform matrix: Ubuntu, macOS, Windows
  - Python version matrix: 3.8, 3.10, 3.12
- No deployment pipeline (local tool, distributed as source code)

### Monitoring & Logging
- **Scanner output**: `print()` statements for scan progress and summary
- **HTTP server**: `log_message()` override (suppressed for clean dashboard operation)
- No structured logging, no APM, no error tracking (local tool)

## Testing & Quality Tools

### Unit Testing Framework(s)
- **pytest** (dev dependency only — not required for users)
- Tests in `tests/` directory

### Integration Testing Tools
- End-to-end tests: Create temp JSONL files → scan → query DB → verify dashboard API
- Python `unittest.mock` for filesystem/API mocking

### Load Testing Tools
- Not applicable (single-user local tool)

### Code Quality Tools
- **Ruff** or **flake8** for linting (dev only)
- **black** or **ruff format** for code formatting (dev only)
- No runtime dependency on any of these

## Third-Party Services & APIs

### Authentication & Authorization
- **GitHub PAT** (Personal Access Token): Used for optional GitHub API integration
  - Scope: `copilot` (read organization Copilot usage)
  - Storage: Environment variable `GITHUB_TOKEN`
  - Never written to disk or logs

### Analytics
- **None** — no telemetry, no analytics, no tracking

### External Integrations
| Integration | Protocol | Auth | Status |
|-------------|----------|------|--------|
| GitHub Copilot Usage API | HTTPS REST | PAT | Planned (v0.2) |
| Chart.js CDN | HTTPS | None | Stable |

### Vendor Dependencies
- **jsdelivr.net CDN**: Chart.js hosting. Fallback: bundle Chart.js locally.
- **GitHub API**: Optional. Tool works fully without it.

## Development Environment

### IDEs / Editors
- VS Code (primary — dogfooding the tool we're building for)
- Any editor works (Python, no build tools)

### Version Control
- **Git** + **GitHub** (source hosting)
- Conventional commits (`feat:`, `fix:`, `docs:`, `ci:`)

### Build Tools
- **None** — no build step. Python source files are the final product.

### Local Development Setup
```bash
git clone <repo-url>
cd ghcp-usage
# Run the tool
python cli.py scan
python cli.py dashboard

# Run tests (dev only)
pip install pytest
pytest tests/
```

## Version Matrix

### Recommended Versions
| Component | Minimum | Recommended | Maximum Tested |
|-----------|---------|-------------|---------------|
| Python | 3.8 | 3.12 | 3.13 |
| SQLite | 3.24 (WITH clause) | 3.35+ | Latest |
| Chart.js | 4.0 | 4.4.0 | 4.x |
| Browser | Chrome 90+ / Firefox 90+ / Safari 15+ / Edge 90+ | Latest | Latest |

### Known Compatibility Issues
- Python 3.7: Missing `pathlib` features used in the scanner
- SQLite < 3.24: Missing `UPSERT` support (workaround: INSERT OR REPLACE)
- IE11: Not supported (ES6+ JavaScript required)

### Deprecation Timeline
- Python 3.8 support will be dropped when Python 3.8 reaches end-of-life (October 2024 — already EOL, but kept for compatibility)
- Chart.js 3.x is not supported (4.x API differences)

## Technology Decisions & Rationale
### Why [Technology X]?
### Alternatives Considered
### Future Technology Considerations