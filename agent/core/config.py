"""Every limit and threshold of the MCP server and the chat service, in one place.

Defaults are the values in production. Each can be overridden with an environment variable (name in the
table below); a bad or out-of-range override is ignored and the default is used, so a typo can never
loosen a limit past its hard bounds. No secrets live here.

`python -m agent.core.config` prints the table that README.md keeps in sync (tests/test_config_docs.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    name: str          # attribute name in this module
    env: str           # environment override
    default: float | int
    lo: float | int    # hard bounds for an override
    hi: float | int
    unit: str
    what: str


def _read(env: str, default, lo, hi):
    raw = os.environ.get(env)
    if raw is None or raw.strip() == "":
        return default
    try:
        val = type(default)(float(raw)) if isinstance(default, int) else float(raw)
    except ValueError:
        return default
    return val if lo <= val <= hi else default


LIMITS: tuple[Limit, ...] = (
    # --- tools (MCP server and chat) ---
    Limit("MAX_TOOL_CALLS", "KW_MAX_TOOL_CALLS", 4, 1, 8, "calls", "distinct tool calls per chat message"),
    Limit("MAX_PREDICTIONS", "KW_MAX_PREDICTIONS", 32, 1, 64, "estimates", "model estimates per tool call"),
    Limit("PARALLEL", "KW_PARALLEL", 5, 1, 10, "threads", "parallel estimate requests to the API"),
    Limit("DEFAULT_MAX_KM", "KW_DEFAULT_MAX_KM", 5.0, 0.5, 50.0, "km", "default radius for budget search near an area"),
    Limit("MIN_KM", "KW_MIN_KM", 0.5, 0.1, 5.0, "km", "smallest allowed max_km"),
    Limit("MAX_KM", "KW_MAX_KM", 50.0, 5.0, 100.0, "km", "largest allowed max_km"),
    Limit("MIN_RENT", "KW_MIN_RENT", 3_000, 500, 50_000, "KES", "smallest monthly rent or budget accepted"),
    Limit("MAX_RENT", "KW_MAX_RENT", 2_000_000, 100_000, 10_000_000, "KES", "largest monthly rent or budget accepted"),
    Limit("MAX_BEDROOMS", "KW_MAX_BEDROOMS", 10, 1, 20, "rooms", "most bedrooms accepted"),
    Limit("MAX_BATHROOMS", "KW_MAX_BATHROOMS", 10, 1, 20, "rooms", "most bathrooms accepted"),
    Limit("MIN_SQ_M", "KW_MIN_SQ_M", 10, 1, 100, "m²", "smallest floor area accepted"),
    Limit("MAX_SQ_M", "KW_MAX_SQ_M", 2000, 100, 10_000, "m²", "largest floor area accepted"),
    Limit("MAX_LOCATION_CHARS", "KW_MAX_LOCATION_CHARS", 60, 10, 200, "chars", "longest neighbourhood name accepted"),
    Limit("MAX_COMPARE_AREAS", "KW_MAX_COMPARE_AREAS", 6, 2, 10, "areas", "most areas in a comparison"),
    Limit("MAX_SEARCH_LIMIT", "KW_MAX_SEARCH_LIMIT", 20, 1, 50, "listings", "most listings one search returns"),
    Limit("LISTING_FETCH_LIMIT", "KW_LISTING_FETCH_LIMIT", 200, 10, 1000, "documents", "approved listings read per search"),
    Limit("MAX_TITLE_CHARS", "KW_MAX_TITLE_CHARS", 80, 20, 200, "chars", "longest listing title returned"),
    Limit("API_TIMEOUT_SECONDS", "KW_API_TIMEOUT_SECONDS", 20.0, 2.0, 60.0, "s", "timeout per kodiwise-api request"),
    Limit("API_RETRIES", "KW_API_RETRIES", 2, 0, 5, "retries", "retries per kodiwise-api request"),
    # --- chat service ---
    Limit("CHAT_USER_DAILY", "CHAT_USER_DAILY", 10, 1, 200, "messages", "chat messages per user per day (Nairobi day)"),
    Limit("CHAT_GLOBAL_DAILY_CAP", "CHAT_GLOBAL_DAILY_CAP", 0, 0, 100_000, "requests",
          "Gemini requests per model per day (Pacific day); 0 = refuse. Set on deploy (300)"),
    Limit("CHAT_RPM_CAP", "CHAT_RPM_CAP", 0, 0, 1000, "requests", "Gemini requests per model per minute; 0 = refuse. Set on deploy (12)"),
    Limit("CHAT_MAX_INSTANCES", "CHAT_MAX_INSTANCES", 1, 1, 10, "instances", "Cloud Run instances (the per-minute cap is split across them)"),
    Limit("CHAT_CONCURRENT", "CHAT_CONCURRENT", 3, 1, 20, "requests", "chat requests handled at once per instance"),
    Limit("MAX_HISTORY", "KW_MAX_HISTORY", 6, 1, 20, "messages", "previous messages sent to Gemini"),
    Limit("MAX_MESSAGE_CHARS", "KW_MAX_MESSAGE_CHARS", 500, 50, 2000, "chars", "longest user message sent to Gemini"),
    Limit("MAX_MODEL_TURN_CHARS", "KW_MAX_MODEL_TURN_CHARS", 300, 50, 1000, "chars", "longest earlier assistant turn kept"),
    Limit("MAX_REPLY_CHARS", "KW_MAX_REPLY_CHARS", 650, 200, 2000, "chars", "longest model reply kept"),
    Limit("MAX_OUTPUT_TOKENS", "KW_MAX_OUTPUT_TOKENS", 400, 100, 2000, "tokens", "Gemini output tokens per request"),
    Limit("GEMINI_TIMEOUT_SECONDS", "KW_GEMINI_TIMEOUT_SECONDS", 30.0, 5.0, 120.0, "s", "timeout per Gemini request"),
    Limit("MESSAGE_DEADLINE_SECONDS", "KW_MESSAGE_DEADLINE_SECONDS", 60.0, 10.0, 240.0, "s", "total time budget for one chat message"),
    Limit("MODEL_RETRIES", "KW_MODEL_RETRIES", 2, 0, 3, "retries", "re-asks after an empty or malformed model reply"),
    Limit("OVERLOAD_BACKOFF_SECONDS", "KW_OVERLOAD_BACKOFF_SECONDS", 1.5, 0.0, 10.0, "s", "wait before the one retry after a 503"),
    Limit("NUMBER_TOLERANCE_PERCENT", "KW_NUMBER_TOLERANCE_PERCENT", 1.0, 0.0, 5.0, "%", "how close a quoted figure must be to a tool figure"),
    Limit("MIN_CHECKED_AMOUNT", "KW_MIN_CHECKED_AMOUNT", 1000, 100, 100_000, "KES", "figures at or above this are checked against tool results"),
    Limit("USER_COUNTER_TTL_DAYS", "KW_USER_COUNTER_TTL_DAYS", 3, 1, 30, "days", "expireAt on counter documents"),
    # --- confidence tiers (must match ml.features.location_confidence; tested) ---
    Limit("CONFIDENCE_HIGH_MIN_LISTINGS", "KW_CONFIDENCE_HIGH_MIN", 10, 1, 100, "listings", "training listings for confidence \"high\""),
    Limit("CONFIDENCE_LOW_MIN_LISTINGS", "KW_CONFIDENCE_LOW_MIN", 3, 1, 100, "listings", "training listings for confidence \"low\" (below = \"none\")"),
)

for _l in LIMITS:
    globals()[_l.name] = _read(_l.env, _l.default, _l.lo, _l.hi)

BY_NAME = {l.name: l for l in LIMITS}
TOLERANCE = globals()["NUMBER_TOLERANCE_PERCENT"] / 100.0


def table() -> str:
    """Markdown table of the production defaults (what README.md shows)."""
    rows = ["| Setting | Default | Env override | Meaning |", "|---|---|---|---|"]
    for l in LIMITS:
        d = f"{l.default:,}" if isinstance(l.default, int) else f"{l.default:g}"
        rows.append(f"| `{l.name}` | {d} {l.unit} | `{l.env}` | {l.what} |")
    return "\n".join(rows)


if __name__ == "__main__":    # pragma: no cover
    print(table())
