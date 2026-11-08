"""Input validation for every tool. Messages are written for the end user."""
from __future__ import annotations

import difflib

from agent.core.errors import KodiWiseError

AMENITY_FIELDS = {
    "generator": "has_generator", "borehole": "has_borehole", "cctv": "has_cctv",
    "dsq": "has_dsq", "play_area": "has_play_area", "garden": "has_garden",
}
_AMENITY_ALIASES = {
    "backup generator": "generator", "gen": "generator",
    "servant quarter": "dsq", "servant quarters": "dsq", "sq": "dsq", "d.s.q": "dsq",
    "play area": "play_area", "playground": "play_area", "kids play area": "play_area",
    "cctv camera": "cctv", "cameras": "cctv",
}
PROPERTY_TYPES = {"apartment", "house", "bedsitter"}
_TYPE_ALIASES = {"flat": "apartment", "studio": "bedsitter", "bed sitter": "bedsitter",
                 "maisonette": "house", "bungalow": "house"}

MAX_BEDROOMS = 10
MAX_BATHROOMS = 10
MIN_RENT, MAX_RENT = 3_000, 2_000_000


def bedrooms(n: object) -> int:
    if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= MAX_BEDROOMS:
        raise KodiWiseError(f"Bedrooms must be a whole number from 0 (studio/bedsitter) to {MAX_BEDROOMS}.")
    return n


def bathrooms(n: object) -> int:
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_BATHROOMS:
        raise KodiWiseError(f"Bathrooms must be a whole number from 1 to {MAX_BATHROOMS}.")
    return n


def rent(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not MIN_RENT <= value <= MAX_RENT:
        raise KodiWiseError(
            f"{what} must be a monthly amount in KES between {MIN_RENT:,} and {MAX_RENT:,}.")
    return float(value)


def sq_m(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 10 <= value <= 2000:
        raise KodiWiseError("Size must be between 10 and 2,000 square metres (or left out).")
    return float(value)


def property_type(value: object) -> str | None:
    if value is None:
        return None
    t = str(value).strip().lower()
    t = _TYPE_ALIASES.get(t, t)
    if t not in PROPERTY_TYPES:
        raise KodiWiseError("Property type must be one of: apartment, house, bedsitter (or left out).")
    return t


def amenities(values: object) -> list[str] | None:
    """None = the user did not say (sent as 'not given'); a list, even an
    empty one, is an answer."""
    if values is None:
        return None
    if isinstance(values, str) or not isinstance(values, (list, tuple, set)):
        raise KodiWiseError("Amenities must be a list such as [\"cctv\", \"generator\"].")
    out: list[str] = []
    for v in values:
        a = str(v).strip().lower().replace("-", "_")
        a = _AMENITY_ALIASES.get(a, a)
        if a not in AMENITY_FIELDS:
            raise KodiWiseError(
                f"Unknown amenity '{v}'. Known amenities: {', '.join(sorted(AMENITY_FIELDS))}.")
        if a not in out:
            out.append(a)
    return out


def location_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KodiWiseError("Please give a Nairobi neighbourhood name, e.g. Kilimani.")
    v = " ".join(value.split())
    if len(v) > 60:
        raise KodiWiseError("That neighbourhood name is too long.")
    return v


def location_list(values: object, lo: int = 2, hi: int = 6) -> list[str]:
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        raise KodiWiseError(f"Give a list of {lo} to {hi} neighbourhoods.")
    seen: dict[str, str] = {}
    for v in values:
        t = location_text(v)
        seen.setdefault(t.casefold(), t)
    out = list(seen.values())
    if not lo <= len(out) <= hi:
        raise KodiWiseError(f"Give between {lo} and {hi} different neighbourhoods (got {len(out)}).")
    return out


def suggest(name: str, known: list[str]) -> list[str]:
    return difflib.get_close_matches(name, known, n=3, cutoff=0.5)


def build_payload(location: str, beds: int, baths: int, size: float | None,
                  furnished: bool | None, ptype: str | None, amen: list[str] | None) -> dict:
    """Request body for /predict. Fields the user did not give are omitted so
    the API reports them as 'not given'. Same rule as the app: amenities are
    sent (all six, 0/1) only once the user has answered."""
    p: dict = {"bedrooms_num": beds, "bathrooms_num": baths, "location_std": location, "explain": True}
    if size is not None:
        p["sq_m"] = size
    if furnished is not None:
        p["is_furnished"] = 1 if furnished else 0
    if ptype is not None:
        p["property_type"] = ptype
    if amen is not None:
        for name, field in AMENITY_FIELDS.items():
            p[field] = 1 if name in amen else 0
    return p
