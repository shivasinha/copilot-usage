# Use Cases & User Workflows

## Use Case Framework
### Definition & Structure
Each use case describes a goal-oriented interaction between an actor and the GHCP Usage Dashboard system. Use cases follow the standard format: actor, preconditions, success scenario (step-by-step), alternative flows, exceptions, and business rules.

### Use Case Notation / Format
- **UC-ID**: Unique identifier (e.g., UC-01)
- **Actor**: Who initiates the use case (maps to personas in `Personas.md`)
- **Trigger**: What event starts the use case
- **Success Scenario**: Happy path, numbered steps
- **Alternative Flows**: Branching paths from the main scenario
- **Exceptions**: Error conditions and recovery

### Actor Definitions
| Actor | Description | Persona Reference |
|-------|-------------|-------------------|
| Developer | Individual developer using VS Code with Copilot | Alex (Persona 1) |
| Team Lead | Engineering manager tracking team usage | Morgan (Persona 2) |
| Cost Analyst | Developer focused on cost optimization | Sam (Persona 3) |
| Admin | Enterprise admin managing org-wide Copilot | Jordan (Persona 4) |

### Success Criteria
A use case is successful when the actor achieves their stated goal and all postconditions are met.

## Primary Use Cases

### UC-01: First-Time Setup and Scan

#### Actor(s)
Developer (Alex)

#### Preconditions
- Python 3.8+ installed
- VS Code with GitHub Copilot extension installed and used (log files exist)
- Repository cloned locally

#### Postconditions
- SQLite database created at `~/.ghcp-usage/usage.db`
- All discoverable Copilot log files parsed and stored
- Terminal displays scan summary (files processed, sessions found, turns added)

#### Success Scenario
##### Step 1: Clone repository
Developer runs `git clone <repo-url> && cd ghcp-usage`

##### Step 2: Run initial scan
Developer runs `python cli.py scan`

##### Step 3: Scanner discovers log files
System locates Copilot extension log files in default VS Code paths:
- Windows: `%APPDATA%\Code\User\globalStorage\github.copilot\`
- macOS: `~/Library/Application Support/Code/User/globalStorage/github.copilot/`
- Linux: `~/.config/Code/User/globalStorage/github.copilot/`

##### Step 4: Scanner parses log files
System reads each JSONL/log file line by line, extracts session metadata, completions, chat turns, and agent interactions.

##### Step 5: Scanner stores data
System creates/updates SQLite database with parsed records.

##### Step 6: Scanner displays summary
System prints:
```
Scan complete:
  New files:     42
  Updated files: 0
  Skipped files: 0
  Turns added:   1,847
  Sessions seen: 156
```

#### Alternative Flows / Variations

##### Variation 1: Custom log directory
- Developer runs `python cli.py scan --logs-dir /custom/path`
- System scans only the specified directory instead of defaults

##### Variation 2: No log files found
- System prints "No Copilot log files found in default paths. Use --logs-dir to specify a custom location."
- Exit code 0 (not an error — user may not have used Copilot yet)

#### Exception Scenarios / Error Handling

##### Exception 1: Python version too old
- Expected Behavior: Print "Python 3.8+ required. You have {version}."
- Recovery Steps: User upgrades Python

##### Exception 2: Permission denied on log directory
- Expected Behavior: Print "Permission denied: {path}. Run with appropriate permissions."
- Recovery Steps: User adjusts file permissions or runs with elevated access

##### Exception 3: Corrupted log file
- Expected Behavior: Print "Warning: error reading {filepath}: {error}" and continue with remaining files
- Recovery Steps: None needed — scanner is fault-tolerant

#### Business Rules Involved
- Rule 1: Scanner must be idempotent — running twice produces the same database state
- Rule 2: Incremental processing — only new/changed files are parsed on subsequent runs
- Rule 3: No data loss — corrupted files are skipped, not deleted

#### Related Use Cases
UC-02 (View Today's Usage), UC-04 (Open Dashboard)

#### Frequency / Importance
- Frequency: Once per installation + daily/weekly re-scans
- Importance: Critical — all other use cases depend on this

#### Performance Expectations
- 1,000 log files scanned in < 5 seconds
- Database creation < 1 second

---

### UC-02: View Today's Usage Summary

#### Actor(s)
Developer (Alex)

#### Preconditions
- Database exists and contains data from at least one scan
- Current date has Copilot usage data

#### Postconditions
- Terminal displays today's usage broken down by model

#### Success Scenario
##### Step 1: Run today command
Developer runs `python cli.py today`

##### Step 2: System queries database
System queries `turns` table for records with today's date, grouped by model.

##### Step 3: System displays summary
```
══════════════════════════════════════════════════════
  GitHub Copilot Usage — Today (2026-04-23)
══════════════════════════════════════════════════════
  gpt-4o                         turns=45   in=125.3K   out=89.2K    cost=$0.5432
  claude-sonnet-4                turns=12   in=34.1K    out=28.7K    cost=$0.5325
  gpt-4o-mini                    turns=8    in=5.2K     out=3.1K     cost=$0.0027
──────────────────────────────────────────────────────
  TOTAL                          turns=65   in=164.6K   out=121.0K   cost=$1.0784

  Sessions today:   7
  Completions:      142 shown / 98 accepted (69%)
──────────────────────────────────────────────────────
```

#### Alternative Flows

##### Variation 1: No data for today
- System prints "No Copilot usage recorded for today."

##### Variation 2: Database doesn't exist
- System prints "Database not found. Run: python cli.py scan"

#### Business Rules Involved
- Costs are calculated using API pricing — includes disclaimer for subscription users
- Only models in the pricing table show cost; others show "n/a"

#### Frequency / Importance
- Frequency: Daily (often multiple times per day)
- Importance: High — the most common quick-check command

---

### UC-03: View All-Time Statistics

#### Actor(s)
Developer (Alex), Team Lead (Morgan)

#### Preconditions
- Database exists with historical data

#### Postconditions
- Terminal displays comprehensive all-time stats

#### Success Scenario
##### Step 1: Run stats command
Developer runs `python cli.py stats`

##### Step 2: System aggregates all data
System queries sessions, turns, and computes totals.

##### Step 3: System displays statistics
```
══════════════════════════════════════════════════════════
  GitHub Copilot Usage - All-Time Statistics
══════════════════════════════════════════════════════════
  Period:           2025-09-15 to 2026-04-23
  Total sessions:   1,247
  Total turns:      18,432

  Input tokens:     45.2M        (raw prompt tokens)
  Output tokens:    31.8M        (generated tokens)
  Completions:      12,847 shown / 8,934 accepted (69.5%)

  Est. total cost:  $287.4210
──────────────────────────────────────────────────────────
  By Model:
    gpt-4o                         sessions=892  turns=12.1K  in=32.1M   out=22.3M  cost=$198.12
    claude-sonnet-4                sessions=245  turns=4.2K   in=8.9M    out=6.7M   cost=$72.15
    gpt-4o-mini                    sessions=110  turns=2.1K   in=4.2M    out=2.8M   cost=$17.13
──────────────────────────────────────────────────────────
  Top Projects:
    mycompany/frontend               sessions=342  turns=5.2K   tokens=18.4M
    mycompany/api-server             sessions=287  turns=4.1K   tokens=15.2M
    personal/side-project            sessions=98   turns=1.4K   tokens=4.8M
──────────────────────────────────────────────────────────
```

#### Frequency / Importance
- Frequency: Weekly to monthly
- Importance: Medium — used for trend analysis and reporting

---

### UC-04: Open Interactive Dashboard

#### Actor(s)
Developer (Alex), Team Lead (Morgan), Cost Analyst (Sam)

#### Preconditions
- Python 3.8+ available
- Browser available on the system

#### Postconditions
- Dashboard running on localhost:8080
- Browser opened to dashboard URL
- Data auto-refreshes every 30 seconds

#### Success Scenario
##### Step 1: Run dashboard command
Developer runs `python cli.py dashboard`

##### Step 2: System runs scan
System performs incremental scan (same as `cli.py scan`).

##### Step 3: System starts HTTP server
Dashboard server starts on `localhost:8080`.

##### Step 4: System opens browser
System opens default browser to `http://localhost:8080`.

##### Step 5: Dashboard loads and displays data
Browser shows: stats row, daily token chart, model distribution, project chart, cost tables, session tables.

##### Step 6: User interacts with dashboard
User filters by model, selects date range, sorts tables, exports CSV.

#### Alternative Flows

##### Variation 1: Custom host/port
- User sets `HOST=0.0.0.0 PORT=9000` environment variables
- Dashboard serves on `0.0.0.0:9000`

##### Variation 2: Port already in use
- System prints "Port 8080 in use. Set PORT environment variable to use a different port."

#### Business Rules Involved
- Dashboard auto-refreshes every 30 seconds
- Model filter and date range selections are persisted in URL query parameters (bookmarkable)
- Rescan button triggers a full database rebuild

#### Frequency / Importance
- Frequency: Weekly (deep dives and reporting)
- Importance: High — primary visual interface

#### Performance Expectations
- Dashboard loads in < 1 second for 30-day view
- Chart rendering smooth for up to 10,000 sessions
- Auto-refresh does not cause visible flicker

---

### UC-05: Export Data to CSV

#### Actor(s)
Team Lead (Morgan)

#### Preconditions
- Dashboard is open with data loaded

#### Postconditions
- CSV file downloaded to browser's default download location

#### Success Scenario
##### Step 1: Open dashboard
User navigates to running dashboard.

##### Step 2: Apply filters
User selects desired model(s) and date range.

##### Step 3: Click export button
User clicks "⇓ CSV" button on Sessions table or Projects table.

##### Step 4: CSV downloads
Browser downloads file named `sessions_2026-04-23_1430.csv` or `projects_2026-04-23_1430.csv`.

#### Business Rules Involved
- CSV includes all filtered rows (not just visible page)
- Cost column uses 4 decimal places
- Filename includes export type and timestamp

---

### UC-06: Track Org-Level Usage via GitHub API (v0.2)

#### Actor(s)
Admin (Jordan), Team Lead (Morgan)

#### Preconditions
- GitHub PAT with `copilot` scope configured
- Organization has Copilot Business or Enterprise plan

#### Postconditions
- Org-level usage metrics stored in SQLite database
- Dashboard shows team-wide adoption metrics

#### Success Scenario
##### Step 1: Configure API token
User sets `GITHUB_TOKEN` environment variable or adds to config file.

##### Step 2: Run API scan
User runs `python cli.py scan --org mycompany`

##### Step 3: System fetches API data
System calls `GET /orgs/mycompany/copilot/usage` and stores daily metrics.

##### Step 4: Dashboard shows org view
Dashboard displays additional "Organization" section with seat count, active users, and daily usage trends.

#### Exception Scenarios

##### Exception 1: Invalid or expired token
- Expected Behavior: Print "GitHub API error 401: Bad credentials. Check your GITHUB_TOKEN."
- Recovery Steps: User regenerates PAT

##### Exception 2: Insufficient permissions
- Expected Behavior: Print "GitHub API error 403: Token lacks 'copilot' scope."
- Recovery Steps: User updates PAT scopes

#### Frequency / Importance
- Frequency: Weekly to monthly
- Importance: Medium — required for team/org reporting use cases

---

## Secondary Use Cases

### UC-07: Compare Models
- Actor: Cost Analyst (Sam)
- Flow: Open dashboard → check only two models in filter → compare daily charts and cost tables
- Value: Helps decide which model provides best value

### UC-08: Analyze Project Usage
- Actor: Team Lead (Morgan)
- Flow: Open dashboard → sort "Cost by Project" table → identify highest-cost projects
- Value: Cost attribution for budget discussions

### UC-09: Rebuild Database
- Actor: Developer (Alex)
- Flow: Run `python cli.py scan --reset` → all processed_files records cleared → full rescan
- Value: Recovery from corrupted data or after major extension update

### UC-10: Check Completion Acceptance Rate (v0.2)
- Actor: Developer (Alex)
- Flow: Open dashboard → view "Completions" section → see acceptance rate by language/project
- Value: Understand which contexts benefit most from Copilot

## Use Case Dependency Map

```
UC-01 (First-Time Scan)
  ├── UC-02 (Today's Usage)
  ├── UC-03 (All-Time Stats)
  ├── UC-04 (Dashboard) ──→ UC-05 (CSV Export)
  │                      ──→ UC-07 (Compare Models)
  │                      ──→ UC-08 (Analyze Projects)
  └── UC-09 (Rebuild DB)

UC-06 (GitHub API) ──→ UC-04 (Dashboard, org view)
```

---

### Use Case 2: [Use Case Name]
#### (Same structure as Use Case 1)

---

### Use Case N: [Use Case Name]
#### (Same structure as Use Case 1)

## Secondary Use Cases (Brief)
### Use Case: [Name]
- Actors: [Who]
- Main Goal: [What]
- Success: [How do we know?]

## Cross-Functional Workflows
### Multi-Actor Workflows
#### Workflow 1: [Workflow Name]
- Actors Involved
- Sequence
- Data Exchanges
- Integration Points

#### Workflow N: [Workflow Name]
- Actors Involved
- Sequence
- Data Exchanges
- Integration Points

## Use Case by Persona
### Use Cases for Persona 1
### Use Cases for Persona 2
### Use Cases for Persona N

## Use Case by Feature
### Feature 1 Use Cases
### Feature 2 Use Cases
### Feature N Use Cases

## Use Case Dependencies
### Use Case Prerequisite Map
### Sequential Workflows
### Parallel Workflows
### Branching Scenarios

## Use Case Performance Profiles
### High-Frequency Use Cases
- Optimization Priority
- Performance SLAs
- Scalability Needs

### High-Impact Use Cases
- Business Criticality
- Failure Impact
- Recovery Requirements

### Complex Use Cases
- Complexity Factors
- Error Scenarios
- Support Impact

## Real-World Scenarios & Examples
### Example 1: [Scenario Description]
- Involved Actors
- Steps Executed
- Data Involved
- Outcome

### Example N: [Scenario Description]
- Involved Actors
- Steps Executed
- Data Involved
- Outcome

## Use Case Metrics
### Usage Frequency
### Success Rate
### Error Rate
### Average Duration
### User Satisfaction

## Known Issues & Workarounds
### Current Limitations
### Work-Arounds for Each Use Case
### Planned Improvements

## Use Case Testing
### Test Scenarios per Use Case
### Test Data Requirements
### Success Metrics
### Regression Risk Assessment