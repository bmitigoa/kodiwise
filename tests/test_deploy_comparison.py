import numpy as np
import pandas as pd
import pytest

from ml.evaluate import (
    _make_baseline_pipeline,
    compare_on_same_rows,
    cross_validate,
    eval_rows_record,
    kfold_labels,
)
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


@pytest.fixture(scope="module")
def current():
    df = _synthetic()
    train, test = _split(df)
    return df, eval_rows_record(train, test)


def test_identical_data_gives_zero_deltas_and_passes(current):
    df, rec = current
    cmp = compare_on_same_rows(df, rec, df, fs, "vX")
    assert cmp["test_mape_delta_pp"] == pytest.approx(0.0, abs=1e-12)
    assert cmp["cv_r2_delta"] == pytest.approx(0.0, abs=1e-12)
    assert cmp["passes"] is True


def test_dropped_and_new_rows_are_accounted_for(current):
    df, rec = current
    dropped_train_id = next(iter(rec["cv_folds"]))
    new_row = df.iloc[[0]].copy()
    new_row["fingerprint"] = "brand-new"
    candidate = pd.concat([df[df["fingerprint"] != dropped_train_id], new_row])
    rows = compare_on_same_rows(df, rec, candidate, fs, "vX")["rows"]
    assert rows["test_rows_shared"] == len(rec["test_ids"])
    assert rows["train_rows_dropped_by_candidate"] == 1
    assert rows["train_rows_new_in_candidate"] == 1
    assert rows["train_rows_candidate"] == rows["train_rows_current"]


def test_missing_current_record_fails_closed():
    out = deploy_comparison(_synthetic(), fs, "v-does-not-exist")
    assert out["passes"] is False
    assert "error" in out
