"""Leak-free cleaning pipeline for the KodiWise baseline dataset.

Applies the project rules section 10 rules, in order, to the raw 580-row
enriched dataset copied from rent_ml. Logs row counts before/after each
rule and writes every dropped row (title, price, neighbourhood, reason)
to data/processed/dropped_rows.csv for manual review.

Run: python -m data_pipeline.clean
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

RAW_PATH = Path("data/raw/nairobi_rentals_enriched_v4.csv")
CLEAN_PATH = Path("data/processed/nairobi_rentals_clean.csv")
DROPPED_PATH = Path("data/processed/dropped_rows.csv")
LOG_PATH = Path("data/processed/clean_log.json")

# Scope rule: Nairobi County only (paper scope; project rules Phase 3 cleaning
# rules). The platform's own `location` field is "<area>, <sub-area>" --
# e.g. "Nakuru, Nakuru Town East" -- so a first segment naming one of
# Kenya's other 46 counties means the listing is outside Nairobi, whatever
# location_std it was mapped to (found: a Nakuru "Pipeline" listing filed
# under Nairobi's Pipeline). Matching only the whole first segment, not a
# substring, keeps Nairobi roads named after towns ("Mombasa Road",
# "Thika Road", "Isiolo Road").
NON_NAIROBI_COUNTIES = {
    "mombasa", "kwale", "kilifi", "tana river", "lamu", "taita taveta",
    "garissa", "wajir", "mandera", "marsabit", "isiolo", "meru",
    "tharaka nithi", "embu", "kitui", "machakos", "makueni", "nyandarua",
    "nyeri", "kirinyaga", "murang'a", "muranga", "kiambu", "turkana",
    "west pokot", "samburu", "trans nzoia", "uasin gishu", "elgeyo marakwet",
    "nandi", "baringo", "laikipia", "nakuru", "narok", "kajiado", "kericho",
    "bomet", "kakamega", "vihiga", "bungoma", "busia", "siaya", "kisumu",
    "homa bay", "migori", "kisii", "nyamira",
}


def is_outside_nairobi(location: object) -> bool:
    if not isinstance(location, str) or not location.strip():
        return False
    first = location.split(",")[0].strip().lower()
    return first in NON_NAIROBI_COUNTIES


# Rule 10.1: short-stay / non-monthly listings.
SHORT_STAY_KEYWORDS = [
    "bnb", "airbnb", "per night", "nightly", "check-out", "check in",
    "hostel", "daily", "weekly",
]
SHORT_STAY_MIN_RENT = 8000

# Rule 10.2 (partial): flat KES rent bound, documented as "KNBS-informed"
# in the original rent_ml cleaning scripts. No real per-segment KNBS
# benchmark data exists in rent_ml (see docs/PROGRESS.md) and Baraka has
# chosen not to fabricate one, so this flat bound is all that's enforced.
RENT_MIN = 3000
RENT_MAX = 300000

# Rule 10.3: dead columns (confirmed via inspection: property_type_std is
# 100% "unknown", estate_name is 100% empty, is_furnished_page is ~99% one
# constant value).
DEAD_COLUMNS = ["property_type_std", "estate_name", "is_furnished_page"]

# Rule 10.4: sq_m outside this range is treated as missing, not dropped.
SQ_M_MIN, SQ_M_MAX = 15, 1000


def _log_dropped(dropped: pd.DataFrame, reason: str, bucket: list[dict]) -> None:
    for _, row in dropped.iterrows():
        bucket.append({
            "title": row.get("title", ""),
            "price_kes": row.get("price_kes"),
            "neighbourhood": row.get("location_std", ""),
            "reason": reason,
        })


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    dropped_rows: list[dict] = []
    steps: list[dict] = []

    n0 = len(df)
    steps.append({"rule": "start", "rows_before": n0, "rows_after": n0, "rows_dropped": 0})

    # --- Scope: drop listings outside Nairobi County ---
    n_before = len(df)
    if "location" in df.columns:
        outside = df["location"].map(is_outside_nairobi).astype(bool)
    else:
        outside = pd.Series(False, index=df.index)
    _log_dropped(df[outside], "outside_nairobi_county", dropped_rows)
    df = df[~outside].copy()
    steps.append({
        "rule": "outside_nairobi_county (location field)",
        "rows_before": n_before, "rows_after": len(df), "rows_dropped": n_before - len(df),
    })

    # --- Rule 10.1a: keyword match on title / title_clean ---
    n_before = len(df)
    text = (df["title"].fillna("") + " " + df["title_clean"].fillna("")).str.lower()
    kw_pattern = "|".join(SHORT_STAY_KEYWORDS)
    is_short_stay_kw = text.str.contains(kw_pattern, regex=True)
    _log_dropped(df[is_short_stay_kw], "short_stay_keyword", dropped_rows)
    df = df[~is_short_stay_kw].copy()
    steps.append({
        "rule": "short_stay_keyword (title/title_clean)",
        "rows_before": n_before, "rows_after": len(df), "rows_dropped": n_before - len(df),
    })

    # --- Rule 10.1b: rent below KES 8,000 (independent signal of a
    # mislabeled nightly/daily rate scraped as if it were monthly) ---
    n_before = len(df)
    is_low_rent = df["price_kes"] < SHORT_STAY_MIN_RENT
    _log_dropped(df[is_low_rent], f"price_below_{SHORT_STAY_MIN_RENT}", dropped_rows)
    df = df[~is_low_rent].copy()
    steps.append({
        "rule": f"short_stay_low_rent (<{SHORT_STAY_MIN_RENT})",
        "rows_before": n_before, "rows_after": len(df), "rows_dropped": n_before - len(df),
    })

    # --- Rule 10.2: flat rent bound (documented "KNBS-informed" bound;
    # see note above re: no real KNBS benchmark data available) ---
    n_before = len(df)
    out_of_bound = (df["price_kes"] < RENT_MIN) | (df["price_kes"] > RENT_MAX)
    _log_dropped(df[out_of_bound], f"price_outside_{RENT_MIN}_{RENT_MAX}", dropped_rows)
    df = df[~out_of_bound].copy()
    steps.append({
        "rule": f"rent_bound ({RENT_MIN}-{RENT_MAX})",
        "rows_before": n_before, "rows_after": len(df), "rows_dropped": n_before - len(df),
    })

    # --- Rule 10.3: drop dead columns (no rows dropped, columns only) ---
    present_dead_cols = [c for c in DEAD_COLUMNS if c in df.columns]
    df = df.drop(columns=present_dead_cols)
    steps.append({
        "rule": f"drop_dead_columns ({present_dead_cols})",
        "rows_before": len(df), "rows_after": len(df), "rows_dropped": 0,
    })

    # --- Rule 10.4: sq_m outside [15, 1000] -> missing, not dropped ---
    n_before = len(df)
    out_of_range = (df["sq_m"] < SQ_M_MIN) | (df["sq_m"] > SQ_M_MAX)
    n_set_missing = int(out_of_range.sum())
    df.loc[out_of_range, "sq_m"] = pd.NA
    steps.append({
        "rule": f"sq_m_out_of_range_to_missing ([{SQ_M_MIN},{SQ_M_MAX}])",
        "rows_before": n_before, "rows_after": len(df), "rows_dropped": 0,
        "sq_m_values_set_missing": n_set_missing,
    })

    df = df.reset_index(drop=True)
    steps.append({"rule": "final", "rows_before": n0, "rows_after": len(df), "rows_dropped": n0 - len(df)})
    return df, dropped_rows, steps


def main() -> None:
    df = pd.read_csv(RAW_PATH)
    cleaned, dropped_rows, steps = clean(df)

    CLEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(CLEAN_PATH, index=False)

    dropped_df = pd.DataFrame(dropped_rows, columns=["title", "price_kes", "neighbourhood", "reason"])
    dropped_df.to_csv(DROPPED_PATH, index=False)

    log = {
        "generated": date.today().isoformat(),
        "source": str(RAW_PATH),
        "output": str(CLEAN_PATH),
        "steps": steps,
    }
    LOG_PATH.write_text(json.dumps(log, indent=2, default=str))

    print(f"Rows: {len(df)} -> {len(cleaned)} ({len(dropped_rows)} dropped)")
    for s in steps:
        print(s)


if __name__ == "__main__":
    main()
