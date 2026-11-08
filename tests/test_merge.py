import pandas as pd
import pytest

from data_pipeline.derive import fingerprint_hash
from data_pipeline.merge import merge


def _base():
    return pd.DataFrame({"platform": ["Jiji"], "scraped_at": ["2026-01-27T15:00:00"],
                         "fingerprint": ["a|1|1|1|t"], "url": ["https://jiji.co.ke/x-" + "A" * 24 + ".html"],
                         "title": ["t"], "price_kes": [10000]})


def _new(fp="b|2|2|2|u", lid="B" * 24):
    return pd.DataFrame({"source": ["Jiji"], "scraped_at": ["2026-11-08T00:00:00+00:00"],
                         "fingerprint_hash": [fingerprint_hash(fp)], "listing_id": [lid],
                         "price_kes": [20000]})


def test_merge_adds_provenance_and_keeps_base_rows_unchanged():
    base = _base()
    out = merge(base, _new())
    assert len(out) == 2
    assert list(out["source"]) == ["Jiji", "Jiji"]
    assert list(out["scrape_date"]) == ["2026-01-27", "2026-11-08"]
    assert out.loc[0, "title"] == "t" and pd.isna(out.loc[1, "title"])  # no text for new rows
    assert out.loc[0, "price_kes"] == 10000


def test_merge_refuses_rows_already_in_base():
    with pytest.raises(ValueError):
        merge(_base(), _new(fp="a|1|1|1|t"))
    with pytest.raises(ValueError):
        merge(_base(), _new(lid="A" * 24))
