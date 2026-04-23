# User Personas & Roles

## Persona Framework Overview
### How to Read This Document
Each persona describes a distinct user archetype for GHCP Usage Dashboard. Personas define who uses the tool, why, and what they need from it. Use these personas to drive feature prioritization, UI decisions, and acceptance criteria.

### Persona Attributes
Each persona includes: demographics, professional context, goals, pain points, technical proficiency, typical workflows, and the features most relevant to them.

### Persona Hierarchy / Relationships
```
Enterprise Admin
  └── Team Lead / Engineering Manager
        └── Individual Developer (primary user)
              └── Cost-Conscious Developer (variant)
```

## Primary Personas

### Persona 1: Alex — The Individual Developer

#### Demographics
- Age Range: 25–40
- Experience Level: Mid-level to Senior (3–10 years)
- Education / Background: CS degree or self-taught developer
- Geography: Global (remote-first)

#### Professional Context
- Role / Job Title: Software Engineer / Full-Stack Developer
- Department / Team: Product engineering team (5–15 people)
- Organization Size: Startup to mid-size (50–500 employees)
- Industry Focus: SaaS, fintech, developer tools

#### Goals & Objectives
- **Primary Goals**: Understand personal Copilot usage patterns — which models are used, how many completions accepted, and how much chat/agent capacity consumed.
- **Secondary Goals**: Optimize workflows by identifying which languages/projects benefit most from Copilot.
- **Success Metrics**: Can answer "How much did I use Copilot this week?" in under 10 seconds.
- **Pain Points**:
  - GitHub's Copilot dashboard shows nothing at the individual level
  - No way to see which model was used for each interaction
  - Cannot track usage trends over time
  - Unclear how much Copilot usage would cost on an API plan

#### Needs & Requirements
- **Functional Needs**: Quick scan & dashboard launch, per-session breakdown, model filtering, date range selection
- **Non-Functional Needs**: Fast startup (< 2s), zero installation friction
- **Integration Requirements**: Reads local VS Code Copilot logs — no API keys needed
- **Support Needs**: Clear README, self-explanatory dashboard

#### Technical Proficiency
- Technical Skills Level: High — comfortable with CLI, Python, Git
- Tool Familiarity: VS Code daily user, GitHub Copilot active user
- Learning Curve Tolerance: Low patience for setup — wants `git clone && python cli.py dashboard`
- Preferred Learning Methods: README quick-start, inline help text

#### Values & Priorities
- What Matters Most: Speed, simplicity, privacy
- Decision Drivers: "Does it work in 60 seconds without installing anything?"
- Risk Tolerance: Low — won't install unknown pip packages
- Budget Constraints: Free / open-source only

#### Typical Workflows
- **Daily**: Runs `python cli.py today` to check morning usage
- **Weekly**: Opens dashboard to review weekly trends, model usage, and project breakdown
- **Monthly**: Exports CSV of session data for personal records or expense reporting

---

### Persona 2: Morgan — The Team Lead / Engineering Manager

#### Demographics
- Age Range: 30–45
- Experience Level: Senior / Lead (8–15 years)
- Education / Background: CS degree, some management training
- Geography: US / EU enterprise settings

#### Professional Context
- Role / Job Title: Engineering Manager / Tech Lead
- Department / Team: Manages 5–20 developers
- Organization Size: Mid to large enterprise (500–10,000 employees)
- Industry Focus: Enterprise software, financial services, healthcare IT

#### Goals & Objectives
- **Primary Goals**: Track team-wide Copilot adoption and usage to justify the license cost to leadership.
- **Secondary Goals**: Identify which teams/projects get the most value from Copilot. Spot under-utilization.
- **Success Metrics**: Can produce a monthly usage report showing adoption rate and estimated cost-per-developer.
- **Pain Points**:
  - GitHub admin dashboard is too high-level (seat counts only)
  - Cannot correlate Copilot usage with project velocity
  - No per-model cost attribution for budget planning
  - Needs data to defend or expand Copilot seat allocation

#### Needs & Requirements
- **Functional Needs**: Org-level API integration, project-level aggregation, cost-by-model tables, CSV export
- **Non-Functional Needs**: Handles 50+ developers' data without performance degradation
- **Integration Requirements**: GitHub Copilot Usage REST API (`GET /orgs/{org}/copilot/usage`)
- **Support Needs**: Documentation on API token setup, data interpretation guide

#### Technical Proficiency
- Technical Skills Level: Medium-high — can run CLI tools but prefers GUI
- Tool Familiarity: VS Code user, GitHub admin console, Jira/Linear
- Learning Curve Tolerance: Medium — willing to spend 15 minutes on setup
- Preferred Learning Methods: Step-by-step guide, screenshots

#### Typical Workflows
- **Weekly**: Reviews team dashboard to spot usage trends
- **Monthly**: Exports project-level CSV for leadership reporting
- **Quarterly**: Compares Copilot cost vs. productivity gains for budget reviews

---

### Persona 3: Sam — The Cost-Conscious Developer

#### Demographics
- Age Range: 22–35
- Experience Level: Junior to Mid-level
- Education / Background: Bootcamp graduate or early-career CS grad
- Geography: Global, often in cost-sensitive regions

#### Professional Context
- Role / Job Title: Junior Developer / Freelance Developer
- Department / Team: Small team or solo
- Organization Size: Freelance / startup (1–20 people)
- Industry Focus: Web development, mobile apps, consulting

#### Goals & Objectives
- **Primary Goals**: Understand what Copilot usage would cost on an API-based plan; decide if the subscription is worth it.
- **Secondary Goals**: Track which features (completions vs. chat vs. agent) provide the most value.
- **Pain Points**:
  - Pays for Copilot Individual ($19/month) but has no idea if they're getting value
  - Worried about hidden costs if they switch to a pay-per-use model
  - Cannot compare cost of different AI coding tools (Copilot vs. Claude Code vs. Cursor)

#### Needs & Requirements
- **Functional Needs**: Cost estimates per model, usage-over-time charts, completion acceptance rates
- **Non-Functional Needs**: Minimal resource usage (runs on low-spec machines)
- **Integration Requirements**: Local logs only — no API keys or tokens
- **Support Needs**: FAQ explaining cost calculation methodology

#### Typical Workflows
- **Weekly**: Checks estimated API cost to compare with subscription price
- **Monthly**: Reviews which models and features were used most to assess value

---

## Secondary Personas

### Persona 4: Jordan — The Enterprise Admin

#### Professional Context
- Role: IT Admin / DevOps Lead / Platform Engineer
- Organization: Large enterprise (10,000+ employees) with Copilot Enterprise license

#### Goals
- Monitor organization-wide Copilot adoption metrics
- Enforce usage policies and track compliance
- Provide cost attribution data to finance teams

#### Key Needs
- GitHub API integration for org-level metrics
- Multi-team aggregation and filtering
- Automated scheduled scans (cron/task scheduler integration)
- Export to enterprise reporting tools (CSV/JSON)

## Persona Comparison Matrix

| Attribute | Alex (Developer) | Morgan (Lead) | Sam (Cost-Conscious) | Jordan (Admin) |
|-----------|-----------------|---------------|---------------------|----------------|
| Primary data source | Local logs | Local + API | Local logs | API only |
| Key metric | Completions/day | Adoption rate | Cost estimates | Org-wide usage |
| Setup tolerance | < 1 minute | < 15 minutes | < 1 minute | < 30 minutes |
| Export needs | Rarely | Monthly CSV | Rarely | Automated reports |
| API token required | No | Yes | No | Yes |
- Quarterly/Annual Activities

#### Pain Points & Frustrations
- Current Challenges
- Unmet Needs
- Workarounds Used
- Feature Requests

#### Feature Usage Patterns
- Most-Used Features
- Rarely-Used Features
- Feature Combinations
- Typical User Journeys

#### Communication Preferences
- Preferred Channels
- Response Time Expectations
- Documentation Format Preferences
- Support Type Preferences

---

### Persona 2: [Name/Title]
#### (Same structure as Persona 1)

---

### Persona N: [Name/Title]
#### (Same structure as Persona 1)

## Secondary Personas (Brief)
### Persona: [Name]
- Role: [Title]
- Primary Need: [Need]
- Key Interaction: [How they use the product]

## Persona Relationships & Interactions
### Persona Collaboration Map
### Permission & Access Patterns
### Hand-off Workflows
### Conflict Scenarios

## Persona Segments
### By Industry
### By Organization Size
### By Geographic Region
### By Use Case
### By Expertise Level

## Persona Evolution
### Changing Needs Over Time
### Maturity Path (Beginner → Advanced)
### Career Progression
### Scaling with Organization Growth

## Anti-Personas
### Who We DON'T Target
### Why They're Not a Good Fit
### How to Identify Anti-Personas

## Persona-Specific Requirements
### Persona 1 Requirements
### Persona 2 Requirements
### Persona N Requirements

## Persona Testing & Validation
### How These Personas Were Defined
### Validation Data / Research
### Last Updated / Review Cycle
### Feedback Mechanisms

## Persona Development Resources
### User Research Data
### Interview Transcripts (Summary)
### Usage Analytics
### Customer Feedback Compilation