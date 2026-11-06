import numpy as np
import pandas as pd

from ml.features import (
    FeatureSet,
    add_location_stats,
    build_location_lookup,
    build_preprocessor,
    coerce_dtypes,
    get_feature_names,
    lookup_location_stats,
    normalize_location,
    property_type_flags,
    recompute_rooms_bath_from_counts,
    resolve_location,
)

TINY_FS = FeatureSet(
    name="tiny",
    numeric=["bedrooms_num", "bathrooms_num", "rooms_total", "bath_per_bed", "sq_m",
             "title_len", "loc_mean_tr", "loc_median_tr", "loc_count_tr"],
    binary=["has_parking"],
    categorical=["location_std"],
)


def _synthetic_df(n=20):
    rng = np.random.default_rng(0)
    locations = ["Kilimani", "Westlands", "South B"]
    return pd.DataFrame({
        "bedrooms_num": rng.integers(0, 4, n),
        "bathrooms_num": rng.integers(1, 3, n),
        "rooms_total": rng.integers(1, 6, n),
        "bath_per_bed": rng.random(n),
        "sq_m": rng.uniform(20, 300, n),
        "title_len": rng.integers(5, 40, n),
        "has_parking": rng.choice(["True", "False"], n),
        "location_std": rng.choice(locations, n),
        "title_clean": [f"furnished apartment {i}" for i in range(n)],
        "price_kes": rng.uniform(10000, 200000, n),
    })


def test_coerce_dtypes_converts_binary_true_false_strings():
    df = _synthetic_df()
    out = coerce_dtypes(df, TINY_FS.binary, TINY_FS.categorical)
    assert out["has_parking"].isin([0, 1]).all()
    assert out["has_parking"].dtype == int


def test_coerce_dtypes_drops_rows_with_no_price():
    df = _synthetic_df()
    df.loc[0, "price_kes"] = None
    out = coerce_dtypes(df, TINY_FS.binary, TINY_FS.categorical)
    assert len(out) == len(df) - 1


def test_location_stats_computed_from_train_only():
    df = _synthetic_df(30)
    train, test = df.iloc[:20], df.iloc[20:]
    train_out, test_out, unseen = add_location_stats(train, test)
    # Training stats must be derivable purely from the training partition.
    manual_mean = train.groupby("location_std")["price_kes"].mean()
    for loc in train["location_std"].unique():
        rows = train_out[train_out["location_std"] == loc]
        # Smoothed mean sits between the raw per-location mean and the global mean.
        global_mean = train["price_kes"].mean()
        lo, hi = sorted([manual_mean[loc], global_mean])
        assert (rows["loc_mean_tr"].between(lo - 1e-6, hi + 1e-6)).all()
    assert unseen == 0  # same 3 locations used in both splits here


def test_location_stats_unseen_location_falls_back_to_global():
    train = _synthetic_df(10)
    test = pd.DataFrame([{**_synthetic_df(1).iloc[0].to_dict(), "location_std": "Karen"}])
    train_out, test_out, unseen = add_location_stats(train, test)
    assert unseen == 1
    global_mean = train["price_kes"].mean()
    assert abs(test_out["loc_mean_tr"].iloc[0] - global_mean) < 1e-6


def test_preprocessor_fits_and_transforms_without_error():
    df = _synthetic_df()
    df = coerce_dtypes(df, TINY_FS.binary, TINY_FS.categorical)
    train, test, _ = add_location_stats(df.iloc[:15], df.iloc[15:])
    pre = build_preprocessor(TINY_FS)
    Xtr = pre.fit_transform(train)
    Xte = pre.transform(test)
    assert Xtr.shape[0] == len(train)
    assert Xte.shape[1] == Xtr.shape[1]
    names = get_feature_names(pre, TINY_FS)
    assert len(names) == Xtr.shape[1]


def test_location_lookup_matches_add_location_stats():
    train = _synthetic_df(20)
    lookup = build_location_lookup(train)
    loc = train["location_std"].iloc[0]
    looked_up = lookup_location_stats(loc, lookup)

    # Cross-check against the row-wise computation used at training time.
    single_row = train.iloc[[0]]
    train_out, _, _ = add_location_stats(train, single_row)
    assert abs(looked_up["loc_mean_tr"] - train_out["loc_mean_tr"].iloc[0]) < 1e-6
    assert abs(looked_up["loc_median_tr"] - train_out["loc_median_tr"].iloc[0]) < 1e-6
    assert looked_up["loc_count_tr"] == train_out["loc_count_tr"].iloc[0]


def test_location_lookup_unseen_location_falls_back_to_global():
    train = _synthetic_df(10)
    lookup = build_location_lookup(train)
    result = lookup_location_stats("Karen", lookup)
    assert abs(result["loc_mean_tr"] - train["price_kes"].mean()) < 1e-6
    assert result["loc_count_tr"] == 0.0


def test_recompute_rooms_bath_overrides_dataset_values_with_api_reproducible_ones():
    df = pd.DataFrame({
        "bedrooms_num": [2, 0, 1],
        "bathrooms_num": [1, 1, 1],
        # Deliberately inconsistent with bedrooms_num/bathrooms_num, as the
        # real dataset's "_filled"-derived columns are.
        "rooms_total": [999, 999, 999],
        "bath_per_bed": [999, 999, 999],
    })
    out = recompute_rooms_bath_from_counts(df)
    assert list(out["rooms_total"]) == [3, 1, 2]
    # Studio (bedrooms_num=0) must not divide by zero / produce inf.
    assert np.isfinite(out["bath_per_bed"]).all()
    assert out["bath_per_bed"].iloc[1] > 1000  # 1 / 1e-6, same convention as rent_ml


def test_property_type_flags_sets_exactly_one_flag():
    assert property_type_flags("house") == {"is_apartment": 0, "is_house": 1, "is_bedsitter": 0}


def test_property_type_flags_none_is_all_zero():
    assert property_type_flags(None) == {"is_apartment": 0, "is_house": 0, "is_bedsitter": 0}


KNOWN = ["Kilimani", "Westlands", "South B", "Langata", "Upperhill"]


def test_normalize_location_is_case_insensitive():
    assert normalize_location("kilimani", KNOWN) == "Kilimani"
    assert normalize_location("KILIMANI", KNOWN) == "Kilimani"
    assert normalize_location("  Kilimani  ", KNOWN) == "Kilimani"


def test_normalize_location_handles_known_aliases():
    assert normalize_location("Westland", KNOWN) == "Westlands"
    assert normalize_location("westland", KNOWN) == "Westlands"
    assert normalize_location("Upper Hill", KNOWN) == "Upperhill"
    assert normalize_location("southb", KNOWN) == "South B"


def test_normalize_location_unknown_returns_none():
    assert normalize_location("Nowhereville", KNOWN) is None
    assert normalize_location("", KNOWN) is None


def test_resolve_location_recognized_vs_not():
    lookup = {"Kilimani": {"loc_mean_tr": 1.0}, "__global__": {"loc_mean_tr": 0.0}}
    name, recognized = resolve_location("KILIMANI", lookup)
    assert (name, recognized) == ("Kilimani", True)

    name, recognized = resolve_location("Nowhereville", lookup)
    assert (name, recognized) == ("Nowhereville", False)


def test_resolve_location_alias_via_full_lookup():
    lookup = {"Westlands": {"loc_mean_tr": 1.0}, "__global__": {"loc_mean_tr": 0.0}}
    name, recognized = resolve_location("Westland", lookup)
    assert (name, recognized) == ("Westlands", True)
