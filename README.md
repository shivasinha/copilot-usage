# GHCP Usage Dashboard

A local, privacy-first dashboard for tracking your **VS Code GitHub Copilot** usage i.e., chat sessions, token counts, model breakdowns, premium request quota, and estimated costs.

No `pip install`. No cloud sync. No telemetry. Everything stays on your machine.

```bash
git clone <repo-url>
cd ghcp-usage
python src/cli.py dashboard
```

Opens your browser at `http://localhost:8080`.

---

## How It Works

The scanner reads VS Code's local Copilot log files (`workspaceStorage/<id>/chatSessions/*.jsonl`), parses each chat turn, and stores results in a local SQLite database. The dashboard is served on `localhost` and reads from that database.

The scanner runs automatically on startup and re-scans every 30 seconds (configurable). It also uses a **file-system watcher** to detect new JSONL entries within 1–3 seconds of each Copilot response. Re-runs are incremental — only new or changed files are processed.

---

## Requirements

- **Python 3.8+** - no pip packages required
- **VS Code** with GitHub Copilot extension installed and active
- A web browser

---

## CLI Commands

```bash
python src/cli.py dashboard        # Scan logs + open browser dashboard
python src/cli.py scan             # Incremental log scan only
python src/cli.py today            # Today's usage by model (terminal)
python src/cli.py stats            # All-time aggregates by model (terminal)

python src/cli.py scan --reset     # Delete DB and re-scan from scratch
python src/cli.py scan --logs-dir /path/to/logs   # Custom log directory
```

---

## Dashboard Features

- **Stat cards** - sessions, turns, premium requests, input/output tokens, estimated cost
- **Date range / Monthly toggle** - 7d / 30d / 90d / All Time or month-by-month navigation
- **Model filter** - multi-select checkboxes
- **Daily turns chart** - stacked bar by model (local timezone)
- **Cost by model table** - turns, tokens, estimated API cost
- **Recent sessions table** - sortable, shows project, model, last active time (local timezone)
- **CSV export** - filtered session and aggregate data
- **Settings panel** (⚙ gear icon) - configure refresh interval, quota limit, data source, price overrides

---

## Settings

Click the **⚙** button in the top-right of the dashboard. Settings are saved to `~/.ghcp-usage/settings.json`.

| Setting | Default | Description |
|---------|---------|-------------|
| Data Refresh Interval | 30s | UI auto-refresh + background scan frequency |
| Monthly Premium Request Limit | 300 | Quota bar percentage base |
| Price Overrides | - | Per-model price overrides in JSON (`{"claude-opus": [15.0, 75.0]}`) |

---

## Project Structure

```
ghcp-usage/
├── src/
│   ├── cli.py              # Entry point - scan, today, stats, dashboard commands
│   ├── scanner.py          # VS Code JSONL log discovery and parsing
│   ├── dashboard.py        # HTTP server + embedded single-page dashboard
│   ├── db.py               # SQLite schema and connection management
│   ├── pricing.py          # Per-model API cost estimates
│   ├── quota.py            # Monthly premium request quota tracking
│   ├── settings.py         # Persistent user settings (~/.ghcp-usage/settings.json)
│   └── watcher.py          # File-system watcher for near-real-time log detection
├── vscode-extension/
│   ├── src/extension.ts    # VS Code extension - spawns Python dashboard, opens WebView
│   ├── package.json        # Extension manifest (commands, settings, icon)
│   └── icon.png            # Extension icon
├── assets/                 # SVG/PNG source assets
├── docs/                   # Product requirements and architecture docs
├── .github/                # Copilot agents and instructions
└── Readme.md
```

Database: `~/.ghcp-usage/usage.db` (auto-created on first scan).

---

## Data Refresh

The scanner runs automatically on startup and re-scans every 30 seconds (configurable in Settings). It also uses a **file-system watcher** to detect new JSONL log entries within 1–3 seconds of each Copilot response — so the dashboard stays current without waiting for the full interval.

The **Data Source** setting in the Settings panel controls which sessions are shown:

| Value | Shows |
|-------|-------|
| **All sessions** (default) | Everything in the database |
| **JSONL logs only** | Excludes any sessions captured by external tools |

---

## Timezone

All timestamps are displayed in **your local timezone** (auto-detected by the browser). Daily chart grouping uses local day boundaries.

---

## Privacy

All data stays local. The tool reads VS Code Copilot log files and writes to a local SQLite file. No data is sent anywhere.

---

## VS Code Extension

A `.vsix` extension is available for running the dashboard directly inside VS Code - no terminal needed.

**Install:**
```powershell
code --install-extension ghcp-usage-dashboard-0.2.0.vsix --force
```

**Commands** (Command Palette `Ctrl+Shift+P`):
- `GHCP: Open Usage Dashboard` - starts Python dashboard and opens it in a WebView panel
- `GHCP: Stop Dashboard` - stops the Python process

**Extension Settings:**

| Setting | Default | Description |
|---------|---------|-------------|
| `ghcpUsage.pythonPath` | `` | Path to Python 3.8+ executable. Leave empty to use system PATH |
| `ghcpUsage.port` | `8080` | Dashboard HTTP server port |
| `ghcpUsage.autoOpen` | `false` | Auto-open dashboard when VS Code starts |

> The extension bundles all Python source files - no separate `git clone` is needed.
> Works on Remote SSH connections (`extensionKind: ui` forces local execution).

---

## Building the Extension (developers)

```powershell
cd vscode-extension
npm install --registry https://registry.npmjs.org
.\node_modules\.bin\vsce package --allow-missing-repository --skip-license
```

Produces `ghcp-usage-dashboard-<version>.vsix`.

---

## Contributing

See `docs/Architecture.md` for system design and `docs/TechStack.md` for constraints (Python stdlib only - no new pip dependencies).

