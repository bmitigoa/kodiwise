import pytest

from data_pipeline.scrape.base import Fetcher
from data_pipeline.scrape.jiji import listing_id, parse_listing
from data_pipeline.scrape.nuxt import decode_nuxt_data
from data_pipeline.scrape.normalize import dedupe, map_location
import pandas as pd

KNOWN = ["Upperhill", "Kilimani", "Langata"]


def test_fetcher_refuses_delay_under_3s():
    with pytest.raises(ValueError):
        Fetcher("jiji", delay_s=2.0)


def test_listing_id():
    assert listing_id("/a/b/x-y-fHDMiMW3o5atPwXGBjmSzRCW.html") == "fHDMiMW3o5atPwXGBjmSzRCW"


def test_no_payload_is_reported_not_raised():
    assert decode_nuxt_data("<html></html>") is None
    assert parse_listing("<html></html>", "u")[1] == "no_payload"


def test_map_location_uses_region_name_then_address_and_never_parent():
    assert map_location({"region_name": "Upper Hill"}, KNOWN) == "Upperhill"
    assert map_location({"region_name": "Kahawa Sukari", "property_address": "Kilimani"}, KNOWN) == "Kilimani"
    assert map_location({"region_name": "Kahawa Sukari",
                         "region_text": "Nairobi, Kilimani, Kahawa Sukari"}, KNOWN) is None


def test_dedupe_rules():
    df = pd.DataFrame({
        "listing_id": ["a", "a", "b", "c", "d"],
        "fingerprint_hash": ["f1", "f1", "f2", "f2", "f9"],
        "scraped_at": ["2026-11-01"] * 5})
    kept, dropped = dedupe(df, existing_fingerprints={"f9"}, existing_ids=set())
    assert list(kept.listing_id) == ["a", "b"]
    assert set(dropped.drop_reason) == {"duplicate_id_in_batch", "near_duplicate_30d",
                                       "already_in_dataset_fingerprint"}
