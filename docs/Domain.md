# Domain Knowledge & Business Context

## Part 1: Business Context & Strategy

### Industry & Market
AI-assisted coding tools are the fastest-growing segment in developer tooling. GitHub Copilot leads the market with 1.8M+ paid subscribers and 77,000+ organizations as of 2025. Competitors include Cursor, Claude Code, Amazon CodeWhisperer, and Tabnine. Developer demand for **usage visibility** is rising as organizations scale AI tool adoption and need to justify ROI.

### Business Goals & Objectives
1. Provide individual developers with granular Copilot usage data that GitHub's native dashboard does not offer.
2. Enable team leads to track adoption and cost at the project/model level.
3. Maintain zero-dependency, local-first architecture for maximum accessibility and trust.
4. Establish the same developer experience pattern proven by `phuryn/claude-usage` (1.2k+ stars).

### Stakeholders & Roles
| Stakeholder | Role | Interest |
|-------------|------|----------|
| Individual Developer | Primary user | Personal usage visibility |
| Team Lead / Manager | Secondary user | Team adoption & cost reporting |
| Enterprise Admin | Tertiary user | Org-wide metrics & compliance |
| Open-Source Contributors | Maintainers | Code quality, feature development |

### Success Metrics
- Time from `git clone` to first dashboard: < 60 seconds
- GitHub stars within 6 months: 500+
- Active users (based on GitHub clones): 1,000+
- Zero runtime dependencies beyond Python stdlib

## Part 2: Domain Fundamentals

### What is GitHub Copilot Usage Tracking?
GitHub Copilot is an AI pair programmer integrated into VS Code (and other IDEs). It provides:
- **Inline completions**: Code suggestions as you type
- **Chat**: Conversational AI for code questions, explanations, and refactoring
- **Agent mode**: Autonomous coding with tool use (file edits, terminal commands, web search)

The Copilot extension writes local telemetry and log data during operation. This data includes model identifiers, token counts, completion acceptance/rejection signals, session IDs, and timestamps. GHCP Usage Dashboard reads this local data and transforms it into human-readable analytics.

### Core Concepts

| Concept | Definition |
|---------|-----------|
| **Completion** | An inline code suggestion offered by Copilot. Can be accepted, partially accepted, or dismissed. |
| **Chat Turn** | A single user→assistant exchange in Copilot Chat (panel or inline). |
| **Agent Interaction** | An autonomous action taken by Copilot in agent mode (file edit, terminal command, tool call). |
| **Session** | A continuous period of Copilot activity within a VS Code window, identified by a session ID. |
| **Model** | The AI model backend used (e.g., GPT-4o, Claude Sonnet 4, Gemini 2.5 Pro, o3-mini). |
| **Token** | The unit of text processing. Input tokens = prompt sent to model; output tokens = response generated. |
| **Acceptance Rate** | Percentage of completions the developer accepted out of total shown. |
| **Project** | The workspace/repository context in which Copilot was active. |

### Domain Boundaries
**In scope**:
- VS Code GitHub Copilot extension logs (local filesystem)
- GitHub Copilot Usage REST API (optional, for org metrics)
- SQLite storage and localhost dashboard

**Out of scope**:
- JetBrains / Neovim / Xcode Copilot usage (different log formats)
- GitHub.com Copilot usage (no local logs generated)
- Copilot Workspace (separate product, server-side)
- Real-time streaming telemetry
- Multi-user remote dashboards

### Related Domains
- **Developer Productivity Analytics** (LinearB, Jellyfish, Pluralsight Flow)
- **AI Cost Management** (cloud cost optimization tools)
- **VS Code Extension Ecosystem** (extension telemetry, output channels)
- **GitHub Platform** (REST API, GraphQL API, Copilot admin console)

## Part 3: Terminology & Reference

### Glossary (A-Z)

| Term | Definition |
|------|-----------|
| **Agent Mode** | Copilot's autonomous coding mode where it can edit files, run terminal commands, and use tools without per-step approval |
| **Cache Read Tokens** | Tokens served from the model provider's prompt cache (cheaper than fresh input tokens) |
| **Cache Write Tokens** | Tokens written to the prompt cache for future reuse (premium over standard input) |
| **Completion** | An inline code suggestion from Copilot, triggered by typing context |
| **Copilot Business** | GitHub Copilot plan for organizations ($19/user/month) |
| **Copilot Enterprise** | GitHub Copilot plan for enterprises ($39/user/month, includes knowledge bases) |
| **Copilot Individual** | GitHub Copilot plan for individual developers ($10/month or $100/year) |
| **Extension Logs** | Log files written by the GitHub Copilot VS Code extension to the local filesystem |
| **Ghost Text** | The dimmed inline suggestion text shown by Copilot before acceptance |
| **JSONL** | JSON Lines format — one JSON object per line, used for structured logs |
| **Model Routing** | GitHub's system for selecting which AI model handles a given request |
| **MTok** | Million tokens — standard unit for API pricing |
| **Output Channel** | VS Code's built-in logging mechanism; Copilot writes diagnostics here |
| **Session** | A continuous period of Copilot interaction within a single VS Code window |
| **Telemetry Cache** | Local cache files where the Copilot extension stores usage data before (optionally) transmitting |
| **Turn** | A single request→response cycle between user and AI model |

### Abbreviations
| Abbreviation | Meaning |
|-------------|---------|
| GHCP | GitHub Copilot |
| LLM | Large Language Model |
| MTok | Million Tokens |
| API | Application Programming Interface |
| CLI | Command-Line Interface |
| DB | Database |
| CSV | Comma-Separated Values |
| JWT | JSON Web Token (used in GitHub API auth) |
| PAT | Personal Access Token (GitHub) |

## Part 4: Standards & Compliance

### Industry Standards
- **GitHub REST API v3**: Used for optional org-level Copilot metrics
- **SQLite**: ACID-compliant embedded database (no server required)
- **Chart.js**: MIT-licensed charting library (loaded from CDN)
- **Python 3.8+ stdlib**: Baseline compatibility target

### Regulatory Requirements
- **GDPR**: Tool is local-only by default; no personal data is transmitted. Org API integration requires GitHub PAT with appropriate scopes.
- **SOC 2**: No external data storage or processing. Compliant by architecture (local-only).
- **Corporate IT Policies**: Zero-install design (no pip packages) reduces security review friction.

### Quality Standards
- PEP 8 compliance for all Python code
- Zero third-party runtime dependencies
- Cross-platform support (Windows, macOS, Linux)
- Incremental scanning (idempotent, no data duplication)

## Part 5: Real-World Scenarios

### Use Cases
1. **Developer checks daily usage**: Runs `python cli.py today` before standup to see completions accepted and models used.
2. **Manager generates monthly report**: Opens dashboard, filters to 30-day range, exports CSV for leadership.
3. **Developer compares model performance**: Uses model filter to compare GPT-4o vs. Claude Sonnet completion rates.
4. **Admin tracks org adoption**: Configures GitHub API token, runs scan to pull org-wide metrics.

### Edge Cases
- Copilot extension updates change log format → scanner gracefully skips unparseable lines
- User has never used Copilot Chat (only completions) → dashboard shows completions data only, chat section empty
- Multiple VS Code windows open simultaneously → each generates separate session IDs, all captured
- Log files from different Copilot extension versions → scanner handles schema variations

### Known Issues
- GitHub Copilot's local log format is undocumented and subject to change
- Token counts for completions may not be directly available (estimated from character count)
- Agent mode telemetry format is new and may evolve rapidly
- Cache token metrics depend on model provider exposing them

## Part 6: Assumptions & Scope

### Key Assumptions
1. GitHub Copilot VS Code extension writes structured log/telemetry data to predictable local paths.
2. Log data includes session IDs, timestamps, model identifiers, and token counts (or sufficient data to estimate them).
3. Users have Python 3.8+ installed (standard for developers using VS Code).
4. The tool targets VS Code users only (JetBrains/Neovim are separate efforts).

### Out of Scope
- Real-time usage monitoring (event streaming)
- Multi-user remote dashboard hosting
- Integration with non-GitHub AI coding tools
- Billing integration or payment processing
- Mobile or web-based dashboard (localhost only)

### Dependencies
- Python 3.8+ standard library
- VS Code with GitHub Copilot extension installed
- (Optional) GitHub Personal Access Token with `copilot` scope for API integration
- (Optional) Internet connection for Chart.js CDN (dashboard works with cached version)