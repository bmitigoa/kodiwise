"""Step 4: compact tool outputs and short tool declarations (free-tier token budget)."""
import json

import pytest

from chat import compact, guard, toolspec
from chat.engine import SYSTEM
from tests.test_chat import make_tools

CALLS = {
    "list_locations": {},
    "estimate_rent": {"location": "Kilimani", "bedrooms": 2, "bathrooms": 2},
    "compare_areas": {"locations": ["Kilimani", "Westlands", "Karen"], "bedrooms": 2, "bathrooms": 2},
    "areas_within_budget": {"budget_kes": 60000, "bedrooms": 2, "bathrooms": 2, "near": "Westlands"},
    "check_listing_price": {"asking_rent_kes": 90000, "location": "Kileleshwa", "bedrooms": 3, "bathrooms": 1},
    "search_listings": {"location": "Kilimani"},
}


def tokens(obj) -> int:
    s = obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"))
    return len(s) // 4


@pytest.fixture()
def results():
    tools, _ = make_tools()
    return {n: toolspec.call_tool(tools, n, a) for n, a in CALLS.items()}


@pytest.mark.parametrize("name", [n for n in CALLS if n not in ("list_locations", "search_listings")])
def test_the_model_sees_less_than_half_of_the_full_result(results, name):
    full, shown = results[name], compact.for_model(name, results[name])
    assert tokens(shown) <= tokens(full) * 0.6, (name, tokens(shown), tokens(full))


@pytest.mark.parametrize("name", list(CALLS))
def test_every_figure_the_model_sees_is_also_in_the_full_result(results, name):
    """Compaction may drop numbers, never add or change one: the number check runs on the full result."""
    full = guard.allowed_numbers([results[name]], [])
    shown = guard.allowed_numbers([compact.for_model(name, results[name])], [])
    for n in shown:
        assert any(abs(n - f) <= 0.5 for f in full), (name, n)


def test_key_figures_survive_compaction(results):
    est = compact.for_model("estimate_rent", results["estimate_rent"])
    for k in ("area", "estimate_kes", "range_low_kes", "range_high_kes", "location_confidence", "model_version"):
        assert est[k] is not None
    comp = compact.for_model("compare_areas", results["compare_areas"])
    assert [a["area"] for a in comp["areas"]] == [a["area"] for a in results["compare_areas"]["areas"]]
    chk = compact.for_model("check_listing_price", results["check_listing_price"])
    assert chk["verdict"] and chk["asking_rent_kes"] == 90000
    bud = compact.for_model("areas_within_budget", results["areas_within_budget"])
    assert bud["near"] == "Westlands" and all("distance_km" in r for r in bud["comfortable"] + bud["stretch"])


def test_lists_are_capped_for_the_model_and_the_hidden_count_is_reported():
    rows = [{"area": f"A{i}", "estimate_kes": 30000 + i, "range_low_kes": 20000, "range_high_kes": 50000,
             "location_confidence": "high"} for i in range(20)]
    out = compact.for_model("areas_within_budget", {"comfortable_areas": rows, "stretch_areas": rows[:3]})
    assert len(out["comfortable"]) == compact.MAX_ROWS and out["more_in_app"] == 20 - compact.MAX_ROWS
    many = {"listings": [{"title": {"untrusted_text": "t"}, "area": {"untrusted_text": "a"}, "rent_kes": 1}] * 12}
    assert len(compact.for_model("search_listings", many)["listings"]) == compact.MAX_LISTINGS


def test_errors_pass_through_unchanged():
    err = {"error": "I don't recognise 'X'."}
    assert compact.for_model("estimate_rent", err) == err


def test_untrusted_wrapper_survives_compaction(results):
    shown = compact.for_model("search_listings", results["search_listings"])
    item = shown["listings"][0]
    assert set(item["title"]) == {"untrusted_text"} and set(item["area"]) == {"untrusted_text"}


def test_short_declarations_are_smaller_and_keep_names_and_required_fields():
    full, short = toolspec.FULL_DECLARATIONS, toolspec._short(toolspec.FULL_DECLARATIONS)
    assert tokens(short) <= tokens(full) * 0.75
    assert [d["name"] for d in short] == [d["name"] for d in full]
    for f, s in zip(full, short):
        assert f["parameters"].get("required") == s["parameters"].get("required")
        assert set(f["parameters"]["properties"]) == set(s["parameters"]["properties"])
        assert all(len(d["description"]) < 100 for d in short)


def test_the_fixed_per_request_overhead_stays_under_a_budget():
    assert tokens(SYSTEM) + tokens(toolspec.DECLARATIONS) < 1100       # was about 1,400 before this step


def test_full_tool_detail_is_available_by_flag(monkeypatch):
    import importlib
    monkeypatch.setenv("CHAT_TOOL_DETAIL", "full")
    mod = importlib.reload(toolspec)
    try:
        assert mod.DECLARATIONS is mod.FULL_DECLARATIONS
    finally:
        monkeypatch.delenv("CHAT_TOOL_DETAIL", raising=False)
        importlib.reload(toolspec)
