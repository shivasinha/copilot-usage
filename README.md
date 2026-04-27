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

The scanner runs automatically on startup and re-runs every 30 seconds (configurable). Re-runs are incremental - only new or changed files are processed.

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
- **Settings panel** (âš™ gear icon) - configure refresh interval, quota limit, data source, price overrides

---

## Settings

Click the **âš™** button in the top-right of the dashboard. Settings are saved to `~/.ghcp-usage/settings.json`.

| Setting | Default | Description |
|---------|---------|-------------|
| Data Refresh Interval | 30s | UI auto-refresh + background scan frequency |
| Monthly Premium Request Limit | 100 | Quota bar percentage base |
| Price Overrides | - | Per-model price overrides in JSON (`{"claude-opus": [15.0, 75.0]}`) |

---

## Project Structure

```
ghcp-usage/
â”œâ”€â”€ src/
â”‚   â”œâ”€â”€ cli.py              # Entry point - scan, today, stats, dashboard commands
â”‚   â”œâ”€â”€ scanner.py          # VS Code JSONL log discovery and parsing
â”‚   â”œâ”€â”€ dashboard.py        # HTTP server + embedded single-page dashboard
â”‚   â”œâ”€â”€ db.py               # SQLite schema and connection management
â”‚   â”œâ”€â”€ pricing.py          # Per-model API cost estimates
â”‚   â”œâ”€â”€ quota.py            # Monthly premium request quota tracking
â”‚   â””â”€â”€ settings.py         # Persistent user settings (~/.ghcp-usage/settings.json)
â”œâ”€â”€ vscode-extension/
â”‚   â”œâ”€â”€ src/extension.ts    # VS Code extension - spawns Python dashboard, opens WebView
â”‚   â”œâ”€â”€ package.json        # Extension manifest (commands, settings, icon)
â”‚   â””â”€â”€ icon.png            # Extension icon
â”œâ”€â”€ assets/                 # SVG/PNG source assets
â”œâ”€â”€ docs/                   # Product requirements and architecture docs
â”œâ”€â”€ .github/                # Copilot agents and instructions
â””â”€â”€ Readme.md
```

Database: `~/.ghcp-usage/usage.db` (auto-created on first scan).

---

## Data Sources

The dashboard can read usage data from two sources, configurable in the **Settings** panel under **Data Source**:

| Source | When to use |
|--------|-------------|
| **JSONL logs** (default) | VS Code writes structured log files for every chat session. This works everywhere — local and Remote SSH — and covers all historical data. No extra setup. |
| **Proxy** (optional) | A local mitmproxy intercept that captures Copilot API calls in real time, before VS Code flushes logs. Useful if logs are delayed or unavailable. Requires mitmproxy installed and the proxy script running separately. **Local VS Code only** — does not work over Remote SSH. |
| **Both** | Combines both sources. Deduplication ensures no double-counting. |

For most users, **JSONL logs** is all you need. The proxy mode is an advanced option for users who need real-time capture or whose log files are missing.

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
code --install-extension ghcp-usage-dashboard-0.1.0.vsix --force
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

