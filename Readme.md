# GHCP Usage Dashboard

A local, privacy-first dashboard for tracking your **VS Code GitHub Copilot** usage — chat sessions, token counts, model breakdowns, premium request quota, and estimated costs.

No `pip install`. No cloud sync. No telemetry. Everything stays on your machine.

```bash
git clone <repo-url>
cd ghcp-usage
python src/cli.py dashboard
```

Opens your browser at `http://localhost:8080`.

---

## How It Works

Data is captured from **two complementary sources**, automatically combined with no double-counting:

| Source | What it captures | Best for |
|--------|-----------------|----------|
| **JSONL scanner** | Reads VS Code's local log files — all sessions including SSH remote, accurate token counts, project names | Default; works everywhere |
| **mitmproxy** (optional) | Intercepts live HTTPS API calls — real-time, no log files needed | Local VS Code only; requires extra setup |

The scanner runs on startup and every 30 seconds (configurable). The two sources share the same DB and are deduplicated by request ID.

---

## Requirements

- **Python 3.8+** — no pip packages required
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

- **Stat cards** — sessions, turns, premium requests, input/output tokens, estimated cost
- **Date range / Monthly toggle** — 7d / 30d / 90d / All Time or month-by-month navigation
- **Model filter** — multi-select checkboxes
- **Daily turns chart** — stacked bar by model (IST timezone)
- **Cost by model table** — turns, tokens, estimated API cost
- **Recent sessions table** — sortable, shows project, model, last active time (IST)
- **CSV export** — filtered session and aggregate data
- **Settings panel** (⚙ gear icon) — configure refresh interval, quota limit, data source, price overrides

---

## Settings

Click the **⚙** button in the top-right of the dashboard. Settings are saved to `~/.ghcp-usage/settings.json`.

| Setting | Default | Description |
|---------|---------|-------------|
| Data Refresh Interval | 30s | UI auto-refresh + JSONL background scan frequency |
| Monthly Premium Request Limit | 100 | Quota bar percentage base |
| Data Source | Both | `Both` / `Proxy only` / `JSONL only` |
| Price Overrides | — | Per-model price overrides in JSON (`{"claude-opus": [15.0, 75.0]}`) |

---

## Project Structure

```
ghcp-usage/
├── src/
│   ├── cli.py          # Entry point — scan, today, stats, dashboard commands
│   ├── scanner.py      # VS Code JSONL log discovery and parsing
│   ├── dashboard.py    # HTTP server + embedded single-page dashboard
│   ├── db.py           # SQLite schema and connection management
│   ├── pricing.py      # Per-model API cost estimates
│   ├── quota.py        # Monthly premium request quota tracking
│   └── settings.py     # Persistent user settings (~/.ghcp-usage/settings.json)
├── docs/               # Product requirements and architecture docs
├── .github/            # Copilot agents and instructions
└── Readme.md
```

Database: `~/.ghcp-usage/usage.db` (auto-created on first scan).

---

## Timezone

All timestamps are displayed in **IST (UTC+5:30)**. Daily chart grouping also uses IST day boundaries.

---

## Privacy

All data stays local. The tool reads VS Code Copilot log files and writes to a local SQLite file. No data is sent anywhere.


---

## CLI Commands

```bash
python src/cli.py scan             # Scan Copilot logs (incremental by default)
python src/cli.py today            # Today's usage by model in terminal
python src/cli.py stats            # All-time aggregates by model in terminal
python src/cli.py dashboard        # Scan + open browser dashboard at http://localhost:8080

python src/cli.py scan --reset     # Delete DB and re-scan from scratch (asks for confirmation)
python src/cli.py scan --logs-dir /path/to/logs   # Custom log directory
```

## Requirements

- **Python 3.8+** — no pip packages required
- **VS Code** with GitHub Copilot extension installed and active
- A web browser (Chrome, Firefox, Safari, Edge)

## Dashboard Features

- **Stat cards** — sessions, turns, premium requests, context resets, input/output tokens, estimated cost
- **View toggle** — switch between *Date Range* and *Monthly* views; all charts, tables, and cards update together
- **Range filter** — 7d / 30d / 90d / All Time (date-range mode)
- **Month navigation** — browse month by month with ← → arrows (monthly mode)
- **Model filter** — multi-select checkboxes; All / None shortcuts
- **Daily turns chart** — stacked bar by model
- **By-model and by-project doughnut charts**
- **Cost by model table** — turns, tokens, estimated API cost per model
- **Recent sessions table** — sortable by date, model, turns, cost

## Data Source

The scanner reads VS Code's `workspaceStorage/<id>/chatSessions/*.jsonl` files.
It supports both the legacy format (VS Code < ~1.100) and the new incremental-patch format (VS Code ≥ ~1.100, used by agent-mode sessions).
Real API token counts (`promptTokens` / `completionTokens`) are used whenever present; character-based estimates are the fallback.

## Project Structure

| File | Purpose |
|------|---------|
| `src/cli.py`        | Entry point — `scan`, `today`, `stats`, `dashboard` commands |
| `src/scanner.py`    | Log discovery, JSONL parsing, incremental scan |
| `src/dashboard.py`  | HTTP server + embedded single-page dashboard |
| `src/db.py`         | SQLite schema, connection management |
| `src/pricing.py`    | Per-model API cost estimates |

Database: `~/.ghcp-usage/usage.db` (auto-created on first scan).

## Privacy

All data stays local. The tool reads VS Code Copilot log files and writes to a local SQLite file. No data is sent to GitHub, OpenAI, Anthropic, or any external service.

---

## Requirements Engineering Workspace

This repository also contains the full product requirements documentation used to specify and implement the tool:

## Purpose

This repository serves as a **GitHub Copilot (GHCP) workspace for requirement engineering**. The markdown files provide structured context that enables Copilot and custom agents to generate high-quality user stories, acceptance criteria, and implementation artifacts.

## Scope of Files

| File | Purpose |
|------|---------|
| [docs/ProductOverview.md](docs/ProductOverview.md) | Executive summary, vision, value props, roadmap, constraints |
| [docs/Personas.md](docs/Personas.md) | User personas (Developer, Team Lead, Cost-Conscious, Admin) |
| [docs/Domain.md](docs/Domain.md) | Domain knowledge, glossary, business context, compliance |
| [docs/Features.md](docs/Features.md) | Feature specs (Scanner, DB, CLI, Dashboard, Cost Estimation) |
| [docs/UseCases.md](docs/UseCases.md) | Use cases with actors, scenarios, exceptions (UC-01 to UC-10) |
| [docs/Architecture.md](docs/Architecture.md) | System architecture, component model, data flow, ADRs |
| [docs/TechStack.md](docs/TechStack.md) | Technology stack (Python stdlib, SQLite, Chart.js CDN) |
| [docs/DataModel.md](docs/DataModel.md) | SQLite schema, ERD, query patterns, migration strategy |
| [docs/API.md](docs/API.md) | Dashboard API endpoints, GitHub API integration plan |
| [docs/SecurityReq.md](docs/SecurityReq.md) | Threat model, OWASP mapping, input validation, XSS prevention |
| [docs/PerfReq.md](docs/PerfReq.md) | Performance targets, benchmarks, resource limits |
| [docs/QualityStd.md](docs/QualityStd.md) | Quality standards, reliability, usability, maintainability |
| [docs/AcceptanceCriteria.md](docs/AcceptanceCriteria.md) | Gherkin acceptance criteria for all features |
| [docs/QuickStart.md](docs/QuickStart.md) | README-style quick start, usage, project structure |
| [docs/ReqTemplate.md](docs/ReqTemplate.md) | Requirements template and guidelines |

## Custom Agents

The `CustomAgent/` directory contains scoped RE agents:

| Agent | Purpose |
|-------|---------|
| `RE-PLM-Problem.agent.md` | Generate problem statements |
| `RE-user-journey-map.agent.md` | Create user journey maps and task cases |
| `RE-user-story-creation.agent.md` | Write user stories with acceptance criteria |
| `copilot-instructions.md` | Shared engineering principles and persona definition |

## How to Use This Workspace

### For requirement engineering with Copilot
1. Open this workspace in VS Code with GitHub Copilot enabled
2. Use the custom agents (invoke via `@workspace` or agent mentions) to generate:
   - Problem statements from `ProductOverview.md` and `Personas.md`
   - User journey maps from `UseCases.md` and `Personas.md`
   - User stories from `Features.md` and `AcceptanceCriteria.md`

### For implementation
1. Start with `QuickStart.md` for the developer-facing README
2. Reference `Architecture.md` and `DataModel.md` for implementation design
3. Use `AcceptanceCriteria.md` to drive test development
4. Follow `TechStack.md` constraints (zero dependencies, Python stdlib only)


Upload all relevant product documents, for example:

- Installation manuals
- Operation manuals
- Maintenance manuals
- Architecture documentation
- Frequently Asked Questions (FAQ)
- Existing test case dump (`.csv`, `.docx`, `.pdf`, etc.)

### 4. Fill One Template per Chat

1. Open the bot and start a new chat.
2. Upload one template markdown file (example: `QuickStart.md`).
3. Use a prompt like:

```text
Read all chapters from QuickStart.md.
Based on the uploaded product knowledge, fill each section with clear and complete content.
Keep the original heading structure.
Return the result in markdown and provide a downloadable link.
```

4. Review and download the generated file.
5. Replace/update the local workspace file with the generated content.

### 5. Start a New Chat for Every Remaining File

Always create a **new chat** before processing the next markdown file. This helps maintain context balance and reduces cross-file contamination.

Recommended order:

1. `ProductOverview.md`
2. `Personas.md`
3. `Domain.md`
4. `Features.md`
5. `UseCases.md`
6. `Architecture.md`
7. `TechStack.md`
8. `DataModel.md`
9. `API.md`
10. `SecurityReq.md`
11. `PerfReq.md`
12. `QualityStd.md`
13. `AcceptanceCriteria.md`
14. `QuickStart.md`

---

## Approach 2: Generate Product-Specific Copilot Instructions

Once all context files are filled, you can generate a tailored `copilot-instructions.md` for your product directly inside GitHub Copilot Chat. This file becomes the authoritative reference for all RE agents and Copilot interactions in your workspace.

### How it works

Open GitHub Copilot Chat (Ctrl+Alt+I) and use a prompt like:

```text
@workspace Read all context files in this workspace:
ProductOverview.md, Personas.md, Domain.md, Features.md,
UseCases.md, Architecture.md, TechStack.md, DataModel.md,
API.md, SecurityReq.md, PerfReq.md, QualityStd.md,
AcceptanceCriteria.md, and ReqTemplate.md.

Using copilot-instructions.md as the template and structure
reference, generate a new, product-specific version of
copilot-instructions.md that:
  1. Replaces all generic placeholders with real product facts.
  2. Defines the correct agent personas and engineering principles
     for this product.
  3. Preserves every chapter and heading from the original.

Return the full markdown content ready to paste into copilot-instructions.md.
```

> **Tip:** After pasting the generated content, review Chapter 1 (Engineering Principles) and Chapter 2 (Agent Persona) to ensure they accurately reflect your product's domain and constraints.

---

## Approach 3: Use Custom RE Agents

The `Agents-Instructions/` folder contains three scoped agents that implement the full RE lifecycle — Problem → Journey → Stories. Each agent is designed to be invoked in order, and each one stops and waits for human review before the next is triggered.

### Agent Overview

| Agent file | Agent name | Purpose |
|---|---|---|
| `RE-PLM-Problem.agent.md` | `RE-PLM-Problem` | Refines a raw idea into a two-line Problem + Benefit statement |
| `RE-user-journey-map.agent.md` | `RE-user-journey-map` | Builds a full User Journey Map from an accepted problem statement |
| `RE-user-story-creation.agent.md` | `RE-user-story-creation` | Generates INVEST-aligned user stories, Gherkin AC, NFRs, and traceability matrix |

---

### Agent 1 — RE-PLM-Problem

**Goal:** Turn a raw, loosely described requirement into a crisp, two-line problem statement.

**Example prompt:**

```text
@RE-PLM-Problem
Users complain that they can't see the maintenance history of a device
from the mobile app. They have to log in to the desktop portal, navigate
to the asset page, and manually export a CSV to check past work orders.
```

**Expected output (exactly two lines):**

```
Problem: In <Product>, field technicians cannot access device maintenance
history from the mobile app due to missing API integration, resulting in
delayed maintenance decisions and repeated desktop logins.

Benefit: Field technicians can check the full maintenance history on-site
from their mobile device, reducing diagnosis time and avoiding unnecessary
escalations.
```

> Review and iterate on these two lines before proceeding to the next agent.

---

### Agent 2 — RE-user-journey-map

**Goal:** Build a detailed User Journey Map and supporting requirement artifacts from an accepted problem statement stored in a `Features/REQ-YYYY-NNN_*.md` file.

**Example prompt:**

```text
@RE-user-journey-map REQ-2026-001
```

The agent will:
1. Validate the requirement number against the `Features/` folder.
2. Read the Problem Statement from the matching file.
3. Produce a full journey map (stages, steps, emotions, FRs, NFRs, and acceptance criteria) written back into the same file.

> Do not provide the full path — only the requirement number (e.g., `REQ-2026-001`). The agent resolves the file automatically.

---

### Agent 3 — RE-user-story-creation

**Goal:** Convert the completed User Journey Map into INVEST-aligned user stories with Gherkin acceptance criteria, NFRs, a traceability matrix, and open questions.

**Example prompt:**

```text
@RE-user-story-creation REQ-2026-001
```

The agent will:
1. Read the User Journey Map from the `Features/REQ-2026-001_*.md` file.
2. Generate user stories for each journey stage.
3. Write acceptance criteria in Given/When/Then format.
4. Append NFRs, a traceability matrix, and open questions into sections 6–8 of the same file.

> Invoke this agent only **after** `RE-user-journey-map` has completed sections 2–5 of the requirement file.

---

### Recommended Workflow

```
Raw idea / feature request
        │
        ▼
  @RE-PLM-Problem          ← refine until problem is accepted
        │
        ▼
  @RE-user-journey-map     ← review journey map before continuing
        │
        ▼
  @RE-user-story-creation  ← final review & sign-off
```
15. `ReqTemplate.md`

## Quality Checklist (Before Finalizing Each File)

- All template headings are present.
- Content is product-specific (not generic filler text).
- Requirements are testable and unambiguous.
- Terms are consistent across files.
- Assumptions and constraints are explicitly stated.
- Output is markdown-clean and readable.

## Suggested Prompt Template

Use this reusable prompt for each file:

```text
You are helping with requirement engineering for Product XXX.
Use all uploaded documentation as source knowledge.
Now fill the attached <FILE_NAME>.md completely.
Rules:
1) Keep all existing headings and order.
2) Write concise, clear, implementation-ready content.
3) Add assumptions where data is missing, and label them clearly.
4) Avoid contradictions with architecture and domain definitions.
5) Return valid markdown and provide a downloadable link.
```

## Review Notes

This process is intended to produce consistent, high-quality markdown artifacts that can be directly used in a GHCP workspace for requirement engineering workflows.
