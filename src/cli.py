"""CLI entry point for ghcp-usage.

Commands:
  python src/cli.py scan        — Scan Copilot logs and populate the database
  python src/cli.py today       — Show today's usage by model (terminal table)
  python src/cli.py stats       — Show all-time aggregates by model (terminal table)
  python src/cli.py dashboard   — Scan + open browser dashboard at http://localhost:8080
"""

import sys

# Python version guard — must come before any relative imports
if sys.version_info < (3, 8):
    print("Python 3.8 or later is required.", file=sys.stderr)
    sys.exit(1)

import argparse
import os
from datetime import date, datetime
from pathlib import Path

import db
import pricing
import quota as _quota
import scanner as _scanner


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _resolve_log_dir(args):
    """Return the log directory path from args or the platform default."""
    raw = getattr(args, "logs_dir", None)
    if raw:
        p, err = _scanner.validate_log_dir(raw)
        if err:
            print(err, file=sys.stderr)
            sys.exit(1)
        return p
    return _scanner.get_default_log_dir()


def _fmt_int(n):
    """Format an integer with thousands separators."""
    return "{:,}".format(int(n or 0))


def _print_usage_table(rows, empty_msg="No data."):
    """Print a fixed-width usage table to stdout.

    Each row must be a sqlite3.Row (or dict-like) with:
      model, completion_count, accepted_count, total_input_tokens,
      total_output_tokens, turn_count
    """
    if not rows:
        print(empty_msg)
        return

    col_model = 30
    header = (
        "{:<{w}}  {:>7}  {:>8}  {:>7}  {:>11}  {:>11}  {:>6}  {:>10}".format(
            "Model", "Shown", "Accepted", "Accept%",
            "Input Tok", "Output Tok", "Turns", "Est. Cost",
            w=col_model,
        )
    )
    sep = "-" * len(header)
    print(header)
    print(sep)

    total_input = total_output = total_turns = total_completions = total_accepted = 0
    total_cost = 0.0
    any_cost = False

    for row in rows:
        model = (row["model"] or "unknown")[:col_model]
        completions   = int(row["completion_count"]   or 0)
        accepted      = int(row["accepted_count"]     or 0)
        input_tokens  = int(row["total_input_tokens"] or 0)
        output_tokens = int(row["total_output_tokens"] or 0)
        turns         = int(row["turn_count"]         or 0)

        accept_pct = (
            "{:.0f}%".format(100.0 * accepted / completions)
            if completions > 0 else "—"
        )

        cost = pricing.estimate_cost(model, input_tokens, output_tokens, 0, 0)
        cost_str = pricing.format_cost(cost)
        if cost is not None:
            total_cost += cost
            any_cost = True

        print(
            "{:<{w}}  {:>7}  {:>8}  {:>7}  {:>11}  {:>11}  {:>6}  {:>10}".format(
                model, _fmt_int(completions), _fmt_int(accepted), accept_pct,
                _fmt_int(input_tokens), _fmt_int(output_tokens),
                _fmt_int(turns), cost_str,
                w=col_model,
            )
        )

        total_input      += input_tokens
        total_output     += output_tokens
        total_turns      += turns
        total_completions += completions
        total_accepted   += accepted

    print(sep)
    total_accept_pct = (
        "{:.0f}%".format(100.0 * total_accepted / total_completions)
        if total_completions > 0 else "—"
    )
    total_cost_str = pricing.format_cost(total_cost) if any_cost else "n/a"
    print(
        "{:<{w}}  {:>7}  {:>8}  {:>7}  {:>11}  {:>11}  {:>6}  {:>10}".format(
            "TOTAL",
            _fmt_int(total_completions), _fmt_int(total_accepted),
            total_accept_pct,
            _fmt_int(total_input), _fmt_int(total_output),
            _fmt_int(total_turns), total_cost_str,
            w=col_model,
        )
    )


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_scan(args):
    """Implements: python src/cli.py scan"""
    log_dir = _resolve_log_dir(args)

    if log_dir is None or not log_dir.exists():
        print(
            "No Copilot workspaceStorage directory found at {}.\n"
            "Is the VS Code Copilot extension installed?".format(log_dir)
        )
        print("Use --logs-dir to specify a custom path.")
        sys.exit(0)

    result = _scanner.scan(
        log_dir,
        db_path=db.get_db_path(),
        reset=getattr(args, "reset", False),
        yes=getattr(args, "yes", False),
    )

    files_processed = result["files_scanned"]
    new_records     = result["new_records"]
    chat_turns      = result["chat_turns"]

    if files_processed == 0 and new_records == 0:
        print(
            "Scanned {} files — 0 new records (chat turns: 0)".format(
                files_processed
            )
        )
    else:
        print(
            "Scanned {files} files — {new} new records inserted "
            "(chat turns: {ct})".format(
                files=files_processed,
                new=new_records,
                ct=chat_turns,
            )
        )


def cmd_today(args):
    """Implements: python src/cli.py today"""
    if not db.db_exists():
        print(
            "No usage database found. Run `python src/cli.py scan` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        conn = db.get_connection(read_only=True)
    except Exception as exc:
        print("Error opening database: {}".format(exc), file=sys.stderr)
        sys.exit(1)

    today = date.today().isoformat()
    with conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                t.model,
                0                       AS completion_count,
                0                       AS accepted_count,
                SUM(t.input_tokens)     AS total_input_tokens,
                SUM(t.output_tokens)    AS total_output_tokens,
                COUNT(*)                AS turn_count
            FROM turns t
            WHERE t.timestamp >= ?
            GROUP BY t.model
            ORDER BY turn_count DESC
            """,
            (today,),
        )
        rows = cur.fetchall()

    _print_usage_table(
        rows,
        "No Copilot activity recorded today. Run `python src/cli.py scan` to update.",
    )

    # Quota summary
    try:
        q = _quota.get_quota_status(conn)
        limit    = q["limit"]
        used     = q["used"]
        pct      = q["percent"]
        over     = q["over_limit"]
        ym       = q["year_month"]
        rem_str  = "({} over limit)".format(used - limit) if over else "({} remaining)".format(q["remaining"])
        print("\nMonthly quota [{}]: {} / {} turns  {:.1f}%  {}".format(
            ym, used, limit, pct, rem_str
        ))
    except Exception:
        pass


def cmd_stats(args):
    """Implements: python src/cli.py stats"""
    if not db.db_exists():
        print(
            "No usage database found. Run `python src/cli.py scan` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        conn = db.get_connection(read_only=True)
    except Exception as exc:
        print("Error opening database: {}".format(exc), file=sys.stderr)
        sys.exit(1)

    with conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                model,
                SUM(completion_count)        AS completion_count,
                SUM(accepted_count)          AS accepted_count,
                SUM(total_input_tokens)      AS total_input_tokens,
                SUM(total_output_tokens)     AS total_output_tokens,
                SUM(turn_count)              AS turn_count
            FROM sessions
            GROUP BY model
            ORDER BY turn_count DESC
            """
        )
        rows = cur.fetchall()

    _print_usage_table(
        rows,
        "No usage data found. Run `python src/cli.py scan` first.",
    )


def cmd_dashboard(args):
    """Implements: python src/cli.py dashboard"""
    # If --port is given, propagate it via the PORT env var that dashboard.run() reads.
    port = getattr(args, "port", None)
    if port is not None:
        os.environ["PORT"] = str(port)
    # Initial JSONL scan so dashboard opens with fresh data
    log_dir = _scanner.get_default_log_dir()
    if log_dir is None:
        print("Warning: could not resolve VS Code workspaceStorage path (APPDATA not set?).", file=sys.stderr)
    elif not log_dir.exists():
        print("Warning: workspaceStorage directory not found: {}".format(log_dir), file=sys.stderr)
        print("  → Dashboard will show no data until VS Code Copilot Chat logs appear at that path.", file=sys.stderr)
    else:
        print("Scanning log directory: {}".format(log_dir))
        try:
            files = _scanner.discover_log_files(log_dir)
            print("  Found {} JSONL session file(s).".format(len(files)))
            result = _scanner.scan(log_dir)
            print("Initial scan: {} new records from JSONL logs.".format(result.get("new_records", 0)))
        except Exception as exc:
            print("Warning: initial scan failed: {}".format(exc), file=sys.stderr)
    import dashboard
    dashboard.run()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="GHCP Usage Dashboard — GitHub Copilot usage tracker",
    )
    parser.add_argument(
        "--version", action="version", version="ghcp-usage 0.1.0"
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # scan
    p_scan = sub.add_parser("scan", help="Scan Copilot logs and update the database")
    p_scan.add_argument(
        "--logs-dir",
        metavar="PATH",
        help="Path to VS Code workspaceStorage directory (default: auto-detect)",
    )
    p_scan.add_argument(
        "--reset",
        action="store_true",
        help="Delete the database and re-scan from scratch",
    )
    p_scan.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt for --reset",
    )
    p_scan.set_defaults(func=cmd_scan)

    # today
    p_today = sub.add_parser("today", help="Show today's usage by model")
    p_today.set_defaults(func=cmd_today)

    # stats
    p_stats = sub.add_parser("stats", help="Show all-time usage statistics by model")
    p_stats.set_defaults(func=cmd_stats)

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Open browser dashboard at http://localhost:8080")
    p_dash.add_argument(
        "--logs-dir",
        metavar="PATH",
        help="Path to VS Code workspaceStorage directory (default: auto-detect)",
    )
    p_dash.add_argument(
        "--port",
        metavar="PORT",
        type=int,
        default=None,
        help="Port for the dashboard HTTP server (default: 8080 or PORT env var)",
    )
    p_dash.set_defaults(func=cmd_dashboard)

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
