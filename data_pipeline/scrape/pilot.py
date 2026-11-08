"""Pilot run: discover -> fetch (snapshots) -> parse -> normalise -> dedupe -> clean.

    python -m data_pipeline.scrape.pilot            # full run (network)
    python -m data_pipeline.scrape.pilot --parse-only   # re-parse snapshots

Outputs (all gitignored) under data/processed/pilot/.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date
from pathlib import Path

import pandas as pd

from data_pipeline import clean as clean_mod
from data_pipeline.derive import derive_row_features, fill_counts, fingerprint_hash
from data_pipeline.scrape import jiji
from data_pipeline.scrape.base import Fetcher, StopScraping, read_snapshot
from data_pipeline.scrape.normalize import dedupe, map_location

OUT = Path("data/processed/pilot")
EXISTING = Path("data/raw/nairobi_rentals_enriched_v4.csv")
CLEAN_EXISTING = Path("data/processed/nairobi_rentals_clean.csv")

# Jiji region slugs for neighbourhoods with < 10 clean training rows
# (probed 2026-11-08; slugs that 404 are reported as "no index page").
TARGET_SLUGS = {
    "Upperhill": "upperhill", "Gigiri": "gigiri", "Loresho": "loresho",
    "Spring Valley": "spring-valley", "Ngara": "ngara", "Hurlingham": "hurlingham",
    "Kitisuru": "kitisuru", "Githurai": "githurai", "Kasarani": "kasarani",
    "Kahawa Wendani": "kahawa-wendani", "Mwiki": "mwiki", "Dagoretti": "dagoretti",
    "Langata": "langata", "Runda": "runda", "Riverside": "riverside",
    "Donholm": "donholm", "Garden Estate": "garden-estate",
}
FILLER_SLUGS = ["kilimani", "westlands", "south-b", "kileleshwa", "utawala", "karen"]
TARGET_N, FILLER_N, PER_TARGET_CAP, PER_FILLER_CAP = 160, 40, 16, 8


def _existing_keys() -> tuple[set[str], set[str]]:
    d = pd.read_csv(EXISTING)
    ids = {jiji.listing_id(u) for u in d["url"].astype(str)} - {""}
    return ids, {fingerprint_hash(f) for f in d["fingerprint"]}


def discover_and_fetch(day: str, seed: int = 42) -> dict:
    ids, _ = _existing_keys()
    f = Fetcher("jiji")
    rng = random.Random(seed)
    log: dict = {"index": {}, "stopped": None}
    queue: dict[str, list[str]] = {}
    try:
        for label, slug in {**TARGET_SLUGS, **{s: s for s in FILLER_SLUGS}}.items():
            status, urls = jiji.discover(f, slug)
            fresh = [u for u in urls if jiji.listing_id(u) not in ids]
            log["index"][label] = {"slug": slug, "http": status,
                                   "on_page": len(urls), "not_in_dataset": len(fresh)}
            rng.shuffle(fresh)
            queue[label] = fresh
        # round-robin so every neighbourhood gets a fair share of the budget
        picked: list[tuple[str, str]] = []
        for group, cap, total in ((list(TARGET_SLUGS), PER_TARGET_CAP, TARGET_N),
                                  (FILLER_SLUGS, PER_FILLER_CAP, FILLER_N)):
            taken = {g: 0 for g in group}
            seen = {u for _, u in picked}
            while len([1 for p in picked if p[0] in group]) < total:
                progressed = False
                for g in group:
                    while queue.get(g) and taken[g] < cap:
                        u = queue[g].pop()
                        if u in seen:
                            continue
                        picked.append((g, u)); seen.add(u); taken[g] += 1
                        progressed = True
                        break
                    if len([1 for p in picked if p[0] in group]) >= total:
                        break
                if not progressed:
                    break
        log["picked"] = len(picked)
        for i, (g, u) in enumerate(picked, 1):
            lid = jiji.listing_id(u)
            status, html = f.get(u)
            log.setdefault("http", {}).setdefault(str(status), 0)
            log["http"][str(status)] += 1
            if status == 200:
                f.save_snapshot(day, lid, html)
            if i % 20 == 0:
                print(f"fetched {i}/{len(picked)}", flush=True)
        log["requests"] = f.n_requests
    except StopScraping as e:
        log["stopped"] = str(e)
        print("STOPPED:", e)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fetch_log.json").write_text(json.dumps(log, indent=2))
    return log


def parse_snapshots(day: str) -> tuple[pd.DataFrame, dict]:
    stats = {"snapshots": 0, "ok": 0, "skipped": {}}
    recs = []
    for p in sorted((Path("data/raw/snapshots/jiji") / day).glob("*.html.gz")):
        stats["snapshots"] += 1
        lid = p.name.split(".")[0]
        try:
            rec, status = jiji.parse_listing(read_snapshot(p), f"{jiji.BASE}/x-{lid}.html",
                                             scraped_at=f"{day}T00:00:00+00:00")
        except Exception as e:  # parser bug -> counted as a parse failure
            rec, status = None, f"exception:{type(e).__name__}"
        if rec is None:
            stats["skipped"][status] = stats["skipped"].get(status, 0) + 1
        else:
            stats["ok"] += 1
            recs.append(rec)
    return pd.DataFrame(recs), stats


def build_frame(raw: pd.DataFrame, known: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if known is None:
        known = sorted(set(pd.read_csv(CLEAN_EXISTING)["location_std"]) - {"Unknown"})
    raw = raw.copy()
    raw["location_std"] = [map_location(r, known) for r in raw.to_dict("records")]
    review = raw[raw["location_std"].isna()][
        ["listing_id", "region_name", "region_text", "property_address"]]
    df = raw[raw["location_std"].notna()].copy()
    feats = pd.DataFrame([
        derive_row_features(r.title, r.price_kes, r.location_std, r.bedrooms, r.bathrooms)
        for r in df.itertuples()], index=df.index)
    df = pd.concat([df, feats], axis=1)
    df["fingerprint_hash"] = df["fingerprint"].map(fingerprint_hash)
    # Old rule (kept by decision): a studio/bedsitter has 0 bedrooms, whatever
    # the platform's own count says; its property type is bedsitter.
    df["bedrooms_raw"] = df["bedrooms"].mask(df["is_studio_or_bedsitter"] == 1, 0)
    df["bathrooms_raw"] = df["bathrooms"]
    df = fill_counts(df)
    df["bedrooms_num"], df["bathrooms_num"] = df["bedrooms_filled"], df["bathrooms_filled"]
    df["platform"], df["source_host"] = "Jiji", "jiji.co.ke"
    df["location"] = df["region_text"]
    return df, review


TEXT_COLUMNS = ["title", "title_clean", "fingerprint", "region_name",
                "property_address", "beds_from_title", "baths_from_title"]


def minimise(df: pd.DataFrame) -> pd.DataFrame:
    """Drop everything that is listing text before anything is written to disk
    (data minimisation: only parsed numeric/flag fields and place names stay)."""
    return df.drop(columns=[c for c in TEXT_COLUMNS if c in df.columns])


def prune_snapshots(source: str = "jiji", keep_latest: int = 1,
                    root: Path = Path("data/raw/snapshots")) -> list[str]:
    """Delete raw HTML from all but the latest `keep_latest` run folders."""
    import shutil
    days = sorted(p for p in (root / source).glob("*") if p.is_dir())
    gone = []
    for p in days[:-keep_latest] if keep_latest else days:
        shutil.rmtree(p)
        gone.append(p.name)
    return gone


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse-only", action="store_true")
    ap.add_argument("--day", default=date.today().isoformat())
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not a.parse_only:
        discover_and_fetch(a.day)
    raw, pstats = parse_snapshots(a.day)
    df, review = build_frame(raw)
    review.to_csv(OUT / "location_review.csv", index=False)  # place names only
    ids, fps = _existing_keys()
    kept, dup = dedupe(df, fps, ids)
    minimise(dup).to_csv(OUT / "duplicates.csv", index=False)
    cleaned, dropped, steps = clean_mod.clean(kept)
    minimise(cleaned).to_csv(OUT / "pilot_clean.csv", index=False)
    minimise(kept).to_csv(OUT / "pilot_pre_clean.csv", index=False)
    pd.DataFrame(dropped).drop(columns=["title"], errors="ignore").to_csv(
        OUT / "pilot_clean_dropped.csv", index=False)
    summary = {"parse": pstats, "mapped": len(df), "unmapped_to_review": len(review),
               "duplicates": dup["drop_reason"].value_counts().to_dict(),
               "kept_after_dedupe": len(kept), "clean_steps": steps,
               "clean_rows": len(cleaned)}
    (OUT / "pilot_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    print("pruned old snapshot runs:", prune_snapshots())


if __name__ == "__main__":
    main()
