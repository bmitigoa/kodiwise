"""Test-set metrics, 5-fold CV, and baseline comparisons.

Mirrors rent_ml/reviewer_rerun_leakfree.py's evaluation logic, refactored
to use ml.features as the single source of truth for columns/preprocessing.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor

from ml.features import (
    FeatureSet, LGBM_PARAMS, TARGET, add_location_stats, build_preprocessor, location_confidence,
)

RANDOM_STATE = 42
ID_COL = "fingerprint"  # unique per listing; identifies rows across data versions


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return dict(
        MAE=float(mean_absolute_error(y_true, y_pred)),
        RMSE=float(np.sqrt(mean_squared_error(y_true, y_pred))),
        R2=float(r2_score(y_true, y_pred)),
        MAPE=float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100),
    )


def make_lgbm_log_pipeline(fs: FeatureSet, model_seed: int | None = None) -> Pipeline:
    """LightGBM log-target pipeline. model_seed overrides LGBM_PARAMS'
    random_state (bagging/column-sampling draws) -- used only by the deploy
    comparison to average over training noise."""
    params = dict(LGBM_PARAMS) if model_seed is None else {**LGBM_PARAMS, "random_state": model_seed}
    model = TransformedTargetRegressor(LGBMRegressor(**params), func=np.log1p, inverse_func=np.expm1)
    return Pipeline([("pre", build_preprocessor(fs)), ("m", model)])


def _baseline_specs(seed: int) -> dict[str, tuple]:
    """Ridge (hedonic linear, log target), Random Forest (log target),
    XGBoost (log target) -- matches the paper's Table 3 baselines.
    Each value is (model, scale_numeric_features)."""
    return {
        "hedonic_linear_ridge": (Ridge(alpha=1.0), True),
        "random_forest": (RandomForestRegressor(n_estimators=500, random_state=seed, n_jobs=-1), False),
        "xgboost": (XGBRegressor(n_estimators=1000, learning_rate=0.03, max_depth=6, subsample=0.85, colsample_bytree=0.85, random_state=seed, n_jobs=-1), False),
    }


def _make_baseline_pipeline(fs: FeatureSet, name: str, seed: int) -> Pipeline:
    model, scale = _baseline_specs(seed)[name]
    return Pipeline([
        ("pre", build_preprocessor(fs, scale=scale)),
        ("m", TransformedTargetRegressor(model, func=np.log1p, inverse_func=np.expm1)),
    ])


def _fold_splits(n: int, k: int, seed: int, folds: np.ndarray | None):
    """(train_idx, val_idx) pairs: KFold(shuffle, seed) by default, or the
    given per-row fold labels (0..k-1) when evaluating on fixed folds."""
    if folds is None:
        return list(KFold(k, shuffle=True, random_state=seed).split(np.arange(n)))
    folds = np.asarray(folds)
    return [(np.where(folds != f)[0], np.where(folds == f)[0]) for f in sorted(set(folds.tolist()))]


def kfold_labels(n: int, k: int = 5, seed: int = RANDOM_STATE) -> np.ndarray:
    """The fold label each row gets under the default KFold split, so a
    version's CV folds can be recorded by row id and reused later."""
    labels = np.empty(n, dtype=int)
    for f, (_, va_idx) in enumerate(_fold_splits(n, k, seed, None)):
        labels[va_idx] = f
    return labels


def cross_validate(
    pipeline_factory, train_df: pd.DataFrame, fs: FeatureSet, k: int = 5, seed: int = RANDOM_STATE,
    folds: np.ndarray | None = None, return_oof: bool = False,
):
    """Generic k-fold CV with location stats recomputed per fold (no
    validation rent ever informs that fold's features). `folds` (one label
    per row of train_df) overrides the default KFold assignment. With
    return_oof, also returns the out-of-fold predictions (train_df order)."""
    trd = train_df.reset_index(drop=True)
    scores = []
    oof = np.full(len(trd), np.nan)
    for tr_idx, va_idx in _fold_splits(len(trd), k, seed, folds):
        f_tr, f_va, _ = add_location_stats(trd.iloc[tr_idx], trd.iloc[va_idx])
        pipe = pipeline_factory()
        pipe.fit(f_tr, f_tr[TARGET].values)
        pred = pipe.predict(f_va)
        oof[va_idx] = pred
        scores.append(metrics(f_va[TARGET].values, pred))
    agg = {}
    for key in scores[0]:
        vals = [s[key] for s in scores]
        agg[key] = {"mean": float(np.mean(vals)), "std": float(np.std(vals))}
    return (agg, oof) if return_oof else agg


def cross_validate_lgbm(
    train_df: pd.DataFrame, fs: FeatureSet, k: int = 5, seed: int = RANDOM_STATE, folds: np.ndarray | None = None,
    model_seed: int | None = None, return_oof: bool = False,
):
    """`seed` picks the KFold split; `model_seed` the LightGBM training seed."""
    return cross_validate(lambda: make_lgbm_log_pipeline(fs, model_seed), train_df, fs, k, seed, folds, return_oof)


def cross_validate_baselines(train_df: pd.DataFrame, fs: FeatureSet, k: int = 5, seed: int = RANDOM_STATE) -> dict:
    return {
        name: cross_validate(lambda n=name: _make_baseline_pipeline(fs, n, seed), train_df, fs, k, seed)
        for name in _baseline_specs(seed)
    }


def run_baselines(train_df: pd.DataFrame, test_df: pd.DataFrame, fs: FeatureSet, seed: int = RANDOM_STATE) -> dict:
    y_tr = train_df[TARGET].values
    y_te = test_df[TARGET].values
    results = {}
    for name in _baseline_specs(seed):
        pipe = _make_baseline_pipeline(fs, name, seed)
        pipe.fit(train_df, y_tr)
        results[name] = metrics(y_te, pipe.predict(test_df))
    return results


def cross_validate_log_residuals(
    train_df: pd.DataFrame, fs: FeatureSet, k: int = 5, seed: int = RANDOM_STATE
) -> np.ndarray:
    """Pooled out-of-fold residuals in log space (log1p(y_true) -
    log1p(y_pred)) for the LightGBM log-target pipeline, location stats
    recomputed per fold. Used to build a CV-calibrated prediction interval:
    at serving time, lower = expm1(log1p(point) + q10), upper =
    expm1(log1p(point) + q90), using quantiles of this pooled array.
    """
    trd = train_df.reset_index(drop=True)
    residuals = []
    for tr_idx, va_idx in KFold(k, shuffle=True, random_state=seed).split(trd):
        f_tr, f_va, _ = add_location_stats(trd.iloc[tr_idx], trd.iloc[va_idx])
        pipe = make_lgbm_log_pipeline(fs)
        pipe.fit(f_tr, f_tr[TARGET].values)
        y_true = f_va[TARGET].values
        y_pred = pipe.predict(f_va)
        residuals.append(np.log1p(y_true) - np.log1p(y_pred))
    return np.concatenate(residuals)


def prediction_interval_widths(pipe, df: pd.DataFrame, q10_log: float, q90_log: float) -> np.ndarray:
    """Per-row range width (high - low) using the same CV-calibrated
    log-space quantile method api/predictor.py uses at serving time.
    Lets Run C and Run D be compared not just on point-accuracy but on how
    wide a range they'd actually hand a user for the same confidence level.
    """
    points = np.clip(pipe.predict(df), 0, None)
    log_points = np.log1p(points)
    low = np.clip(np.expm1(log_points + q10_log), 0, None)
    high = np.clip(np.expm1(log_points + q90_log), 0, None)
    return high - low


# ---------------------------------------------------------------------------
# Deploy comparison (deploy rule): candidate vs current on the same rows.
# ---------------------------------------------------------------------------

DEPLOY_MAX_MAPE_WORSE_PP = 0.5
DEPLOY_MAX_CV_R2_DROP = 0.01
# Training seeds averaged over in the deploy comparison. Same rows, same
# folds, same row order for every seed -- only LightGBM's bagging/column
# sampling draws change. 42 (the production seed) is included.
DEPLOY_SEEDS = (42, 43, 44, 45, 46)


def eval_rows_record(train: pd.DataFrame, test: pd.DataFrame, k: int = 5, seed: int = RANDOM_STATE) -> dict:
    """Which rows a version was evaluated on, by row id: its test rows and
    the CV fold of each training row (same assignment cross_validate uses
    by default). Saved with every version so a later candidate can be
    scored on exactly the same rows. Both lists keep the split's row order:
    LightGBM's bagging/column sampling depends on row order, so the same
    rows in a different order give measurably different scores."""
    labels = kfold_labels(len(train), k, seed)
    return {
        "id_col": ID_COL,
        "k": k,
        "test_ids": test[ID_COL].astype(str).tolist(),
        "cv_folds": {str(i): int(f) for i, f in zip(train[ID_COL].astype(str), labels)},
    }


def _fold_for_new_row(row_id: str, k: int) -> int:
    """Stable fold for a row the current version never saw (new scrape)."""
    return zlib.crc32(row_id.encode()) % k


def _in_recorded_order(df: pd.DataFrame, ordered_ids: list[str]) -> pd.DataFrame:
    """Rows of df whose id is in ordered_ids, in that order, followed by
    any rows of df not in ordered_ids (in their existing order)."""
    ids = df[ID_COL].astype(str)
    pos = {i: n for n, i in enumerate(ordered_ids)}
    known = df[ids.isin(pos)]
    known = known.iloc[np.argsort([pos[i] for i in known[ID_COL].astype(str)], kind="stable")]
    return pd.concat([known, df[~ids.isin(pos)]])


def _fit_and_score(train: pd.DataFrame, test: pd.DataFrame, fs: FeatureSet, model_seed: int | None = None,
                   return_pred: bool = False):
    tr, te, _ = add_location_stats(train, test)
    pipe = make_lgbm_log_pipeline(fs, model_seed)
    pipe.fit(tr, tr[TARGET].values)
    pred = pipe.predict(te)
    m = metrics(te[TARGET].values, pred)
    return (m, pred) if return_pred else m


CONFIDENCE_GROUPS = ("high", "low", "none")


def _group_errors(y: np.ndarray, pred: np.ndarray, groups: np.ndarray) -> dict:
    """MAPE / MAE per location-confidence group."""
    out = {}
    for g in CONFIDENCE_GROUPS:
        mask = groups == g
        if mask.any():
            err = np.abs(y[mask] - pred[mask])
            out[g] = {"n": int(mask.sum()), "MAPE": float(np.mean(err / y[mask]) * 100), "MAE": float(np.mean(err))}
    return out


def _confidence_groups(rows: pd.DataFrame, train_counts: pd.Series) -> np.ndarray:
    """Location confidence of each row from its location's training count."""
    counts = rows["location_std"].map(train_counts).fillna(0.0)
    return np.array([location_confidence(c) for c in counts])


def compare_on_same_rows(
    current_df: pd.DataFrame, current_rows: dict, candidate_df: pd.DataFrame, fs: FeatureSet,
    current_version: str, seeds: tuple[int, ...] = DEPLOY_SEEDS, current_fs: FeatureSet | None = None,
) -> dict:
    """Score the current version's data and the candidate's data on the
    same evaluation rows, each trained once per seed in `seeds`, with the
    same hyperparameters. `fs` is the candidate's feature set; `current_fs`
    the deployed one's (defaults to `fs`, i.e. a data-only change). The gate
    applies to the means over seeds; the per-seed values and spread are
    reported alongside, plus errors per location-confidence group
    (out-of-fold CV predictions and test rows).

    - Test: the current version's test rows that still exist in the
      candidate data. Rows the candidate dropped leave both sides alike;
      rows new to the candidate can only go to training.
    - CV: the current version's recorded folds over its training rows;
      for the candidate, rows keep their recorded fold, dropped rows
      disappear, new rows get a stable hash fold.
    Both sides are dtype-coerced copies (callers pass coerce_dtypes output).
    """
    k = current_rows["k"]
    test_order = current_rows["test_ids"]
    fold_of = current_rows["cv_folds"]
    train_order = list(fold_of)  # JSON keeps insertion order = training order
    cur_test_ids = set(test_order)
    cur_ids = current_df[ID_COL].astype(str)
    cand_ids = candidate_df[ID_COL].astype(str)

    shared_test = cur_test_ids & set(cand_ids)
    cur_train = _in_recorded_order(current_df[~cur_ids.isin(cur_test_ids)], train_order)
    cur_test = _in_recorded_order(current_df[cur_ids.isin(shared_test)], test_order)
    cand_train = _in_recorded_order(candidate_df[~cand_ids.isin(cur_test_ids)], train_order)
    cand_test = _in_recorded_order(candidate_df[cand_ids.isin(shared_test)], test_order)

    cur_folds = np.array([fold_of[i] for i in cur_train[ID_COL].astype(str)])
    cand_fold_ids = cand_train[ID_COL].astype(str)
    cand_folds = np.array([fold_of.get(i, _fold_for_new_row(i, k)) for i in cand_fold_ids])

    # Confidence groups use the deployed version's training counts, so both
    # sides are broken down over identical rows.
    train_counts = cur_train.groupby("location_std").size().astype(float)

    def run_side(train: pd.DataFrame, test: pd.DataFrame, folds: np.ndarray, side_fs: FeatureSet) -> dict:
        per_seed = []
        y_tr = train[TARGET].to_numpy(float)
        y_te = test[TARGET].to_numpy(float)
        g_tr = _confidence_groups(train, train_counts)
        g_te = _confidence_groups(test, train_counts)
        for s in seeds:
            test_m, test_pred = _fit_and_score(train, test, side_fs, model_seed=s, return_pred=True)
            cv, oof = cross_validate_lgbm(train, side_fs, k=k, folds=folds, model_seed=s, return_oof=True)
            per_seed.append({
                "seed": s, "test": test_m,
                "cv_r2_mean": cv["R2"]["mean"], "cv_mape_mean": cv["MAPE"]["mean"],
                "groups_oof": _group_errors(y_tr, oof, g_tr),
                "groups_test": _group_errors(y_te, test_pred, g_te),
            })
        return {"feature_set": side_fs.name, "per_seed": per_seed, "summary": {
            "test_mape": _spread([r["test"]["MAPE"] for r in per_seed]),
            "test_r2": _spread([r["test"]["R2"] for r in per_seed]),
            "cv_r2": _spread([r["cv_r2_mean"] for r in per_seed]),
            "cv_mape": _spread([r["cv_mape_mean"] for r in per_seed]),
        }}

    cur = run_side(cur_train, cur_test, cur_folds, current_fs or fs)
    cand = run_side(cand_train, cand_test, cand_folds, fs)

    def by_group(key: str) -> dict:
        out = {}
        for g in CONFIDENCE_GROUPS:
            c_rows = [r[key][g] for r in cur["per_seed"] if g in r[key]]
            n_rows = [r[key][g] for r in cand["per_seed"] if g in r[key]]
            if not c_rows or not n_rows:
                continue
            paired = [n["MAPE"] - c["MAPE"] for c, n in zip(c_rows, n_rows)]
            out[g] = {
                "n_rows": c_rows[0]["n"],
                "current": {"MAPE": _spread([r["MAPE"] for r in c_rows]), "MAE": _spread([r["MAE"] for r in c_rows])},
                "candidate": {"MAPE": _spread([r["MAPE"] for r in n_rows]), "MAE": _spread([r["MAE"] for r in n_rows])},
                "mape_delta_pp": _spread(paired),
            }
        return out

    mape_delta = cand["summary"]["test_mape"]["mean"] - cur["summary"]["test_mape"]["mean"]
    cv_r2_delta = cand["summary"]["cv_r2"]["mean"] - cur["summary"]["cv_r2"]["mean"]
    passes = bool(mape_delta <= DEPLOY_MAX_MAPE_WORSE_PP and cv_r2_delta >= -DEPLOY_MAX_CV_R2_DROP)
    # Paired per-seed deltas: same seed on both sides, so these show how
    # much of the mean delta is stable vs. seed noise.
    paired_mape = [c["test"]["MAPE"] - o["test"]["MAPE"] for c, o in zip(cand["per_seed"], cur["per_seed"])]
    paired_cv_r2 = [c["cv_r2_mean"] - o["cv_r2_mean"] for c, o in zip(cand["per_seed"], cur["per_seed"])]

    return {
        "rule": (f"Deploy rule: on the same evaluation rows, averaged over {len(seeds)} training seeds, "
                 f"mean test MAPE not worse by > {DEPLOY_MAX_MAPE_WORSE_PP} pp and mean CV R2 not lower "
                 f"by > {DEPLOY_MAX_CV_R2_DROP}"),
        "current_version": current_version,
        "seeds": list(seeds),
        "rows": {
            "test_rows_shared": len(shared_test),
            "test_rows_dropped_by_candidate": len(cur_test_ids - shared_test),
            "train_rows_current": len(cur_train),
            "train_rows_candidate": len(cand_train),
            "train_rows_new_in_candidate": int((~cand_fold_ids.isin(fold_of.keys())).sum()),
            "train_rows_dropped_by_candidate": int((~cur_train[ID_COL].astype(str).isin(set(cand_ids))).sum()),
        },
        "current": cur,
        "candidate": cand,
        "test_mape_delta_pp": float(mape_delta),
        "cv_r2_delta": float(cv_r2_delta),
        "paired_seed_deltas": {"test_mape_pp": _spread(paired_mape), "cv_r2": _spread(paired_cv_r2)},
        "by_confidence": {
            "note": "groups from the deployed version's training counts; out-of-fold CV is the main evidence",
            "cv_oof": by_group("groups_oof"),
            "test": by_group("groups_test"),
        },
        "passes": passes,
    }


def _spread(values: list[float]) -> dict:
    v = np.asarray(values, dtype=float)
    return {"mean": float(v.mean()), "std": float(v.std(ddof=1)) if len(v) > 1 else 0.0,
            "min": float(v.min()), "max": float(v.max())}
