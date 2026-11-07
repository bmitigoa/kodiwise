"""Trains and evaluates the KodiWise leak-free LightGBM baseline.

Runs two experiments side by side (per Baraka's instructions):
  Run A - paper reproduction: raw 580-row dataset, no cleaning, the
          paper's exact leak-free feature set (reproduction check target).
  Run B - KodiWise baseline: cleaned dataset, dead columns dropped.

Both use the same split seed (42) and LightGBM hyperparameters
(project reproducibility rules). Only Run B is saved as a versioned, deployable model
(ml/models/v{date}/) -- Run A exists purely to validate the pipeline
against the published paper.

Run: python -m ml.train
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from ml.evaluate import (
    compare_on_same_rows,
    cross_validate_baselines,
    cross_validate_lgbm,
    cross_validate_log_residuals,
    eval_rows_record,
    make_lgbm_log_pipeline,
    metrics,
    prediction_interval_widths,
    run_baselines,
)
from ml.features import (
    APP_FEATURE_SET,
    FeatureSet,
    KODIWISE_FEATURE_SET,
    PAPER_FEATURE_SET,
    RUN_D_FEATURE_SET,
    STRATIFY_COL,
    TARGET,
    add_location_stats,
    build_location_lookup,
    coerce_dtypes,
    get_feature_names,
    recompute_rooms_bath_from_counts,
    simulate_app_predict_input,
)

RANDOM_STATE = 42
RAW_PATH = Path("data/raw/nairobi_rentals_enriched_v4.csv")
CLEAN_PATH = Path("data/processed/nairobi_rentals_clean.csv")
MODELS_DIR = Path("ml/models")
# Exact data each saved version was trained/evaluated on (gitignored, never
# uploaded), so a later candidate can be compared on the same rows.
SNAPSHOT_DIR = Path("data/processed/snapshots")


def load_version_eval(version: str, fs: FeatureSet) -> tuple[pd.DataFrame, dict] | None:
    rows_path = MODELS_DIR / version / "eval_rows.json"
    snap_path = SNAPSHOT_DIR / f"{version}.csv"
    if not (rows_path.exists() and snap_path.exists()):
        return None
    df = coerce_dtypes(pd.read_csv(snap_path), fs.binary, fs.categorical)
    return df, json.loads(rows_path.read_text())


def deploy_comparison(candidate_df: pd.DataFrame, fs: FeatureSet, current_version: str) -> dict:
    """Deploy-rule gate on the same evaluation rows. If the current
    version has no recorded rows/snapshot, the gate cannot be evaluated and
    fails closed (deploying then needs Baraka's explicit decision)."""
    loaded = load_version_eval(current_version, fs)
    if loaded is None:
        return {"current_version": current_version, "passes": False,
                "error": "current version has no eval_rows.json / data snapshot; comparison not possible"}
    current_df, current_rows = loaded
    return compare_on_same_rows(current_df, current_rows, candidate_df, fs, current_version)


def run_experiment(
    df: pd.DataFrame, fs: FeatureSet, save_model: bool = False, return_artifacts: bool = False,
    version: str | None = None, compare_to: str | None = None,
) -> dict:
    input_df = df
    df = coerce_dtypes(df, fs.binary, fs.categorical)

    idx_tr, idx_te = train_test_split(
        np.arange(len(df)), test_size=0.2, random_state=RANDOM_STATE, stratify=df[STRATIFY_COL]
    )
    train_raw, test_raw = df.iloc[idx_tr], df.iloc[idx_te]
    train, test, unseen = add_location_stats(train_raw, test_raw)

    pipe = make_lgbm_log_pipeline(fs)
    pipe.fit(train, train[TARGET].values)
    test_metrics = metrics(test[TARGET].values, pipe.predict(test))

    cv_lgbm = cross_validate_lgbm(train, fs)
    cv_baselines = cross_validate_baselines(train, fs)
    test_baselines = run_baselines(train, test, fs)

    lgbm_model = pipe.named_steps["m"].regressor_
    feature_names = get_feature_names(pipe.named_steps["pre"], fs)
    importances = sorted(
        zip(feature_names, lgbm_model.feature_importances_.tolist()),
        key=lambda x: x[1], reverse=True,
    )

    result = {
        "feature_set": fs.name,
        "n_total": len(df),
        "n_train": len(train),
        "n_test": len(test),
        "unseen_test_locations": unseen,
        "test_metrics": test_metrics,
        "cv_lgbm_log_target": cv_lgbm,
        "cv_baselines": cv_baselines,
        "test_baselines": test_baselines,
        "top_feature_importances": importances[:15],
    }

    if save_model:
        version = version or date.today().strftime("v%Y%m%d")
        out_dir = MODELS_DIR / version
        if (out_dir / "model.joblib").exists():
            # Versions are immutable (deploy rule): a deployed model must
            # stay reproducible from its own folder. Bump the version instead.
            raise FileExistsError(f"{out_dir} already holds a model; refusing to overwrite")
        out_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipe, out_dir / "model.joblib")

        location_lookup = build_location_lookup(train)
        (out_dir / "location_lookup.json").write_text(json.dumps(location_lookup, indent=2))

        residuals = cross_validate_log_residuals(train, fs)
        q10, q90 = np.percentile(residuals, [10, 90])
        prediction_interval = {
            "method": "cv_log_residual_quantiles",
            "q10_log": float(q10),
            "q90_log": float(q90),
            "n_cv_residuals": int(len(residuals)),
        }

        widths = prediction_interval_widths(pipe, test, q10, q90)
        prediction_interval["median_test_range_width_kes"] = float(np.median(widths))
        prediction_interval["test_range_width_p25_kes"] = float(np.percentile(widths, 25))
        prediction_interval["test_range_width_p75_kes"] = float(np.percentile(widths, 75))

        metrics_payload = {
            "version": version,
            "generated": date.today().isoformat(),
            "feature_set": fs.name,
            "numeric_features": fs.numeric,
            "binary_features": fs.binary,
            "categorical_features": fs.categorical,
            "text_feature": fs.text,
            "hyperparameters": "see ml/features.py LGBM_PARAMS",
            "data_source": str(CLEAN_PATH),
            "n_train": len(train),
            "n_test": len(test),
            "test_metrics": test_metrics,
            "cv_lgbm_log_target": cv_lgbm,
            "test_baselines": test_baselines,
            "cv_baselines": cv_baselines,
            "prediction_interval": prediction_interval,
        }
        if compare_to:
            metrics_payload["deploy_comparison"] = deploy_comparison(df, fs, compare_to)
            result["deploy_comparison"] = metrics_payload["deploy_comparison"]
        (out_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2))
        (out_dir / "eval_rows.json").write_text(json.dumps(eval_rows_record(train, test), indent=2))
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        input_df.to_csv(SNAPSHOT_DIR / f"{version}.csv", index=False)
        (out_dir / "feature_importance.json").write_text(json.dumps(importances[:50], indent=2))
        result["model_version"] = version
        result["model_dir"] = str(out_dir)
        result["prediction_interval"] = prediction_interval

    if return_artifacts:
        result["_pipe"] = pipe
        result["_test"] = test

    return result


def score_app_degraded(run_b_result: dict) -> dict:
    """Score Run B's already-fitted pipeline on its own held-out test set,
    with inputs degraded to what PredictionFormActivity actually sends
    (synthetic title, zeroed amenity flags, missing sq_m/income_band_final/
    platform/source_host). No retraining -- pure inference-time check of
    how much Run B degrades under real production conditions."""
    pipe = run_b_result["_pipe"]
    test = run_b_result["_test"]
    degraded = simulate_app_predict_input(test, KODIWISE_FEATURE_SET.binary, KODIWISE_FEATURE_SET.categorical)
    return metrics(degraded[TARGET].values, pipe.predict(degraded))


def title_len_source_proxy(clean_df: pd.DataFrame) -> dict:
    """title_len was the #1 feature importance in Run A/B. Check whether it
    is substantially a proxy for which platform a listing was scraped from
    (a signal the app can never reproduce, since it synthesizes a short
    placeholder title instead of copying a real listing's title)."""
    g = clean_df.groupby("platform").agg(
        mean_title_len=("title_len", "mean"), mean_price_kes=("price_kes", "mean"), n=("price_kes", "size")
    )
    return {
        "by_platform": g.round(2).to_dict(orient="index"),
        "title_len_price_correlation": round(float(clean_df["title_len"].corr(clean_df["price_kes"])), 4),
    }


RUN_C_VERSION = "v20261106-appC"  # historical; no longer re-saved
# v20261107-appD: Run D retrained after the cleaning step started dropping
# listings outside Nairobi County (1 row: a Nakuru listing mapped to
# "Pipeline"). v20261106-appD is kept as-is for rollback.
RUN_D_VERSION = "v20261107-appD"
PRODUCTION_VERSION = RUN_D_VERSION
# The version currently deployed. A new Run D candidate (bump RUN_D_VERSION)
# is compared with it on the same rows; see ml.evaluate.compare_on_same_rows.
DEPLOYED_VERSION = "v20261107-appD"


def main() -> None:
    raw_df = pd.read_csv(RAW_PATH)
    clean_df = pd.read_csv(CLEAN_PATH)

    print("=== Run A: paper reproduction (raw data, paper feature set) ===")
    run_a = run_experiment(raw_df, PAPER_FEATURE_SET, save_model=False)
    print(json.dumps({k: v for k, v in run_a.items() if k != "top_feature_importances"}, indent=2))

    print("\n=== Run B: KodiWise baseline (cleaned data, KodiWise feature set) ===")
    run_b = run_experiment(clean_df, KODIWISE_FEATURE_SET, save_model=False, return_artifacts=True)
    print(json.dumps({k: v for k, v in run_b.items() if k not in ("top_feature_importances", "_pipe", "_test")}, indent=2))

    print("\n=== Run B scored under app-realistic (degraded) inputs ===")
    run_b_app_degraded_metrics = score_app_degraded(run_b)
    print(json.dumps(run_b_app_degraded_metrics, indent=2))

    # rooms_total/bath_per_bed in the dataset come from a title-parsed,
    # location-median-imputed "_filled" pipeline the API can't reproduce
    # (bedrooms_num != bedrooms_filled on ~28% of rows). Run C/D must use
    # the API-reproducible versions, computed directly from bedrooms_num/
    # bathrooms_num, or they'd reintroduce the exact skew this exercise is
    # meant to eliminate. Run A/B intentionally keep the dataset's native
    # columns -- they're diagnostic-only and were never going to be served.
    serving_safe_df = recompute_rooms_bath_from_counts(clean_df)

    print(f"\n=== Run C: app-realistic (bedrooms/bathrooms/location only) -- reported only; {RUN_C_VERSION} kept as saved ===")
    run_c = run_experiment(serving_safe_df, APP_FEATURE_SET, save_model=False)
    print(json.dumps({k: v for k, v in run_c.items() if k != "top_feature_importances"}, indent=2))

    print(f"\n=== Run D: app-realistic + expanded-form features -- SAVED as production ({RUN_D_VERSION}) ===")
    run_d = run_experiment(serving_safe_df, RUN_D_FEATURE_SET, save_model=True, version=RUN_D_VERSION,
                           compare_to=DEPLOYED_VERSION if DEPLOYED_VERSION != RUN_D_VERSION else None)
    print(json.dumps({k: v for k, v in run_d.items() if k != "top_feature_importances"}, indent=2))
    gate = run_d.get("deploy_comparison")
    if gate is not None:
        verdict = "PASSES" if gate["passes"] else "FAILS -- do not deploy without Baraka's decision"
        print(f"\n=== Deploy gate vs {DEPLOYED_VERSION} (same rows): {verdict} ===")

    print("\n=== title_len as a source-platform proxy ===")
    proxy = title_len_source_proxy(clean_df)
    print(json.dumps(proxy, indent=2))

    run_b_clean = {k: v for k, v in run_b.items() if k not in ("_pipe", "_test")}
    report = {
        "generated": date.today().isoformat(),
        "production_model_version": PRODUCTION_VERSION,
        "run_a_paper_reproduction": run_a,
        "run_b_kodiwise_baseline": run_b_clean,
        "run_b_scored_with_app_realistic_inputs": run_b_app_degraded_metrics,
        "run_c_app_realistic": run_c,
        "run_d_app_expanded_form_deployed": run_d,
        "title_len_source_platform_proxy": proxy,
    }
    report_path = MODELS_DIR / PRODUCTION_VERSION / "run_comparison.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nComparison report saved to {report_path}")


if __name__ == "__main__":
    main()
