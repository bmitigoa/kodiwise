import numpy as np
import pandas as pd
import pytest

from ml.evaluate import (
    DEPLOY_SEEDS,
    _make_baseline_pipeline,
    _spread,
    compare_on_same_rows,
    cross_validate,
    eval_rows_record,
    kfold_labels,
    make_lgbm_log_pipeline,
)
from ml.features import LGBM_PARAMS
from ml.features import RUN_D_FEATURE_SET as fs, coerce_dtypes, recompute_rooms_bath_from_counts
from ml.train import deploy_comparison


def _synthetic(n: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    locs = rng.choice(["A", "B", "C"], n)
    beds = rng.integers(1, 4, n)
    df = pd.DataFrame({
        "fingerprint": [f"id{i}" for i in range(n)],
        "location_std": locs,
        "bedrooms_num": beds,
        "bathrooms_num": rng.integers(1, 3, n),
        "sq_m": rng.uniform(30, 150, n),
        "title_len": 40,
        "title_clean": "",
        "income_band_final": rng.choice(["low", "high"], n),
        "price_kes": 20000 * beds + np.where(locs == "A", 30000, 0) + rng.normal(0, 3000, n),
    })
    for c in fs.binary:
        df[c] = 0
    return coerce_dtypes(recompute_rooms_bath_from_counts(df), fs.binary, fs.categorical)


def _split(df: pd.DataFrame, n_test: int = 12):
    order = np.random.default_rng(1).permutation(len(df))
    return df.iloc[order[n_test:]], df.iloc[order[:n_test]]


def test_eval_rows_record_keeps_split_order_and_covers_train():
    df = _synthetic()
    train, test = _split(df)
    rec = eval_rows_record(train, test)
    assert rec["test_ids"] == test["fingerprint"].tolist()
    assert list(rec["cv_folds"]) == train["fingerprint"].tolist()
    assert set(rec["cv_folds"].values()) == set(range(5))


def test_fixed_folds_reproduce_default_kfold():
    df = _synthetic()
    factory = lambda: _make_baseline_pipeline(fs, "hedonic_linear_ridge", 42)  # fast
    default = cross_validate(factory, df, fs)
    fixed = cross_validate(factory, df, fs, folds=kfold_labels(len(df)))
    assert fixed == default


TEST_SEEDS = (42, 43)  # two seeds keep the suite fast; production uses DEPLOY_SEEDS


@pytest.fixture(scope="module")
def current():
    df = _synthetic()
    train, test = _split(df)
    return df, eval_rows_record(train, test)


def test_identical_data_gives_zero_deltas_and_passes(current):
    df, rec = current
    cmp = compare_on_same_rows(df, rec, df, fs, "vX", seeds=TEST_SEEDS)
    assert cmp["test_mape_delta_pp"] == pytest.approx(0.0, abs=1e-12)
    assert cmp["cv_r2_delta"] == pytest.approx(0.0, abs=1e-12)
    assert cmp["passes"] is True


def test_dropped_and_new_rows_are_accounted_for(current):
    df, rec = current
    dropped_train_id = next(iter(rec["cv_folds"]))
    new_row = df.iloc[[0]].copy()
    new_row["fingerprint"] = "brand-new"
    candidate = pd.concat([df[df["fingerprint"] != dropped_train_id], new_row])
    rows = compare_on_same_rows(df, rec, candidate, fs, "vX", seeds=(42,))["rows"]
    assert rows["test_rows_shared"] == len(rec["test_ids"])
    assert rows["train_rows_dropped_by_candidate"] == 1
    assert rows["train_rows_new_in_candidate"] == 1
    assert rows["train_rows_candidate"] == rows["train_rows_current"]


def test_missing_current_record_fails_closed():
    out = deploy_comparison(_synthetic(), fs, "v-does-not-exist")
    assert out["passes"] is False
    assert "error" in out


def test_deploy_seeds_are_five_and_include_production_seed():
    assert len(DEPLOY_SEEDS) == 5
    assert LGBM_PARAMS["random_state"] in DEPLOY_SEEDS


def test_model_seed_overrides_only_random_state():
    default = make_lgbm_log_pipeline(fs).named_steps["m"].regressor
    seeded = make_lgbm_log_pipeline(fs, model_seed=7).named_steps["m"].regressor
    assert default.random_state == LGBM_PARAMS["random_state"]
    assert seeded.random_state == 7
    assert {k: v for k, v in seeded.get_params().items() if k != "random_state"} ==         {k: v for k, v in default.get_params().items() if k != "random_state"}


def test_comparison_reports_every_seed_and_gates_on_means(current):
    df, rec = current
    candidate = df.copy()
    candidate.loc[candidate.index[::7], "price_kes"] *= 1.3  # perturb some rows
    cmp = compare_on_same_rows(df, rec, candidate, fs, "vX", seeds=TEST_SEEDS)
    assert cmp["seeds"] == list(TEST_SEEDS)
    for side in ("current", "candidate"):
        assert [r["seed"] for r in cmp[side]["per_seed"]] == list(TEST_SEEDS)
        mapes = [r["test"]["MAPE"] for r in cmp[side]["per_seed"]]
        assert cmp[side]["summary"]["test_mape"]["mean"] == pytest.approx(np.mean(mapes))
    expected_delta = (cmp["candidate"]["summary"]["test_mape"]["mean"]
                      - cmp["current"]["summary"]["test_mape"]["mean"])
    assert cmp["test_mape_delta_pp"] == pytest.approx(expected_delta)
    assert cmp["paired_seed_deltas"]["test_mape_pp"]["mean"] == pytest.approx(expected_delta)
    expected_pass = (cmp["test_mape_delta_pp"] <= 0.5) and (cmp["cv_r2_delta"] >= -0.01)
    assert cmp["passes"] is expected_pass


def test_spread_summary():
    out = _spread([1.0, 2.0, 3.0])
    assert out == {"mean": 2.0, "std": 1.0, "min": 1.0, "max": 3.0}
    assert _spread([5.0])["std"] == 0.0
