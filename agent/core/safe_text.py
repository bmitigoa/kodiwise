"""Cleaning of landlord-written text before it reaches a model.

Listing titles are typed by landlords: untrusted input (a prompt-injection
path) that may also contain phone numbers or emails. We never return
descriptions, and titles are reduced to short plain text.
"""
from __future__ import annotations

import re
import unicodedata

MAX_TITLE_CHARS = 80

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
# 7+ digits, allowing spaces, dots, dashes, parentheses and a leading +
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{5,}\d(?!\w)")
_MARKUP = re.compile(r"[<>`{}\[\]\\|]")
_SPACES = re.compile(r"\s+")


def _strip_invisible(s: str) -> str:
    """Drop control, zero-width and bidi-override characters."""
    return "".join(
        ch for ch in s
        if unicodedata.category(ch) not in ("Cc", "Cf", "Cs", "Co") or ch in "\n\t"
    )


def clean_title(raw: object) -> str:
    if not isinstance(raw, str):
        return "(untitled)"
    s = _strip_invisible(raw)
    s = _EMAIL.sub("[removed]", s)
    s = _URL.sub("[removed]", s)
    s = _PHONE.sub("[removed]", s)
    s = _MARKUP.sub(" ", s)
    s = _SPACES.sub(" ", s).strip()
    if len(s) > MAX_TITLE_CHARS:
        s = s[: MAX_TITLE_CHARS - 1].rstrip() + "…"
    return s or "(untitled)"
