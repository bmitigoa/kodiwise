"""Test-set metrics, 5-fold CV, and baseline comparisons.

Mirrors rent_ml/reviewer_rerun_leakfree.py's evaluation logic, refactored
to use ml.features as the single source of truth for columns/preprocessing.
"""
from __future__ import annotations

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

from ml.features import FeatureSet, LGBM_PARAMS, TARGET, add_location_stats, build_preprocessor

RANDOM_STATE = 42


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return dict(
        MAE=float(mean_absolute_error(y_true, y_pred)),
        RMSE=float(np.sqrt(mean_squared_error(y_true, y_pred))),
        R2=float(r2_score(y_true, y_pred)),
        MAPE=float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100),
    )


def make_lgbm_log_pipeline(fs: FeatureSet) -> Pipeline:
    model = TransformedTargetRegressor(LGBMRegressor(**LGBM_PARAMS), func=np.log1p, inverse_func=np.expm1)
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


def cross_validate(
    pipeline_factory, train_df: pd.DataFrame, fs: FeatureSet, k: int = 5, seed: int = RANDOM_STATE
) -> dict:
    """Generic k-fold CV with location stats recomputed per fold (no
    validation rent ever informs that fold's features)."""
    trd = train_df.reset_index(drop=True)
    scores = []
    for tr_idx, va_idx in KFold(k, shuffle=True, random_state=seed).split(trd):
        f_tr, f_va, _ = add_location_stats(trd.iloc[tr_idx], trd.iloc[va_idx])
        pipe = pipeline_factory()
        pipe.fit(f_tr, f_tr[TARGET].values)
        scores.append(metrics(f_va[TARGET].values, pipe.predict(f_va)))
    agg = {}
    for key in scores[0]:
        vals = [s[key] for s in scores]
        agg[key] = {"mean": float(np.mean(vals)), "std": float(np.std(vals))}
    return agg


def cross_validate_lgbm(train_df: pd.DataFrame, fs: FeatureSet, k: int = 5, seed: int = RANDOM_STATE) -> dict:
    return cross_validate(lambda: make_lgbm_log_pipeline(fs), train_df, fs, k, seed)


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
