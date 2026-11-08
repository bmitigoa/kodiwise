"""Location normalisation (ml.features.normalize_location, unchanged),
cross-source / within-window dedupe."""
from __future__ import annotations

import pandas as pd

from ml.features import normalize_location


def candidate_texts(rec: dict) -> list[str]:
    """Most specific first. region_text parents are deliberately NOT used:
    mapping 'Kahawa Sukari' to its parent 'Kasarani' would be a guess."""
    return [t for t in (rec.get("region_name"), rec.get("property_address")) if t]


def map_location(rec: dict, known: list[str]) -> str | None:
    for t in candidate_texts(rec):
        hit = normalize_location(t, known)
        if hit:
            return hit
    return None


def dedupe(df: pd.DataFrame, existing_fingerprints: set[str],
           existing_ids: set[str], window_days: int = 30) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drop (a) listing ids / fingerprints already in the dataset, (b) repeats
    within this batch by id, and (c) near-identical price+beds+location+title
    within `window_days`. Returns (kept, dropped_with_reason)."""
    df = df.copy()
    df["_t"] = pd.to_datetime(df["scraped_at"], utc=True, errors="coerce")
    reason = pd.Series("", index=df.index)
    reason[df["listing_id"].isin(existing_ids)] = "already_in_dataset_id"
    reason[(reason == "") & df["fingerprint_hash"].isin(existing_fingerprints)] = "already_in_dataset_fingerprint"
    reason[(reason == "") & df.duplicated("listing_id", keep="first")] = "duplicate_id_in_batch"
    keyed = df[reason == ""].sort_values("_t")
    last: dict[str, pd.Timestamp] = {}
    for idx, row in keyed.iterrows():
        k = row["fingerprint_hash"]
        if k in last and (row["_t"] - last[k]).days <= window_days:
            reason[idx] = "near_duplicate_30d"
        else:
            last[k] = row["_t"]
    kept = df[reason == ""].drop(columns="_t")
    dropped = df[reason != ""].assign(drop_reason=reason[reason != ""]).drop(columns="_t")
    return kept, dropped
