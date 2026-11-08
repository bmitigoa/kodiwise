"""data_pipeline.derive must reproduce the existing dataset's derived
columns exactly (per-row logic ported from the rent_ml scripts)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data_pipeline.derive import (KEYWORD_FLAGS, derive_row_features,
                                  extract_sq_m, fill_counts, has_kw)

RAW = Path("data/raw/nairobi_rentals_enriched_v4.csv")
pytestmark = pytest.mark.skipif(not RAW.exists(), reason="dataset not present (gitignored)")


@pytest.fixture(scope="module")
def raw() -> pd.DataFrame:
    return pd.read_csv(RAW)


@pytest.fixture(scope="module")
def derived(raw):
    f = pd.DataFrame([derive_row_features(r.title, r.price_kes, r.location_std,
                                          r.bedrooms, r.bathrooms)
                      for r in raw.itertuples()])
    return f


@pytest.mark.parametrize("col", [
    "title_clean", "title_len", "is_bedsitter", "is_apartment", "is_house",
    "is_studio_or_bedsitter", "is_furnished", "income_band_final", "fingerprint"])
def test_row_features_match_existing_dataset_exactly(raw, derived, col):
    assert (derived[col].values == raw[col].values).all()


def test_count_fill_chain_matches_existing_dataset(raw, derived):
    d = raw.copy()
    d["bedrooms_raw"], d["bathrooms_raw"] = raw.bedrooms, raw.bathrooms
    d["beds_from_title"] = derived.beds_from_title
    d["baths_from_title"] = derived.baths_from_title
    d["is_studio_or_bedsitter"] = derived.is_studio_or_bedsitter
    g = fill_counts(d)
    for c in ["bedrooms_filled", "bathrooms_filled", "rooms_total", "bath_per_bed"]:
        assert np.allclose(g[c], raw[c], atol=1e-4)


def test_sq_m_and_keyword_flags_match_up_to_text_truncation(raw):
    # The originals scanned the full page; only the first 4000 chars were
    # stored, so a handful of rows can differ. Require >= 99% agreement.
    txt = raw.amenities_text.fillna("")
    sq = pd.Series([extract_sq_m(t) or extract_sq_m(ti) for t, ti in zip(txt, raw.title)], dtype=float)
    assert ((sq.fillna(-1) - raw.sq_m.fillna(-1)).abs() < 1e-3).mean() >= 0.99
    for col, kws in KEYWORD_FLAGS.items():
        agree = (txt.map(lambda t: has_kw(t, kws)).values == raw[col].fillna(0).values).mean()
        assert agree >= 0.99, col
