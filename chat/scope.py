"""Scope guard: decide, without a model, whether a message is a Nairobi rent question.

Refusing early saves a Gemini request (the free quota is the scarce resource) and keeps the assistant on
its job. The rule is deliberately generous: anything that mentions renting, a home, money, a covered area
or a Swahili housing word goes to the model. Only clear off-topic text, or a place KodiWise does not
cover, is refused. Short follow-ups ("and Westlands?", "why?") pass when the chat is already about rent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

RENT_WORDS = {
    "rent", "rents", "rental", "rentals", "renting", "kodi", "kukodi", "nyumba", "nyumbani", "bei", "bajeti",
    "chumba", "vyumba", "ghorofa", "house", "houses", "home", "homes", "apartment", "apartments", "flat", "flats",
    "bedsitter", "bedsit", "studio", "maisonette", "bungalow", "bedroom", "bedrooms", "bed", "beds", "bathroom",
    "bathrooms", "bath", "landlord", "tenant", "lease", "deposit", "estimate", "estimated", "price", "prices",
    "cost", "costs", "afford", "affordable", "budget", "listing", "listings", "neighbourhood", "neighbourhoods",
    "neighborhood", "estate", "area", "areas", "furnished", "unfurnished", "sqm", "expensive", "cheap",
    "cheaper", "compare", "near", "fair", "overpriced", "kes", "ksh", "kshs", "month", "monthly", "per",
}
OTHER_PLACES = {
    "mombasa", "kisumu", "nakuru", "eldoret", "nyeri", "thika", "ruiru", "kiambu", "kitengela", "ngong", "rongai",
    "machakos", "malindi", "naivasha", "kampala", "dar es salaam", "arusha", "kigali", "lagos", "accra", "london",
    "dubai", "johannesburg", "cape town", "new york",
}
GREETING = re.compile(
    r"^\s*(?:hi|hello|hey|hallo|habari|mambo|sasa|niaje|jambo|good (?:morning|afternoon|evening)|thanks|thank you|"
    r"asante|ok|okay|bye|goodbye|kwaheri)\b[\s!.?,]*(?:\w+\W*){0,3}$", re.I)
MONEY = re.compile(r"\b\d{1,3}(?:[ ,]\d{3})+\b|\b\d+\s?(?:k|m|kes|ksh|shillings?)\b", re.I)
_WORD = re.compile(r"[a-zA-Z']+")

GREETING_REPLY = ("Hello! I can help with rent in Nairobi: ask for an estimate, compare areas, find areas for your "
                  "budget, or check whether an asking rent is fair.")
OFF_TOPIC_REPLY = ("I can only help with renting a home in Nairobi: estimates, comparing areas, budgets and "
                   "checking an asking rent. What would you like to know?")
NOT_NAIROBI_REPLY = ("KodiWise covers Nairobi neighbourhoods only, so I can't estimate rent there. Tell me a "
                     "Nairobi area and I will help.")


@dataclass
class Verdict:
    allowed: bool
    reply: str = ""
    reason: str = ""          # "ok" | "greeting" | "off_topic" | "not_nairobi"


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def _mentions_area(text_l: str, areas: Iterable[str]) -> bool:
    return any(a.casefold() in text_l for a in areas)


def _mentions_other_place(text_l: str) -> bool:
    return any(re.search(rf"\b{re.escape(p)}\b", text_l) for p in OTHER_PLACES)


def on_topic(text: str, areas: Iterable[str]) -> bool:
    words = set(_words(text))
    t = text.casefold()
    return bool(words & RENT_WORDS) or bool(MONEY.search(text)) or _mentions_area(t, areas)


def check(user_messages: list[str], areas: Iterable[str]) -> Verdict:
    """`user_messages`: the user's messages in the chat, oldest first (already cleaned). The last one is
    the question being asked."""
    areas = list(areas)
    if not user_messages:
        return Verdict(False, OFF_TOPIC_REPLY, "off_topic")
    last = user_messages[-1]
    last_l = last.casefold()
    if _mentions_other_place(last_l) and not _mentions_area(last_l, areas):
        return Verdict(False, NOT_NAIROBI_REPLY, "not_nairobi")
    if on_topic(last, areas):
        return Verdict(True, reason="ok")
    if GREETING.match(last):
        return Verdict(False, GREETING_REPLY, "greeting")
    if len(_words(last)) <= 6 and any(on_topic(m, areas) for m in user_messages[:-1]):
        return Verdict(True, reason="ok")          # a short follow-up in a chat that is about rent
    return Verdict(False, OFF_TOPIC_REPLY, "off_topic")
