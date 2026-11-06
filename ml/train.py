"""Trains and evaluates the KodiWise leak-free LightGBM baseline.

Runs two experiments side by side (per Baraka's instructions):
  Run A - paper reproduction: raw 580-row dataset, no cleaning, the
          paper's exact leak-free feature set (project rules check target).
  Run B - KodiWise baseline: cleaned dataset, dead columns dropped.

Both use the same split seed (42) and LightGBM hyperparameters
(project rules #3). Only Run B is saved as a versioned, deployable model
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

from ml.evaluate import cross_validate_baselines, cross_validate_lgbm, make_lgbm_log_pipeline, metrics, run_baselines
from ml.features import (
    FeatureSet,
    KODIWISE_FEATURE_SET,
    PAPER_FEATURE_SET,
    STRATIFY_COL,
    TARGET,
    add_location_stats,
    coerce_dtypes,
    get_feature_names,
)

RANDOM_STATE = 42
RAW_PATH = Path("data/raw/nairobi_rentals_enriched_v4.csv")
CLEAN_PATH = Path("data/processed/nairobi_rentals_clean.csv")
MODELS_DIR = Path("ml/models")


def run_experiment(df: pd.DataFrame, fs: FeatureSet, save_model: bool = False) -> dict:
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
        version = date.today().strftime("v%Y%m%d")
        out_dir = MODELS_DIR / version
        out_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipe, out_dir / "model.joblib")
        train[["location_std", TARGET]].to_csv(out_dir / "location_stats_training_data.csv", index=False)
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
        }
        (out_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2))
        (out_dir / "feature_importance.json").write_text(json.dumps(importances[:50], indent=2))
        result["model_version"] = version
        result["model_dir"] = str(out_dir)

    return result


def main() -> None:
    raw_df = pd.read_csv(RAW_PATH)
    clean_df = pd.read_csv(CLEAN_PATH)

    print("=== Run A: paper reproduction (raw data, paper feature set) ===")
    run_a = run_experiment(raw_df, PAPER_FEATURE_SET, save_model=False)
    print(json.dumps({k: v for k, v in run_a.items() if k != "top_feature_importances"}, indent=2))

    print("\n=== Run B: KodiWise baseline (cleaned data, KodiWise feature set) ===")
    run_b = run_experiment(clean_df, KODIWISE_FEATURE_SET, save_model=True)
    print(json.dumps({k: v for k, v in run_b.items() if k != "top_feature_importances"}, indent=2))

    report = {"generated": date.today().isoformat(), "run_a_paper_reproduction": run_a, "run_b_kodiwise_baseline": run_b}
    report_path = MODELS_DIR / run_b["model_version"] / "run_comparison.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nComparison report saved to {report_path}")


if __name__ == "__main__":
    main()
