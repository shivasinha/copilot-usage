"""HTTP server for the GHCP Usage Dashboard.

Serves:
  GET /              → Single-page HTML dashboard (embedded below)
  GET /api/data      → JSON all data for client-side filtering
  GET /api/quota     → JSON monthly quota status
  GET /api/export    → CSV download (?model=&since=&until=)
  POST /api/rescan   → Trigger incremental log scan, returns {new, updated}

Security (NFR-05-B/C):
  - Binds to localhost by default; HOST env var required for 0.0.0.0.
  - All dynamic dashboard content uses esc() helper (no raw user-data innerHTML).
  - CSV values RFC 4180-escaped (NFR-08-B).
  - Export endpoint serves only DB-derived data — no filesystem access (NFR-08-C).
"""

import csv
import io
import json
import os
import socket
import sqlite3
import sys
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import db
import quota
import settings as _settings
from pricing import PRICING_DATE, PRICING_SOURCE_URL, estimate_cost, format_cost

# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _filter_clause(params):
    """Build a WHERE clause fragment and values list from request params.

    Supported params: model (repeatable), since (YYYY-MM-DD), until (YYYY-MM-DD).
    Returns (clause_fragment, values_list).
    """
    clauses = []
    values = []

    models = params.get("model", [])
    if models:
        placeholders = ",".join("?" * len(models))
        clauses.append("model IN ({})".format(placeholders))
        values.extend(models)

    since = params.get("since", [None])[0]
    if since:
        clauses.append("DATE(timestamp) >= ?")
        values.append(since)

    until = params.get("until", [None])[0]
    if until:
        clauses.append("DATE(timestamp) <= ?")
        values.append(until)

    if clauses:
        return "WHERE " + " AND ".join(clauses), values
    return "", []


_IST = timezone(timedelta(hours=5, minutes=30))

def _to_ist(ts: str) -> str:
    """Convert UTC ISO timestamp string to IST (UTC+5:30) 'YYYY-MM-DD HH:MM' string."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_IST).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts[:16].replace("T", " ")


def _query_models(conn):
    cur = conn.execute("""
        SELECT COALESCE(model, 'unknown') AS model
        FROM turns
        GROUP BY model
        ORDER BY SUM(input_tokens + output_tokens) DESC
    """)
    return [row["model"] for row in cur.fetchall()]


def _source_clause(source: str):
    """Return a WHERE fragment and params to filter turns/sessions by data source."""
    if source == "jsonl":
        return "WHERE session_id NOT LIKE 'proxy-%'", []
    return "", []  # both


def _query_all_data(conn):
    """Return all data for client-side filtering.

    Sends the complete session list, daily per-model turn aggregates, and the
    model list. The browser JS handles range/model filtering without extra
    round-trips.
    """
    all_models = _query_models(conn)
    source = _settings.load().get("data_source", "both")
    src_where, _ = _source_clause(source)

    # Daily per-model aggregates (full history — client filters by range)
    cur = conn.execute("""
        SELECT
            DATE(datetime(timestamp, '+5 hours', '30 minutes')) AS day,
            COALESCE(model, 'unknown') AS model,
            SUM(input_tokens)            AS input,
            SUM(output_tokens)           AS output,
            COUNT(*)                     AS turns
        FROM turns
        {src_where}
        GROUP BY day, model
        ORDER BY day, model
    """.format(src_where=src_where))
    daily_by_model = [dict(row) for row in cur.fetchall()]

    # All sessions with server-side cost estimate
    ses_where = src_where if src_where else ""
    cur = conn.execute("""
        SELECT
            session_id, project_name, model,
            first_timestamp, last_timestamp,
            total_input_tokens, total_output_tokens,
            total_cache_read, total_cache_creation,
            turn_count,
            COALESCE(premium_requests, 0.0)   AS premium_requests,
            COALESCE(compaction_count, 0)      AS compaction_count,
            COALESCE(max_context_tokens, 0)    AS max_context_tokens
        FROM sessions
        {ses_where}
        ORDER BY last_timestamp DESC
    """.format(ses_where=ses_where))
    sessions = []
    for row in cur.fetchall():
        inp = row["total_input_tokens"]  or 0
        out = row["total_output_tokens"] or 0
        cr  = row["total_cache_read"]    or 0
        cc  = row["total_cache_creation"] or 0
        cost = estimate_cost(row["model"], inp, out, cr, cc)
        try:
            t1 = datetime.fromisoformat((row["first_timestamp"] or "").replace("Z", "+00:00"))
            t2 = datetime.fromisoformat((row["last_timestamp"]  or "").replace("Z", "+00:00"))
            dur = round((t2 - t1).total_seconds() / 60, 1)
        except Exception:
            dur = 0
        sessions.append({
            "session_id":        row["session_id"][:8],
            "project":           row["project_name"] or "unknown",
            "model":             row["model"] or "unknown",
            "last":              _to_ist(row["last_timestamp"] or ""),
            "last_date":         _to_ist(row["last_timestamp"] or "")[:10],
            "turns":             row["turn_count"]      or 0,
            "input":             inp,
            "output":            out,
            "cost_usd":          cost,
            "duration_min":      dur,
            "premium_requests":  round(float(row["premium_requests"]), 2),
            "compaction_count":  int(row["compaction_count"]),
            "max_context_tokens": int(row["max_context_tokens"]),
        })

    return {
        "all_models":     all_models,
        "daily_by_model": daily_by_model,
        "sessions_all":   sessions,
        "generated_at":   datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _generate_csv(conn, params):
    """Generate CSV bytes for the filtered view (RFC 4180, NFR-08-B)."""
    where, vals = _filter_clause(params)
    cur = conn.execute("""
        SELECT
            COALESCE(model, 'unknown') AS model,
            COUNT(*)                     AS turns,
            SUM(input_tokens)            AS input_tokens,
            SUM(output_tokens)           AS output_tokens,
            SUM(cache_read_tokens)       AS cache_read,
            SUM(cache_creation_tokens)   AS cache_creation
        FROM turns
        {where}
        GROUP BY model
        ORDER BY input_tokens + output_tokens DESC
    """.format(where=where), vals)

    output = io.StringIO()
    writer = csv.writer(output, dialect="excel")
    writer.writerow([
        "Model", "Turns", "Input Tokens", "Output Tokens", "Est. Cost (USD)",
    ])

    totals = {"turns": 0, "input": 0, "output": 0, "cost": 0.0}
    for row in cur.fetchall():
        inp   = row["input_tokens"] or 0
        out   = row["output_tokens"] or 0
        cost  = estimate_cost(row["model"], inp, out,
                              row["cache_read"] or 0, row["cache_creation"] or 0)
        writer.writerow([row["model"], row["turns"], inp, out, format_cost(cost)])
        totals["turns"]  += row["turns"] or 0
        totals["input"]  += inp
        totals["output"] += out
        if cost is not None:
            totals["cost"] += cost

    writer.writerow([
        "TOTAL", totals["turns"], totals["input"], totals["output"], format_cost(totals["cost"]),
    ])
    return output.getvalue().encode("utf-8")


def _csv_filename(params):
    """Build a descriptive filename for the CSV export."""
    models = params.get("model", [])
    since  = params.get("since", [None])[0]
    until  = params.get("until", [None])[0]

    model_part = models[0] if len(models) == 1 else "all-models"
    if since and until:
        date_part = "{}_{}".format(since, until)
    elif since:
        date_part = "from-{}".format(since)
    elif until:
        date_part = "until-{}".format(until)
    else:
        date_part = "all-time"

    return "ghcp-usage_{}_{}.csv".format(date_part, model_part)


# ---------------------------------------------------------------------------
# Embedded dashboard HTML  (redesigned to match claude-usage visual style)
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GHCP Usage Dashboard</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg viewBox='0 0 512 416' xmlns='http://www.w3.org/2000/svg' fill='white' fill-rule='evenodd' clip-rule='evenodd'%3E%3Cpath fill-rule='nonzero' d='M181.33 266.143c0-11.497 9.32-20.818 20.818-20.818 11.498 0 20.819 9.321 20.819 20.818v38.373c0 11.497-9.321 20.818-20.819 20.818-11.497 0-20.818-9.32-20.818-20.818v-38.373zM308.807 245.325c-11.477 0-20.798 9.321-20.798 20.818v38.373c0 11.497 9.32 20.818 20.798 20.818 11.497 0 20.818-9.32 20.818-20.818v-38.373c0-11.497-9.32-20.818-20.818-20.818z'/%3E%3Cpath d='M512.002 246.393v57.384c-.02 7.411-3.696 14.638-9.67 19.011C431.767 374.444 344.695 416 256 416c-98.138 0-196.379-56.542-246.33-93.21-5.975-4.374-9.65-11.6-9.671-19.012v-57.384a35.347 35.347 0 016.857-20.922l15.583-21.085c8.336-11.312 20.757-14.31 33.98-14.31 4.988-56.953 16.794-97.604 45.024-127.354C155.194 5.77 226.56 0 256 0c29.441 0 100.807 5.77 154.557 62.722 28.19 29.75 40.036 70.401 45.025 127.354 13.263 0 25.602 2.936 33.958 14.31l15.583 21.127c4.476 6.077 6.878 13.345 6.878 20.88zm-97.666-26.075c-.677-13.058-11.292-18.19-22.338-21.824-11.64 7.309-25.848 10.183-39.46 10.183-14.454 0-41.432-3.47-63.872-25.869-5.667-5.625-9.527-14.454-12.155-24.247a212.902 212.902 0 00-20.469-1.088c-6.098 0-13.099.349-20.551 1.088-2.628 9.793-6.509 18.622-12.155 24.247-22.4 22.4-49.418 25.87-63.872 25.87-13.612 0-27.86-2.855-39.501-10.184-11.005 3.613-21.558 8.828-22.277 21.824-1.17 24.555-1.272 49.11-1.375 73.645-.041 12.318-.082 24.658-.288 36.976.062 7.166 4.374 13.818 10.882 16.774 52.97 24.124 103.045 36.278 149.137 36.278 46.01 0 96.085-12.154 149.014-36.278 6.508-2.956 10.84-9.608 10.881-16.774.637-36.832.124-73.809-1.642-110.62h.041zM107.521 168.97c8.643 8.623 24.966 14.392 42.56 14.392 13.448 0 39.03-2.874 60.156-24.329 9.28-8.951 15.05-31.35 14.413-54.079-.657-18.231-5.769-33.28-13.448-39.665-8.315-7.371-27.203-10.574-48.33-8.644-22.399 2.238-41.267 9.588-50.875 19.833-20.798 22.728-16.323 80.317-4.476 92.492zm130.556-56.008c.637 3.51.965 7.35 1.273 11.517 0 2.875 0 5.77-.308 8.952 6.406-.636 11.847-.636 16.959-.636s10.553 0 16.959.636c-.329-3.182-.329-6.077-.329-8.952.329-4.167.657-8.007 1.294-11.517-6.735-.637-12.812-.965-17.924-.965s-11.21.328-17.924.965zm49.275-8.008c-.637 22.728 5.133 45.128 14.413 54.08 21.105 21.454 46.708 24.328 60.155 24.328 17.596 0 33.918-5.769 42.561-14.392 11.847-12.175 16.322-69.764-4.476-92.492-9.608-10.245-28.476-17.595-50.875-19.833-21.127-1.93-40.015 1.273-48.33 8.644-7.679 6.385-12.791 21.434-13.448 39.665z'/%3E%3C/svg%3E">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0f1117; --card: #1a1d27; --border: #2a2d3a;
    --text: #e2e8f0; --muted: #8892a4; --accent: #4f8ef7;
    --green: #4ade80; --yellow: #fbbf24; --red: #f87171;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }
  header { background: var(--card); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  header h1 { font-size: 18px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }
  .meta { color: var(--muted); font-size: 12px; }
  #rescan-btn { background: var(--card); border: 1px solid var(--border); color: var(--muted); padding: 4px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
  #rescan-btn:hover { color: var(--text); border-color: var(--accent); }
  #rescan-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  #settings-btn { background: var(--card); border: 1px solid var(--border); color: var(--muted); padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 14px; line-height: 1; }
  #settings-btn:hover { color: var(--text); border-color: var(--accent); }
  /* Settings modal */
  #settings-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 1000; align-items: center; justify-content: center; }
  #settings-overlay.open { display: flex; }
  #settings-modal { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 28px 32px; min-width: 340px; max-width: 420px; width: 90%; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }
  #settings-modal h2 { font-size: 15px; font-weight: 600; margin-bottom: 20px; color: var(--text); }
  .setting-row { margin-bottom: 18px; }
  .setting-row label { display: block; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 6px; }
  .setting-row input { width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 7px 10px; border-radius: 6px; font-size: 14px; }
  .setting-row input:focus { outline: none; border-color: var(--accent); }
  .setting-row .hint { font-size: 11px; color: var(--muted); margin-top: 4px; }
  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 22px; }
  .modal-actions button { padding: 6px 18px; border-radius: 6px; border: 1px solid var(--border); cursor: pointer; font-size: 13px; }
  #settings-cancel { background: transparent; color: var(--muted); }
  #settings-cancel:hover { color: var(--text); }
  #settings-save { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
  #settings-save:hover { opacity: 0.88; }
  #quota-bar { background: var(--card); border-bottom: 1px solid var(--border); padding: 10px 24px; }
  #quota-inner { max-width: 1400px; margin: 0 auto; }
  .quota-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .quota-label { font-size: 14px; font-weight: 600; }
  .quota-pct { font-size: 14px; font-weight: 700; min-width: 48px; text-align: right; }
  .quota-track { flex: 1; min-width: 100px; background: #21262d; border-radius: 4px; height: 10px; overflow: hidden; }
  .quota-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
  .quota-sub { font-size: 12px; color: var(--muted); white-space: nowrap; }
  .quota-note { font-size: 11px; color: #6e7681; margin-top: 4px; }
  #filter-bar { background: var(--card); border-bottom: 1px solid var(--border); padding: 10px 24px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .filter-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); white-space: nowrap; }
  .filter-sep { width: 1px; height: 22px; background: var(--border); flex-shrink: 0; }
  #model-checkboxes { display: flex; flex-wrap: wrap; gap: 6px; }
  .model-cb-label { display: flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 20px; border: 1px solid var(--border); cursor: pointer; font-size: 12px; color: var(--muted); transition: border-color 0.15s, color 0.15s, background 0.15s; user-select: none; }
  .model-cb-label:hover { border-color: var(--accent); color: var(--text); }
  .model-cb-label.checked { background: rgba(79,142,247,0.12); border-color: var(--accent); color: var(--text); }
  .model-cb-label input { display: none; }
  .filter-btn { padding: 3px 10px; border-radius: 4px; border: 1px solid var(--border); background: transparent; color: var(--muted); font-size: 11px; cursor: pointer; white-space: nowrap; }
  .filter-btn:hover { border-color: var(--accent); color: var(--text); }
  .range-group { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; flex-shrink: 0; }
  .range-btn { padding: 4px 13px; background: transparent; border: none; border-right: 1px solid var(--border); color: var(--muted); font-size: 12px; cursor: pointer; transition: background 0.15s, color 0.15s; }
  .range-btn:last-child { border-right: none; }
  .range-btn:hover { background: rgba(255,255,255,0.04); color: var(--text); }
  .range-btn.active { background: rgba(79,142,247,0.15); color: var(--accent); font-weight: 600; }
  .container { max-width: 1400px; margin: 0 auto; padding: 24px; }
  .stats-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .stat-card .label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
  .stat-card .value { font-size: 22px; font-weight: 700; }
  .stat-card .sub { color: var(--muted); font-size: 11px; margin-top: 4px; }
  .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  .chart-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
  .chart-card.wide { grid-column: 1 / -1; }
  .chart-card h2 { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 16px; }
  .chart-wrap { position: relative; height: 240px; }
  .chart-wrap.tall { height: 300px; }
  .chart-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:4px; }
  .chart-header h2 { margin:0; }
  #filter-bar select { background:var(--card); border:1px solid var(--border); color:var(--muted); padding:3px 8px; border-radius:4px; font-size:12px; cursor:pointer; height:28px; }
  #filter-bar select:focus { outline:none; border-color:var(--accent); }
  .month-nav { display:flex; align-items:center; gap:6px; }
  .month-nav button { background:var(--card); border:1px solid var(--border); color:var(--muted); width:24px; height:24px; border-radius:4px; cursor:pointer; font-size:13px; line-height:1; }
  .month-nav button:hover { color:var(--text); border-color:var(--accent); }
  .month-nav button:disabled { opacity:0.3; cursor:not-allowed; }
  .month-nav span { font-size:12px; color:var(--muted); white-space:nowrap; min-width:90px; text-align:center; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 8px 12px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); border-bottom: 1px solid var(--border); white-space: nowrap; }
  th.sortable { cursor: pointer; user-select: none; }
  th.sortable:hover { color: var(--text); }
  .sort-icon { font-size: 9px; opacity: 0.8; }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,0.02); }
  .model-tag { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 11px; background: rgba(79,142,247,0.15); color: var(--accent); }
  .cost { color: var(--green); font-family: monospace; }
  .cost-na { color: var(--muted); font-family: monospace; font-size: 11px; }
  .num { font-family: monospace; text-align: right; }
  .muted { color: var(--muted); }
  .section-title { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }
  .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .section-header .section-title { margin-bottom: 0; }
  .export-btn { background: var(--card); border: 1px solid var(--border); color: var(--muted); padding: 3px 10px; border-radius: 5px; cursor: pointer; font-size: 11px; }
  .export-btn:hover { color: var(--text); border-color: var(--accent); }
  .table-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 24px; overflow-x: auto; }
  footer { border-top: 1px solid var(--border); padding: 20px 24px; margin-top: 8px; }
  .footer-content { max-width: 1400px; margin: 0 auto; }
  .footer-content p { color: var(--muted); font-size: 12px; line-height: 1.7; margin-bottom: 4px; }
  .footer-content a { color: var(--accent); text-decoration: none; }
  .footer-content a:hover { text-decoration: underline; }
  @media (max-width: 768px) { .charts-grid { grid-template-columns: 1fr; } .chart-card.wide { grid-column: 1; } }
</style>
</head>
<body>
<header>
  <h1><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 416" fill="white" fill-rule="evenodd" clip-rule="evenodd" height="22" width="27" style="flex-shrink:0"><path fill-rule="nonzero" d="M181.33 266.143c0-11.497 9.32-20.818 20.818-20.818 11.498 0 20.819 9.321 20.819 20.818v38.373c0 11.497-9.321 20.818-20.819 20.818-11.497 0-20.818-9.32-20.818-20.818v-38.373zM308.807 245.325c-11.477 0-20.798 9.321-20.798 20.818v38.373c0 11.497 9.32 20.818 20.798 20.818 11.497 0 20.818-9.32 20.818-20.818v-38.373c0-11.497-9.32-20.818-20.818-20.818z"/><path d="M512.002 246.393v57.384c-.02 7.411-3.696 14.638-9.67 19.011C431.767 374.444 344.695 416 256 416c-98.138 0-196.379-56.542-246.33-93.21-5.975-4.374-9.65-11.6-9.671-19.012v-57.384a35.347 35.347 0 016.857-20.922l15.583-21.085c8.336-11.312 20.757-14.31 33.98-14.31 4.988-56.953 16.794-97.604 45.024-127.354C155.194 5.77 226.56 0 256 0c29.441 0 100.807 5.77 154.557 62.722 28.19 29.75 40.036 70.401 45.025 127.354 13.263 0 25.602 2.936 33.958 14.31l15.583 21.127c4.476 6.077 6.878 13.345 6.878 20.88zm-97.666-26.075c-.677-13.058-11.292-18.19-22.338-21.824-11.64 7.309-25.848 10.183-39.46 10.183-14.454 0-41.432-3.47-63.872-25.869-5.667-5.625-9.527-14.454-12.155-24.247a212.902 212.902 0 00-20.469-1.088c-6.098 0-13.099.349-20.551 1.088-2.628 9.793-6.509 18.622-12.155 24.247-22.4 22.4-49.418 25.87-63.872 25.87-13.612 0-27.86-2.855-39.501-10.184-11.005 3.613-21.558 8.828-22.277 21.824-1.17 24.555-1.272 49.11-1.375 73.645-.041 12.318-.082 24.658-.288 36.976.062 7.166 4.374 13.818 10.882 16.774 52.97 24.124 103.045 36.278 149.137 36.278 46.01 0 96.085-12.154 149.014-36.278 6.508-2.956 10.84-9.608 10.881-16.774.637-36.832.124-73.809-1.642-110.62h.041zM107.521 168.97c8.643 8.623 24.966 14.392 42.56 14.392 13.448 0 39.03-2.874 60.156-24.329 9.28-8.951 15.05-31.35 14.413-54.079-.657-18.231-5.769-33.28-13.448-39.665-8.315-7.371-27.203-10.574-48.33-8.644-22.399 2.238-41.267 9.588-50.875 19.833-20.798 22.728-16.323 80.317-4.476 92.492zm130.556-56.008c.637 3.51.965 7.35 1.273 11.517 0 2.875 0 5.77-.308 8.952 6.406-.636 11.847-.636 16.959-.636s10.553 0 16.959.636c-.329-3.182-.329-6.077-.329-8.952.329-4.167.657-8.007 1.294-11.517-6.735-.637-12.812-.965-17.924-.965s-11.21.328-17.924.965zm49.275-8.008c-.637 22.728 5.133 45.128 14.413 54.08 21.105 21.454 46.708 24.328 60.155 24.328 17.596 0 33.918-5.769 42.561-14.392 11.847-12.175 16.322-69.764-4.476-92.492-9.608-10.245-28.476-17.595-50.875-19.833-21.127-1.93-40.015 1.273-48.33 8.644-7.679 6.385-12.791 21.434-13.448 39.665z"/></svg> GHCP Usage Dashboard</h1>
  <div class="meta" id="meta">Loading&hellip;</div>
  <div style="display:flex;gap:6px;align-items:center">
    <button id="rescan-btn" onclick="triggerRescan()" title="Re-scan Copilot logs and refresh">&#x21bb; Rescan</button>
    <button id="settings-btn" onclick="openSettings()" title="Settings">&#x2699;&#xFE0F;</button>
  </div>
</header>
<!-- Settings modal -->
<div id="settings-overlay" onclick="closeSettingsIfOutside(event)">
  <div id="settings-modal">
    <h2>&#x2699; Settings</h2>
    <div class="setting-row">
      <label>Data Refresh Interval (seconds)</label>
      <input type="number" id="s-refresh" min="10" max="3600" value="__REFRESH_INTERVAL_S__">
      <div class="hint">Controls both UI auto-refresh and background JSONL scan. Min 10s.</div>
    </div>
    <div class="setting-row">
      <label>Monthly Premium Request Limit</label>
      <input type="number" id="s-quota" min="1" max="100000" value="__QUOTA_LIMIT__">
      <div class="hint">Used for the quota bar percentage. Default is 100 (Copilot Individual/Business).</div>
    </div>
    <div class="setting-row">
      <label>Data Source</label>
      <select id="s-source" style="width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:7px 10px;border-radius:6px;font-size:14px">
        <option value="both">All JSONL logs</option>
        <option value="jsonl">JSONL logs only (excludes legacy proxy sessions)</option>
      </select>
      <div class="hint">Controls what data is displayed and whether JSONL scanning runs.</div>
    </div>
    <div class="setting-row">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
        <label style="margin:0">Pricing</label>
        <div style="display:flex;gap:4px">
          <button onclick="setPricingTab('url')" id="ptab-url" style="padding:2px 10px;border-radius:4px;border:1px solid var(--border);background:rgba(79,142,247,0.15);color:var(--accent);font-size:11px;cursor:pointer">Source</button>
          <button onclick="setPricingTab('overrides')" id="ptab-overrides" style="padding:2px 10px;border-radius:4px;border:1px solid var(--border);background:transparent;color:var(--muted);font-size:11px;cursor:pointer">Overrides</button>
        </div>
      </div>
      <!-- Source tab -->
      <div id="pricing-tab-url">
        <div style="background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px 10px;font-size:12px;font-family:monospace;color:var(--muted);word-break:break-all" id="s-pricing-url-display"></div>
        <div class="hint">Pricing reference used in the footer. Built-in table last updated <strong>__PRICING_DATE__</strong>. Read-only &mdash; update <code style="color:#79c0ff">src/pricing.py</code> to change rates.</div>
      </div>
      <!-- Overrides tab -->
      <div id="pricing-tab-overrides" style="display:none">
        <div style="display:flex;justify-content:flex-end;margin-bottom:4px">
          <button onclick="resetPriceOverrides()" style="padding:2px 9px;border-radius:4px;border:1px solid var(--border);background:transparent;color:var(--red);font-size:11px;cursor:pointer">&#x21BA; Reset to built-in</button>
        </div>
        <textarea id="s-price-overrides" rows="5" style="width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:7px 10px;border-radius:6px;font-size:12px;font-family:monospace;resize:vertical" placeholder='{&#10;  "claude-opus": [15.0, 75.0],&#10;  "gpt-4o": [2.50, 10.00]&#10;}'></textarea>
        <div class="hint">Override per-model prices ($/MTok). Substring-matched. Format: <code style="color:#79c0ff">{"model-key": [input, output]}</code>. Empty = use built-in table.</div>
      </div>
    </div>
    <div class="modal-actions">
      <button id="settings-cancel" onclick="closeSettings()">Cancel</button>
      <button id="settings-save" onclick="saveSettings()">Save</button>
    </div>
  </div>
</div>
<div id="quota-bar"><div id="quota-inner"><span style="color:var(--muted);font-size:13px">Loading quota&hellip;</span></div></div>
<div id="filter-bar">
  <div class="filter-label">View</div>
  <select id="daily-mode-select" onchange="setChartDailyMode(this.value)">
    <option value="range">Date Range</option>
    <option value="monthly">Monthly</option>
  </select>
  <div class="month-nav" id="month-nav" style="display:none">
    <button id="month-prev" onclick="shiftMonth(-1)" title="Previous month">&#8592;</button>
    <span id="month-nav-label"></span>
    <button id="month-next" onclick="shiftMonth(1)" title="Next month">&#8594;</button>
  </div>
  <div class="filter-sep" id="range-sep"></div>
  <div class="filter-label" id="range-label">Range</div>
  <div class="range-group" id="range-group">
    <button class="range-btn" data-range="7d"  onclick="setRange('7d')">7d</button>
    <button class="range-btn" data-range="30d" onclick="setRange('30d')">30d</button>
    <button class="range-btn" data-range="90d" onclick="setRange('90d')">90d</button>
    <button class="range-btn" data-range="all" onclick="setRange('all')">All</button>
  </div>
  <div class="filter-sep"></div>
  <div class="filter-label">Models</div>
  <div id="model-checkboxes"></div>
  <button class="filter-btn" onclick="selectAllModels()">All</button>
  <button class="filter-btn" onclick="clearAllModels()">None</button>
</div>
<div class="container">
  <div class="stats-row" id="stats-row"></div>
  <div class="charts-grid">
    <div class="chart-card wide">
      <div class="chart-header">
        <h2 id="daily-title">Daily Turns by Model</h2>
      </div>
      <div class="chart-wrap tall"><canvas id="chart-daily"></canvas></div>
    </div>
    <div class="chart-card">
      <h2>By Model</h2>
      <div class="chart-wrap"><canvas id="chart-model"></canvas></div>
    </div>
    <div class="chart-card">
      <h2>Top Projects by Turns</h2>
      <div class="chart-wrap"><canvas id="chart-project"></canvas></div>
    </div>
  </div>
  <div class="table-card">
    <div class="section-title">Cost by Model</div>
    <table>
      <thead><tr>
        <th>Model</th>
        <th class="sortable" onclick="setModelSort('turns')">Turns <span class="sort-icon" id="msort-turns"></span></th>
        <th class="sortable" onclick="setModelSort('input')">Input Tok <span class="sort-icon" id="msort-input"></span></th>
        <th class="sortable" onclick="setModelSort('output')">Output Tok <span class="sort-icon" id="msort-output"></span></th>
        <th class="sortable" onclick="setModelSort('cost')">Est. Cost <span class="sort-icon" id="msort-cost"></span></th>
      </tr></thead>
      <tbody id="model-cost-body"></tbody>
    </table>
  </div>
  <div class="table-card">
    <div class="section-header">
      <div class="section-title">Recent Sessions</div>
      <button class="export-btn" onclick="exportSessionsCSV()" title="Export filtered sessions to CSV">&#x2913; CSV</button>
    </div>
    <table>
      <thead><tr>
        <th>Session</th>
        <th>Project</th>
        <th>Model</th>
        <th class="sortable" onclick="setSessionSort('last')">Last Active <span class="sort-icon" id="sort-last"></span></th>
        <th class="sortable" onclick="setSessionSort('turns')">Turns <span class="sort-icon" id="sort-turns"></span></th>
        <th class="sortable" onclick="setSessionSort('premium_requests')">Prem.&nbsp;Req <span class="sort-icon" id="sort-premium_requests"></span></th>
        <th class="sortable" onclick="setSessionSort('compaction_count')">Ctx&nbsp;Resets <span class="sort-icon" id="sort-compaction_count"></span></th>
        <th class="sortable" onclick="setSessionSort('max_context_tokens')">Peak&nbsp;Ctx <span class="sort-icon" id="sort-max_context_tokens"></span></th>
        <th class="sortable" onclick="setSessionSort('input')">Input <span class="sort-icon" id="sort-input"></span></th>
        <th class="sortable" onclick="setSessionSort('output')">Output <span class="sort-icon" id="sort-output"></span></th>
        <th class="sortable" onclick="setSessionSort('cost_usd')">Est. Cost <span class="sort-icon" id="sort-cost_usd"></span></th>
      </tr></thead>
      <tbody id="sessions-body"></tbody>
    </table>
  </div>
  <div class="table-card">
    <div class="section-header">
      <div class="section-title">Cost by Project</div>
      <button class="export-btn" onclick="exportProjectsCSV()" title="Export projects to CSV">&#x2913; CSV</button>
    </div>
    <table>
      <thead><tr>
        <th>Project</th>
        <th class="sortable" onclick="setProjectSort('sessions')">Sessions <span class="sort-icon" id="psort-sessions"></span></th>
        <th class="sortable" onclick="setProjectSort('turns')">Turns <span class="sort-icon" id="psort-turns"></span></th>
        <th class="sortable" onclick="setProjectSort('cost')">Est. Cost <span class="sort-icon" id="psort-cost"></span></th>
      </tr></thead>
      <tbody id="project-cost-body"></tbody>
    </table>
  </div>
</div>
<footer>
  <div class="footer-content">
    <p>Cost estimates based on public API pricing as of __PRICING_DATE__. Estimates only &mdash; not your Copilot subscription cost. <a href="__PRICING_URL__" target="_blank" rel="noopener noreferrer">Pricing source</a></p>
    <p>Data scanned from local VS Code Copilot logs &mdash; no data leaves your machine.</p>
  </div>
</footer>

<script>
// ── Helpers ──────────────────────────────────────────────────────────────────
function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s == null ? '' : s);
  return d.innerHTML;
}

// ── State ────────────────────────────────────────────────────────────────────
let rawData = null;
let selectedModels = new Set();
let selectedRange = 'all';
let selectedMonth = null;   // 'YYYY-MM', null = current month
let chartDailyMode = 'range'; // 'range' | 'monthly'
let charts = {};
let sessionSortCol = 'last', sessionSortDir = 'desc';
let modelSortCol   = 'cost', modelSortDir   = 'desc';
let projectSortCol = 'cost', projectSortDir = 'desc';
let lastFilteredSessions = [];
let lastByProject = [];

// ── Chart palette ─────────────────────────────────────────────────────────────
const PALETTE = ['#4f8ef7','#4ade80','#fbbf24','#f87171','#a78bfa','#34d399','#60a5fa','#fb7185','#d97757','#38bdf8'];

// ── Range ─────────────────────────────────────────────────────────────────────
const RANGE_LABELS = { '7d': 'Last 7 Days', '30d': 'Last 30 Days', '90d': 'Last 90 Days', 'all': 'All Time' };
const RANGE_TICKS  = { '7d': 7, '30d': 15, '90d': 13, 'all': 12 };

function getRangeCutoff(range) {
  if (range === 'all') return null;
  const days = { '7d': 7, '30d': 30, '90d': 90 }[range];
  const d = new Date(); d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

// ── Month navigation ──────────────────────────────────────────────────────────
function currentYearMonth() {
  const now = new Date();
  return now.toISOString().slice(0, 7);
}
function monthLabel(ym) {
  const [y, m] = ym.split('-').map(Number);
  return new Date(y, m - 1, 1).toLocaleString('default', { month: 'long', year: 'numeric' });
}
function availableMonths() {
  if (!rawData) return [];
  const s = new Set(rawData.daily_by_model.map(r => r.day.slice(0,7)));
  return [...s].sort();
}
function shiftMonth(dir) {
  const months = availableMonths();
  if (!months.length) return;
  const cur = selectedMonth || currentYearMonth();
  let idx = months.indexOf(cur);
  if (idx === -1) idx = months.length - 1;
  idx = Math.max(0, Math.min(months.length - 1, idx + dir));
  selectedMonth = months[idx];
  applyFilter();
}
function updateMonthNavButtons() {
  const months = availableMonths();
  const cur = selectedMonth || currentYearMonth();
  const idx = months.indexOf(cur);
  const prevBtn = document.getElementById('month-prev');
  const nextBtn = document.getElementById('month-next');
  if (prevBtn) prevBtn.disabled = idx <= 0;
  if (nextBtn) nextBtn.disabled = idx >= months.length - 1 || idx === -1;
  const lbl = document.getElementById('month-nav-label');
  if (lbl) lbl.textContent = monthLabel(cur);
}
function setChartDailyMode(mode) {
  chartDailyMode = mode;
  document.getElementById('daily-mode-select').value = mode;
  const isMonthly = mode === 'monthly';
  document.getElementById('month-nav').style.display = isMonthly ? 'flex' : 'none';
  document.getElementById('range-sep').style.display = isMonthly ? 'none' : '';
  document.getElementById('range-label').style.display = isMonthly ? 'none' : '';
  document.getElementById('range-group').style.display = isMonthly ? 'none' : '';
  applyFilter();
}
function readURLRange() {
  const p = new URLSearchParams(window.location.search).get('range');
  return ['7d','30d','90d','all'].includes(p) ? p : '30d';
}
function setRange(r) {
  selectedRange = r;
  document.querySelectorAll('.range-btn').forEach(b => b.classList.toggle('active', b.dataset.range === r));
  updateURL(); applyFilter(); // month chart is independent of range filter
}

// ── Model filter ──────────────────────────────────────────────────────────────
function readURLModels(all) {
  const p = new URLSearchParams(window.location.search).get('models');
  if (!p) return new Set(all);
  const s = new Set(p.split(',').map(x => x.trim()).filter(Boolean));
  return new Set(all.filter(m => s.has(m)));
}
function isAllSelected(all) {
  return all.length === selectedModels.size && all.every(m => selectedModels.has(m));
}
function buildFilterUI(all) {
  selectedModels = readURLModels(all);
  document.getElementById('model-checkboxes').innerHTML = all.map(m => {
    const chk = selectedModels.has(m);
    return `<label class="model-cb-label ${chk ? 'checked' : ''}" data-model="${esc(m)}">` +
           `<input type="checkbox" value="${esc(m)}" ${chk ? 'checked' : ''} onchange="onModelToggle(this)">${esc(m)}</label>`;
  }).join('');
}
function onModelToggle(cb) {
  const lbl = cb.closest('label');
  if (cb.checked) { selectedModels.add(cb.value); lbl.classList.add('checked'); }
  else            { selectedModels.delete(cb.value); lbl.classList.remove('checked'); }
  updateURL(); applyFilter();
}
function selectAllModels() {
  document.querySelectorAll('#model-checkboxes input').forEach(cb => {
    cb.checked = true; selectedModels.add(cb.value); cb.closest('label').classList.add('checked');
  }); updateURL(); applyFilter();
}
function clearAllModels() {
  document.querySelectorAll('#model-checkboxes input').forEach(cb => {
    cb.checked = false; selectedModels.delete(cb.value); cb.closest('label').classList.remove('checked');
  }); updateURL(); applyFilter();
}

// ── URL persistence ───────────────────────────────────────────────────────────
function updateURL() {
  const all = Array.from(document.querySelectorAll('#model-checkboxes input')).map(cb => cb.value);
  const p = new URLSearchParams();
  if (selectedRange !== '30d') p.set('range', selectedRange);
  if (!isAllSelected(all)) p.set('models', Array.from(selectedModels).join(','));
  history.replaceState(null, '', p.toString() ? '?' + p.toString() : window.location.pathname);
}

// ── Sorting ───────────────────────────────────────────────────────────────────
function cmp(a, b, col, dir) {
  const av = a[col] ?? 0, bv = b[col] ?? 0;
  if (typeof av === 'string') return dir === 'desc' ? bv.localeCompare(av) : av.localeCompare(bv);
  return dir === 'desc' ? bv - av : av - bv;
}
function sortSessions(arr) { return [...arr].sort((a,b) => cmp(a,b,sessionSortCol,sessionSortDir)); }
function sortModels(arr)   { return [...arr].sort((a,b) => cmp(a,b,modelSortCol,modelSortDir)); }
function sortProjects(arr) { return [...arr].sort((a,b) => cmp(a,b,projectSortCol,projectSortDir)); }

function setSessionSort(c) {
  sessionSortDir = sessionSortCol === c ? (sessionSortDir==='desc'?'asc':'desc') : 'desc';
  sessionSortCol = c; updateSortIcons(); renderSessionsTable(sortSessions(lastFilteredSessions).slice(0,25));
}
function setModelSort(c) {
  modelSortDir = modelSortCol === c ? (modelSortDir==='desc'?'asc':'desc') : 'desc';
  modelSortCol = c; updateSortIcons(); applyFilter();
}
function setProjectSort(c) {
  projectSortDir = projectSortCol === c ? (projectSortDir==='desc'?'asc':'desc') : 'desc';
  projectSortCol = c; updateSortIcons(); renderProjectCostTable(sortProjects(lastByProject).slice(0,25));
}
function updateSortIcons() {
  document.querySelectorAll('.sort-icon').forEach(el => el.textContent = '');
  const si = document.getElementById('sort-' + sessionSortCol);
  if (si) si.textContent = sessionSortDir === 'desc' ? ' \u25bc' : ' \u25b2';
  const mi = document.getElementById('msort-' + modelSortCol);
  if (mi) mi.textContent = modelSortDir === 'desc' ? ' \u25bc' : ' \u25b2';
  const pi = document.getElementById('psort-' + projectSortCol);
  if (pi) pi.textContent = projectSortDir === 'desc' ? ' \u25bc' : ' \u25b2';
}

// ── Number formatting ─────────────────────────────────────────────────────────
function fmt(n) {
  if (n >= 1e9) return (n/1e9).toFixed(2)+'B';
  if (n >= 1e6) return (n/1e6).toFixed(2)+'M';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return String(n);
}
function fmtCost(c)    { return (c == null || c === 0) ? 'n/a' : '$' + c.toFixed(4); }
function fmtCostBig(c) { return (c == null || c === 0) ? '$0.00' : '$' + c.toFixed(2); }
function fmtPct(n, d)  { return d > 0 ? (100*n/d).toFixed(1)+'%' : '\u2014'; }

// ── Filter & aggregate ────────────────────────────────────────────────────────
function applyFilter() {
  if (!rawData) return;
  const isMonthly = chartDailyMode === 'monthly';
  const ym = selectedMonth || currentYearMonth();
  const cutoff = getRangeCutoff(selectedRange);

  const sessions = rawData.sessions_all.filter(s => {
    if (!selectedModels.has(s.model)) return false;
    if (isMonthly) return s.last_date.slice(0,7) === ym;
    return !cutoff || s.last_date >= cutoff;
  });
  const daily = rawData.daily_by_model.filter(r => {
    if (!selectedModels.has(r.model)) return false;
    if (isMonthly) return r.day.slice(0,7) === ym;
    return !cutoff || r.day >= cutoff;
  });

  // Daily chart data — either range mode or monthly mode
  let dailyRows, modelsInDaily;
  if (isMonthly) {
    const [ymYear, ymMon] = ym.split('-').map(Number);
    const daysInMonth = new Date(ymYear, ymMon, 0).getDate();
    const dayMap = {};
    for (let d2 = 1; d2 <= daysInMonth; d2++) {
      const key = ym + '-' + String(d2).padStart(2,'0');
      dayMap[key] = { day: key };
    }
    for (const r of daily) {
      if (!dayMap[r.day]) dayMap[r.day] = { day: r.day };
      dayMap[r.day][r.model] = (dayMap[r.day][r.model] || 0) + r.turns;
    }
    dailyRows = Object.values(dayMap).sort((a,b) => a.day.localeCompare(b.day));
    modelsInDaily = [...new Set(daily.map(r => r.model))];
  } else {
    // Range mode — same as original behaviour
    const dayMap = {};
    if (cutoff) {
      const cur2 = new Date(cutoff), end = new Date();
      while (cur2 <= end) {
        const key = cur2.toISOString().slice(0, 10);
        dayMap[key] = { day: key };
        cur2.setDate(cur2.getDate() + 1);
      }
    }
    for (const r of daily) {
      if (!dayMap[r.day]) dayMap[r.day] = { day: r.day };
      dayMap[r.day][r.model] = (dayMap[r.day][r.model] || 0) + r.turns;
    }
    dailyRows = Object.values(dayMap).sort((a,b) => a.day.localeCompare(b.day));
    modelsInDaily = [...new Set(daily.map(r => r.model))];
  }

  // By model (aggregate from sessions)
  const modelMap = {};
  for (const s of sessions) {
    if (!modelMap[s.model]) modelMap[s.model] = {model:s.model,turns:0,input:0,output:0,cost:0,sessions:0,premium_requests:0,compaction_count:0};
    const m = modelMap[s.model];
    m.turns+=s.turns;
    m.input+=s.input; m.output+=s.output; m.cost+=(s.cost_usd||0); m.sessions++;
    m.premium_requests+=(s.premium_requests||0);
    m.compaction_count+=(s.compaction_count||0);
  }
  const byModel = Object.values(modelMap).map(m => ({
    ...m, sessions: m.sessions
  })).sort((a,b) => b.turns-a.turns);

  // By project
  const projMap = {};
  for (const s of sessions) {
    if (!projMap[s.project]) projMap[s.project] = {project:s.project,sessions:0,turns:0,cost:0};
    const p = projMap[s.project];
    p.sessions++; p.turns+=s.turns; p.cost+=(s.cost_usd||0);
  }
  const byProject = Object.values(projMap).sort((a,b) => b.turns-a.turns);

  // Totals
  const T = {
    sessions:         sessions.length,
    turns:            byModel.reduce((s,m)=>s+m.turns,0),
    input:            byModel.reduce((s,m)=>s+m.input,0),
    output:           byModel.reduce((s,m)=>s+m.output,0),
    cost:             byModel.reduce((s,m)=>s+m.cost,0),
    premium_requests:  byModel.reduce((s,m)=>s+(m.premium_requests||0),0),
    compaction_count:  sessions.reduce((s,r)=>s+(r.compaction_count||0),0),
  };

  if (isMonthly) {
    document.getElementById('daily-title').textContent = 'Daily Turns \u2014 ' + monthLabel(ym);
    updateMonthNavButtons();
  } else {
    document.getElementById('daily-title').textContent = 'Daily Turns by Model \u2014 ' + RANGE_LABELS[selectedRange];
  }
  renderStats(T);
  renderDailyChart(dailyRows, modelsInDaily);
  renderModelChart(byModel);
  renderProjectChart(byProject);
  lastFilteredSessions = sortSessions(sessions);
  lastByProject = sortProjects(byProject);
  renderSessionsTable(lastFilteredSessions.slice(0,25));
  renderModelCostTable(byModel);
  renderProjectCostTable(lastByProject.slice(0,25));
  updateSortIcons();
}

// ── Stats cards ───────────────────────────────────────────────────────────────
function renderStats(T) {
  const rl = RANGE_LABELS[selectedRange].toLowerCase();
  const stats = [
    {label:'Sessions',          value:T.sessions.toLocaleString(),    sub:rl},
    {label:'Turns',             value:fmt(T.turns),                   sub:rl},
    {label:'Premium Requests',  value:T.premium_requests.toLocaleString(undefined,{maximumFractionDigits:1}), sub:'quota consumed', color:'var(--yellow)'},
    {label:'Ctx Resets',        value:T.compaction_count.toLocaleString(), sub:'context compactions', color:'var(--orange, #f97316)'},
    {label:'Input Tokens',      value:fmt(T.input),                   sub:rl},
    {label:'Output Tokens',     value:fmt(T.output),                  sub:rl},
    {label:'Est. Cost',         value:fmtCostBig(T.cost),             sub:'API pricing', color:'var(--green)'},
  ];
  document.getElementById('stats-row').innerHTML = stats.map(s =>
    `<div class="stat-card"><div class="label">${esc(s.label)}</div>` +
    `<div class="value"${s.color?` style="color:${s.color}"`:''}>${esc(s.value)}</div>` +
    (s.sub?`<div class="sub">${esc(s.sub)}</div>`:'') + `</div>`
  ).join('');
}

// ── Charts ────────────────────────────────────────────────────────────────────
function renderDailyChart(rows, models) {
  if (charts.daily) { charts.daily.destroy(); charts.daily = null; }
  const ctx = document.getElementById('chart-daily').getContext('2d');
  if (!rows.length) return;
  charts.daily = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: rows.map(r => r.day),
      datasets: models.map((m,i) => ({
        label: m, stack: 'turns',
        data: rows.map(r => r[m]||0),
        backgroundColor: PALETTE[i % PALETTE.length],
      }))
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ labels:{ color:'#8892a4', boxWidth:12 } } },
      scales:{
        x:{ ticks:{ color:'#8892a4', maxTicksLimit: chartDailyMode==='monthly'?31:RANGE_TICKS[selectedRange], callback(v){ const lbl=this.getLabelForValue(v); return (lbl&&chartDailyMode==='monthly')?lbl.slice(8):lbl||v; } }, grid:{ color:'#2a2d3a' } },
        y:{ ticks:{ color:'#8892a4', callback:v=>fmt(v) }, grid:{ color:'#2a2d3a' } },
      }
    }
  });
}
function renderModelChart(byModel) {
  const ctx = document.getElementById('chart-model').getContext('2d');
  if (charts.model) charts.model.destroy();
  if (!byModel.length) return;
  charts.model = new Chart(ctx, {
    type:'doughnut',
    data:{
      labels: byModel.map(m=>m.model),
      datasets:[{ data:byModel.map(m=>m.turns), backgroundColor:PALETTE, borderWidth:2, borderColor:'#1a1d27' }]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{
        legend:{ position:'bottom', labels:{ color:'#8892a4', boxWidth:12, font:{size:11} } },
        tooltip:{ callbacks:{ label:c=>` ${c.label}: ${fmt(c.raw)} turns` } }
      }
    }
  });
}
function renderProjectChart(byProject) {
  const top = byProject.slice(0,10);
  const ctx = document.getElementById('chart-project').getContext('2d');
  if (charts.project) charts.project.destroy();
  if (!top.length) return;
  charts.project = new Chart(ctx, {
    type:'bar',
    data:{
      labels: top.map(p=>p.project.length>22?'\u2026'+p.project.slice(-20):p.project),
      datasets:[{ label:'Turns', data:top.map(p=>p.turns), backgroundColor:PALETTE[0] }]
    },
    options:{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ display:false } },
      scales:{
        x:{ ticks:{ color:'#8892a4', callback:v=>fmt(v) }, grid:{ color:'#2a2d3a' } },
        y:{ ticks:{ color:'#8892a4', font:{size:11} }, grid:{ color:'#2a2d3a' } },
      }
    }
  });
}

// ── Tables ────────────────────────────────────────────────────────────────────
function renderModelCostTable(byModel) {
  document.getElementById('model-cost-body').innerHTML = sortModels(byModel).map(m => {
    const cc = m.cost>0 ? `<td class="cost num">${esc(fmtCost(m.cost))}</td>` : `<td class="cost-na num">n/a</td>`;
    return `<tr><td><span class="model-tag">${esc(m.model)}</span></td>` +
      `<td class="num">${fmt(m.turns)}</td>` +
      `<td class="num">${fmt(m.input)}</td><td class="num">${fmt(m.output)}</td>${cc}</tr>`;
  }).join('');
}
function renderSessionsTable(sessions) {
  document.getElementById('sessions-body').innerHTML = sessions.map(s => {
    const cc = s.cost_usd>0 ? `<td class="cost num">${esc(fmtCost(s.cost_usd))}</td>` : `<td class="cost-na num">n/a</td>`;
    return `<tr>` +
      `<td class="muted" style="font-family:monospace">${esc(s.session_id)}&hellip;</td>` +
      `<td>${esc(s.project)}</td>` +
      `<td><span class="model-tag">${esc(s.model)}</span></td>` +
      `<td class="muted">${esc(s.last)}</td>` +
      `<td class="num">${s.turns}</td>` +
      `<td class="num" style="color:var(--yellow)">${(s.premium_requests||0).toLocaleString(undefined,{maximumFractionDigits:1})}</td>` +
      `<td class="num" style="color:${(s.compaction_count||0)>0?'var(--orange,#f97316)':'inherit'}">${s.compaction_count||0}</td>` +
      `<td class="num muted">${fmt(s.max_context_tokens||0)}</td>` +
      `<td class="num">${fmt(s.input)}</td><td class="num">${fmt(s.output)}</td>${cc}</tr>`;
  }).join('');
}
function renderProjectCostTable(byProject) {
  document.getElementById('project-cost-body').innerHTML = sortProjects(byProject).map(p =>
    `<tr><td>${esc(p.project)}</td><td class="num">${p.sessions}</td>` +
    `<td class="num">${fmt(p.turns)}</td>` +
    `<td class="cost num">${esc(fmtCost(p.cost))}</td></tr>`
  ).join('');
}

// ── CSV export ────────────────────────────────────────────────────────────────
function csvField(v) {
  const s = String(v==null?'':v);
  return (s.includes(',')||s.includes('"')||s.includes('\n')) ? '"'+s.replace(/"/g,'""')+'"' : s;
}
function csvTs() {
  const d=new Date();
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')
    +'_'+String(d.getHours()).padStart(2,'0')+String(d.getMinutes()).padStart(2,'0');
}
function downloadCSV(name, hdr, rows) {
  const lines = [hdr.map(csvField).join(','),...rows.map(r=>r.map(csvField).join(','))];
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/csv;charset=utf-8;'}));
  a.download = name+'_'+csvTs()+'.csv'; a.click(); URL.revokeObjectURL(a.href);
}
function exportSessionsCSV() {
  downloadCSV('ghcp-sessions',
    ['Session','Project','Model','Last Active','Turns','Premium Requests','Ctx Resets','Peak Context Tokens','Input Tokens','Output Tokens','Est. Cost USD'],
    lastFilteredSessions.map(s=>[s.session_id,s.project,s.model,s.last,s.turns,(s.premium_requests||0).toFixed(2),(s.compaction_count||0),(s.max_context_tokens||0),s.input,s.output,(s.cost_usd||0).toFixed(6)])
  );
}
function exportProjectsCSV() {
  downloadCSV('ghcp-projects',
    ['Project','Sessions','Turns','Est. Cost USD'],
    lastByProject.map(p=>[p.project,p.sessions,p.turns,p.cost.toFixed(6)])
  );
}

// ── Rescan ────────────────────────────────────────────────────────────────────
async function triggerRescan() {
  const btn = document.getElementById('rescan-btn');
  btn.disabled = true; btn.textContent = '\u21bb Scanning\u2026';
  try {
    const r = await fetch('/api/rescan', {method:'POST'});
    const d = await r.json();
    btn.textContent = d.error ? '\u21bb Error' : `\u21bb Done (${d.new} new)`;
    await loadData();
  } catch(e) { btn.textContent = '\u21bb Error'; console.error(e); }
  setTimeout(() => { btn.textContent = '\u21bb Rescan'; btn.disabled = false; }, 4000);
}

// ── Quota ─────────────────────────────────────────────────────────────────────
async function loadQuota() {
  const c = document.getElementById('quota-inner');
  try {
    const d = await (await fetch('/api/quota')).json();
    const pct = d.percent, w = Math.min(100,pct);
    const color = pct>=100?'var(--red)':pct>=80?'var(--yellow)':'var(--green)';
    const remStr = d.over_limit
      ? `<span style="color:var(--red)">${(d.used-d.limit).toLocaleString(undefined,{maximumFractionDigits:1})} over limit</span>`
      : `<span class="quota-sub">${d.remaining.toLocaleString(undefined,{maximumFractionDigits:1})} remaining</span>`;
    c.innerHTML =
      `<div class="quota-row">` +
      `<span class="quota-label">${esc(d.year_month)} &mdash; ${d.used.toLocaleString(undefined,{maximumFractionDigits:1})} / ${d.limit.toLocaleString()} premium requests</span>` +
      `<span class="quota-pct" style="color:${color}">${pct}%</span>` +
      `<div class="quota-track"><div class="quota-fill" style="width:${w}%;background:${color}"></div></div>` +
      `${remStr}</div>` +
      `<div class="quota-note">${esc(d.turns)} chat turns this month (turns &times; model multiplier = premium requests). Set <code style="color:#79c0ff">GHCP_QUOTA</code> env var to adjust limit (default __DEFAULT_QUOTA__).</div>`;
  } catch(e) { c.innerHTML = '<span style="color:var(--muted)">Quota unavailable</span>'; }
}

// ── Data loading ──────────────────────────────────────────────────────────────
async function loadData() {
  try {
    const d = await (await fetch('/api/data')).json();
    if (d.error) {
      document.body.innerHTML = `<div style="padding:40px;color:var(--red)">${esc(d.error)}</div>`;
      return;
    }
    _lastUpdated = 'Updated: ' + d.generated_at.replace('T',' ');
    _countdownSecs = Math.round(_refreshInterval / 1000);
    _updateMetaCountdown();
    const first = rawData === null;
    rawData = d;
    if (first) {
      selectedRange = readURLRange();
      document.querySelectorAll('.range-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.range === selectedRange));
      buildFilterUI(d.all_models);
      updateSortIcons();
      // Default selectedMonth to the latest available month
      const months = availableMonths();
      selectedMonth = months.length ? months[months.length - 1] : currentYearMonth();
      document.getElementById('daily-mode-select').value = 'range';
      document.getElementById('month-nav').style.display = 'none';
      document.getElementById('range-sep').style.display = '';
      document.getElementById('range-label').style.display = '';
      document.getElementById('range-group').style.display = '';
    }
    applyFilter();
  } catch(e) { console.error('loadData', e); }
}

// ── Settings ─────────────────────────────────────────────────────────────────
function setPricingTab(tab) {
  const isUrl = tab === 'url';
  document.getElementById('pricing-tab-url').style.display = isUrl ? '' : 'none';
  document.getElementById('pricing-tab-overrides').style.display = isUrl ? 'none' : '';
  document.getElementById('ptab-url').style.background = isUrl ? 'rgba(79,142,247,0.15)' : 'transparent';
  document.getElementById('ptab-url').style.color = isUrl ? 'var(--accent)' : 'var(--muted)';
  document.getElementById('ptab-overrides').style.background = isUrl ? 'transparent' : 'rgba(79,142,247,0.15)';
  document.getElementById('ptab-overrides').style.color = isUrl ? 'var(--muted)' : 'var(--accent)';
}
function resetPriceOverrides() {
  if (!confirm('Clear all price overrides and use the built-in pricing table?')) return;
  document.getElementById('s-price-overrides').value = '';
}
let _refreshInterval = __REFRESH_INTERVAL_MS__;
let _refreshTimer = setInterval(loadData, _refreshInterval);
let _lastUpdated = '';
let _countdownSecs = Math.round(_refreshInterval / 1000);
let _countdownTimer = setInterval(() => {
  if (_countdownSecs > 1) { _countdownSecs--; } else { _countdownSecs = Math.round(_refreshInterval / 1000); }
  _updateMetaCountdown();
}, 1000);
function _updateMetaCountdown() {
  const el = document.getElementById('meta');
  if (el) el.textContent = _lastUpdated + ' \u00b7 Refresh in ' + _countdownSecs + 's';
}

function openSettings() {
  // Populate selects from current server settings
  fetch('/api/settings').then(r=>r.json()).then(s=>{
    document.getElementById('s-refresh').value = s.refresh_interval_seconds || __REFRESH_INTERVAL_S__;
    document.getElementById('s-quota').value   = s.quota_limit || __QUOTA_LIMIT__;
    document.getElementById('s-source').value  = s.data_source || 'both';
    document.getElementById('s-pricing-url-display').textContent = s.pricing_source_url || '__PRICING_URL__';
    const ov = s.price_overrides && Object.keys(s.price_overrides).length ? JSON.stringify(s.price_overrides, null, 2) : '';
    document.getElementById('s-price-overrides').value = ov;
    setPricingTab('url');
  }).catch(()=>{});
  document.getElementById('settings-overlay').classList.add('open');
}
function closeSettings() {
  document.getElementById('settings-overlay').classList.remove('open');
}
function closeSettingsIfOutside(e) {
  if (e.target === document.getElementById('settings-overlay')) closeSettings();
}
async function saveSettings() {
  const refresh = parseInt(document.getElementById('s-refresh').value, 10);
  const quota   = parseInt(document.getElementById('s-quota').value, 10);
  const source  = document.getElementById('s-source').value;
  const pricingUrl = '';  // read-only — not editable from UI
  let priceOverrides = {};
  const rawOverrides = document.getElementById('s-price-overrides').value.trim();
  if (rawOverrides) {
    try { priceOverrides = JSON.parse(rawOverrides); }
    catch(e) { alert('Price Overrides is not valid JSON: ' + e.message); return; }
  }
  if (isNaN(refresh) || refresh < 10 || isNaN(quota) || quota < 1) {
    alert('Invalid values. Refresh must be \u226510s, quota must be \u22651.'); return;
  }
  const btn = document.getElementById('settings-save');
  btn.textContent = 'Saving\u2026'; btn.disabled = true;
  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({refresh_interval_seconds: refresh, quota_limit: quota, data_source: source, pricing_source_url: pricingUrl, price_overrides: priceOverrides})
    });
    if (!r.ok) throw new Error('Server error');
    // Restart interval with new value
    clearInterval(_refreshTimer);
    clearInterval(_countdownTimer);
    _refreshInterval = refresh * 1000;
    _refreshTimer = setInterval(loadData, _refreshInterval);
    _countdownSecs = Math.round(_refreshInterval / 1000);
    _countdownTimer = setInterval(() => {
      if (_countdownSecs > 1) { _countdownSecs--; } else { _countdownSecs = Math.round(_refreshInterval / 1000); }
      _updateMetaCountdown();
    }, 1000);
    closeSettings();
    await loadQuota();
    await loadData();
  } catch(e) { alert('Failed to save settings: ' + e.message); }
  finally { btn.textContent = 'Save'; btn.disabled = false; }
}

loadData();
loadQuota();
</script>
</body>
</html>"""


def _build_dashboard_html():
    """Inject server-side values into the dashboard template."""
    from pricing import PRICING_DATE, PRICING_SOURCE_URL
    s = _settings.load()
    html = _DASHBOARD_HTML
    html = html.replace("__PRICING_DATE__", PRICING_DATE)
    html = html.replace("__PRICING_URL__", s.get("pricing_source_url") or PRICING_SOURCE_URL)
    html = html.replace("__DEFAULT_QUOTA__", str(quota._DEFAULT_QUOTA))
    html = html.replace("__REFRESH_INTERVAL_MS__", str(s["refresh_interval_seconds"] * 1000))
    html = html.replace("__REFRESH_INTERVAL_S__", str(s["refresh_interval_seconds"]))
    html = html.replace("__QUOTA_LIMIT__", str(s["quota_limit"]))
    return html


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Suppress default access log noise
        pass

    def _db_connection(self):
        try:
            return db.get_connection(read_only=True)
        except Exception:
            return None

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_csv(self, data, filename):
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header(
            "Content-Disposition",
            'attachment; filename="{}"'.format(filename),
        )
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _send_error_json(self, status, message):
        self._send_json({"error": message}, status=status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        params = parse_qs(parsed.query, keep_blank_values=False)

        if path == "/" or path == "":
            self._send_html(_build_dashboard_html())
            return

        conn = self._db_connection()
        if conn is None:
            self._send_error_json(503, "Database unavailable")
            return

        try:
            with conn:
                if path == "/api/data":
                    data = _query_all_data(conn)
                    self._send_json(data)

                elif path == "/api/quota":
                    data = quota.get_quota_status(conn)
                    self._send_json(data)

                elif path == "/api/export":
                    csv_bytes = _generate_csv(conn, params)
                    filename  = _csv_filename(params)
                    self._send_csv(csv_bytes, filename)

                elif path == "/api/settings":
                    self._send_json(_settings.load())

                else:
                    self._send_error_json(404, "Not found")
        except sqlite3.OperationalError as exc:
            self._send_error_json(503, str(exc))
        finally:
            conn.close()

    def do_POST(self):
        """Handle POST /api/rescan or /api/settings."""
        parsed = urlparse(self.path)
        if parsed.path == "/api/settings":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                saved = _settings.save(body)
                self._send_json(saved)
            except Exception as exc:
                self._send_error_json(400, str(exc))
            return
        if parsed.path != "/api/rescan":
            self._send_error_json(404, "Not found")
            return
        try:
            import scanner as _scanner
            log_dir = _scanner.get_default_log_dir()
            if log_dir is None or not log_dir.exists():
                self._send_error_json(503, "Log directory not found")
                return
            result = _scanner.scan(log_dir)
            self._send_json({
                "new":     result.get("new_records", 0),
                "updated": result.get("files_scanned", 0),
            })
        except Exception as exc:
            self._send_error_json(500, str(exc))


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------

def _is_port_in_use(host, port):
    # Use a bind attempt — same test that HTTPServer will perform — to avoid
    # false positives from the connect-based check (a dying process may still
    # briefly accept connections while releasing the port).
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def run(db_path=None):
    """Start the HTTP server.  Reads HOST and PORT from environment."""
    host = os.environ.get("HOST", "localhost")
    raw_port = os.environ.get("PORT", "8080")

    try:
        port = int(raw_port)
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        print("Error: PORT must be an integer between 1 and 65535.", file=sys.stderr)
        sys.exit(1)

    if _is_port_in_use(host, port):
        print(
            "Port {} is already in use. Set PORT=<other> environment "
            "variable to use a different port.".format(port),
            file=sys.stderr,
        )
        sys.exit(1)

    server = HTTPServer((host, port), _Handler)
    url = "http://{}:{}".format(host, port)
    print("Dashboard available at {}".format(url))

    def _bg_scan():
        """Periodically scan JSONL logs — interval read from settings each cycle."""
        import time
        import scanner as _scanner
        while True:
            s = _settings.load()
            interval = s.get("refresh_interval_seconds", 30)
            time.sleep(interval)
            try:
                log_dir = _scanner.get_default_log_dir()
                if log_dir and log_dir.exists():
                    _scanner.scan(log_dir)
            except Exception:
                pass

    threading.Thread(target=_bg_scan, daemon=True).start()

    def _open_browser():
        import time
        time.sleep(0.8)
        try:
            webbrowser.open(url)
        except Exception:
            pass  # silently continue — server is still accessible (NFR-05 browser-fail scenario)

    t = threading.Thread(target=_open_browser, daemon=True)
    t.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("Dashboard stopped.")
