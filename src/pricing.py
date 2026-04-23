"""Per-model API pricing table for cost estimates.

All prices are in USD per 1,000,000 tokens (per MTok).
Tuple layout: (input_usd, output_usd, cache_read_usd, cache_creation_usd)

This is the SINGLE authoritative pricing table in the codebase (NFR-07-A).
Costs are estimates using public API pricing — not subscription/plan charges.
"""

PRICING_DATE = "April 2026"
PRICING_SOURCE_URL = "https://platform.openai.com/docs/pricing"  # generic reference

# model_key → (input $/MTok, output $/MTok, cache_read $/MTok, cache_creation $/MTok)
PRICING_TABLE = {
    # OpenAI GPT-4o family
    "gpt-4o":              (2.50,  10.00, 1.25,  0.00),
    "gpt-4o-mini":         (0.15,   0.60, 0.075, 0.00),
    # OpenAI o-series
    "o1":                  (15.00, 60.00, 7.50,  0.00),
    "o1-mini":             (3.00,  12.00, 1.50,  0.00),
    "o1-preview":          (15.00, 60.00, 7.50,  0.00),
    "o3":                  (10.00, 40.00, 2.50,  0.00),
    "o3-mini":             (1.10,   4.40, 0.55,  0.00),
    "o4-mini":             (1.10,   4.40, 0.275, 0.00),
    # Anthropic Claude 3.x
    "claude-3-5-sonnet":   (3.00,  15.00, 0.30,  3.75),
    "claude-3-5-haiku":    (0.80,   4.00, 0.08,  1.00),
    "claude-3-opus":       (15.00, 75.00, 1.50,  18.75),
    "claude-3-sonnet":     (3.00,  15.00, 0.30,  3.75),
    "claude-3-haiku":      (0.25,   1.25, 0.03,  0.30),
    # Anthropic Claude 4.x
    "claude-sonnet-4":     (3.00,  15.00, 0.30,  3.75),
    "claude-opus-4":       (15.00, 75.00, 1.50,  18.75),
    "claude-haiku-4":      (0.80,   4.00, 0.08,  1.00),
    # Google Gemini
    "gemini-2.5-pro":      (1.25,  10.00, 0.00,  0.00),
    "gemini-2.5-flash":    (0.15,   0.60, 0.00,  0.00),
    "gemini-1.5-pro":      (1.25,   5.00, 0.00,  0.00),
    "gemini-1.5-flash":    (0.075,  0.30, 0.00,  0.00),
    "gemini-1.0-pro":      (0.50,   1.50, 0.00,  0.00),
}


# GitHub Copilot subscription quota multipliers per model.
# Source: https://docs.github.com/en/copilot/concepts/billing/copilot-requests#model-multipliers
# (verified April 2026)
# GitHub Copilot bills 1 premium request per user prompt × model multiplier.
# Included/free models (GPT-4.1, GPT-4o, GPT-5 mini) have multiplier 0 on paid plans.
#
# Key: lower-case substring match against normalised model id.
# Value: float multiplier — first match wins.
COPILOT_MULTIPLIER_TABLE = [
    # Ordered most-specific first to avoid early partial matches
    # Claude Opus fast mode (preview) — must come before plain opus
    ("claude-opus-4.6-fast",  30.0),
    ("claude-opus-4-6-fast",  30.0),
    ("opus-4.6-fast",         30.0),
    # Claude Opus 4.7
    ("claude-opus-4.7",        7.5),
    ("claude-opus-4-7",        7.5),
    # Claude Opus 4.5 / 4.6 (3x)
    ("claude-opus",            3.0),
    # Claude Haiku 4.5 (0.33x)
    ("claude-haiku",           0.33),
    # Claude Sonnet — all variants (1x)
    ("claude-sonnet",          1.0),
    # GPT included models — 0 premium requests on paid plans
    ("gpt-4.1",                0.0),
    ("gpt-4o",                 0.0),
    ("gpt-5-mini",             0.0),
    ("gpt-5mini",              0.0),
    # GPT-5.4 family
    ("gpt-5.4-nano",           0.25),
    ("gpt-5.4-mini",           0.33),
    ("gpt-5.4",                1.0),
    # GPT-5.3 / 5.2 (1x)
    ("gpt-5",                  1.0),
    # Gemini Flash (0.33x)
    ("gemini-3-flash",         0.33),
    ("gemini-3.1-flash",       0.33),
    ("gemini-2.5-flash",       0.33),
    # Gemini Pro (1x)
    ("gemini",                 1.0),
    # Grok Code Fast (0.25x)
    ("grok-code-fast",         0.25),
    # o-series / other OpenAI (1x fallback)
    ("o3",                     1.0),
    ("o4",                     1.0),
]


def get_model_multiplier(model_name):
    """Return the GitHub Copilot quota multiplier for *model_name* (default 1.0).

    Multipliers are floats — e.g. Claude Haiku is 0.33, Claude Opus is 3.0.
    Returns 1.0 for any unrecognised model (conservative default).
    """
    if not model_name:
        return 1.0
    lower = model_name.lower()
    for substr, mult in COPILOT_MULTIPLIER_TABLE:
        if substr in lower:
            return mult
    return 1.0


def _match_pricing(model_name):
    """Return pricing tuple for *model_name* or None if unrecognised.

    Matching order:
    1. Exact lower-case match
    2. Any pricing key that appears as a substring of the model name
    3. Family heuristics (gpt-4o-mini before gpt-4o, o3-mini before o3, etc.)
    """
    if not model_name:
        return None
    lower = model_name.lower()

    # 1. Exact match
    if lower in PRICING_TABLE:
        return PRICING_TABLE[lower]

    # 2. Substring match — longest key wins to avoid false positives
    matches = [(k, v) for k, v in PRICING_TABLE.items() if k in lower]
    if matches:
        best_key, best_val = max(matches, key=lambda kv: len(kv[0]))
        return best_val

    # 3. Family heuristics for model names with version suffixes
    if "gpt-4o-mini" in lower:
        return PRICING_TABLE["gpt-4o-mini"]
    if "gpt-4o" in lower or "gpt4o" in lower:
        return PRICING_TABLE["gpt-4o"]
    if "o4-mini" in lower:
        return PRICING_TABLE["o4-mini"]
    if "o3-mini" in lower or "o3mini" in lower:
        return PRICING_TABLE["o3-mini"]
    if "o3" in lower:
        return PRICING_TABLE["o3"]
    if "o1-mini" in lower or "o1mini" in lower:
        return PRICING_TABLE["o1-mini"]
    if "o1" in lower:
        return PRICING_TABLE["o1"]
    if "claude" in lower:
        if "haiku" in lower:
            return PRICING_TABLE["claude-3-5-haiku"]
        if "opus" in lower:
            return PRICING_TABLE["claude-opus-4"]
        return PRICING_TABLE["claude-sonnet-4"]  # default Claude family
    if "gemini" in lower:
        if "flash" in lower:
            return PRICING_TABLE["gemini-2.5-flash"]
        return PRICING_TABLE["gemini-2.5-pro"]

    return None


def estimate_cost(model_name, input_tokens, output_tokens,
                  cache_read=0, cache_creation=0):
    """Return estimated cost in USD (float), or None if model is unrecognised.

    Uses separate per-MTok rates for input, output, cache read, and cache
    creation tokens (NFR-07-B).
    """
    prices = _match_pricing(model_name)
    if prices is None:
        return None
    inp_price, out_price, cr_price, cc_price = prices
    cost = (
        input_tokens    * inp_price +
        output_tokens   * out_price +
        (cache_read     or 0) * cr_price +
        (cache_creation or 0) * cc_price
    ) / 1_000_000
    return cost


def format_cost(cost):
    """Format a cost float as a USD string, or return 'n/a' for None."""
    if cost is None:
        return "n/a"
    return "${:.4f}".format(cost)
