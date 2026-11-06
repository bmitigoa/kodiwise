import pytest
from fastapi.testclient import TestClient

from api.main import app, predictor


@pytest.fixture(scope="module", autouse=True)
def _load_model():
    predictor.load()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["model_loaded"] is True


def test_model_version(client):
    resp = client.get("/model-version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["feature_set"] == "app_expanded_form"
    assert body["n_train"] > 0


def test_predict_minimal_input_returns_sane_range(client):
    """Only the three required fields -- everything else omitted, as a
    client that hasn't built the expanded form yet would send."""
    resp = client.post("/predict", json={
        "bedrooms_num": 2,
        "bathrooms_num": 1,
        "location_std": "Kilimani",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_rent_kes"] > 0
    assert body["predicted_rent_low_kes"] <= body["predicted_rent_kes"] <= body["predicted_rent_high_kes"]
    assert body["model_version"] == "v20261106-appD"
    assert body["location_recognised"] is True
    assert "estimate" in body["note"].lower()
    # No LOW/FAIR/HIGH verdict should ever be in the response.
    assert "verdict" not in body
    assert "band" not in body


def test_predict_full_input_returns_sane_range(client):
    resp = client.post("/predict", json={
        "bedrooms_num": 2,
        "bathrooms_num": 1,
        "location_std": "Kilimani",
        "sq_m": 65,
        "is_furnished": 1,
        "property_type": "apartment",
        "has_generator": 1,
        "has_borehole": 0,
        "has_cctv": 1,
        "has_dsq": 0,
        "has_play_area": 0,
        "has_garden": 1,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_rent_kes"] > 0
    assert body["predicted_rent_low_kes"] <= body["predicted_rent_kes"] <= body["predicted_rent_high_kes"]


def test_predict_dont_know_size_omits_sq_m(client):
    """sq_m must be optional -- "I don't know the size" in the UI sends no
    sq_m at all, which must not error and must not be treated as sq_m=0."""
    resp = client.post("/predict", json={
        "bedrooms_num": 2,
        "bathrooms_num": 1,
        "location_std": "Kilimani",
        "property_type": "apartment",
    })
    assert resp.status_code == 200
    assert resp.json()["predicted_rent_kes"] > 0


def test_predict_invalid_property_type_returns_422(client):
    resp = client.post("/predict", json={
        "bedrooms_num": 2,
        "bathrooms_num": 1,
        "location_std": "Kilimani",
        "property_type": "mansion",
    })
    assert resp.status_code == 422


def test_predict_amenity_flag_out_of_range_returns_422(client):
    resp = client.post("/predict", json={
        "bedrooms_num": 2,
        "bathrooms_num": 1,
        "location_std": "Kilimani",
        "has_generator": 2,
    })
    assert resp.status_code == 422


def test_predict_unseen_location_falls_back_without_error(client):
    resp = client.post("/predict", json={
        "bedrooms_num": 1,
        "bathrooms_num": 1,
        "location_std": "SomeNeighbourhoodNotInTraining",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_rent_kes"] > 0
    assert body["location_recognised"] is False


@pytest.mark.parametrize("variant", ["kilimani", "KILIMANI", "  Kilimani  ", "KiLiMaNi"])
def test_predict_location_case_variants_match_canonical(client, variant):
    """The bug report: "kilimani"/"KILIMANI" used to silently fall back to
    the global mean instead of matching "Kilimani"."""
    canonical = client.post("/predict", json={
        "bedrooms_num": 2, "bathrooms_num": 1, "location_std": "Kilimani",
    }).json()
    variant_resp = client.post("/predict", json={
        "bedrooms_num": 2, "bathrooms_num": 1, "location_std": variant,
    })
    assert variant_resp.status_code == 200
    body = variant_resp.json()
    assert body["location_recognised"] is True
    assert body["predicted_rent_kes"] == canonical["predicted_rent_kes"]


@pytest.mark.parametrize("alias,canonical_name", [
    ("Westland", "Westlands"),
    ("westland", "Westlands"),
    ("Upper Hill", "Upperhill"),
    ("southb", "South B"),
])
def test_predict_known_aliases_match_canonical(client, alias, canonical_name):
    canonical = client.post("/predict", json={
        "bedrooms_num": 2, "bathrooms_num": 1, "location_std": canonical_name,
    }).json()
    alias_resp = client.post("/predict", json={
        "bedrooms_num": 2, "bathrooms_num": 1, "location_std": alias,
    })
    assert alias_resp.status_code == 200
    body = alias_resp.json()
    assert body["location_recognised"] is True
    assert body["predicted_rent_kes"] == canonical["predicted_rent_kes"]


def test_predict_truly_unknown_location_does_not_match_anything(client):
    resp = client.post("/predict", json={
        "bedrooms_num": 2, "bathrooms_num": 1, "location_std": "Nowhereville",
    })
    assert resp.status_code == 200
    assert resp.json()["location_recognised"] is False


def test_get_locations_returns_known_neighbourhoods(client):
    resp = client.get("/locations")
    assert resp.status_code == 200
    locations = resp.json()["locations"]
    assert "Kilimani" in locations
    assert "Westlands" in locations
    # Internal data-artifact bucket, not a real neighbourhood -- must not
    # be offered to users as a pickable location.
    assert "Unknown" not in locations
    assert locations == sorted(locations)


def test_predict_missing_field_returns_422(client):
    resp = client.post("/predict", json={"bedrooms_num": 2, "bathrooms_num": 1})
    assert resp.status_code == 422


def test_predict_negative_bedrooms_returns_422(client):
    resp = client.post("/predict", json={
        "bedrooms_num": -1,
        "bathrooms_num": 1,
        "location_std": "Kilimani",
    })
    assert resp.status_code == 422


def test_predict_blank_location_returns_422(client):
    resp = client.post("/predict", json={
        "bedrooms_num": 2,
        "bathrooms_num": 1,
        "location_std": "   ",
    })
    assert resp.status_code == 422
