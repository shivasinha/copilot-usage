# Product Overview

## Executive Summary

GHCP Usage Dashboard is a local, privacy-first tool that tracks and visualizes VS Code GitHub Copilot usage — completions, chat sessions, agent-mode interactions, model breakdowns, and estimated costs. Inspired by [phuryn/claude-usage](https://github.com/phuryn/claude-usage), it fills the visibility gap that GitHub's native Copilot reporting does not cover for individual developers.

GitHub Copilot writes telemetry and log data locally during operation. This tool scans those local artifacts (extension logs, telemetry cache, and optionally the GitHub Copilot Usage API for org-level data), stores them in a SQLite database, and serves an interactive browser dashboard on `localhost`.

## Product Name & Version

- **Product Name**: GHCP Usage Dashboard (`ghcp-usage`)
- **Version**: 0.1.0 (MVP)
- **License**: MIT

## Product Vision & Mission

- **Vision**: Every developer using GitHub Copilot should have full visibility into their AI-assisted coding patterns — what models they use, how many completions they accept, how much chat/agent capacity they consume, and what it costs.
- **Mission**: Provide a zero-dependency, local-only Python tool that turns raw Copilot telemetry into actionable charts and cost estimates, with the same simplicity as `python cli.py dashboard`.

## Target Market & User Base

| Segment | Description |
|---------|-------------|
| Individual developers | Developers on Copilot Individual, Business, or Enterprise plans who want to understand their personal usage patterns |
| Team leads / Engineering managers | Need aggregated usage data across team members (via GitHub API integration) |
| Enterprise admins | Track adoption metrics and cost attribution across an organization |
| Cost-conscious developers | Want to understand per-model cost implications of their Copilot usage |

## Key Value Propositions

1. **Visibility GitHub doesn't provide** — GitHub's Copilot dashboard shows org-level seat counts; this shows per-session, per-model, per-project token and completion metrics.
2. **Zero dependencies** — Python 3.8+ standard library only (`sqlite3`, `http.server`, `json`, `pathlib`). No `pip install`.
3. **Privacy-first** — All data stays local. No external telemetry. No cloud sync.
4. **Works on all plans** — Individual, Business, and Enterprise Copilot subscriptions all generate local telemetry data.
5. **Incremental scanning** — Re-runs are fast; only new/changed log files are processed.
6. **Cost estimates** — Maps model usage (GPT-4o, Claude Sonnet, Gemini, o1, etc.) to known API pricing for cost awareness.

## Core Capabilities & Features

- **Log Scanner**: Parses VS Code GitHub Copilot extension logs and telemetry cache files from the local filesystem.
- **SQLite Database**: Stores completions, chat turns, agent interactions, models, tokens, and project context.
- **CLI Commands**: `scan`, `today`, `stats`, `dashboard` — same ergonomics as claude-usage.
- **Web Dashboard**: Single-page HTML/JS app served on localhost with Chart.js charts, model filters, date-range selectors, sortable tables, and CSV export.
- **VS Code Extension**: Optional `.vsix` that wraps the Python CLI — launch and view the dashboard directly inside VS Code without a terminal. Works on Remote SSH.
- **GitHub API Integration** (optional): Pull org-level Copilot usage metrics via `GET /orgs/{org}/copilot/usage` for team/enterprise views.
- **Multi-Model Tracking**: Tracks usage across GPT-4o, GPT-4o-mini, Claude Sonnet 4, Gemini 2.5, o1, o3, and other models Copilot routes to.

## Product Positioning

GHCP Usage Dashboard is the **individual developer's companion** to GitHub's admin-facing Copilot metrics. It occupies the same niche as `phuryn/claude-usage` does for Claude Code — a lightweight, local-first tool that provides the visibility the vendor's UI does not.

## Market Differentiation

| Aspect | GitHub Admin Dashboard | GHCP Usage Dashboard |
|--------|----------------------|---------------------|
| Scope | Org-wide seat & adoption metrics | Per-developer, per-session, per-model granularity |
| Data Source | GitHub server-side telemetry | Local VS Code logs + optional API |
| Privacy | Cloud-hosted | 100% local, no data leaves the machine |
| Cost Estimates | Not provided | Per-model API pricing calculations |
| Dependencies | GitHub Enterprise license | Python 3.8+ (zero pip dependencies) |
| Completions tracking | Acceptance rate (aggregate) | Per-file, per-language, per-session detail |

## Success Metrics / KPIs

| Metric | Target (MVP) |
|--------|-------------|
| Time to first dashboard | < 60 seconds from `git clone` |
| Scan performance | 1000 log files in < 5 seconds |
| Dashboard load time | < 1 second for 30-day view |
| Zero external dependencies | No `pip install` required |
| Platform support | Windows, macOS, Linux |
| Test coverage | > 80% line coverage |

## Product Roadmap (High-Level)

| Phase | Scope |
|-------|-------|
| **v0.1 (MVP)** | CLI scanner + SQLite DB + localhost dashboard. Parse completions and chat sessions from local Copilot logs. |
| **v0.2** | GitHub API integration for org-level metrics. Agent-mode interaction tracking. |
| **v0.3** | VS Code extension wrapper (run dashboard from command palette). Multi-user team view. |
| **v0.4** | Historical trend analysis. Budget alerts. Exportable reports (PDF/CSV). |

## Related Products / Ecosystem

- [phuryn/claude-usage](https://github.com/phuryn/claude-usage) — Inspiration project; equivalent tool for Claude Code
- [GitHub Copilot Metrics API](https://docs.github.com/en/rest/copilot/copilot-usage) — Organization-level usage data via REST API
- [VS Code GitHub Copilot Extension](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) — The extension whose logs we parse
- [copilot-metrics-viewer](https://github.com/github-copilot-resources/copilot-metrics-viewer) — GitHub's official org-level metrics viewer (React app, requires API token)

## Constraints & Limitations

- **No server-side data**: Only data written locally by the VS Code Copilot extension is captured. Copilot usage from github.com, JetBrains IDEs, or Neovim is not included unless those tools write compatible local logs.
- **Log format instability**: GitHub Copilot's local log format is undocumented and may change without notice between extension versions.
- **Cost estimates are approximations**: Actual costs depend on subscription plan (Individual, Business, Enterprise). Per-token API pricing is used as a proxy.
- **No real-time streaming**: The tool scans logs on demand (or at dashboard refresh), not in real-time.
- **Single-user local tool**: No built-in multi-user auth or remote access (by design — privacy-first).

## Market Context & Industry Standards

- AI coding assistants are rapidly growing: GitHub reports 77,000+ organizations using Copilot as of 2025.
- Cost visibility is a top concern for engineering leaders adopting AI tools.
- The "local dashboard for AI tool usage" pattern established by claude-usage (1.2k+ GitHub stars) validates strong developer demand.
- GDPR and corporate data policies favor local-only tools that don't transmit usage data externally.