"""Merge cleaned scraped rows into a NEW dataset version.

The existing clean file is never modified. New rows carry no listing text
(title/title_clean/fingerprint are blank; ``fingerprint_hash`` is the dedupe
key) and every row gets ``source``, ``scrape_date`` and ``fingerprint_hash``.

    python -m data_pipeline.merge --new data/processed/pilot/pilot_clean.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from data_pipeline.derive import fingerprint_hash

BASE = Path("data/processed/nairobi_rentals_clean.csv")
VERSIONS = Path("data/processed/versions")


def merge(base: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    base = base.copy()
    if "source" not in base.columns:
        base["source"] = base["platform"]
    if "scrape_date" not in base.columns:
        base["scrape_date"] = pd.to_datetime(base["scraped_at"], errors="coerce").dt.date.astype("string")
    if "fingerprint_hash" not in base.columns:
        base["fingerprint_hash"] = base["fingerprint"].map(fingerprint_hash)
    new = new.copy()
    new["scrape_date"] = pd.to_datetime(new["scraped_at"], utc=True, errors="coerce").dt.date.astype("string")
    new["platform"] = new["source"]
    dup = new["fingerprint_hash"].isin(base["fingerprint_hash"]) | new["listing_id"].isin(
        base["url"].astype(str).str.extract(r"-([A-Za-z0-9]{24})\.html")[0])
    if dup.any():
        raise ValueError(f"{int(dup.sum())} new rows already in the base dataset")
    # new rows only carry what they have; every other base column stays empty
    cols = list(base.columns) + [c for c in new.columns if c not in base.columns]
    return pd.concat([base, new], ignore_index=True)[cols]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = merge(pd.read_csv(BASE), pd.read_csv(a.new))
    VERSIONS.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else VERSIONS / f"nairobi_rentals_clean_{pd.Timestamp.today():%Y%m%d}.csv"
    out.to_csv(path, index=False)
    print(path, len(out), out["source"].value_counts().to_dict())


if __name__ == "__main__":
    main()
