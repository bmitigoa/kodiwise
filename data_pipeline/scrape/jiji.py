"""Jiji (jiji.co.ke) listing discovery and parsing.

Robots.txt allows these paths; the terms of use have no automated-access
clause (checked 2026-11-08, see docs/PROGRESS.md). We read only the fields
the model needs. Advertiser names, phone numbers and photos are never
stored in the parsed record (the raw snapshot is private and gitignored).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from data_pipeline.derive import KEYWORD_FLAGS, extract_sq_m, has_kw
from data_pipeline.scrape.base import Fetcher
from data_pipeline.scrape.nuxt import decode_nuxt_data, find_advert

BASE = "https://jiji.co.ke"
CATEGORY = "houses-apartments-for-rent"
_LINK_RE = re.compile(r'href="(/[a-z0-9-]+/%s/[^"?#]*\.html)' % CATEGORY)


def index_url(region_slug: str, page: int = 1) -> str:
    u = f"{BASE}/{region_slug}/{CATEGORY}"
    return u if page == 1 else f"{u}?page={page}"


def listing_id(url_or_path: str) -> str:
    m = re.search(r"-([A-Za-z0-9]{24})\.html", url_or_path)
    return m.group(1) if m else ""


def discover(fetcher: Fetcher, region_slug: str, page: int = 1) -> tuple[int, list[str]]:
    status, html = fetcher.get(index_url(region_slug, page))
    if status != 200:
        return status, []
    seen: dict[str, str] = {}
    for path in _LINK_RE.findall(html):
        seen.setdefault(listing_id(path), BASE + path)
    return status, [u for k, u in seen.items() if k]


def _attrs(advert: dict) -> dict:
    return {a.get("name"): a.get("value") for a in advert.get("attrs") or []}


def parse_listing(html: str, url: str, scraped_at: str | None = None) -> tuple[dict | None, str]:
    """Return (record, status). status is 'ok' or a reason the page was
    not usable ('no_payload', 'no_advert', 'inactive', 'not_monthly_rent',
    'no_price')."""
    root = decode_nuxt_data(html)
    if root is None:
        return None, "no_payload"
    ad = find_advert(root)
    if ad is None:
        return None, "no_advert"
    if ad.get("category_slug") != CATEGORY:
        return None, "wrong_category"
    if not ad.get("is_active", True) or ad.get("is_closed"):
        return None, "inactive"
    po = ad.get("price_obj") or {}
    if not isinstance(po.get("value"), (int, float)):
        return None, "no_price"
    if (po.get("period") or "").lower() != "per month":
        return None, "not_monthly_rent"

    at = _attrs(ad)
    title = ad.get("title") or ""
    desc = ad.get("description") or ""
    # Flags come from title + description only (closest to the original
    # whole-page method; Jiji's Facilities tag list is deliberately not used).
    text = f"{title} {desc}"
    size = at.get("Property Size")
    unit = next((a.get("unit") for a in ad["attrs"] if a.get("name") == "Property Size"), None)
    if isinstance(size, (int, float)) and unit and "sq" in str(unit).lower():
        sq_m = float(size)
    else:
        sq_m = extract_sq_m(desc) or extract_sq_m(title)
    rec = {
        "source": "Jiji",
        "listing_id": ad.get("guid") or listing_id(url),
        "url": (BASE + ad["url"]) if ad.get("url") else url.split("?")[0],
        "scraped_at": scraped_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "listed_at": ad.get("date_created"),
        "title": title,
        "price_kes": float(po["value"]),
        "bedrooms": at.get("Bedrooms") if isinstance(at.get("Bedrooms"), (int, float)) else None,
        "bathrooms": at.get("Bathrooms") if isinstance(at.get("Bathrooms"), (int, float)) else None,
        "sq_m": sq_m,
        "property_type_raw": at.get("Property Type"),
        "furnishing_raw": at.get("Furnishing"),
        "region_name": ad.get("region_name"),
        "region_text": ad.get("region_text"),
        "property_address": at.get("Property Address"),
        "n_images": ad.get("count_images"),
    }
    for flag, kws in KEYWORD_FLAGS.items():
        rec[flag] = has_kw(text, kws)
    return rec, "ok"
