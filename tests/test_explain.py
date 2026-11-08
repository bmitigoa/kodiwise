import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import app, predictor
from ml import explain
from ml.explain import (FACTOR_GROUPS, FEATURE_TO_GROUP, build_explanation, contributions,
                        group_of, kes_effect)
from ml.features import FEATURE_SETS

ROWS = [
    dict(bedrooms_num=2, bathrooms_num=2, location_std="Kilimani", sq_m=90, is_furnished=1,
         property_type="apartment", has_cctv=1, has_generator=1),
    dict(bedrooms_num=3, bathrooms_num=3, location_std="Upperhill"),
    dict(bedrooms_num=0, bathrooms_num=1, location_std="Ngara", property_type="bedsitter"),
    dict(bedrooms_num=4, bathrooms_num=4, location_std="Karen", sq_m=300, property_type="house",
         has_garden=1, has_borehole=1, has_dsq=1),
    dict(bedrooms_num=1, bathrooms_num=1, location_std="Nowhereville"),
]


@pytest.fixture(scope="module", autouse=True)
def _load():
    predictor.load()


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.mark.parametrize("kw", ROWS)
def test_contributions_plus_bias_reproduce_the_model_log_prediction(kw):
    row, *_ = predictor.build_row(**{k: v for k, v in kw.items()})
    names, contrib, bias = contributions(predictor.pipe, row)
    model_log = float(np.log1p(predictor.pipe.predict(row)[0]))
    assert contrib.sum() + bias == pytest.approx(model_log, abs=1e-6)
    assert len(names) == len(contrib)


def test_grouping_covers_every_served_feature_exactly_once():
    fs = predictor.feature_set
    served = fs.numeric + fs.binary
    assert all(f in FEATURE_TO_GROUP for f in served)
    flat = [f for fs_ in FACTOR_GROUPS.values() for f in fs_]
    assert len(flat) == len(set(flat))                       # no feature in two groups
    row, *_ = predictor.build_row(2, 2, "Kilimani")
    names, _, _ = contributions(predictor.pipe, row)
    assert sorted(names) == sorted(served)
    for n in names:
        group_of(n)


def test_every_tree_feature_set_is_covered_or_text_only():
    for name, fs in FEATURE_SETS.items():
        if fs.text or fs.categorical:
            continue                                          # paper sets use TF-IDF / one-hot
        for f in fs.numeric + fs.binary:
            assert f in FEATURE_TO_GROUP, f"{name}: {f}"


def test_unknown_feature_is_an_error_not_silently_dropped():
    with pytest.raises(KeyError):
        group_of("price_per_bedroom")


def test_kes_effect_formula():
    assert kes_effect(100000, 0.0) == 0
    assert kes_effect(100000, math.log(2)) == pytest.approx(50000)     # halves without it
    assert kes_effect(100000, -math.log(2)) == pytest.approx(-100000)  # doubles without it


def test_small_factors_are_hidden_and_at_most_five_are_returned():
    names = ["sq_m", "is_furnished", "has_cctv", "bedrooms_num", "loc_mean_tr", "is_house", "lat"]
    contrib = np.array([0.001, 0.30, 0.20, 0.10, 0.50, -0.25, 0.0])
    out = build_explanation(names, contrib, math.log1p(60000), 100000.0,
                            {"location": "Kilimani", "location_recognised": True,
                             "bedrooms_num": 2, "bathrooms_num": 1})
    sizes = [abs(f["effect_kes"]) for f in out["factors"]]
    assert sizes == sorted(sizes, reverse=True) and len(out["factors"]) <= 5
    assert "Size" not in [f["name"] for f in out["factors"]]       # 0.001 -> ~KES 100 < floor
    assert all(s >= max(0.02 * 100000, 1000) for s in sizes)
    assert out["factors"][0]["name"] == "Location"
    assert {f["direction"] for f in out["factors"]} <= {"+", "-"}
    assert out["baseline_rent_kes"] == 60000


def test_api_explain_default_on_with_note_and_factors(client):
    r = client.post("/predict", json=ROWS[0]).json()
    ex = r["explanation"]
    assert 1 <= len(ex["factors"]) <= 5 and ex["baseline_rent_kes"] > 0
    assert "do not add up exactly" in ex["note"]
    for f in ex["factors"]:
        assert f["direction"] == ("+" if f["effect_kes"] > 0 else "-")
    assert any(f["name"] == "Location" and f["label"] == "Kilimani location" for f in ex["factors"])


def test_api_explain_false_omits_explanation_and_keeps_prediction(client):
    on = client.post("/predict", json=ROWS[0]).json()
    off = client.post("/predict", json={**ROWS[0], "explain": False}).json()
    assert "explanation" not in off
    assert off["predicted_rent_kes"] == on["predicted_rent_kes"]
    assert off["predicted_rent_low_kes"] == on["predicted_rent_low_kes"]


def test_api_size_not_given_is_labelled_honestly(client):
    r = client.post("/predict", json={"bedrooms_num": 2, "bathrooms_num": 2, "location_std": "Kilimani"}).json()
    sizes = [f for f in r["explanation"]["factors"] if f["name"] == "Size"]
    assert all("not given" in f["label"] for f in sizes)


def test_api_unrecognised_location_does_not_claim_a_named_area(client):
    r = client.post("/predict", json=ROWS[4]).json()
    labels = [f["label"] for f in r["explanation"]["factors"] if f["name"] == "Location"]
    assert all("Nowhereville" not in l for l in labels)


def test_explain_latency_overhead_is_small(client):
    import time
    def p50(body):
        for _ in range(10):
            client.post("/predict", json=body)
        t = []
        for _ in range(60):
            s = time.perf_counter(); client.post("/predict", json=body); t.append(time.perf_counter() - s)
        return sorted(t)[len(t) // 2] * 1000
    off, on = p50({**ROWS[0], "explain": False}), p50(ROWS[0])
    assert on - off < 50, f"explain adds {on - off:.1f} ms (off {off:.1f}, on {on:.1f})"


# --- labels: a missing field must never be shown as a fact -------------------
from ml.explain import _label  # noqa: E402

BASE = {"location": "Kilimani", "location_recognised": True, "location_confidence": "high",
        "bedrooms_num": 2, "bathrooms_num": 2}


def lab(group, **kw):
    return _label(group, {**BASE, **kw})


def test_furnished_label_missing_vs_given():
    assert lab("Furnished") == "Furnishing (not given)"
    assert lab("Furnished", is_furnished=None) == "Furnishing (not given)"
    assert lab("Furnished", is_furnished=0) == "Not furnished"
    assert lab("Furnished", is_furnished=1) == "Furnished"


def test_size_and_property_type_label_missing_vs_given():
    assert "not given" in lab("Size")
    assert lab("Size", sq_m=90) == "Size (90 m²)"
    assert lab("Property type") == "Property type (not given)"
    assert lab("Property type", property_type="house") == "House"


def test_amenities_label_missing_vs_given():
    assert lab("Amenities") == "Amenities (not given)"
    flags = ["has_generator", "has_borehole", "has_cctv", "has_dsq", "has_play_area", "has_garden"]
    for f in flags:   # any single field given as absent is a real answer, not a gap
        assert lab("Amenities", **{f: 0}) == "No extra amenities listed"
        assert lab("Amenities", **{f: 1}).startswith("Amenities: ")
    assert lab("Amenities", has_cctv=1, has_garden=None, has_generator=0) == "Amenities: CCTV"


@pytest.mark.parametrize("conf,expected", [
    ("high", "Kilimani location"),
    ("low", "Kilimani location (limited local data)"),
    ("none", "Kilimani location (limited local data)"),
])
def test_location_label_flags_thin_data(conf, expected):
    assert lab("Location", location_confidence=conf) == expected


def test_unrecognised_location_label_never_names_an_area():
    assert lab("Location", location="Nowhereville", location_recognised=False,
               location_confidence="none") == "Location (area average used)"


def test_api_missing_optionals_never_appear_as_facts(client):
    r = client.post("/predict", json={"bedrooms_num": 2, "bathrooms_num": 2,
                                      "location_std": "Kilimani"}).json()
    for f in r["explanation"]["factors"]:
        if f["name"] == "Furnished":
            assert f["label"] == "Furnishing (not given)"
        if f["name"] == "Amenities":
            assert f["label"] == "Amenities (not given)"
        if f["name"] == "Size":
            assert "not given" in f["label"]
        if f["name"] == "Property type":
            assert f["label"] == "Property type (not given)"


def test_api_given_fields_are_labelled_as_facts(client):
    r = client.post("/predict", json={**ROWS[0], "is_furnished": 0}).json()
    labels = {f["name"]: f["label"] for f in r["explanation"]["factors"]}
    if "Furnished" in labels:
        assert labels["Furnished"] == "Not furnished"


def test_api_location_label_follows_confidence(client):
    by_conf = {}
    for loc in predictor.known_locations():
        c = client.post("/predict", json={"bedrooms_num": 2, "bathrooms_num": 2,
                                          "location_std": loc}).json()
        conf = c["location_confidence"]
        label = [f["label"] for f in c["explanation"]["factors"] if f["name"] == "Location"]
        if label:
            by_conf.setdefault(conf, []).append(label[0])
    assert by_conf.get("high") and by_conf.get("none")
    assert all("limited local data" not in l for l in by_conf["high"])
    assert all(l.endswith("(limited local data)") for l in by_conf["none"] + by_conf.get("low", []))
