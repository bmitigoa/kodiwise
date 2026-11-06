"""Loads the production model and builds predictions using ml.features --
the same feature construction code used at training time, so the API can
never silently drift from what the model was actually trained on.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.features import (
    RUN_D_FEATURE_SET,
    lookup_location_stats,
    property_type_flags,
    recompute_rooms_bath_from_counts,
    resolve_location,
)

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

    def known_locations(self) -> list[str]:
        """Public-facing neighbourhood list for GET /locations -- excludes
        the internal "Unknown" bucket (a data artifact for unparseable
        training rows, not a real neighbourhood a user should pick)."""
        return sorted(loc for loc in self.location_lookup if loc not in ("__global__", "Unknown"))

    def predict(
        self,
        bedrooms_num: int,
        bathrooms_num: int,
        location_std: str,
        sq_m: float | None = None,
        is_furnished: int | None = None,
        property_type: str | None = None,
        has_generator: int | None = None,
        has_borehole: int | None = None,
        has_cctv: int | None = None,
        has_dsq: int | None = None,
        has_play_area: int | None = None,
        has_garden: int | None = None,
    ) -> dict:
        row = pd.DataFrame([{"bedrooms_num": bedrooms_num, "bathrooms_num": bathrooms_num}])
        row = recompute_rooms_bath_from_counts(row)

        resolved_location, location_recognised = resolve_location(location_std, self.location_lookup)
        loc_stats = lookup_location_stats(resolved_location, self.location_lookup)
        for key, value in loc_stats.items():
            row[key] = value

        # sq_m is genuinely missing-aware: NaN flows through to the same
        # SimpleImputer(median) the trained pipeline already has, rather
        # than defaulting to a value that would be wrong (e.g. 0 sq. m).
        row["sq_m"] = sq_m if sq_m is not None else math.nan

        # Binary flags default to 0 ("not mentioned" -> assume absent),
        # matching how the Android forms behave for an unchecked box.
        row["is_furnished"] = is_furnished if is_furnished is not None else 0
        for key, value in property_type_flags(property_type).items():
            row[key] = value
        row["has_generator"] = has_generator if has_generator is not None else 0
        row["has_borehole"] = has_borehole if has_borehole is not None else 0
        row["has_cctv"] = has_cctv if has_cctv is not None else 0
        row["has_dsq"] = has_dsq if has_dsq is not None else 0
        row["has_play_area"] = has_play_area if has_play_area is not None else 0
        row["has_garden"] = has_garden if has_garden is not None else 0

        row = row[RUN_D_FEATURE_SET.numeric + RUN_D_FEATURE_SET.binary]

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
            "location_recognised": location_recognised,
            "note": (
                "Estimate only, not an exact valuation. The range reflects "
                "10th-90th percentile prediction error observed in 5-fold "
                "cross-validation -- treat it as a rough guide, not a verdict."
            ),
        }
