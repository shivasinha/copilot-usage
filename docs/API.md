# API Overview & Getting Started

## Introduction

### What is This API?
GHCP Usage Dashboard exposes a lightweight internal HTTP API on `localhost` for communication between the dashboard frontend (browser) and the Python backend. It also optionally consumes the GitHub Copilot Usage REST API for organization-level metrics.

This document covers both:
1. **Internal Dashboard API** — served by `dashboard.py` on localhost
2. **GitHub Copilot Usage API** — external API consumed for org metrics (v0.2)

### API Purpose & Capabilities
| API | Direction | Purpose |
|-----|-----------|---------|
| Dashboard API | Backend → Frontend | Serve usage data as JSON for the browser dashboard |
| Rescan API | Frontend → Backend | Trigger a database rescan from the dashboard UI |
| GitHub API (v0.2) | Backend → GitHub | Fetch org-level Copilot usage metrics |

### Who Should Use This API
- **Dashboard frontend**: Calls `/api/data` and `/api/rescan` automatically
- **Advanced users**: Can curl the API for custom integrations or scripts
- **Team leads/admins**: Configure GitHub API integration for org metrics

### API Maturity Level
- Dashboard API: **Stable** (v0.1)
- GitHub API integration: **Planned** (v0.2)

## Quick Start

### 5-Minute Quick Start

#### Step 1: Start the dashboard server
```bash
python cli.py dashboard
# Server starts on http://localhost:8080
```

#### Step 2: Make your first API request
```bash
curl http://localhost:8080/api/data
```

#### Step 3: Parse the response
The response is a JSON object:
```json
{
    "all_models": ["gpt-4o", "claude-sonnet-4", "gpt-4o-mini"],
    "daily": [...],
    "sessions_all": [...],
    "generated_at": "2026-04-23T14:35:00"
}
```

#### What's Next?
- Use `/api/rescan` (POST) to rebuild the database
- Configure `HOST` and `PORT` env vars for custom binding

### Code Examples

**Python**:
```python
import json
import urllib.request

resp = urllib.request.urlopen("http://localhost:8080/api/data")
data = json.loads(resp.read())
print(f"Models: {data['all_models']}")
print(f"Sessions: {len(data['sessions_all'])}")
```

**PowerShell**:
```powershell
$data = Invoke-RestMethod http://localhost:8080/api/data
$data.all_models
$data.sessions_all.Count
```

**curl + jq**:
```bash
curl -s http://localhost:8080/api/data | jq '.all_models'
curl -s http://localhost:8080/api/data | jq '.sessions_all | length'
```

---

## Dashboard API Reference

### GET /

**Description**: Serve the dashboard HTML page.

| Field | Value |
|-------|-------|
| Method | GET |
| Path | `/` or `/index.html` |
| Content-Type | `text/html; charset=utf-8` |
| Auth | None (localhost only) |

**Response**: Full HTML page with embedded CSS and JavaScript.

---

### GET /api/data

**Description**: Return all usage data as JSON for the dashboard frontend.

| Field | Value |
|-------|-------|
| Method | GET |
| Path | `/api/data` |
| Content-Type | `application/json` |
| Auth | None |

**Response Body**:

```json
{
    "all_models": ["gpt-4o", "claude-sonnet-4", "gpt-4o-mini"],
    "daily": [
        {
            "day": "2026-04-23",
            "model": "gpt-4o",
            "input": 125300,
            "output": 89200,
            "cache_read": 45000,
            "cache_creation": 12000,
            "turns": 45
        }
    ],
    "sessions_all": [
        {
            "session_id": "a1b2c3d4",
            "project": "mycompany/frontend",
            "last": "2026-04-23 14:30",
            "last_date": "2026-04-23",
            "duration_min": 45.2,
            "model": "gpt-4o",
            "turns": 23,
            "input": 67000,
            "output": 45000,
            "cache_read": 12000,
            "cache_creation": 3000
        }
    ],
    "generated_at": "2026-04-23T14:35:00"
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `all_models` | string[] | All distinct models in the database, sorted by total tokens descending |
| `daily` | object[] | Daily token aggregations by model |
| `daily[].day` | string | Date in `YYYY-MM-DD` format |
| `daily[].model` | string | Model name |
| `daily[].input` | integer | Total input tokens for that day+model |
| `daily[].output` | integer | Total output tokens |
| `daily[].cache_read` | integer | Tokens served from cache |
| `daily[].cache_creation` | integer | Tokens written to cache |
| `daily[].turns` | integer | Number of turns |
| `sessions_all` | object[] | All sessions, ordered by last activity descending |
| `sessions_all[].session_id` | string | First 8 characters of session ID |
| `sessions_all[].project` | string | Project name (derived from cwd) |
| `sessions_all[].last` | string | Last activity timestamp (`YYYY-MM-DD HH:MM`) |
| `sessions_all[].last_date` | string | Last activity date (`YYYY-MM-DD`) |
| `sessions_all[].duration_min` | number | Session duration in minutes |
| `sessions_all[].model` | string | Primary model used |
| `sessions_all[].turns` | integer | Turn count |
| `sessions_all[].input` | integer | Total input tokens |
| `sessions_all[].output` | integer | Total output tokens |
| `sessions_all[].cache_read` | integer | Cache read tokens |
| `sessions_all[].cache_creation` | integer | Cache creation tokens |
| `generated_at` | string | ISO 8601 timestamp of when this data was generated |

**Error Response** (database not found):
```json
{
    "error": "Database not found. Run: python cli.py scan"
}
```

---

### POST /api/rescan

**Description**: Trigger a full database rescan from the dashboard UI.

| Field | Value |
|-------|-------|
| Method | POST |
| Path | `/api/rescan` |
| Content-Type | `application/json` |
| Auth | None |

**Response Body**:
```json
{
    "new": 5,
    "updated": 2,
    "skipped": 35,
    "turns": 127,
    "sessions": 12
}
```

| Field | Type | Description |
|-------|------|-------------|
| `new` | integer | Number of newly discovered log files |
| `updated` | integer | Number of files with new content since last scan |
| `skipped` | integer | Number of unchanged files skipped |
| `turns` | integer | Number of new turns added |
| `sessions` | integer | Number of distinct sessions in new data |

---

## GitHub Copilot Usage API (v0.2 — Planned)

### Overview
The [GitHub Copilot Usage API](https://docs.github.com/en/rest/copilot/copilot-usage) provides organization-level metrics. GHCP Usage Dashboard will consume this API to supplement local log data.

### Endpoint
```
GET /orgs/{org}/copilot/usage
```

### Authentication
- Requires GitHub PAT with `copilot` scope
- Set via environment variable: `GITHUB_TOKEN`

### Configuration
```bash
# Set token
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Scan with org data
python cli.py scan --org mycompany
```

### Response Fields (from GitHub)
| Field | Description |
|-------|-------------|
| `day` | Date of usage |
| `total_suggestions_count` | Completions shown |
| `total_acceptances_count` | Completions accepted |
| `total_lines_suggested` | Lines of code suggested |
| `total_lines_accepted` | Lines of code accepted |
| `total_active_users` | Users active that day |
| `breakdown` | Per-language and per-editor breakdown |

### Rate Limits
- GitHub API: 5,000 requests/hour for authenticated users
- Copilot usage endpoint: Returns daily data; one call returns up to 28 days
- Recommended: Scan weekly or monthly (not daily)