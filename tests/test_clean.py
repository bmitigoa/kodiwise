import pandas as pd

from data_pipeline.clean import clean


def _row(**overrides):
    base = dict(
        title="Furnished 1bdrm Apartment in Kilimani for rent",
        title_clean="furnished 1bdrm apartment in kilimani for rent",
        price_kes=60000,
        location_std="Kilimani",
        sq_m=80,
        property_type_std="unknown",
        estate_name=None,
        is_furnished_page=1,
    )
    base.update(overrides)
    return base


def test_keyword_match_drops_short_stay_listing():
    df = pd.DataFrame([
        _row(),
        _row(title="Studio Apartment Airbnb", title_clean="studio apartment airbnb"),
    ])
    cleaned, dropped, steps = clean(df)
    assert len(cleaned) == 1
    assert dropped[0]["reason"] == "short_stay_keyword"


def test_low_rent_drops_regardless_of_keywords():
    df = pd.DataFrame([_row(), _row(price_kes=5000)])
    cleaned, dropped, steps = clean(df)
    assert len(cleaned) == 1
    assert dropped[0]["reason"] == "price_below_8000"


def test_rent_bound_excludes_extreme_price():
    df = pd.DataFrame([_row(), _row(price_kes=500000)])
    cleaned, dropped, _ = clean(df)
    assert len(cleaned) == 1
    assert dropped[0]["reason"] == "price_outside_3000_300000"


def test_dead_columns_are_dropped():
    df = pd.DataFrame([_row()])
    cleaned, _, _ = clean(df)
    for col in ("property_type_std", "estate_name", "is_furnished_page"):
        assert col not in cleaned.columns


def test_sq_m_out_of_range_becomes_missing_not_dropped():
    df = pd.DataFrame([_row(sq_m=5), _row(sq_m=5000)])
    cleaned, dropped, _ = clean(df)
    assert len(cleaned) == 2
    assert cleaned["sq_m"].isna().all()
    assert len(dropped) == 0


def test_row_counts_are_logged_per_step():
    df = pd.DataFrame([_row(), _row(price_kes=5000)])
    _, _, steps = clean(df)
    rule_names = [s["rule"] for s in steps]
    assert "start" in rule_names
    assert "final" in rule_names
    final = next(s for s in steps if s["rule"] == "final")
    assert final["rows_before"] == 2
    assert final["rows_dropped"] == 1
