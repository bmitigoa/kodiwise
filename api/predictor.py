"""Loads the production model and builds predictions using ml.features --
the same feature construction code used at training time, so the API can
never silently drift from what the model was actually trained on.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.features import APP_FEATURE_SET, lookup_location_stats, recompute_rooms_bath_from_counts

MODELS_DIR = Path(__file__).resolve().parent.parent / "ml" / "models"


class Predictor:
    def __init__(self, version: str):
        self.version = version
        self.model_dir = MODELS_DIR / version
        self.pipe = None
        self.location_lookup: dict = {}
        self.metrics: dict = {}

    def load(self) -> None:
        self.pipe = joblib.load(self.model_dir / "model.joblib")
        self.location_lookup = json.loads((self.model_dir / "location_lookup.json").read_text())
        self.metrics = json.loads((self.model_dir / "metrics.json").read_text())

    @property
    def loaded(self) -> bool:
        return self.pipe is not None

    def predict(self, bedrooms_num: int, bathrooms_num: int, location_std: str) -> dict:
        row = pd.DataFrame([{"bedrooms_num": bedrooms_num, "bathrooms_num": bathrooms_num}])
        row = recompute_rooms_bath_from_counts(row)

        loc_stats = lookup_location_stats(location_std, self.location_lookup)
        for key, value in loc_stats.items():
            row[key] = value
        row = row[APP_FEATURE_SET.numeric]

        point = max(float(self.pipe.predict(row)[0]), 0.0)

        interval = self.metrics["prediction_interval"]
        log_point = np.log1p(point)
        low = max(float(np.expm1(log_point + interval["q10_log"])), 0.0)
        high = max(float(np.expm1(log_point + interval["q90_log"])), low)

        return {
            "predicted_rent_kes": round(point, 2),
            "predicted_rent_low_kes": round(low, 2),
            "predicted_rent_high_kes": round(high, 2),
            "model_version": self.version,
            "note": (
                "Estimate only, not an exact valuation. The range reflects "
                "10th-90th percentile prediction error observed in 5-fold "
                "cross-validation -- treat it as a rough guide, not a verdict."
            ),
        }
