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
    assert body["feature_set"] == "app_realistic"
    assert body["n_train"] > 0


def test_predict_known_input_returns_sane_range(client):
    resp = client.post("/predict", json={
        "bedrooms_num": 2,
        "bathrooms_num": 1,
        "location_std": "Kilimani",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_rent_kes"] > 0
    assert body["predicted_rent_low_kes"] <= body["predicted_rent_kes"] <= body["predicted_rent_high_kes"]
    assert body["model_version"] == "v20261106-appC"
    assert "estimate" in body["note"].lower()
    # No LOW/FAIR/HIGH verdict should ever be in the response.
    assert "verdict" not in body
    assert "band" not in body


def test_predict_unseen_location_falls_back_without_error(client):
    resp = client.post("/predict", json={
        "bedrooms_num": 1,
        "bathrooms_num": 1,
        "location_std": "SomeNeighbourhoodNotInTraining",
    })
    assert resp.status_code == 200
    assert resp.json()["predicted_rent_kes"] > 0


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
