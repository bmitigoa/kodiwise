"""Instruction-like text in untrusted input (prompt-injection attempts).

Two jobs:
  * `scan` / `neutralise`: find text that tries to give the model orders (override phrases, role tags,
    tool-call syntax, "reveal your prompt", links) and cut it out, so it never reaches a model as a
    sentence it could obey. The event is logged with the source and the categories only, never the text.
  * `untrusted` / `plain`: untrusted strings (listing titles, areas, echoed user text) are returned to
    models inside a clearly named field, {"untrusted_text": "..."}; the system prompt and the MCP
    instructions say that content in such a field is data, not instructions.

Best effort: this lowers the risk, it does not remove it. The real protections are structural: tools are
read-only, arguments are validated again by agent.core.validate, and every figure in a reply is checked
against tool results.
"""
from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("kodiwise.security")

REMOVED = "[removed]"
UNTRUSTED_KEY = "untrusted_text"

_TOOLS = "estimate_rent|compare_areas|areas_within_budget|check_listing_price|search_listings|list_locations"
_PATTERNS: dict[str, re.Pattern] = {
    "override": re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass|skip)\b[^.\n]{0,40}?"
        r"\b(?:instructions?|rules?|prompts?|guidelines?|directions?|constraints?|guardrails?|polic(?:y|ies))\b",
        re.I),
    "reveal": re.compile(
        r"\b(?:reveal|show|print|repeat|leak|output|display)\b[^.\n]{0,30}?"
        r"\b(?:system prompt|your prompt|your instructions|hidden instructions|api key|secret|password|token)\b", re.I),
    "role_claim": re.compile(
        r"\b(?:you are now|from now on you|act as|pretend (?:to be|you are)|new instructions?|developer mode|"
        r"jailbreak|do anything now)\b", re.I),
    "role_tag": re.compile(
        r"(?:<\|?\s*/?\s*(?:system|assistant|user|developer|im_start|im_end)\s*\|?>|\[/?INST\]|<<\s*SYS\s*>>|"
        r"^\s*(?:system|assistant|developer)\s*:)", re.I | re.M),
    "tool_syntax": re.compile(
        rf"(?:function_?call|tool_?call|tool_use|\bcall\s+(?:the\s+)?(?:tool|function)\b|"
        rf"\b(?:{_TOOLS})\s*\(|\"name\"\s*:\s*\"(?:{_TOOLS})\")", re.I),
    "tell_user": re.compile(
        r"\b(?:tell|say to|respond with|answer with|reply with|inform)\b[^.\n]{0,25}?"
        r"\b(?:the user|users|everyone|the tenant|them)\b[^.\n]{0,40}", re.I),
    "url": re.compile(r"(?:https?://|www\.)\S+", re.I),
}


def scan(text: object) -> list[str]:
    """Categories of instruction-like text found in `text` (empty if none)."""
    if not isinstance(text, str) or not text:
        return []
    return [name for name, pat in _PATTERNS.items() if pat.search(text)]


def neutralise(text: str, source: str, log_event: bool = True) -> str:
    """`text` with every instruction-like span replaced by [removed]. Logs a redacted event."""
    cats: list[str] = []
    out = text
    for name, pat in _PATTERNS.items():
        if pat.search(out):
            cats.append(name)
            out = pat.sub(REMOVED, out)
    if cats and log_event:
        log.warning("instruction-like text neutralised: source=%s categories=%s", source, ",".join(cats))
        _count(source, cats)
    return re.sub(r"\s{2,}", " ", out).strip() if cats else out


def _count(source: str, cats: list[str]) -> None:
    try:
        from agent.core import telemetry
        telemetry.event("injection_neutralised", source=source, categories=",".join(cats))
    except Exception:      # observability must never break a request
        pass


def untrusted(text: str) -> dict[str, str]:
    return {UNTRUSTED_KEY: text}


def plain(value: Any) -> Any:
    """The string inside an {"untrusted_text": ...} field (cards and logs use plain text)."""
    if isinstance(value, dict) and UNTRUSTED_KEY in value:
        return value[UNTRUSTED_KEY]
    return value


def echo(text: object, limit: int = 40) -> str:
    """Safe way to repeat user- or model-supplied text inside a message: short, one line, neutralised."""
    s = neutralise(" ".join(str(text).split())[:200], "echo")      # cut instructions out before shortening
    return s[:limit]
