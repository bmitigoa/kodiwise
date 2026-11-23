"""Strip personal details from a user's message before it goes to Gemini (free tier: Google may use
the data). Best effort: phone numbers, emails, links, long ID-like numbers and names the user
introduces themselves with. Free text cannot be scanned for every name, so the app also tells the
user not to share personal details."""
from __future__ import annotations

import re
from typing import Iterable

from agent.core import config

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
# Kenyan mobile: 07xx / 01xx / +2547xx / 2541xx, with optional spaces or dashes.
PHONE_KE = re.compile(r"(?<!\d)(?:\+?254[\s-]?|0)[17]\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)")
# Any other international number written with a leading +.
PHONE_INTL = re.compile(r"(?<![\w+])\+\d{1,3}[\s-]?\d[\d\s-]{6,}\d(?!\d)")
# 8+ digit runs (national ID, account numbers). Rents never reach 8 digits.
LONG_DIGITS = re.compile(r"(?<![\d,.])\d{8,}(?![\d,])")
# "my name is Jane Wanjiru", "I am Peter", "call me Ann", "this is Mary"
NAME_INTRO = re.compile(
    r"\b(?:my name is|my name's|i am|i'm|im|call me|this is|name:)\s+([A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){0,2})\b",
    re.I)
SPACES = re.compile(r"[ \t]+")

MAX_MESSAGE_CHARS = config.MAX_MESSAGE_CHARS


def strip_pii(text: str, known_names: Iterable[str] = (), keep: Iterable[str] = ()) -> str:
    """`known_names`: e.g. the user's display name from their token (removed wherever it appears).
    `keep`: words that are not personal even when capitalised after "I am" (area names)."""
    s = text[:MAX_MESSAGE_CHARS * 2]
    for pattern, repl in ((EMAIL, "[email removed]"), (URL, "[link removed]"),
                          (PHONE_KE, "[phone removed]"), (PHONE_INTL, "[phone removed]"),
                          (LONG_DIGITS, "[number removed]")):
        s = pattern.sub(repl, s)
    keep_l = {k.casefold() for k in keep}

    def _name(m: re.Match) -> str:
        words = m.group(1).split()
        if all(w.casefold() in keep_l for w in words) or m.group(1).casefold() in keep_l:
            return m.group(0)
        lead = m.group(0)[: m.start(1) - m.start(0)]
        return f"{lead}[name removed]"

    s = NAME_INTRO.sub(_name, s)
    for name in known_names:
        for part in {name.strip(), *name.split()}:
            if len(part) >= 3:
                s = re.sub(rf"\b{re.escape(part)}\b", "[name removed]", s, flags=re.I)
    s = SPACES.sub(" ", s).strip()
    return s[:MAX_MESSAGE_CHARS]
