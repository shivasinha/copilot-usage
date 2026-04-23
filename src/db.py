"""Database initialization and connection management."""

import os
import sqlite3
from pathlib import Path

_DEFAULT_DB_PATH = Path.home() / ".ghcp-usage" / "usage.db"


def get_db_path():
    """Return the DB path, honouring the DB_PATH env var."""
    return Path(os.environ.get("DB_PATH", str(_DEFAULT_DB_PATH)))


def get_connection(db_path=None, read_only=False):
    """Open a SQLite connection with Row factory enabled."""
    if db_path is None:
        db_path = get_db_path()
    path = str(db_path)
    if read_only:
        conn = sqlite3.connect("file:{}?mode=ro".format(path), uri=True)
    else:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    """Create all tables and indexes; run forward-compatible schema migrations."""
    cur = conn.cursor()

    cur.executescript("""
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
            quota_input_tokens      INTEGER DEFAULT 0,
            quota_output_tokens     INTEGER DEFAULT 0,
            premium_requests        REAL DEFAULT 0,
            model                   TEXT,
            turn_count              INTEGER DEFAULT 0,
            completion_count        INTEGER DEFAULT 0,
            accepted_count          INTEGER DEFAULT 0,
            compaction_count        INTEGER DEFAULT 0,
            max_context_tokens      INTEGER DEFAULT 0
        );

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
            accepted                INTEGER,
            multiplier              REAL DEFAULT 1.0,
            context_compacted       INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS processed_files (
            path    TEXT PRIMARY KEY,
            mtime   REAL,
            lines   INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_project   ON sessions(project_name);
        CREATE INDEX IF NOT EXISTS idx_sessions_timestamp ON sessions(first_timestamp);
        CREATE INDEX IF NOT EXISTS idx_sessions_model     ON sessions(model);

        CREATE INDEX IF NOT EXISTS idx_turns_session   ON turns(session_id);
        CREATE INDEX IF NOT EXISTS idx_turns_timestamp ON turns(timestamp);
        CREATE INDEX IF NOT EXISTS idx_turns_model     ON turns(model);
    """)

    # Partial unique index on message_id — needs a separate statement
    try:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_turns_message_id
                ON turns(message_id)
                WHERE message_id IS NOT NULL AND message_id != ''
        """)
    except sqlite3.OperationalError:
        pass  # already exists or SQLite version doesn't support partial indexes

    conn.commit()
    migrate_db(conn)


def migrate_db(conn):
    """Apply forward-compatible schema migrations for columns added after initial release."""
    cur = conn.cursor()
    # Add multiplier column if missing (added in v2)
    cols = {row[1] for row in cur.execute("PRAGMA table_info(turns)")}
    if "multiplier" not in cols:
        cur.execute("ALTER TABLE turns ADD COLUMN multiplier REAL DEFAULT 1.0")
        conn.commit()
    # Add context_compacted column if missing (added in v3)
    if "context_compacted" not in cols:
        cur.execute("ALTER TABLE turns ADD COLUMN context_compacted INTEGER DEFAULT 0")
        conn.commit()
    # Add quota/premium columns to sessions if missing (added in v2)
    scols = {row[1] for row in cur.execute("PRAGMA table_info(sessions)")}
    if "quota_input_tokens" not in scols:
        cur.execute("ALTER TABLE sessions ADD COLUMN quota_input_tokens INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE sessions ADD COLUMN quota_output_tokens INTEGER DEFAULT 0")
    if "premium_requests" not in scols:
        cur.execute("ALTER TABLE sessions ADD COLUMN premium_requests REAL DEFAULT 0")
    # Add compaction columns if missing (added in v3)
    if "compaction_count" not in scols:
        cur.execute("ALTER TABLE sessions ADD COLUMN compaction_count INTEGER DEFAULT 0")
    if "max_context_tokens" not in scols:
        cur.execute("ALTER TABLE sessions ADD COLUMN max_context_tokens INTEGER DEFAULT 0")
    conn.commit()


def db_exists(db_path=None):
    """Return True if the database file exists."""
    return get_db_path().exists() if db_path is None else Path(db_path).exists()
