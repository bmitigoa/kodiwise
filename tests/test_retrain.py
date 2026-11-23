import numpy as np
import pandas as pd

from data_pipeline.derive import fingerprint_hash
from ml.evaluate import (
    _make_baseline_pipeline,
    cross_validate,
    kfold_labels,
    normalize_ids,
    normalize_rows_record,
    to_row_id,
)
from ml.features import RUN_D_FEATURE_SET as fs
from ml.retrain import FLAG_DRIFT_STOP_PP, area_report, flag_drift, served_version, tier_changes
from tests.test_deploy_comparison import _synthetic


def test_old_fingerprint_and_new_hash_give_the_same_row_id():
    fp = "embakasi|30000|1.0|2.0|apartments for rent in embakasi, nairobi"
    assert to_row_id(fp) == fingerprint_hash(fp)
    assert to_row_id(fingerprint_hash(fp)) == fingerprint_hash(fp)      # idempotent
    assert to_row_id("id7") == "id7"                                     # ids without '|' are kept


def test_normalize_keeps_order_and_maps_eval_rows():
    fps = ["a|1|1|1|x", "b|2|2|2|y"]
    df = normalize_ids(pd.DataFrame({"fingerprint": fps}))
    assert df["fingerprint"].tolist() == [fingerprint_hash(f) for f in fps]
    rec = normalize_rows_record({"id_col": "fingerprint", "k": 5, "test_ids": fps[:1], "cv_folds": {fps[1]: 3}})
    assert rec["test_ids"] == [fingerprint_hash(fps[0])]
    assert rec["cv_folds"] == {fingerprint_hash(fps[1]): 3}


def test_strict_cv_never_scores_fixed_rows_but_always_trains_on_them():
    df = _synthetic(80)
    folds = kfold_labels(len(df))
    fixed = np.zeros(len(df), dtype=bool)
    fixed[60:] = True                                  # the "new" rows
    factory = lambda: _make_baseline_pipeline(fs, "hedonic_linear_ridge", 42)
    _, oof = cross_validate(factory, df, fs, folds=folds, return_oof=True, fixed_train=fixed)
    assert np.isnan(oof[fixed]).all()                  # new rows get no out-of-fold score
    assert not np.isnan(oof[~fixed]).any()             # every old row is scored once
    loose = cross_validate(factory, df, fs, folds=folds, return_oof=True)[1]
    assert not np.isnan(loose).any()                   # the loose figure scores everything
    # new rows in training changes the fit, so the old rows' predictions differ from CV on old rows alone
    _, oof_old_only = cross_validate(factory, df.iloc[:60], fs, folds=folds[:60], return_oof=True)
    assert not np.allclose(oof[:60], oof_old_only, equal_nan=True)


def test_strict_cv_without_fixed_rows_is_unchanged():
    df = _synthetic()
    factory = lambda: _make_baseline_pipeline(fs, "hedonic_linear_ridge", 42)
    assert cross_validate(factory, df, fs) == cross_validate(factory, df, fs, fixed_train=None)


def test_area_report_and_tier_changes():
    old = pd.DataFrame({"location_std": ["A"] * 2 + ["B"] * 20})
    new = pd.DataFrame({"location_std": ["A"] * 14 + ["B"] * 20 + ["C"] * 2})
    rep = area_report(old, new).set_index("area")
    assert rep.loc["A", ["before", "now", "added"]].tolist() == [2, 14, 12]
    assert (rep.loc["A", "tier_before"], rep.loc["A", "tier_now"]) == ("none", "high")
    assert rep.loc["B", "tier_now"] == "high" and rep.loc["C", "tier_now"] == "none"
    ch = tier_changes({"A": {"loc_count_tr": 2.0}, "B": {"loc_count_tr": 16.0}},
                      {"A": {"loc_count_tr": 11.0}, "B": {"loc_count_tr": 16.0}})
    assert [(c["area"], c["tier_before"], c["tier_now"]) for c in ch] == [("A", "none", "high")]


def test_flag_drift_measures_new_rows_against_old_jiji_rows():
    old = pd.DataFrame({"platform": ["Jiji"] * 10 + ["KenyaPropertyCentre"] * 10,
                        "has_cctv": [0] * 10 + [1] * 10, "is_furnished": [1] * 5 + [0] * 15})
    fresh = pd.DataFrame({"has_cctv": [1] * 3 + [0] * 7, "is_furnished": [1] * 5 + [0] * 5})
    d = flag_drift(old, fresh).set_index("flag")
    assert d.loc["has_cctv", "old_pct"] == 0.0 and d.loc["has_cctv", "diff_pp"] == 30.0   # Jiji rows only
    assert abs(d.loc["is_furnished", "diff_pp"]) < FLAG_DRIFT_STOP_PP + 40


def test_served_version_is_read_from_api_main():
    assert served_version().startswith("v2026")
