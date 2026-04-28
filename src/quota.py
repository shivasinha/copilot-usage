"""Monthly premium request quota tracking.

GitHub Copilot's "included premium requests" counter is server-side only and
cannot be read from the local filesystem.  This module approximates it by
summing ``multiplier`` values from the local turns table (each turn contributes
its model's request multiplier, e.g. 3.0 for claude-opus-4.6).

Configure the monthly limit by setting the GHCP_QUOTA environment variable
(default: _DEFAULT_QUOTA — the standard Copilot Individual/Business included quota).
"""

import os
from datetime import datetime

_DEFAULT_QUOTA = 300


def get_quota_limit():
    """Return the configured monthly quota limit.

    Priority: settings.json → GHCP_QUOTA env var → _DEFAULT_QUOTA.
    The settings UI always takes precedence; GHCP_QUOTA is a legacy fallback.
    """
    try:
        import settings as _settings
        return _settings.load()["quota_limit"]
    except Exception:
        pass
    raw = os.environ.get("GHCP_QUOTA", "")
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return _DEFAULT_QUOTA


def get_monthly_premium_requests(conn, year_month=None):
    """Return the total premium-request count for *year_month* (YYYY-MM, UTC).

    Each chat turn contributes ``COALESCE(multiplier, 1.0)`` to the sum, so
    a claude-opus-4.6 turn (3×) counts as 3 premium requests.

    Defaults to the current UTC month.
    """
    if year_month is None:
        year_month = datetime.utcnow().strftime("%Y-%m")

    cur = conn.execute(
        "SELECT COALESCE(SUM(COALESCE(multiplier, 1.0)), 0.0) "
        "FROM turns WHERE timestamp LIKE ?",
        (year_month + "%",),
    )
    row = cur.fetchone()
    return float(row[0]) if row else 0.0


def get_monthly_turns(conn, year_month=None):
    """Return the raw turn count for *year_month* (YYYY-MM, UTC)."""
    if year_month is None:
        year_month = datetime.utcnow().strftime("%Y-%m")

    cur = conn.execute(
        "SELECT COUNT(*) FROM turns WHERE timestamp LIKE ?",
        (year_month + "%",),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def get_quota_status(conn, year_month=None):
    """Return a quota status dict for *year_month*.

    Keys:
        year_month       str    "YYYY-MM"
        used             float  premium requests consumed this month
        turns            int    raw turn count this month
        limit            int    configured monthly limit
        percent          float  used / limit * 100  (can exceed 100)
        over_limit       bool
        remaining        float  max(0, limit - used)
    """
    if year_month is None:
        year_month = datetime.utcnow().strftime("%Y-%m")

    limit = get_quota_limit()
    used = get_monthly_premium_requests(conn, year_month)
    turns = get_monthly_turns(conn, year_month)
    percent = round(100.0 * used / limit, 1) if limit > 0 else 0.0

    return {
        "year_month": year_month,
        "used": used,
        "turns": turns,
        "limit": limit,
        "percent": percent,
        "over_limit": used > limit,
        "remaining": max(0.0, limit - used),
    }
