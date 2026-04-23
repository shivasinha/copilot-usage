# Data Models & Database Schema

## Introduction

### Overview
GHCP Usage Dashboard stores all parsed Copilot usage data in a single SQLite database file. The schema is designed for fast read queries (dashboard and CLI stats) while supporting incremental writes from the scanner.

### Scope
This document covers the SQLite database schema, all table definitions, indexes, relationships, and the data flow from raw log files to stored records.

### Design Principles
- **Append-mostly**: New turns are inserted; sessions are upserted. Deletes are rare (only on `--reset`).
- **Denormalized sessions**: Session table stores aggregated totals for fast dashboard queries; totals are recomputed from turns after each scan.
- **Idempotent writes**: `INSERT OR IGNORE` on turns (dedup by message_id), `UPSERT` on sessions.
- **Forward-compatible schema**: New columns added via `ALTER TABLE ADD COLUMN` with defaults.

### Last Updated / Version
Schema version: 1.0 (MVP) — April 2026

## Database Design Overview

### Database Type
- **SQLite 3** (embedded, serverless, zero-config)
- File location: `~/.ghcp-usage/usage.db` (configurable)
- Access via Python `sqlite3` module
- No high-availability setup needed (single-user local tool)

### Design Principles
- ACID-compliant (SQLite default)
- Partially normalized: turns are fully normalized; sessions store denormalized aggregates for query speed
- No foreign key enforcement (pragmatic choice for append-heavy workload)
- Indexes on frequently queried columns (session_id, timestamp, model)

### Entity Relationship Diagram (ERD)

```
┌─────────────────┐        ┌─────────────────────┐
│    sessions      │        │       turns          │
├─────────────────┤        ├─────────────────────┤
│ session_id (PK) │◄───────│ session_id (FK)      │
│ project_name    │        │ id (PK, AUTO)        │
│ first_timestamp │        │ timestamp            │
│ last_timestamp  │        │ turn_type            │
│ git_branch      │        │ model                │
│ total_input     │        │ input_tokens         │
│ total_output    │        │ output_tokens        │
│ total_cache_rd  │        │ cache_read_tokens    │
│ total_cache_wr  │        │ cache_creation_tokens│
│ model           │        │ tool_name            │
│ turn_count      │        │ cwd                  │
│ completion_count│        │ message_id           │
│ accepted_count  │        │ language             │
└─────────────────┘        │ accepted             │
                           └─────────────────────┘

┌──────────────────────┐
│   processed_files    │
├──────────────────────┤
│ path (PK)            │
│ mtime                │
│ lines                │
└──────────────────────┘
```

## Core Data Models

### Entity 1: sessions

#### Overview
- **Purpose**: Store session-level metadata and aggregated usage totals
- **Business Domain**: Session tracking
- **Criticality**: Critical — primary entity for dashboard and stats
- **Access Patterns**: High read (every dashboard load), medium write (upsert on scan)

#### Schema

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id              TEXT PRIMARY KEY,
    project_name            TEXT,
    first_timestamp         TEXT,
    last_timestamp          TEXT,
    git_branch              TEXT,
    total_input_tokens      INTEGER DEFAULT 0,
    total_output_tokens     INTEGER DEFAULT 0,
    total_cache_read        INTEGER DEFAULT 0,
    total_cache_creation    INTEGER DEFAULT 0,
    model                   TEXT,
    turn_count              INTEGER DEFAULT 0,
    completion_count        INTEGER DEFAULT 0,
    accepted_count          INTEGER DEFAULT 0
);
```

#### Column Details

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `session_id` | TEXT | No (PK) | Unique session identifier from Copilot logs |
| `project_name` | TEXT | Yes | Derived from workspace/cwd path (last 2 path components) |
| `first_timestamp` | TEXT | Yes | ISO 8601 timestamp of first activity in session |
| `last_timestamp` | TEXT | Yes | ISO 8601 timestamp of last activity in session |
| `git_branch` | TEXT | Yes | Git branch active during the session (if available) |
| `total_input_tokens` | INTEGER | No | Sum of input tokens across all turns (recomputed from turns table) |
| `total_output_tokens` | INTEGER | No | Sum of output tokens across all turns |
| `total_cache_read` | INTEGER | No | Sum of cache read tokens |
| `total_cache_creation` | INTEGER | No | Sum of cache creation tokens |
| `model` | TEXT | Yes | Primary model used in the session (last seen model) |
| `turn_count` | INTEGER | No | Count of turns in the session (recomputed) |
| `completion_count` | INTEGER | No | Number of inline completions shown |
| `accepted_count` | INTEGER | No | Number of completions accepted by the user |

#### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_name);
CREATE INDEX IF NOT EXISTS idx_sessions_timestamp ON sessions(first_timestamp);
CREATE INDEX IF NOT EXISTS idx_sessions_model ON sessions(model);
```

---

### Entity 2: turns

#### Overview
- **Purpose**: Store individual request→response interactions (chat turns, completions, agent actions)
- **Business Domain**: Granular usage tracking
- **Criticality**: Critical — source of truth for all aggregations
- **Access Patterns**: High write (bulk insert on scan), medium read (aggregation queries)

#### Schema

```sql
CREATE TABLE IF NOT EXISTS turns (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              TEXT,
    timestamp               TEXT,
    turn_type               TEXT,
    model                   TEXT,
    input_tokens            INTEGER DEFAULT 0,
    output_tokens           INTEGER DEFAULT 0,
    cache_read_tokens       INTEGER DEFAULT 0,
    cache_creation_tokens   INTEGER DEFAULT 0,
    tool_name               TEXT,
    cwd                     TEXT,
    message_id              TEXT,
    language                TEXT,
    accepted                INTEGER
);
```

#### Column Details

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No (PK) | Auto-incrementing primary key |
| `session_id` | TEXT | Yes | Reference to sessions table |
| `timestamp` | TEXT | Yes | ISO 8601 timestamp of this turn |
| `turn_type` | TEXT | Yes | Type: `completion`, `chat`, `agent` |
| `model` | TEXT | Yes | Model used for this turn (e.g., `gpt-4o`, `claude-sonnet-4`) |
| `input_tokens` | INTEGER | No | Prompt tokens sent to model |
| `output_tokens` | INTEGER | No | Response tokens generated by model |
| `cache_read_tokens` | INTEGER | No | Tokens served from prompt cache |
| `cache_creation_tokens` | INTEGER | No | Tokens written to prompt cache |
| `tool_name` | TEXT | Yes | Tool used in agent mode (e.g., `file_edit`, `terminal`) |
| `cwd` | TEXT | Yes | Working directory at time of turn |
| `message_id` | TEXT | Yes | Unique message identifier for deduplication |
| `language` | TEXT | Yes | Programming language context (for completions) |
| `accepted` | INTEGER | Yes | 1 = completion accepted, 0 = dismissed, NULL = not a completion |

#### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_timestamp ON turns(timestamp);
CREATE INDEX IF NOT EXISTS idx_turns_model ON turns(model);
CREATE UNIQUE INDEX IF NOT EXISTS idx_turns_message_id
    ON turns(message_id) WHERE message_id IS NOT NULL AND message_id != '';
```

---

### Entity 3: processed_files

#### Overview
- **Purpose**: Track which log files have been scanned and their state at scan time
- **Business Domain**: Incremental scanning
- **Criticality**: Important — enables fast re-scans
- **Access Patterns**: Read on every scan (check if file changed), write after processing

#### Schema

```sql
CREATE TABLE IF NOT EXISTS processed_files (
    path    TEXT PRIMARY KEY,
    mtime   REAL,
    lines   INTEGER
);
```

#### Column Details

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `path` | TEXT | No (PK) | Absolute path to the log file |
| `mtime` | REAL | Yes | File modification time (from `os.path.getmtime()`) |
| `lines` | INTEGER | Yes | Number of lines processed (for detecting appended content) |

---

## Dashboard API Data Model

The `/api/data` endpoint returns a JSON object consumed by the dashboard frontend:

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

## Query Patterns

### Dashboard Queries

```sql
-- All models (for filter UI)
SELECT COALESCE(model, 'unknown') as model
FROM turns
GROUP BY model
ORDER BY SUM(input_tokens + output_tokens) DESC;

-- Daily aggregation
SELECT
    DATE(timestamp) as day,
    COALESCE(model, 'unknown') as model,
    SUM(input_tokens) as input,
    SUM(output_tokens) as output,
    SUM(cache_read_tokens) as cache_read,
    SUM(cache_creation_tokens) as cache_creation,
    COUNT(*) as turns
FROM turns
GROUP BY day, model
ORDER BY day;

-- Session list with aggregated totals
SELECT
    s.session_id, s.project_name, s.model,
    s.first_timestamp, s.last_timestamp,
    s.total_input_tokens, s.total_output_tokens,
    s.total_cache_read, s.total_cache_creation,
    s.turn_count
FROM sessions s
ORDER BY s.last_timestamp DESC;
```

### CLI Stats Queries

```sql
-- Today's usage by model
SELECT model, SUM(input_tokens) as inp, SUM(output_tokens) as out,
       SUM(cache_read_tokens) as cr, SUM(cache_creation_tokens) as cc,
       COUNT(*) as turns
FROM turns
WHERE DATE(timestamp) = DATE('now')
GROUP BY model
ORDER BY inp + out DESC;

-- All-time totals
SELECT SUM(input_tokens) as inp, SUM(output_tokens) as out,
       SUM(cache_read_tokens) as cr, SUM(cache_creation_tokens) as cc,
       COUNT(*) as turns
FROM turns;
```

## Schema Migration Strategy

Schema changes are handled in `init_db()`:

```python
def init_db(conn):
    # Create tables with IF NOT EXISTS
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (...);
        CREATE TABLE IF NOT EXISTS turns (...);
        CREATE TABLE IF NOT EXISTS processed_files (...);
    """)
    # Add new columns for upgrades
    try:
        conn.execute("SELECT language FROM turns LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE turns ADD COLUMN language TEXT")
    # ... similar for other new columns
    conn.commit()
```

This approach:
- Works without migration files or version tracking
- Is forward-compatible (new columns have defaults)
- Handles first-run and upgrade scenarios identically