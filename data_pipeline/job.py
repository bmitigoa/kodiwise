"""Weekly scrape job (Cloud Run Job entrypoint).

    BUCKET=<name> MAX_LISTINGS=300 python -m data_pipeline.job
    LOCAL_STORE_DIR=<dir> ...            # same thing against a local folder

Reads the newest ``datasets/nairobi_rentals_clean_*.csv`` from the store,
scrapes new Jiji listings (<= MAX_LISTINGS pages, ~80% for neighbourhoods with
< 10 rows), parses, normalises, dedupes, applies the unchanged clean rules,
and writes a NEW dated dataset. Existing objects are never overwritten.
Raw HTML of the latest run is kept under ``snapshots/``; older runs are
deleted. Only counts are logged. Stops on 403/429.
"""
from __future__ import annotations

import io
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import pandas as pd

from data_pipeline import clean as clean_mod
from data_pipeline.merge import merge
from data_pipeline.scrape import jiji
from data_pipeline.scrape.base import Fetcher, StopScraping
from data_pipeline.scrape.normalize import dedupe
from data_pipeline.scrape.pilot import FILLER_SLUGS, build_frame, minimise

DATASET_RE = re.compile(r"^datasets/nairobi_rentals_clean_(\d{8})(?:_\d{6})?\.csv$")
# Jiji region slugs that exist for neighbourhoods (the 404s found in the pilot
# are left out: Langata, Runda, Riverside, Donholm, Garden Estate).
TARGET_SLUGS = {
    "Upperhill": "upperhill", "Gigiri": "gigiri", "Loresho": "loresho",
    "Spring Valley": "spring-valley", "Ngara": "ngara", "Hurlingham": "hurlingham",
    "Kitisuru": "kitisuru", "Githurai": "githurai", "Kasarani": "kasarani",
    "Kahawa Wendani": "kahawa-wendani", "Mwiki": "mwiki", "Dagoretti": "dagoretti",
}
LOW_ROWS = 10  # neighbourhoods below this many rows are "low"/"none"
TARGET_SHARE = 0.8


class Store(Protocol):
    def list(self, prefix: str) -> list[str]: ...
    def read(self, name: str) -> bytes: ...
    def write_new(self, name: str, data: bytes) -> None: ...   # raises FileExistsError
    def delete(self, name: str) -> None: ...


class LocalStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def list(self, prefix: str) -> list[str]:
        names = (p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        return sorted(n for n in names if n.startswith(prefix))

    def read(self, name: str) -> bytes:
        return (self.root / name).read_bytes()

    def write_new(self, name: str, data: bytes) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "xb") as fh:  # 'x': fail rather than overwrite
            fh.write(data)

    def delete(self, name: str) -> None:
        (self.root / name).unlink()


class GcsStore:
    def __init__(self, bucket: str) -> None:
        from google.cloud import storage
        # Application Default Credentials (gcloud auth application-default login);
        # no key files.
        self.bucket = storage.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT")).bucket(bucket)

    def list(self, prefix: str) -> list[str]:
        return sorted(b.name for b in self.bucket.list_blobs(prefix=prefix))

    def read(self, name: str) -> bytes:
        return self.bucket.blob(name).download_as_bytes()

    def write_new(self, name: str, data: bytes) -> None:
        from google.api_core.exceptions import PreconditionFailed
        try:
            self.bucket.blob(name).upload_from_string(data, if_generation_match=0)
        except PreconditionFailed as e:
            raise FileExistsError(name) from e

    def delete(self, name: str) -> None:
        self.bucket.blob(name).delete()


def latest_dataset(store: Store) -> str:
    found = sorted(n for n in store.list("datasets/") if DATASET_RE.match(n))
    if not found:
        raise RuntimeError("no dataset in store under datasets/")
    return found[-1]


def round_robin(queues: dict[str, list[str]], budget: int, per_cap: int) -> list[str]:
    picked: list[str] = []
    taken = {k: 0 for k in queues}
    seen: set[str] = set()
    while len(picked) < budget:
        progressed = False
        for k, q in queues.items():
            while q and taken[k] < per_cap and len(picked) < budget:
                u = q.pop()
                if u in seen:
                    continue
                seen.add(u)
                picked.append(u)
                taken[k] += 1
                progressed = True
                break
        if not progressed:
            break
    return picked


def write_dataset(store: Store, df: pd.DataFrame, day: str, now: datetime) -> str:
    data = df.to_csv(index=False).encode("utf8")
    name = f"datasets/nairobi_rentals_clean_{day.replace('-', '')}.csv"
    try:
        store.write_new(name, data)
    except FileExistsError:
        name = f"datasets/nairobi_rentals_clean_{now:%Y%m%d_%H%M%S}.csv"
        store.write_new(name, data)
    return name


def upload_snapshots_and_prune(store: Store, snap_dir: Path, day: str) -> tuple[int, int]:
    n_up = 0
    for p in sorted(snap_dir.glob("*.html.gz")):
        try:
            store.write_new(f"snapshots/jiji/{day}/{p.name}", p.read_bytes())
            n_up += 1
        except FileExistsError:
            pass
    n_del = 0
    for name in store.list("snapshots/jiji/"):
        if not name.startswith(f"snapshots/jiji/{day}/"):
            store.delete(name)
            n_del += 1
    return n_up, n_del


def _count(d: dict, key: str) -> None:
    d[key] = d.get(key, 0) + 1


def run(store: Store, max_listings: int, work_dir: Path, fetcher: Fetcher | None = None,
        now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    ts = now.isoformat(timespec="seconds")
    summary: dict = {"started": ts, "max_listings": max_listings, "stopped": None}

    base_name = latest_dataset(store)
    base = pd.read_csv(io.BytesIO(store.read(base_name)))
    summary["base_dataset"], summary["base_rows"] = base_name, len(base)
    known_ids = set(base["url"].astype(str).str.extract(r"-([A-Za-z0-9]{24})\.html")[0].dropna())
    known_hashes = set(base["fingerprint_hash"])
    known_locs = sorted(set(base["location_std"].dropna()) - {"Unknown"})
    counts = base["location_std"].value_counts()
    thin = [k for k in TARGET_SLUGS if counts.get(k, 0) < LOW_ROWS]
    summary["thin_neighbourhoods"] = thin

    f = fetcher or Fetcher("jiji", snapshot_root=work_dir / "snapshots")
    snap_dir = Path(f.snapshot_root) / "jiji" / day
    raw_recs: list[dict] = []
    parse_stats: dict = {"fetched": 0, "ok": 0, "skipped": {}}
    index_requests = 0
    try:
        t_queues: dict[str, list[str]] = {}
        f_queues: dict[str, list[str]] = {}
        for label in thin:
            index_requests += 1
            _, urls = jiji.discover(f, TARGET_SLUGS[label])
            t_queues[label] = [u for u in urls if jiji.listing_id(u) not in known_ids]
        for slug in FILLER_SLUGS:
            index_requests += 1
            _, urls = jiji.discover(f, slug)
            f_queues[slug] = [u for u in urls if jiji.listing_id(u) not in known_ids]
        n_target = int(max_listings * TARGET_SHARE) if t_queues else 0
        picked = round_robin(t_queues, n_target, per_cap=max(4, n_target // max(1, len(t_queues))))
        picked += round_robin(f_queues, max_listings - len(picked), per_cap=max(4, max_listings // 6))
        for url in picked:
            status, html = f.get(url)
            parse_stats["fetched"] += 1
            if status != 200:
                _count(parse_stats["skipped"], f"http_{status}")
                continue
            f.save_snapshot(day, jiji.listing_id(url), html)
            rec, st = jiji.parse_listing(html, url, scraped_at=ts)
            if rec is None:
                _count(parse_stats["skipped"], st)
            else:
                parse_stats["ok"] += 1
                raw_recs.append(rec)
    except StopScraping as e:
        summary["stopped"] = str(e)
    summary["parse"] = parse_stats
    summary["requests"] = getattr(f, "n_requests", None)
    summary["index_requests"] = index_requests

    new_rows = 0
    if raw_recs:
        df, review = build_frame(pd.DataFrame(raw_recs), known=known_locs)
        kept, dup = dedupe(df, known_hashes, known_ids)
        cleaned, dropped, _ = clean_mod.clean(kept)
        summary.update(unmapped_location=len(review), duplicates=len(dup),
                       dropped_by_clean=len(dropped),
                       unmapped_names=review["region_name"].value_counts().head(10).to_dict())
        if len(cleaned):
            out = merge(base, minimise(cleaned))
            new_rows = len(out) - len(base)
            summary["new_dataset"] = write_dataset(store, out, day, now)
            summary["new_rows_by_neighbourhood"] = cleaned["location_std"].value_counts().to_dict()
    summary["new_rows"] = new_rows

    n_up, n_del = upload_snapshots_and_prune(store, snap_dir, day) if snap_dir.exists() else (0, 0)
    summary["snapshots_uploaded"], summary["old_snapshots_deleted"] = n_up, n_del
    summary["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.write_new(f"runs/{now:%Y%m%dT%H%M%S}.json", json.dumps(summary, indent=2).encode())
    return summary


EXIT_STOPPED = 3  # 403/429 or robots disallow: this week is skipped


def main() -> int:
    max_listings = int(os.environ.get("MAX_LISTINGS", "300"))
    local = os.environ.get("LOCAL_STORE_DIR")
    store: Store = LocalStore(Path(local)) if local else GcsStore(os.environ["BUCKET"])
    with tempfile.TemporaryDirectory() as tmp:
        summary = run(store, max_listings, Path(tmp))
    print(json.dumps(summary))   # counts only; never listing text
    return EXIT_STOPPED if summary["stopped"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
