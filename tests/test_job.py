"""Weekly scrape job against a local store and a fake (offline) fetcher."""
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from data_pipeline.derive import fingerprint_hash
from data_pipeline.job import LocalStore, latest_dataset, round_robin, run

NOW = datetime(2026, 11, 9, 0, 0, 5, tzinfo=timezone.utc)


def nuxt_html(advert: dict) -> str:
    """Encode `advert` the way Nuxt does (flat array, ints are references)."""
    arr: list = []

    def add(v):
        if isinstance(v, dict):
            idx = len(arr); arr.append(None)
            arr[idx] = {k: add(x) for k, x in v.items()}
            return idx
        if isinstance(v, list):
            idx = len(arr); arr.append(None)
            arr[idx] = [add(x) for x in v]
            return idx
        arr.append(v)
        return len(arr) - 1

    add({"data": {"ad": advert}})
    return f'<html><script type="application/json" id="__NUXT_DATA__">{json.dumps(arr)}</script></html>'


def advert(guid, price=50000, region="Upperhill", period="per month", beds=2, title=None):
    return {
        "guid": guid, "category_slug": "houses-apartments-for-rent", "is_active": True,
        "is_closed": False, "title": title or f"{beds}bdrm Apartment in {region} for rent {guid[:4]}",
        "description": "nice place with cctv", "date_created": "x", "count_images": 3,
        "price_obj": {"value": price, "period": period}, "region_name": region,
        "region_text": f"Nairobi, {region}", "url": f"/{region.lower()}/houses-apartments-for-rent/x-{guid}.html",
        "attrs": [{"name": "Bedrooms", "value": beds}, {"name": "Bathrooms", "value": 1},
                  {"name": "Property Address", "value": region}],
    }


def gid(c: str) -> str:
    return (c * 24)[:24]


class FakeFetcher:
    def __init__(self, root: Path, listings: dict[str, str]):
        self.snapshot_root = root
        self.listings = listings          # url -> html
        self.n_requests = 0
        self.fetched: list[str] = []
        self.stop_after: int | None = None

    def get(self, url):
        self.n_requests += 1
        if "?page" not in url and url.endswith("houses-apartments-for-rent"):
            slug = url.split("/")[-2]
            links = "".join(f'<a href="{u[len("https://jiji.co.ke"):]}">x</a>'
                            for u in self.listings if u.split("/")[3] == slug)
            return 200, f"<html>{links}</html>"
        from data_pipeline.scrape.base import StopScraping
        if self.stop_after is not None and len(self.fetched) >= self.stop_after:
            raise StopScraping("HTTP 429")
        self.fetched.append(url)
        return 200, self.listings[url]

    def save_snapshot(self, day, key, text):
        p = self.snapshot_root / "jiji" / day / f"{key}.html.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(gzip.compress(text.encode()))


def url_of(slug, g):
    return f"https://jiji.co.ke/{slug}/houses-apartments-for-rent/x-{g}.html"


def base_df() -> pd.DataFrame:
    rows = [{"url": url_of("kilimani", gid("A")), "location_std": "Kilimani", "platform": "Jiji",
             "scraped_at": "2026-01-01T00:00:00", "price_kes": 90000, "source": "Jiji",
             "scrape_date": "2026-01-01", "fingerprint_hash": fingerprint_hash("old")}]
    rows += [{"url": url_of("kilimani", gid(c)), "location_std": "Kilimani", "platform": "Jiji",
              "scraped_at": "2026-01-01T00:00:00", "price_kes": 80000, "source": "Jiji",
              "scrape_date": "2026-01-01", "fingerprint_hash": fingerprint_hash(c)} for c in "BCDEFGHIJK"]
    rows += [{"url": url_of("upperhill", gid("U")), "location_std": "Upperhill", "platform": "Jiji",
              "scraped_at": "2026-01-01T00:00:00", "price_kes": 70000, "source": "Jiji",
              "scrape_date": "2026-01-01", "fingerprint_hash": fingerprint_hash("u")}]
    return pd.DataFrame(rows)


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / "bucket")
    s.write_new("datasets/nairobi_rentals_clean_20260108.csv", base_df().to_csv(index=False).encode())
    s.write_new("snapshots/jiji/2026-11-02/old.html.gz", b"old run")
    return s


def listings():
    L = {}
    for g, a in {
        gid("n"): advert(gid("n"), 60000, "Upperhill"),                       # new, thin hood
        gid("m"): advert(gid("m"), 65000, "Upperhill", beds=3),               # new, thin hood
        gid("U"): advert(gid("U"), 70000, "Upperhill"),                       # id already in base
        gid("w"): advert(gid("w"), 5000, "Upperhill", period="per night"),    # not monthly
        gid("c"): advert(gid("c"), 400000, "Upperhill"),                      # over KES 300k cap
        gid("f"): advert(gid("f"), 95000, "Kilimani"),                        # filler
    }.items():
        L[url_of(a["region_name"].lower(), g)] = nuxt_html(a)
    return L


def test_run_writes_new_dataset_without_touching_old_and_prunes(store, tmp_path):
    f = FakeFetcher(tmp_path / "w", listings())
    s = run(store, 20, tmp_path / "w", fetcher=f, now=NOW)

    assert s["new_rows"] == 3 and s["stopped"] is None
    assert s["new_dataset"] == "datasets/nairobi_rentals_clean_20261109_000005.csv"
    old = pd.read_csv(pd.io.common.BytesIO(store.read("datasets/nairobi_rentals_clean_20260108.csv")))
    assert len(old) == 12                                        # base file unchanged
    new = pd.read_csv(pd.io.common.BytesIO(store.read(s["new_dataset"])))
    assert len(new) == 15 and (new.scrape_date == "2026-11-09").sum() == 3
    assert new[["title", "title_clean"]].isna().all().all() if "title" in new else True
    assert "description" not in new.columns
    assert s["dropped_by_clean"] == 1                             # the 400k listing
    assert s["parse"]["skipped"] == {"not_monthly_rent": 1}
    # already-known id was never fetched
    assert url_of("upperhill", gid("U")) not in f.fetched
    # snapshots: new run kept, older run deleted
    snaps = store.list("snapshots/jiji/")
    assert snaps and all(n.startswith("snapshots/jiji/2026-11-09/") for n in snaps)
    assert s["old_snapshots_deleted"] == 1
    assert store.list("runs/")


def test_max_listings_cap_is_respected(store, tmp_path):
    f = FakeFetcher(tmp_path / "w", listings())
    s = run(store, 2, tmp_path / "w", fetcher=f, now=NOW)
    assert s["parse"]["fetched"] == 2 and len(f.fetched) == 2


def test_every_run_gets_a_timestamped_file_and_never_overwrites(store, tmp_path):
    s1 = run(store, 20, tmp_path / "w1", fetcher=FakeFetcher(tmp_path / "w1", listings()), now=NOW)
    assert s1["new_dataset"] == "datasets/nairobi_rentals_clean_20261109_000005.csv"
    first = store.read(s1["new_dataset"])
    later = datetime(2026, 11, 9, 0, 30, 0, tzinfo=timezone.utc)
    L2 = listings()
    L2[url_of("upperhill", gid("z"))] = nuxt_html(advert(gid("z"), 45000, "Upperhill", beds=1))
    s2 = run(store, 20, tmp_path / "w2", fetcher=FakeFetcher(tmp_path / "w2", L2), now=later)
    assert s2["new_dataset"] == "datasets/nairobi_rentals_clean_20261109_003000.csv"
    assert store.read(s1["new_dataset"]) == first          # first file untouched
    assert s2["new_rows"] == 1                              # only the genuinely new listing
    assert not [n for n in store.list("datasets/") if len(n.rsplit("_", 1)) == 2 and n.endswith("20261109.csv")]
    assert latest_dataset(store) == s2["new_dataset"]


def test_stops_on_429_and_keeps_what_it_has(store, tmp_path):
    f = FakeFetcher(tmp_path / "w", listings())
    f.stop_after = 2
    s = run(store, 20, tmp_path / "w", fetcher=f, now=NOW)
    assert s["stopped"] == "HTTP 429"
    assert s["parse"]["fetched"] == 2


def test_round_robin_spreads_budget():
    q = {"a": ["a1", "a2", "a3"], "b": ["b1"], "c": []}
    got = round_robin(q, 3, per_cap=5)
    assert len(got) == 3 and "b1" in got
