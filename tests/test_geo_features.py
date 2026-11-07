import numpy as np
import pandas as pd
import pytest

from ml.features import (
    GEO_FEATURES,
    SPATIAL_PRIOR_COL,
    TARGET,
    add_location_stats,
    build_location_lookup,
    distance_to_polyline_km,
    haversine_km,
    load_geo_reference,
    location_geo_features,
    lookup_location_stats,
    spatial_location_means,
)


def test_haversine_one_degree_of_longitude_at_equator():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)
    assert haversine_km(-1.28, 36.8, -1.28, 36.8) == pytest.approx(0.0)


def test_distance_to_polyline_uses_nearest_segment_not_just_vertices():
    # Straight east-west road along the equator from lon 0 to lon 1.
    road = [np.array([[0.0, 0.0], [0.0, 1.0]])]
    assert distance_to_polyline_km(0.0, 0.5, road) == pytest.approx(0.0, abs=1e-6)
    # 0.01 deg north of the road's midpoint: ~1.11 km, far less than to either end.
    assert distance_to_polyline_km(0.01, 0.5, road) == pytest.approx(1.112, abs=0.01)


def test_reference_features_are_sane():
    zim = location_geo_features("Zimmerman")       # right by Thika Road
    sb = location_geo_features("South B")          # right by Mombasa Road
    assert zim["dist_thika_rd_km"] < 1.0
    assert sb["dist_mombasa_rd_km"] < 1.0
    assert location_geo_features("Westlands")["dist_westlands_km"] == pytest.approx(0.0)


def test_unknown_location_uses_cbd_point():
    geo = load_geo_reference()
    f = location_geo_features("Nowhereville")
    assert (f["lat"], f["lon"]) == geo.fallback_point()
    assert f["dist_cbd_km"] == pytest.approx(0.0)


def _train(rows):
    return pd.DataFrame(rows, columns=["location_std", TARGET])


def test_spatial_prior_keeps_well_sampled_locations_and_shrinks_sparse_ones_toward_neighbours():
    geo = load_geo_reference()
    # Kilimani (well sampled, expensive) is ~1.6 km from Hurlingham; Utawala
    # (well sampled, cheap) is ~19 km away. Hurlingham has one listing.
    rows = [("Kilimani", 100_000)] * 12 + [("Utawala", 20_000)] * 12 + [("Hurlingham", 60_000)]
    tr = _train(rows)
    stats = tr.groupby("location_std")[TARGET].agg(["mean", "median"])
    stats["n"] = tr.groupby("location_std").size()
    gm = tr[TARGET].mean()
    smoothed = (stats["n"] * stats["mean"] + 5 * gm) / (stats["n"] + 5)
    spatial = spatial_location_means(stats, smoothed, gm, 5, geo)

    assert spatial["Kilimani"] == pytest.approx(smoothed["Kilimani"])   # n >= 10: unchanged
    assert spatial["Utawala"] == pytest.approx(smoothed["Utawala"])
    # Sparse Hurlingham is pulled toward nearby Kilimani, i.e. above the
    # plain city-mean shrinkage.
    assert spatial["Hurlingham"] > smoothed["Hurlingham"]
    # A neighbourhood absent from training gets its pure neighbour prior.
    assert "Lavington" in spatial.index


def test_spatial_prior_uses_training_rents_only():
    train = _train([("Kilimani", 100_000)] * 12 + [("Hurlingham", 60_000)])
    other = _train([("Hurlingham", 1_000_000), ("Kilimani", 1)])
    tr_a, ot_a, _ = add_location_stats(train, other)
    other2 = other.copy()
    other2[TARGET] = [5, 5]                       # change only the held-out rents
    _, ot_b, _ = add_location_stats(train, other2)
    assert np.allclose(ot_a[SPATIAL_PRIOR_COL], ot_b[SPATIAL_PRIOR_COL])
    assert np.allclose(ot_a[GEO_FEATURES], ot_b[GEO_FEATURES])


def test_training_and_serving_build_identical_location_features():
    train = _train([("Kilimani", 90_000)] * 12 + [("Hurlingham", 70_000), ("Unknown", 40_000)])
    other = _train([("Kilimani", 0), ("Hurlingham", 0), ("Nowhereville", 0)])
    _, ot, _ = add_location_stats(train, other)
    lookup = build_location_lookup(train)
    cols = ["loc_mean_tr", "loc_median_tr", "loc_count_tr", SPATIAL_PRIOR_COL] + GEO_FEATURES
    for i, loc in enumerate(other["location_std"]):
        served = lookup_location_stats(loc, lookup)
        for c in cols:
            assert served[c] == pytest.approx(ot.iloc[i][c]), (loc, c)
