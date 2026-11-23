"""Hard guardrails applied in code to every reply, whatever the model wrote."""
from __future__ import annotations

import re
from typing import Any

from agent.core import config

MIN_CHECKED = config.MIN_CHECKED_AMOUNT   # amounts (KES) are checked; counts such as "2 bedrooms" are not
TOLERANCE = config.TOLERANCE              # "about 60k" for 59,749 is fine; invented prices are not
MAX_BASE_CHARS = config.MAX_REPLY_CHARS   # the model's own text; required wording is added after

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:[ ,]\d{3})+|\d+(?:\.\d+)?)\s*(k|m|million|thousand)?\b", re.I)


def kes(x: float) -> str:
    return f"KES {x:,.0f}"


def _numbers_in_text(text: str) -> list[float]:
    out = []
    for m in _NUM.finditer(text):
        raw, suffix = m.group(1), (m.group(2) or "").lower()
        try:
            val = float(raw.replace(",", "").replace(" ", ""))
        except ValueError:
            continue
        if suffix in ("k", "thousand"):
            val *= 1_000
        elif suffix in ("m", "million"):
            val *= 1_000_000
        out.append(val)
    return out


def _walk(obj: Any, acc: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        acc.append(float(obj))
    elif isinstance(obj, str):
        acc.extend(_numbers_in_text(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk(v, acc)


def allowed_numbers(tool_results: list[Any], user_texts: list[str]) -> list[float]:
    acc: list[float] = []
    _walk(tool_results, acc)
    for t in user_texts:
        acc.extend(_numbers_in_text(t))
    return acc


def untraceable_amounts(reply: str, allowed: list[float]) -> list[float]:
    """Amounts in the reply (>= 1000) that match no number from a tool result or the user's message."""
    bad = []
    for n in _numbers_in_text(reply):
        if n < MIN_CHECKED:
            continue
        if not any(abs(n - a) <= max(1.0, TOLERANCE * a) for a in allowed):
            bad.append(n)
    return bad


_AMT = r"(?:\d{1,3}(?:,\s?\d{3}|\s\d{3})+|\d+(?:\.\d+)?)"
_SUF = r"(?:\s?(?:k|m|million|thousand)\b)?"
_MONEY = re.compile(
    rf"(?<![A-Za-z])(?:K\s?ES|KSh?s?)\.?\s*(?P<a>{_AMT}){_SUF}"          # KES 45,510 / KES45,510 / K ES 45, 510
    rf"|(?<![\w.,])(?P<b>{_AMT}){_SUF}\s*(?:KES|KSh?s?)\b",                # 45,510KES / 45,510 KES
    re.I)


def _money_value(raw: str, text: str) -> float | None:
    m = re.match(r"\s?(k|m|million|thousand)\b", text[len(raw):], re.I)
    try:
        val = float(re.sub(r"[,\s]", "", raw))
    except ValueError:
        return None
    if m:
        val *= 1_000 if m.group(1).lower() in ("k", "thousand") else 1_000_000
    return val


def normalize_money(reply: str, allowed: list[float]) -> str | None:
    """Rewrite every KES figure as "KES 45,510", using the tool's own number, and fix the spacing around it.
    Returns None if a figure of KES 1,000 or more matches no tool or user number (the caller then uses the
    templated answer instead)."""
    failed = False

    def one(m: re.Match) -> str:
        nonlocal failed
        raw = m.group("a") or m.group("b")
        val = _money_value(raw, m.group(0)[m.group(0).find(raw):])
        if val is None:
            failed = True
            return m.group(0)
        if val < MIN_CHECKED:
            return f"KES {val:,.0f}"
        near = [a for a in allowed if abs(val - a) <= max(1.0, TOLERANCE * a)]
        if not near:
            failed = True
            return m.group(0)
        best = min(near, key=lambda a: abs(a - val))
        before = reply[m.start() - 1] if m.start() else " "
        after = reply[m.end()] if m.end() < len(reply) else " "
        lead = " " if (before.isalnum() or before in ":;,") else ""      # one space before, unless at an opening mark
        tail = " " if after.isalnum() else ""                            # one space after, none before punctuation
        return lead + f"KES {best:,.0f}" + tail

    out = _MONEY.sub(one, reply)
    if failed:
        return None
    return re.sub(r"[ 	]{2,}", " ", out)


def fallback_reply(cards: list[dict]) -> str:
    """Plain wording built only from the cards, used when the model's text fails the number check."""
    parts = []
    for c in cards:
        if c["type"] == "estimate":
            conf = f" Confidence: {c['confidence']}." if c.get("confidence") else ""
            parts.append(f"{c['area']}: about {kes(c['estimate_kes'])} a month "
                         f"(range {kes(c['range_low_kes'])} to {kes(c['range_high_kes'])}).{conf}")
        elif c["type"] == "areas":
            rows = (c.get("areas") or []) + (c.get("comfortable") or []) + (c.get("stretch") or [])
            parts.append("Here is what I found; see the cards for each area's range.")
            if not rows:
                parts[-1] = "No area matched."
    return " ".join(parts) or "Sorry, I couldn't put a reliable answer together. Please try the Rent Assistant."


def finish(reply: str, cards: list[dict], guard_failed: bool) -> str:
    """Required wording, added deterministically: range for a single estimate, thin-data note,
    and "estimate only"."""
    empty = not reply.strip()
    if (guard_failed or empty) and cards:
        text = fallback_reply(cards)
    elif guard_failed:
        text = "Sorry, I can only share rent figures that come from KodiWise's estimates. Please ask me for an estimate."
    elif empty:
        text = "Sorry, I couldn't answer that. Please try again or use the Rent Assistant."
    else:
        text = reply.strip()
    if len(text) > MAX_BASE_CHARS:
        text = text[: MAX_BASE_CHARS - 1].rstrip() + "…"
    est = [c for c in cards if c["type"] == "estimate"]
    if len(est) == 1 and not guard_failed:
        c = est[0]
        lo, hi = f"{c['range_low_kes']:,.0f}", f"{c['range_high_kes']:,.0f}"
        if lo not in text or hi not in text:
            text += f" Range: {kes(c['range_low_kes'])} to {kes(c['range_high_kes'])}."
    thin = sorted({r["area"] for c in cards for r in _rows(c) if r.get("confidence") in ("low", "none") and r.get("area")})
    if thin and not re.search(r"thin|rough|little|limited|few listings|not much", text, re.I):
        text += f" Note: {', '.join(thin)} {'has' if len(thin) == 1 else 'have'} little local data, so treat that figure as rough."
    if cards and "estimate only" not in text.lower():
        text += " Estimate only, not a valuation."
    return text


def _rows(card: dict) -> list[dict]:
    if card["type"] == "estimate":
        return [card]
    return (card.get("areas") or []) + (card.get("comfortable") or []) + (card.get("stretch") or [])
