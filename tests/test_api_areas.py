"""/areas-within-budget: the Rent Assistant endpoint (same logic as the MCP tool)."""
import threading

import pytest
from fastapi.testclient import TestClient

from api import areas as areas_mod
from api.main import app, predictor


@pytest.fixture(scope="module", autouse=True)
def _load_model():
    predictor.load()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


BASE = {"budget_kes": 60000, "bedrooms": 2, "bathrooms": 1}


def test_post_returns_comfortable_and_stretch_with_note(client):
    r = client.post("/areas-within-budget", json=BASE)
    assert r.status_code == 200
    body = r.json()
    assert "Estimate only" in body["note"]
    assert body["areas_checked"] == 32
    for row in body["comfortable_areas"]:
        assert row["estimate_kes"] <= 60000
        assert row["range_low_kes"] <= row["estimate_kes"] <= row["range_high_kes"]
        assert row["location_confidence"] in {"high", "low", "none"}
        assert "why" not in row                      # no explanations in the sweep
    for row in body["stretch_areas"]:
        assert row["estimate_kes"] > 60000 >= row["range_low_kes"]
    ests = [r["estimate_kes"] for r in body["comfortable_areas"]]
    assert ests == sorted(ests, reverse=True)        # most home for the money first
    assert len(body["comfortable_areas"]) + len(body["stretch_areas"]) + body["areas_out_of_reach"] == 32


def test_get_matches_post(client):
    g = client.get("/areas-within-budget", params=BASE).json()
    p = client.post("/areas-within-budget", json=BASE).json()
    assert g == p


def test_near_and_max_km_filter_and_sort_by_distance(client):
    r = client.post("/areas-within-budget", json={**BASE, "budget_kes": 200000, "near": "Kilimani", "max_km": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["near"] == "Kilimani" and body["max_km"] == 5
    assert body["areas_checked"] == len(body["areas_within_max_km"]) < 32
    rows = body["comfortable_areas"] + body["stretch_areas"]
    assert rows and all(x["distance_km"] <= 5 for x in rows)
    dists = [x["distance_km"] for x in body["comfortable_areas"]]
    assert dists == sorted(dists)
    assert "straight-line" in body["distance_note"]


def test_get_with_near(client):
    r = client.get("/areas-within-budget", params={**BASE, "near": "kilimani", "max_km": 10})
    assert r.status_code == 200 and r.json()["near"] == "Kilimani"


def test_unknown_near_is_a_friendly_422(client):
    r = client.post("/areas-within-budget", json={**BASE, "near": "Atlantis"})
    assert r.status_code == 422
    assert "Atlantis" in r.json()["detail"]


@pytest.mark.parametrize("bad", [
    {"budget_kes": 100}, {"budget_kes": 99_000_000}, {"bedrooms": 11}, {"bathrooms": -1},
    {"max_km": 0.1}, {"max_km": 500}, {"budget_kes": "lots"},
])
def test_bad_input_is_rejected(client, bad):
    r = client.post("/areas-within-budget", json={**BASE, **bad})
    assert r.status_code == 422


def test_budget_too_low_for_validation_message_is_friendly(client):
    r = client.post("/areas-within-budget", json={**BASE, "budget_kes": 100})
    assert "KES" in r.json()["detail"]


def test_missing_fields_rejected(client):
    assert client.post("/areas-within-budget", json={"budget_kes": 50000}).status_code == 422
    assert client.get("/areas-within-budget", params={"budget_kes": 50000}).status_code == 422


def test_work_is_capped_at_32_model_runs(client, monkeypatch):
    calls = []
    real = predictor.predict

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(predictor, "predict", counting)
    assert client.post("/areas-within-budget", json=BASE).status_code == 200
    assert 0 < len(calls) <= 32


def test_busy_server_returns_429_not_a_queue(client, monkeypatch):
    monkeypatch.setattr(areas_mod, "_slots", threading.BoundedSemaphore(0))
    r = client.post("/areas-within-budget", json=BASE)
    assert r.status_code == 429
    assert "try again" in r.json()["detail"].lower()


def test_slot_is_released_after_a_failed_request(client, monkeypatch):
    sem = threading.BoundedSemaphore(1)
    monkeypatch.setattr(areas_mod, "_slots", sem)
    assert client.post("/areas-within-budget", json={**BASE, "near": "Atlantis"}).status_code == 422
    assert client.post("/areas-within-budget", json=BASE).status_code == 200      # slot was freed


def test_unloaded_model_gives_503(client, monkeypatch):
    monkeypatch.setattr(type(predictor), "loaded", property(lambda self: False))
    assert client.post("/areas-within-budget", json=BASE).status_code == 503


def test_matches_mcp_tool_logic_on_the_same_model(client):
    """The endpoint returns exactly what the shared Tools logic produces for the same model."""
    from agent.core.tools import Tools
    direct = Tools(areas_mod.LocalApi(predictor)).areas_within_budget(60000, 2, 1)
    assert client.post("/areas-within-budget", json=BASE).json() == direct
