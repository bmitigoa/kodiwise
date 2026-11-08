"""Per-row feature derivations, ported from the rent_ml scripts.

Sources (read-only, in rent_ml/scripts_feature_engineering/):
  clean_nairobi_and_features_v2.py   norm_text, bedrooms/bathrooms from title,
                                      fingerprint, rooms_total, bath_per_bed,
                                      AMENITY_PATTERNS (is_furnished), title_len
  clean_nairobi_and_features_v2_1.py title_clean, property type flags,
                                      income_band_final
  enrich_listings_strong_predictors_v4.py  extract_sq_m, keyword amenity flags

Only the per-row logic is ported. The dataset-wide fallbacks in v2 (fill a
missing bedroom/bathroom count with the location, then global, median) are
applied by ``fill_counts`` so a batch uses its own medians, as v2 did.
"""
from __future__ import annotations

import hashlib
import re

import numpy as np
import pandas as pd

AMENITY_PATTERNS = {"is_furnished": r"\bfurnished\b|\bfully furnished\b"}

# enrich_v4 keyword flags (substring match, as in has_kw)
KEYWORD_FLAGS = {
    "has_generator": ["generator", "backup generator"],
    "has_borehole": ["borehole"],
    "has_dsq": ["dsq", "servant quarter", "staff quarter"],
    "has_garden": ["garden", "private garden"],
    "has_cctv": ["cctv"],
    "has_play_area": ["play area", "children play"],
}


def norm_text(x: object) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return re.sub(r"\s+", " ", str(x).strip().lower())


def extract_bedrooms_from_title(title: object) -> float | None:
    t = norm_text(title)
    if re.search(r"\bstudio\b|\bbedsitter\b|\bbed sitter\b|\bsingle room\b", t):
        return 0
    m = re.search(r"(\d+)\s*[- ]?\s*(bedroom|bed|br)\b", t)
    if m:
        return int(m.group(1))
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8}
    m2 = re.search(r"\b(one|two|three|four|five|six|seven|eight)\s*(bedroom|bed)\b", t)
    return words[m2.group(1)] if m2 else None


def extract_bathrooms_from_title(title: object) -> float | None:
    m = re.search(r"(\d+(\.\d+)?)\s*[- ]?\s*(bathroom|bath|baths)\b", norm_text(title))
    return float(m.group(1)) if m else None


def infer_property_type(title_clean: str) -> str:
    """v2_1 rule on the lower-cased title."""
    if "bedsitter" in title_clean or "studio" in title_clean:
        return "bedsitter"
    if "apartment" in title_clean or "flat" in title_clean:
        return "apartment"
    if "maisonette" in title_clean:
        return "maisonette"
    if "house" in title_clean or "bungalow" in title_clean:
        return "house"
    if "villa" in title_clean:
        return "villa"
    return "apartment"


def income_band(price: float) -> str:
    return "low" if price < 25000 else "middle" if price < 60000 else "high"


def extract_sq_m(text: object) -> float | None:
    if not isinstance(text, str) or not text:
        return None
    t = text.lower()
    for pat in (r"(\d{2,5})\s*(sqm|sq m|m2|m²|square meters|square metres)",
                r"(\d{2,5})\s*(sqft|sq ft|ft2|ft²)"):
        m = re.search(pat, t)
        if m:
            val = float(m.group(1))
            return val * 0.092903 if "ft" in m.group(2) else val
    return None


def has_kw(text: str, kws: list[str]) -> int:
    t = text.lower()
    return int(any(k in t for k in kws))


def fingerprint(location_std: str, price: float, beds: float | None,
                baths: float | None, title: str) -> str:
    """v2 fingerprint: loc|price|beds|baths|title[:60], with the raw
    (unfilled) bedroom/bathroom numbers and -1 for missing."""
    b = -1.0 if beds is None or pd.isna(beds) else float(beds)
    ba = -1.0 if baths is None or pd.isna(baths) else float(baths)
    return (f"{norm_text(location_std)}|{int(round(price))}|{b}|{ba}|"
            f"{norm_text(title)[:60]}")


def derive_row_features(title: str, price: float, location_std: str,
                        beds_raw: float | None, baths_raw: float | None) -> dict:
    """Everything derivable from one row (no batch medians)."""
    title_norm = norm_text(title)
    title_clean = str(title).lower() if title is not None else ""
    ptype = infer_property_type(title_clean)
    studio = int(bool(re.search(
        r"\bstudio\b|\bbedsitter\b|\bbed sitter\b|\bsingle room\b", title_norm)))
    return {
        "title_clean": title_clean,
        "title_len": len(title_norm),
        "is_bedsitter": int(ptype == "bedsitter"),
        "is_apartment": int(ptype == "apartment"),
        "is_house": int(ptype == "house"),
        "is_studio_or_bedsitter": studio,
        "is_furnished": int(bool(re.search(AMENITY_PATTERNS["is_furnished"], title_norm))),
        "income_band_final": income_band(price),
        "log_price": float(np.log1p(price)),
        "fingerprint": fingerprint(location_std, price, beds_raw, baths_raw, title),
        "beds_from_title": extract_bedrooms_from_title(title),
        "baths_from_title": extract_bathrooms_from_title(title),
    }


def fill_counts(df: pd.DataFrame) -> pd.DataFrame:
    """v2 bedroom/bathroom fill chain + rooms_total/bath_per_bed.

    Needs columns bedrooms_raw, bathrooms_raw, beds_from_title,
    baths_from_title, is_studio_or_bedsitter, location_std.
    """
    df = df.copy()
    b = pd.to_numeric(df["bedrooms_raw"], errors="coerce")
    b = b.fillna(pd.to_numeric(df["beds_from_title"], errors="coerce"))
    b = b.mask(b.isna() & (df["is_studio_or_bedsitter"] == 1), 0)
    b = b.fillna(b.groupby(df["location_std"]).transform("median"))
    b = b.fillna(b.median())
    ba = pd.to_numeric(df["bathrooms_raw"], errors="coerce")
    ba = ba.fillna(pd.to_numeric(df["baths_from_title"], errors="coerce"))
    ba = ba.mask(ba.isna() & (df["is_studio_or_bedsitter"] == 1), 1)
    ba = ba.fillna(ba.groupby(df["location_std"]).transform("median"))
    ba = ba.fillna(ba.median())
    df["bedrooms_filled"] = b.clip(0, 10)
    df["bathrooms_filled"] = ba.clip(0.5, 10)
    df["rooms_total"] = df["bedrooms_filled"] + df["bathrooms_filled"]
    df["bath_per_bed"] = df["bathrooms_filled"] / (df["bedrooms_filled"] + 1e-6)
    return df


def fingerprint_hash(fp: str) -> str:
    """Stable id for a fingerprint. New rows store only this (never the title
    text inside the fingerprint); dedupe compares hashes."""
    return hashlib.sha1(fp.encode("utf8")).hexdigest()[:20]
