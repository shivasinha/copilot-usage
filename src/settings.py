"""Persistent user settings stored in ~/.ghcp-usage/settings.json.

Settings:
  refresh_interval_seconds  — how often UI auto-refreshes AND JSONL background scan runs (default 30)
  quota_limit               — monthly premium request limit shown in the quota bar (default 100)
"""

import json
import os
from pathlib import Path

_SETTINGS_PATH = Path(os.path.expanduser("~/.ghcp-usage/settings.json"))

DEFAULTS = {
    "refresh_interval_seconds": 30,
    "quota_limit": 100,
    "data_source": "both",   # "both" | "proxy" | "jsonl"
    "pricing_source_url": "https://platform.openai.com/docs/pricing",
    "price_overrides": {},   # {"model-key": [input_$/MTok, output_$/MTok]}
}

_BOUNDS = {
    "refresh_interval_seconds": (10, 3600),
    "quota_limit": (1, 100_000),
    "data_source": None,
    "pricing_source_url": None,
    "price_overrides": None,
}

_VALID_DATA_SOURCES = {"both", "proxy", "jsonl"}


def load() -> dict:
    """Return current settings, falling back to defaults for any missing keys."""
    try:
        if _SETTINGS_PATH.exists():
            data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**DEFAULTS, **{k: data[k] for k in DEFAULTS if k in data}}
    except Exception:
        pass
    return dict(DEFAULTS)


def save(updates: dict) -> dict:
    """Validate, merge with existing settings, persist, and return the saved settings."""
    current = load()
    for key, val in updates.items():
        if key not in DEFAULTS:
            continue
        if key == "data_source":
            if val in _VALID_DATA_SOURCES:
                current[key] = val
            continue
        if key == "pricing_source_url":
            if isinstance(val, str) and val.strip():
                current[key] = val.strip()
            continue
        if key == "price_overrides":
            if isinstance(val, dict):
                # Validate: values must be 2-element numeric lists
                clean = {}
                for mk, mv in val.items():
                    try:
                        if len(mv) >= 2:
                            clean[str(mk)] = [float(mv[0]), float(mv[1])]
                    except (TypeError, ValueError):
                        pass
                current[key] = clean
            continue
        try:
            val = type(DEFAULTS[key])(val)
        except (TypeError, ValueError):
            continue
        lo, hi = _BOUNDS.get(key, (None, None))
        if lo is not None and not (lo <= val <= hi):
            continue
        current[key] = val
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current
