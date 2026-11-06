"""Single source of truth for feature definitions and preprocessing.

Imported by ml/train.py, ml/evaluate.py, and (in a later phase) api/.
Ports the leak-free feature set from rent_ml/reviewer_rerun_leakfree.py.

Ground rule (project rules #1): no feature may be derived from price_kes
except the smoothed/fallback location statistics below, which are always
computed from the training split only.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

TARGET = "price_kes"
STRATIFY_COL = "income_band_final"
TEXT_COL = "title_clean"

# Numeric columns that exist on the raw data (not leak-derived).
_NUMERIC_RAW = ["bedrooms_num", "bathrooms_num", "rooms_total", "bath_per_bed", "sq_m", "title_len"]
# Added by add_location_stats(); always computed from the training split only.
_NUMERIC_LOCATION = ["loc_mean_tr", "loc_median_tr", "loc_count_tr"]
NUMERIC = _NUMERIC_RAW + _NUMERIC_LOCATION

# Binary indicators, as used in reviewer_rerun_leakfree.py.
PAPER_BINARY = [
    "is_high_income_area", "is_middle_income_area", "is_low_income_area",
    "is_furnished", "is_serviced", "is_furnished_page", "is_serviced_page",
    "has_parking", "has_balcony", "has_gym", "has_pool", "has_security",
    "has_lift", "has_wifi", "pet_friendly", "has_ensuite", "has_backup_water",
    "has_borehole", "has_generator", "has_cctv", "has_garden", "has_play_area",
    "has_dsq", "is_bedsitter", "is_apartment", "is_house",
]
# KodiWise baseline drops is_furnished_page: project rules #10.3 dead column
# (~99% constant at 1.0).
KODIWISE_BINARY = [c for c in PAPER_BINARY if c != "is_furnished_page"]

PAPER_CATEGORICAL = [
    "location_std", "income_band_final", "platform",
    "property_type_std", "estate_name", "source_host",
]
# KodiWise baseline drops property_type_std (100% "unknown") and
# estate_name (100% empty): project rules #10.3 dead columns.
KODIWISE_CATEGORICAL = [c for c in PAPER_CATEGORICAL if c not in ("property_type_std", "estate_name")]

# Features that must never be used: derived from price_kes (target leakage).
FORBIDDEN_LEAKY_FEATURES = [
    "price_per_bedroom", "price_per_bathroom",
    "location_mean_price_all", "location_median_price_all", "location_listing_count_all",
]

LGBM_PARAMS = dict(
    n_estimators=2000, learning_rate=0.03, num_leaves=64, max_depth=-1,
    min_child_samples=15, subsample=0.85, subsample_freq=1,
    colsample_bytree=0.85, reg_alpha=0.2, reg_lambda=0.2,
    random_state=42, n_jobs=-1, verbose=-1,
)


@dataclass(frozen=True)
class FeatureSet:
    name: str
    numeric: list[str]
    binary: list[str]
    categorical: list[str]
    text: str | None = TEXT_COL


PAPER_FEATURE_SET = FeatureSet("paper_reproduction", NUMERIC, PAPER_BINARY, PAPER_CATEGORICAL)
KODIWISE_FEATURE_SET = FeatureSet("kodiwise_baseline", NUMERIC, KODIWISE_BINARY, KODIWISE_CATEGORICAL)

# Run C: only fields PredictionFormActivity actually collects/sends
# (bedrooms_num, bathrooms_num, location_std), plus features purely derived
# from those (bath_per_bed, rooms_total, and the train-only location stats).
# No sq_m (never sent), no amenity flags (PredictionFormActivity never sets
# any of the 9 optional ones on PredictionRequest -- they default to 0), no
# title/text (the app only ever sends a synthetic "apartment in {location}"
# placeholder, never a real listing title), no title_len, no
# income_band_final/platform/source_host (dataset-only, not sent by the app).
APP_NUMERIC = ["bedrooms_num", "bathrooms_num", "rooms_total", "bath_per_bed",
               "loc_mean_tr", "loc_median_tr", "loc_count_tr"]
APP_FEATURE_SET = FeatureSet("app_realistic", APP_NUMERIC, [], [], text=None)


def simulate_app_predict_input(df: pd.DataFrame, binary_cols: list[str], categorical_cols: list[str]) -> pd.DataFrame:
    """Degrade a dataframe to what PredictionFormActivity actually sends:
    only bedrooms_num/bathrooms_num/location_std are real; everything else
    the trained KODIWISE_FEATURE_SET model expects is unavailable at that
    call site and takes its "nothing sent" value. Used to measure Run B's
    production-conditions degradation -- does not retrain, only perturbs
    inputs scored by an already-fitted pipeline.
    """
    df = df.copy()
    df[TEXT_COL] = "apartment in " + df["location_std"].astype(str)
    df["title_len"] = df[TEXT_COL].str.len()
    df["sq_m"] = np.nan
    for c in binary_cols:
        df[c] = 0
    for c in categorical_cols:
        if c != "location_std":
            df[c] = "missing"
    return df


def coerce_dtypes(df: pd.DataFrame, binary_cols: list[str], categorical_cols: list[str]) -> pd.DataFrame:
    """Type coercion matching reviewer_rerun_leakfree.py exactly."""
    df = df.copy()
    for c in _NUMERIC_RAW:
        df[c] = pd.to_numeric(df.get(c, 0), errors="coerce")
    for c in binary_cols:
        s = pd.Series(df.get(c, 0)).fillna(0).astype(str).str.strip().replace({"True": "1", "False": "0"})
        df[c] = pd.to_numeric(s, errors="coerce").fillna(0).astype(int)
    for c in categorical_cols:
        df[c] = df.get(c, "missing")
        df[c] = df[c].fillna("missing").astype(str)
    df[TEXT_COL] = df.get(TEXT_COL, "").fillna("").astype(str)
    df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")
    df = df.dropna(subset=[TARGET]).reset_index(drop=True)
    return df


def add_location_stats(
    train: pd.DataFrame, other: pd.DataFrame, m: int = 5
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Compute location_std -> rent stats from `train` only, smoothed toward
    the global training mean (weight m), and map them onto both `train` and
    `other`. Unseen locations in `other` fall back to the global train
    mean/median/0 count. Never touches `other`'s price_kes.
    """
    g = train.groupby("location_std")[TARGET]
    global_mean = train[TARGET].mean()
    global_median = train[TARGET].median()
    stats = pd.DataFrame({"mean": g.mean(), "median": g.median(), "n": g.count()})
    smoothed_mean = (stats["n"] * stats["mean"] + m * global_mean) / (stats["n"] + m)

    def _apply(d: pd.DataFrame) -> pd.DataFrame:
        d = d.copy()
        d["loc_mean_tr"] = d["location_std"].map(smoothed_mean).fillna(global_mean)
        d["loc_median_tr"] = d["location_std"].map(stats["median"]).fillna(global_median)
        d["loc_count_tr"] = d["location_std"].map(stats["n"]).fillna(0)
        return d

    unseen = int((~other["location_std"].isin(stats.index)).sum())
    return _apply(train), _apply(other), unseen


def build_preprocessor(fs: FeatureSet, scale: bool = False) -> ColumnTransformer:
    """ColumnTransformer matching reviewer_rerun_leakfree.py's pre().
    Categorical and text branches are omitted entirely when the feature set
    doesn't use them (e.g. Run C), rather than built with zero columns.
    """
    numeric_steps = [("imp", SimpleImputer(strategy="median"))]
    if scale:
        numeric_steps.append(("sc", StandardScaler()))
    transformers = [("num", Pipeline(numeric_steps), fs.numeric + fs.binary)]
    if fs.categorical:
        transformers.append(("cat", Pipeline([
            ("imp", SimpleImputer(strategy="most_frequent")),
            ("oh", OneHotEncoder(handle_unknown="ignore")),
        ]), fs.categorical))
    if fs.text:
        transformers.append(("txt", TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=2), fs.text))
    return ColumnTransformer(transformers)


def get_feature_names(preprocessor: ColumnTransformer, fs: FeatureSet) -> list[str]:
    names: list[str] = list(fs.numeric) + list(fs.binary)
    if fs.categorical:
        oh = preprocessor.named_transformers_["cat"].named_steps["oh"]
        for col, cats in zip(fs.categorical, oh.categories_):
            names.extend(f"{col}={c}" for c in cats)
    if fs.text:
        vocab = preprocessor.named_transformers_["txt"].vocabulary_
        inv_vocab = {i: term for term, i in vocab.items()}
        names.extend(f"title:{inv_vocab[i]}" for i in range(len(inv_vocab)))
    return names
