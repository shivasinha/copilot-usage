"""Log scanner: discover, parse and persist VS Code GitHub Copilot chat sessions.

Workflow (WF-01):
  1. Resolve the workspaceStorage root (default OS path or --logs-dir override).
  2. Build a workspace-ID to project-name map from workspace.json files.
  3. Discover all chatSessions/*.jsonl files under workspaceStorage.
  4. Open (or create) the SQLite DB and run init_db().
  5. For each file: skip if path+mtime unchanged; otherwise parse all requests.
  6. Recompute session-level aggregates from the turns table.
  7. Print a summary to stdout.

Data source (Windows):
  AppData/Roaming/Code/User/workspaceStorage/<id>/chatSessions/<session>.jsonl
  Each JSONL file is a Copilot Chat session.  Each line is a JSON object with
  a 'kind' discriminator and 'v' value.  Requests live in v.requests[].
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import db
from pricing import get_model_multiplier


# ---------------------------------------------------------------------------
# Default log-directory resolution
# ---------------------------------------------------------------------------

def get_default_log_dir():
    """Return the platform-specific VS Code workspaceStorage root.

    Checks multiple candidate paths and returns the first that exists.
    On Linux this also covers VS Code Server (remote SSH target).
    """
    platform = sys.platform
    if platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return None
        return Path(appdata) / "Code" / "User" / "workspaceStorage"
    if platform == "darwin":
        return (Path.home() / "Library" / "Application Support"
                / "Code" / "User" / "workspaceStorage")
    # Linux / other — check standard Code path first, then vscode-server
    candidates = []
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    config_root = Path(xdg) if xdg else Path.home() / ".config"
    candidates.append(config_root / "Code" / "User" / "workspaceStorage")
    candidates.append(Path.home() / ".vscode-server" / "data" / "User" / "workspaceStorage")
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # fall back to standard path even if absent


def validate_log_dir(path):
    """Validate --logs-dir argument.  Returns (Path, error_message)."""
    p = Path(path)
    if not p.exists():
        return None, "Error: --logs-dir path does not exist: {}".format(path)
    if not p.is_dir():
        return None, "Error: --logs-dir path is not a directory: {}".format(path)
    if not os.access(str(p), os.R_OK):
        return None, "Error: Cannot read directory {} — check permissions.".format(path)
    return p, None


# ---------------------------------------------------------------------------
# Workspace map: folder hash → project name
# ---------------------------------------------------------------------------

def _uri_to_project_name(uri_str):
    """Convert a VS Code workspace URI to a short display name.

    Examples:
      file:///d%3A/code/ghcp-usage          → ghcp-usage
      vscode-remote://ssh-remote%2Bhost/home/user/code/tps → tps
    """
    try:
        decoded = unquote(uri_str)
        # Drop the scheme
        if "://" in decoded:
            decoded = decoded.split("://", 1)[1]
            # For vscode-remote, drop the authority
            if decoded.startswith("ssh-remote") or decoded.startswith("dev-"):
                decoded = decoded.split("/", 1)[1] if "/" in decoded else decoded
        # Normalise path separators
        parts = [p for p in decoded.replace("\\", "/").split("/") if p]
        if len(parts) >= 2:
            return "{}/{}".format(parts[-2], parts[-1])
        return parts[-1] if parts else uri_str
    except Exception:
        return uri_str


def build_workspace_map(storage_root):
    """Return a dict mapping workspace folder-hash → project_name.

    Reads every workspace.json under *storage_root* and derives a human-readable
    project name from the URI stored in the file.
    """
    mapping = {}
    storage_root = Path(storage_root)
    for entry in storage_root.iterdir():
        if not entry.is_dir():
            continue
        wj = entry / "workspace.json"
        if not wj.exists():
            continue
        try:
            data = json.loads(wj.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        uri = data.get("folder") or data.get("workspace")
        if uri:
            mapping[entry.name] = _uri_to_project_name(uri)
    return mapping


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_log_files(storage_root):
    """Return a sorted list of chatSession files under *storage_root*.

    Looks for files matching:
      <storage_root>/<workspace_id>/chatSessions/*.jsonl  (VS Code < ~1.100)
      <storage_root>/<workspace_id>/chatSessions/*.json   (VS Code >= ~1.100)
    """
    storage_root = Path(storage_root)
    files = []
    for ws_dir in storage_root.iterdir():
        if not ws_dir.is_dir():
            continue
        chat_sessions = ws_dir / "chatSessions"
        if not chat_sessions.is_dir():
            continue
        for pattern in ("*.jsonl", "*.json"):
            for f in chat_sessions.glob(pattern):
                files.append(f)
    return sorted(set(files))


# ---------------------------------------------------------------------------
# chatSession JSONL parser
# ---------------------------------------------------------------------------

def _parse_timestamp(raw):
    """Normalise a timestamp to ISO 8601 (UTC, no microseconds)."""
    if not raw:
        return None
    if isinstance(raw, (int, float)):
        # Unix milliseconds
        ts = raw / 1000.0 if raw > 1e10 else float(raw)
        return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")
    raw = str(raw)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw[:26], fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return raw[:26]


def _estimate_tokens(text):
    """Rough token estimate: 1 token ≈ 4 characters (OpenAI heuristic)."""
    if not text:
        return 0
    return max(1, len(str(text)) // 4)


def _normalise_model(model_id):
    """Strip the 'copilot/' vendor prefix from modelId."""
    if model_id and model_id.startswith("copilot/"):
        return model_id[len("copilot/"):]
    return model_id


def _extract_response_text(response):
    """Extract all text content from a response items array.

    Handles all response item kinds that contain model-generated text:
    - kind=None / 'markdownContent': plain markdown text
    - kind='thinking': extended reasoning text
    - kind='textEditGroup': file edits written by the model (edits[*][*].text)
    - kind='progressTaskSerialized': progress/compaction messages
    """
    parts = []
    for item in response or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind is None or kind == "markdownContent":
            val = item.get("value")
            if isinstance(val, str):
                parts.append(val)
            elif isinstance(val, dict):
                parts.append(val.get("value", ""))
        elif kind == "thinking":
            val = item.get("value", "")
            if val:
                parts.append(val)
        elif kind == "textEditGroup":
            # edits is a list of edit-groups, each a list of {text, range} edits
            for edit_group in item.get("edits") or []:
                for edit in edit_group or []:
                    if isinstance(edit, dict):
                        t = edit.get("text", "")
                        if t:
                            parts.append(t)
        elif kind == "progressTaskSerialized":
            content = item.get("content") or {}
            if isinstance(content, dict):
                val = content.get("value", "")
                if val:
                    parts.append(val)
    return " ".join(parts)


def _extract_tool_call_rounds_output_tokens(req):
    """Extract output tokens from result.metadata.toolCallRounds.

    In agent-mode sessions the model produces reasoning and intermediate text
    across multiple tool-call rounds *before* writing the final response[]
    items.  This text lives in result.metadata.toolCallRounds[*].response
    and [*].thinking and is NOT present in response[] — making it the single
    largest source of undercounting for long agentic sessions.

    The 'thinking' field can be a string or a dict {id, text} depending on
    the VS Code version; both forms are handled.
    """
    result = req.get("result") or {}
    if not isinstance(result, dict):
        return 0
    metadata = result.get("metadata") or {}
    if not isinstance(metadata, dict):
        return 0
    total_chars = 0
    for round_ in metadata.get("toolCallRounds") or []:
        if not isinstance(round_, dict):
            continue
        # response: partial text emitted before tool calls in this round
        resp = round_.get("response") or ""
        total_chars += len(resp) if isinstance(resp, str) else len(str(resp))
        # thinking: extended reasoning (string or {id, text} dict)
        think = round_.get("thinking") or ""
        if isinstance(think, str):
            total_chars += len(think)
        elif isinstance(think, dict):
            total_chars += len(think.get("text", ""))
        elif isinstance(think, list):
            for t in think:
                if isinstance(t, dict):
                    total_chars += len(t.get("text", ""))
                elif isinstance(t, str):
                    total_chars += len(t)
    return max(0, total_chars // 4)


def _extract_variable_data_text(req):
    """Extract injected context text from variableData.variables[*].value.

    VS Code injects skills, customisations, and other context into every request
    via the variableData payload.  These are part of the actual input sent to
    the model and must be included in the token estimate.
    """
    vd = req.get("variableData") or {}
    if not isinstance(vd, dict):
        return ""
    parts = []
    for var in vd.get("variables") or []:
        if not isinstance(var, dict):
            continue
        val = var.get("value")
        if isinstance(val, str) and val:
            parts.append(val)
    return " ".join(parts)


def _detect_compaction(req):
    """Return True if this turn triggered or IS a compaction event.

    Detection uses three independent signals (any one is sufficient):
    1. result.metadata.summaries non-empty — VS Code replaces conversation
       history with summaries after compaction; this field is set on the
       FIRST request sent after a compaction.
    2. A 'progressTaskSerialized' response item whose value contains the word
       "compact" — VS Code emits this notification to the UI during compaction.
    3. This is checked at the session level in parse_session_file() as a
       token-drop fallback (promptTokens drops >50% and >20 K vs prior turn).
    """
    result = req.get("result") or {}
    metadata = result.get("metadata") or {} if isinstance(result, dict) else {}
    if isinstance(metadata, dict) and metadata.get("summaries"):
        return True
    for item in req.get("response") or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "progressTaskSerialized":
            content = item.get("content") or {}
            val = content.get("value", "") if isinstance(content, dict) else ""
            if "compact" in str(val).lower():
                return True
    return False


def _extract_api_token_counts(req):
    """Return (prompt_tokens, output_tokens) from result when available.

    Handles two formats:
      Old format: result.metadata.promptTokens / result.metadata.outputTokens
      New format: result.usage.promptTokens / result.usage.completionTokens
        (VS Code v1.100+, chatSessions kind=1 patch with k=['requests',N,'result'])

    Both fields are returned as ints, or (None, None) if either is absent.
    """
    result = req.get("result") or {}
    if not isinstance(result, dict):
        return None, None

    # New format: result.usage (from kind=1 patch)
    usage = result.get("usage")
    if isinstance(usage, dict):
        pt = usage.get("promptTokens")
        ot = usage.get("completionTokens")
        if pt is not None and ot is not None:
            try:
                return int(pt), int(ot)
            except (TypeError, ValueError):
                pass

    # Old format: result.metadata
    metadata = result.get("metadata") or {}
    if not isinstance(metadata, dict):
        return None, None
    pt = metadata.get("promptTokens")
    ot = metadata.get("outputTokens")
    if pt is None or ot is None:
        return None, None
    try:
        return int(pt), int(ot)
    except (TypeError, ValueError):
        return None, None


def _extract_rendered_input_tokens(req):
    """Fallback: estimate input tokens from renderedUserMessage char count.

    Used only when result.metadata.promptTokens is absent (cancelled requests
    or older VS Code versions that do not store API metrics).

    renderedUserMessage captures user message + conversation history +
    injected context, but NOT system instructions or tool definitions.  Use
    _extract_api_token_counts() as the preferred path.

    Returns the token estimate, or None if the field is not present.
    """
    result = req.get("result") or {}
    if not isinstance(result, dict):
        return None
    metadata = result.get("metadata") or {}
    if not isinstance(metadata, dict):
        return None
    rendered = metadata.get("renderedUserMessage")
    if not rendered:
        return None
    total_chars = 0
    if isinstance(rendered, list):
        for entry in rendered:
            if isinstance(entry, dict):
                total_chars += len(entry.get("text", ""))
    elif isinstance(rendered, str):
        total_chars = len(rendered)
    return max(1, total_chars // 4) if total_chars else None


def _collect_requests(file_path):
    """Parse a chatSession JSONL file and return a deduplicated list of requests.

    Handles two chatSession JSONL formats:

    Old format (VS Code < ~1.100):
      Each line: {'kind': int, 'v': dict}.  Requests live in v.requests[].

    New format (VS Code >= ~1.100):
      kind=0  line: v is a dict with v.requests[] containing initial requests.
      kind=2  lines: v is a list; items with 'requestId' are new requests appended
                     to the session.
      kind=1  lines: incremental patches.  k is a path list like
                     ['requests', N, 'result'].  When it patches a result, v
                     contains {usage: {promptTokens, completionTokens}, details, ...}
                     which is merged into requests[N].result.
    """
    requests_by_id = {}   # requestId -> request dict
    requests_ordered = [] # ordered list to support index-based kind=1 patches
    session_id = file_path.stem

    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict):
                    continue

                kind = obj.get("kind")
                v = obj.get("v")
                k = obj.get("k")

                if isinstance(v, dict):
                    # Old format or new kind=0: requests list inside v.requests
                    for req in v.get("requests", []):
                        if not isinstance(req, dict):
                            continue
                        rid = req.get("requestId")
                        if rid and rid not in requests_by_id:
                            requests_by_id[rid] = req
                            requests_ordered.append(req)

                    # New format kind=1: incremental patch to requests[N].result
                    # k = ['requests', N, 'result']
                    if (
                        kind == 1
                        and isinstance(k, list)
                        and len(k) == 3
                        and k[0] == "requests"
                        and k[2] == "result"
                        and isinstance(k[1], int)
                    ):
                        idx = k[1]
                        if 0 <= idx < len(requests_ordered):
                            requests_ordered[idx]["result"] = v

                elif isinstance(v, list):
                    # New format kind=2: list may contain new request objects
                    for item in v:
                        if not isinstance(item, dict):
                            continue
                        rid = item.get("requestId")
                        if rid and rid not in requests_by_id:
                            requests_by_id[rid] = item
                            requests_ordered.append(item)

    except OSError:
        pass

    return session_id, requests_ordered


def parse_session_file(file_path, workspace_id=None, project_name=None):
    """Parse a chatSession JSONL file into a list of turn records.

    Token estimation strategy:
    - Output tokens: estimated from the assistant response text (~4 chars/token).
    - Input tokens (per-turn base): user message text + injected variableData
      context (skills, customisations) that VS Code sends with every request.
    - Cumulative context correction: each API call to the model includes the
      full conversation history from the same session.  For turn N the model
      receives turns 0..N-1 as context, so actual input tokens grow with each
      turn.  We simulate this by adding the accumulated prior-turn tokens to
      each turn's input estimate.

    VS Code does not expose real token counts in local logs; all values are
    estimates.

    Returns:
        (session_id, list_of_turn_dicts)
    """
    session_id, requests = _collect_requests(file_path)

    turns = []
    for req in requests:
        model_raw = req.get("modelId")
        model = _normalise_model(model_raw)

        timestamp = _parse_timestamp(req.get("timestamp"))
        if not timestamp:
            timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        # Estimate output tokens from assistant response content.
        # Prefer result.metadata.outputTokens (the actual API-reported count)
        # when available.  Fall back to char-based estimation.
        api_input_tokens, api_output_tokens = _extract_api_token_counts(req)

        if api_output_tokens is not None:
            output_tokens = api_output_tokens
        else:
            response_text = _extract_response_text(req.get("response", []))
            output_tokens = (
                _estimate_tokens(response_text)
                + _extract_tool_call_rounds_output_tokens(req)
            )

        # Estimate base input tokens.
        # Priority order:
        #   1. result.metadata.promptTokens  — actual API count (full context:
        #      system + tools + history + user message).  Most accurate.
        #   2. result.metadata.renderedUserMessage char count  — captures
        #      message + history but NOT system/tool overhead.  ~4-5x undercount
        #      for agent-mode sessions.
        #   3. message.text + variableData  — bare minimum fallback.
        if api_input_tokens is not None:
            base_input_tokens = api_input_tokens
            has_full_context = True
        else:
            rendered_input_tokens = _extract_rendered_input_tokens(req)
            if rendered_input_tokens is not None:
                base_input_tokens = rendered_input_tokens
                has_full_context = True
            else:
                msg = req.get("message") or {}
                user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)
                var_text = _extract_variable_data_text(req)
                base_input_tokens = _estimate_tokens(user_text) + _estimate_tokens(var_text)
                has_full_context = False

        # Detect whether this turn is a compaction event.
        compacted = _detect_compaction(req)

        # Read model multiplier from pricing table so quota-adjusted usage
        # can be computed in the dashboard.
        multiplier = get_model_multiplier(model)

        turns.append({
            "session_id":            session_id,
            "timestamp":             timestamp,
            "turn_type":             "chat",
            "model":                 model,
            "_base_input_tokens":    base_input_tokens,
            "_has_rendered":         has_full_context,
            "input_tokens":          base_input_tokens,   # updated below
            "output_tokens":         output_tokens,
            "cache_read_tokens":     0,
            "cache_creation_tokens": 0,
            "tool_name":             None,
            "cwd":                   None,
            "message_id":            req.get("requestId"),
            "language":              None,
            "accepted":              None,
            "project_name":          project_name,
            "multiplier":            multiplier,
            "context_compacted":     int(compacted),
        })

    # Apply cumulative context correction for turns that do NOT have the full
    # rendered payload (i.e., renderedUserMessage was absent).  For turns that
    # have the rendered payload, the full context window is already captured.
    # Sort by timestamp first so history accumulates in chronological order.
    turns.sort(key=lambda t: t["timestamp"] or "")
    cumulative_context = 0
    for turn in turns:
        if turn["_has_rendered"]:
            # renderedUserMessage already includes history — no correction needed.
            # Reset the cumulative counter to the token count in this turn so
            # subsequent non-rendered turns can still accumulate from here.
            cumulative_context = turn["_base_input_tokens"] + turn["output_tokens"]
        else:
            turn["input_tokens"] = turn["_base_input_tokens"] + cumulative_context
            cumulative_context += turn["_base_input_tokens"] + turn["output_tokens"]

    # Token-drop fallback: if promptTokens drops by >50% AND >20 K tokens vs
    # the previous turn, the context was almost certainly compacted.  This
    # catches sessions where neither summaries nor progressTaskSerialized is
    # present (older VS Code versions or cancelled compaction notifications).
    prev_input = 0
    for turn in turns:
        inp = turn["input_tokens"]
        if (not turn["context_compacted"] and prev_input > 40_000
                and inp < prev_input * 0.5 and (prev_input - inp) > 20_000):
            turn["context_compacted"] = 1
        prev_input = inp

    # Remove internal helper fields before returning
    for turn in turns:
        del turn["_base_input_tokens"]
        del turn["_has_rendered"]  # type: ignore[misc]

    return session_id, turns


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _insert_turn(cur, record):
    """INSERT OR REPLACE a turn record (dedup by message_id, NFR-02-D).

    OR REPLACE ensures that token counts are updated when a file is re-scanned
    after the estimation logic changes.  The UNIQUE index on message_id
    guarantees only one row per logical turn.
    """
    cur.execute("""
        INSERT OR REPLACE INTO turns
            (session_id, timestamp, turn_type, model,
             input_tokens, output_tokens, cache_read_tokens,
             cache_creation_tokens, tool_name, cwd,
             message_id, language, accepted, multiplier,
             context_compacted)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        record["session_id"],  record["timestamp"],
        record["turn_type"],   record["model"],
        record["input_tokens"],        record["output_tokens"],
        record["cache_read_tokens"],   record["cache_creation_tokens"],
        record["tool_name"],   record["cwd"],
        record["message_id"],  record["language"],
        record["accepted"],    record.get("multiplier", 1),
        record.get("context_compacted", 0),
    ))
    return cur.rowcount


def _recompute_session_aggregates(conn):
    """Recompute session-level aggregated totals from the turns table.

    This prevents inflation from partial re-scans (WF-01).
    Project name is taken from the sessions table if already stored there
    (populated during scan), because turns.cwd is always NULL for chatSession
    data.
    """
    conn.execute("""
        INSERT OR REPLACE INTO sessions
            (session_id, project_name, first_timestamp, last_timestamp,
             total_input_tokens, total_output_tokens,
             total_cache_read, total_cache_creation,
             quota_input_tokens, quota_output_tokens,
             premium_requests,
             compaction_count, max_context_tokens,
             model, turn_count, completion_count, accepted_count)
        SELECT
            t.session_id,
            COALESCE(
                (SELECT project_name FROM sessions WHERE session_id = t.session_id),
                MAX(t.cwd)
            ),
            MIN(t.timestamp),
            MAX(t.timestamp),
            COALESCE(SUM(t.input_tokens), 0),
            COALESCE(SUM(t.output_tokens), 0),
            COALESCE(SUM(t.cache_read_tokens), 0),
            COALESCE(SUM(t.cache_creation_tokens), 0),
            COALESCE(SUM(t.input_tokens  * COALESCE(t.multiplier, 1.0)), 0),
            COALESCE(SUM(t.output_tokens * COALESCE(t.multiplier, 1.0)), 0),
            COALESCE(SUM(COALESCE(t.multiplier, 1.0)), 0),
            COALESCE(SUM(COALESCE(t.context_compacted, 0)), 0),
            COALESCE(MAX(t.input_tokens), 0),
            MAX(t.model),
            COUNT(*),
            SUM(CASE WHEN t.turn_type = 'completion' THEN 1 ELSE 0 END),
            SUM(CASE WHEN t.accepted = 1 THEN 1 ELSE 0 END)
        FROM turns t
        GROUP BY t.session_id
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Main scan entry point
# ---------------------------------------------------------------------------

def scan(log_dir, db_path=None, reset=False, yes=False):
    """Scan *log_dir* (workspaceStorage root) and persist records to the DB.

    Args:
        log_dir:  Path to the VS Code workspaceStorage directory.
        db_path:  Override for the DB file path.
        reset:    If True, prompt for confirmation then delete the DB first.
        yes:      Skip interactive prompt (for non-TTY / --yes flag).

    Returns a dict:
        {files_scanned, files_skipped, new_records, chat_turns}
    """
    if db_path is None:
        db_path = db.get_db_path()
    db_path = Path(db_path)

    # WF-05: --reset flow
    if reset:
        if db_path.exists():
            if not yes:
                if not sys.stdin.isatty():
                    print(
                        "Aborted: use --yes flag to confirm reset in "
                        "non-interactive mode.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                answer = input(
                    "This will delete all stored usage data and re-scan "
                    "from scratch. Continue? [y/N] "
                ).strip().lower()
                if answer != "y":
                    print("Aborted.")
                    sys.exit(0)
            print("Rebuilding database…")
            db_path.unlink()

    # Ensure DB directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    storage_root = Path(log_dir)

    # Build workspace-ID → project name map once
    workspace_map = build_workspace_map(storage_root)

    files = discover_log_files(storage_root)

    stats = {
        "files_scanned": 0,
        "files_skipped": 0,
        "new_records":   0,
        "chat_turns":    0,
    }

    # Check for DB lock before opening
    try:
        conn = db.get_connection(db_path)
    except Exception as exc:
        if "locked" in str(exc).lower():
            print(
                "Error: Usage database is locked. Is another scan running?",
                file=sys.stderr,
            )
            sys.exit(1)
        raise

    with conn:
        db.init_db(conn)
        cur = conn.cursor()

        for file_path in files:
            try:
                mtime = file_path.stat().st_mtime
            except OSError:
                continue

            path_str = str(file_path)

            # Incremental check (FR-16 / NFR-09)
            cur.execute(
                "SELECT mtime FROM processed_files WHERE path = ?",
                (path_str,),
            )
            row = cur.fetchone()
            if row and row["mtime"] == mtime:
                stats["files_skipped"] += 1
                continue

            # Derive workspace ID and project name from the file's grandparent dir
            workspace_id = file_path.parent.parent.name
            project_name = workspace_map.get(workspace_id)

            # Parse the session file
            try:
                session_id, turns = parse_session_file(
                    file_path, workspace_id=workspace_id,
                    project_name=project_name,
                )
            except OSError as exc:
                print(
                    "Warning: Could not read {}: {}".format(file_path, exc),
                    file=sys.stderr,
                )
                continue

            if not turns:
                # File has no requests yet (session just started); still track it
                cur.execute("""
                    INSERT OR REPLACE INTO processed_files (path, mtime, lines)
                    VALUES (?, ?, ?)
                """, (path_str, mtime, 0))
                stats["files_scanned"] += 1
                continue

            # Store session project_name before recompute picks it up
            cur.execute("""
                INSERT OR IGNORE INTO sessions
                    (session_id, project_name, first_timestamp, last_timestamp,
                     total_input_tokens, total_output_tokens,
                     total_cache_read, total_cache_creation,
                     model, turn_count, completion_count, accepted_count)
                VALUES (?, ?, '', '', 0, 0, 0, 0, NULL, 0, 0, 0)
            """, (session_id, project_name))
            # Always refresh project_name in case workspace.json changed
            if project_name:
                cur.execute(
                    "UPDATE sessions SET project_name = ? WHERE session_id = ?",
                    (project_name, session_id),
                )

            new_in_file = 0
            for record in turns:
                inserted = _insert_turn(cur, record)
                if inserted:
                    new_in_file += 1
                    stats["chat_turns"] += 1

            # Update processed_files
            cur.execute("""
                INSERT OR REPLACE INTO processed_files (path, mtime, lines)
                VALUES (?, ?, ?)
            """, (path_str, mtime, len(turns)))

            stats["new_records"] += new_in_file
            stats["files_scanned"] += 1

        conn.commit()

        # Recompute session aggregates from turns
        _recompute_session_aggregates(conn)

    return stats
