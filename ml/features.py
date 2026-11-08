"""Single source of truth for feature definitions and preprocessing.

Imported by ml/train.py, ml/evaluate.py, and (in a later phase) api/.
Ports the leak-free feature set from rent_ml/reviewer_rerun_leakfree.py.

Ground rule (no target leakage): no feature may be derived from price_kes
except the smoothed/fallback location statistics below, which are always
computed from the training split only.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

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
# KodiWise baseline drops is_furnished_page: dead column (cleaning rules)
# (~99% constant at 1.0).
KODIWISE_BINARY = [c for c in PAPER_BINARY if c != "is_furnished_page"]

PAPER_CATEGORICAL = [
    "location_std", "income_band_final", "platform",
    "property_type_std", "estate_name", "source_host",
]
# KodiWise baseline drops property_type_std (100% "unknown") and
# estate_name (100% empty): dead columns (cleaning rules).
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

# Run D: APP_FEATURE_SET plus the fields a user could realistically fill in
# on an expanded form -- sq_m (optional numeric), furnished, property type,
# and the amenity flags that actually carry signal in Run B's own feature
# importances (has_generator, has_borehole, has_cctv, has_dsq, has_play_area,
# has_garden -- the only amenity flags that appear in Run B's top 50 at all;
# has_parking/has_balcony/has_gym/has_pool/has_security/has_lift/has_wifi/
# pet_friendly/has_ensuite/has_backup_water did not and are deliberately
# left out of this proposal). Still no location one-hot, still no text.
RUN_D_NUMERIC = APP_NUMERIC + ["sq_m"]
RUN_D_BINARY = [
    "is_furnished", "is_apartment", "is_house", "is_bedsitter",
    "has_generator", "has_borehole", "has_cctv", "has_dsq", "has_play_area", "has_garden",
]
RUN_D_FEATURE_SET = FeatureSet("app_expanded_form", RUN_D_NUMERIC, RUN_D_BINARY, [], text=None)

# Run E: Run D + location geography. Coordinates and distances come from
# the neighbourhood name only (data/reference/, OpenStreetMap), so the app
# request does not change. loc_mean_spatial_tr is the train-only location
# mean shrunk toward nearby neighbourhoods (see spatial_location_means).
GEO_FEATURES = [
    "lat", "lon",
    "dist_cbd_km", "dist_westlands_km", "dist_upperhill_km", "dist_jkia_km",
    "dist_thika_rd_km", "dist_mombasa_rd_km",
]
SPATIAL_PRIOR_COL = "loc_mean_spatial_tr"
RUN_E_NUMERIC = RUN_D_NUMERIC + GEO_FEATURES + [SPATIAL_PRIOR_COL]
RUN_E_FEATURE_SET = FeatureSet("app_expanded_form_gps", RUN_E_NUMERIC, RUN_D_BINARY, [], text=None)
# Run E2: Run D + GPS only, without the spatial prior (the prior added
# nothing measurable in the Run E sensitivity checks).
RUN_E2_NUMERIC = RUN_D_NUMERIC + GEO_FEATURES
RUN_E2_FEATURE_SET = FeatureSet("app_expanded_form_gps_no_prior", RUN_E2_NUMERIC, RUN_D_BINARY, [], text=None)

FEATURE_SETS = {fs.name: fs for fs in [
    PAPER_FEATURE_SET, KODIWISE_FEATURE_SET, APP_FEATURE_SET, RUN_D_FEATURE_SET, RUN_E_FEATURE_SET,
    RUN_E2_FEATURE_SET,
]}

PROPERTY_TYPES = ["apartment", "house", "bedsitter"]


def property_type_flags(property_type: str | None) -> dict:
    """Single source of truth for turning a single property-type choice
    into the is_apartment/is_house/is_bedsitter one-hot flags Run D was
    trained on. None (not selected) -> all zero, same as any other missing
    binary flag.
    """
    return {f"is_{t}": int(property_type == t) for t in PROPERTY_TYPES}


def recompute_rooms_bath_from_counts(df: pd.DataFrame) -> pd.DataFrame:
    """rooms_total and bath_per_bed in the dataset are NOT simple functions
    of bedrooms_num/bathrooms_num: rent_ml's feature engineering
    (clean_nairobi_and_features_v2.py) computes them from separate
    "_filled" columns (bedrooms_filled/bathrooms_filled), which go through
    title-text parsing, studio/bedsitter special-casing, and per-location
    median imputation that the API has no way to reproduce -- confirmed by
    direct inspection: bedrooms_num != bedrooms_filled on ~28% of rows,
    sometimes by more than one bedroom.

    Training Run C/D on the dataset's native rooms_total/bath_per_bed would
    silently reintroduce the exact training-serving skew this whole
    exercise is meant to eliminate, since the API can only ever compute
    these from bedrooms_num/bathrooms_num directly. This recomputes both
    columns that way -- matching exactly what api/ will do at serving
    time -- using the same epsilon convention as the original formula
    (bath_per_bed = bathrooms_num / (bedrooms_num + 1e-6)) so a studio
    (bedrooms_num=0) doesn't divide by zero.
    """
    df = df.copy()
    df["rooms_total"] = df["bedrooms_num"] + df["bathrooms_num"]
    df["bath_per_bed"] = df["bathrooms_num"] / (df["bedrooms_num"] + 1e-6)
    return df


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


# ---------------------------------------------------------------------------
# Geography (Run E). Reference data: data/reference/, built from
# OpenStreetMap by data_pipeline/geocode.py ((c) OpenStreetMap contributors).
# ---------------------------------------------------------------------------

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"
EARTH_RADIUS_KM = 6371.0088
SPATIAL_BANDWIDTH_KM = 3.0   # kernel scale for neighbouring neighbourhoods
SPATIAL_MIN_N = 10           # locations with >= this many train rows keep loc_mean_tr


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (scalars or numpy arrays)."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(x, dtype=float)) for x in (lat1, lon1, lat2, lon2))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(h))


def distance_to_polyline_km(lat: float, lon: float, ways: list[np.ndarray]) -> float:
    """Shortest distance (km) from a point to a road made of OSM ways (each an
    (n, 2) array of lat/lon vertices), measured to the nearest segment in a
    local equirectangular projection -- accurate to metres at city scale."""
    k_lat = np.radians(1.0) * EARTH_RADIUS_KM
    k_lon = k_lat * np.cos(np.radians(lat))
    best = np.inf
    for way in ways:
        xy = np.column_stack(((way[:, 1] - lon) * k_lon, (way[:, 0] - lat) * k_lat))
        if len(xy) == 1:
            best = min(best, float(np.hypot(*xy[0])))
            continue
        a, b = xy[:-1], xy[1:]
        ab = b - a
        denom = np.maximum((ab ** 2).sum(axis=1), 1e-12)
        t = np.clip(-(a * ab).sum(axis=1) / denom, 0.0, 1.0)
        closest = a + ab * t[:, None]
        best = min(best, float(np.hypot(closest[:, 0], closest[:, 1]).min()))
    return best


@dataclass(frozen=True)
class GeoReference:
    centroids: dict          # neighbourhood -> (lat, lon)
    pois: dict               # poi key -> (lat, lon)
    roads: dict              # road key -> list of (n, 2) lat/lon arrays

    def features_at(self, lat: float, lon: float) -> dict:
        f = {"lat": lat, "lon": lon}
        for poi in ("cbd", "westlands", "upperhill", "jkia"):
            plat, plon = self.pois[poi]
            f[f"dist_{poi}_km"] = float(haversine_km(lat, lon, plat, plon))
        for road in ("thika_rd", "mombasa_rd"):
            f[f"dist_{road}_km"] = distance_to_polyline_km(lat, lon, self.roads[road])
        return f

    def fallback_point(self) -> tuple[float, float]:
        """Unknown / unrecognised location: the CBD, in training and serving alike."""
        return self.pois["cbd"]


@lru_cache(maxsize=4)
def load_geo_reference(ref_dir: str = str(REFERENCE_DIR)) -> GeoReference:
    d = Path(ref_dir)
    cents = pd.read_csv(d / "neighbourhood_centroids.csv")
    pois = pd.read_csv(d / "pois.csv")
    roads = pd.read_csv(d / "roads.csv").sort_values(["road", "way_id", "seq"])
    return GeoReference(
        centroids={r.name: (float(r.lat), float(r.lon)) for r in cents.itertuples()},
        pois={r.poi: (float(r.lat), float(r.lon)) for r in pois.itertuples()},
        roads={road: [g[["lat", "lon"]].to_numpy(float) for _, g in grp.groupby("way_id")]
               for road, grp in roads.groupby("road")},
    )


@lru_cache(maxsize=64)
def _geo_features_cached(location: str, ref_dir: str) -> tuple:
    geo = load_geo_reference(ref_dir)
    lat, lon = geo.centroids.get(location, geo.fallback_point())
    f = geo.features_at(lat, lon)
    return tuple(f[c] for c in GEO_FEATURES)


def location_geo_features(location: str, ref_dir: str = str(REFERENCE_DIR)) -> dict:
    """GEO_FEATURES for a neighbourhood name (CBD point if it has no centroid)."""
    return dict(zip(GEO_FEATURES, _geo_features_cached(location, ref_dir)))


def spatial_location_means(stats: pd.DataFrame, smoothed_mean: pd.Series, global_mean: float,
                           m: int, geo: GeoReference,
                           bandwidth_km: float | None = None, min_n: int | None = None) -> pd.Series:
    """Spatially smoothed location prior, from training stats only.

    Locations with >= min_n training rows keep the usual smoothed mean.
    Sparser locations with coordinates are shrunk (weight m) toward a
    distance-weighted mean of the *other* training neighbourhoods,
    w_j = n_j * exp(-d_ij / bandwidth), instead of toward the city mean.
    Returns one value per location in the training stats plus every
    neighbourhood with coordinates (a location absent from this split gets
    its pure neighbourhood prior).
    """
    h = SPATIAL_BANDWIDTH_KM if bandwidth_km is None else bandwidth_km
    min_n = SPATIAL_MIN_N if min_n is None else min_n
    with_coords = [loc for loc in stats.index if loc in geo.centroids]
    out = {}
    for loc in sorted(set(stats.index) | set(geo.centroids)):
        n = float(stats["n"].get(loc, 0.0))
        if n >= min_n or loc not in geo.centroids:
            out[loc] = float(smoothed_mean.get(loc, global_mean))
            continue
        lat, lon = geo.centroids[loc]
        others = [j for j in with_coords if j != loc]
        if others:
            d = haversine_km(lat, lon, [geo.centroids[j][0] for j in others], [geo.centroids[j][1] for j in others])
            w = stats.loc[others, "n"].to_numpy(float) * np.exp(-d / h)
            prior = float((w * stats.loc[others, "mean"].to_numpy(float)).sum() / w.sum()) if w.sum() > 1e-9 else global_mean
        else:
            prior = global_mean
        mean = float(stats["mean"].get(loc, 0.0))
        out[loc] = (n * mean + m * prior) / (n + m)
    return pd.Series(out)


def _location_stats(train: pd.DataFrame, m: int):
    g = train.groupby("location_std")[TARGET]
    global_mean = train[TARGET].mean()
    global_median = train[TARGET].median()
    stats = pd.DataFrame({"mean": g.mean(), "median": g.median(), "n": g.count()})
    smoothed_mean = (stats["n"] * stats["mean"] + m * global_mean) / (stats["n"] + m)
    spatial = spatial_location_means(stats, smoothed_mean, global_mean, m, load_geo_reference())
    return stats, smoothed_mean, spatial, global_mean, global_median


def add_location_stats(
    train: pd.DataFrame, other: pd.DataFrame, m: int = 5
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Compute location_std -> rent stats from `train` only, smoothed toward
    the global training mean (weight m), and map them onto both `train` and
    `other`. Unseen locations in `other` fall back to the global train
    mean/median/0 count. Never touches `other`'s price_kes.

    Also adds the Run E columns: GEO_FEATURES (a pure function of the
    neighbourhood name) and loc_mean_spatial_tr (train-only spatial prior).
    Feature sets that do not list them simply ignore them.
    """
    stats, smoothed_mean, spatial, global_mean, global_median = _location_stats(train, m)

    def _apply(d: pd.DataFrame) -> pd.DataFrame:
        d = d.copy()
        d["loc_mean_tr"] = d["location_std"].map(smoothed_mean).fillna(global_mean)
        d["loc_median_tr"] = d["location_std"].map(stats["median"]).fillna(global_median)
        d["loc_count_tr"] = d["location_std"].map(stats["n"]).fillna(0)
        d[SPATIAL_PRIOR_COL] = d["location_std"].map(spatial).fillna(global_mean)
        geo = pd.DataFrame([location_geo_features(str(loc)) for loc in d["location_std"]], index=d.index)
        for c in GEO_FEATURES:
            d[c] = geo[c]
        return d

    unseen = int((~other["location_std"].isin(stats.index)).sum())
    return _apply(train), _apply(other), unseen


def build_location_lookup(train: pd.DataFrame, m: int = 5) -> dict:
    """Precompute the same train-only smoothed location stats as
    add_location_stats(), as a plain dict the API can load once at startup
    and look up in O(1) per request -- no raw per-row rents are exposed,
    only the aggregated/smoothed stats actually needed to serve. The
    "__global__" key is the fallback for a location unseen in training
    (city-mean stats, CBD coordinates).
    """
    stats, smoothed_mean, spatial, global_mean, global_median = _location_stats(train, m)

    locations = {
        loc: {
            "loc_mean_tr": float(smoothed_mean[loc]),
            "loc_median_tr": float(stats["median"][loc]),
            "loc_count_tr": float(stats["n"][loc]),
            SPATIAL_PRIOR_COL: float(spatial.get(loc, smoothed_mean[loc])),
            **location_geo_features(str(loc)),
        }
        for loc in stats.index
    }
    locations["__global__"] = {
        "loc_mean_tr": float(global_mean),
        "loc_median_tr": float(global_median),
        "loc_count_tr": 0.0,
        SPATIAL_PRIOR_COL: float(global_mean),
        **location_geo_features("__global__"),
    }
    return locations


def lookup_location_stats(location_std: str, lookup: dict) -> dict:
    """Apply a build_location_lookup() dict to one location at serving
    time, falling back to the global training mean/median/0 count for a
    location unseen in training -- same fallback rule as add_location_stats.
    """
    return lookup.get(location_std, lookup["__global__"])


LocationConfidence = str  # "high" | "low" | "none"


def location_confidence(loc_count_tr: float) -> LocationConfidence:
    """How much training data actually backs a location's stats.
    "high" (n>=10): enough rows that loc_mean_tr/median reflect the area,
    not noise. "low" (3-9): some signal, but a handful of listings can
    swing the number a lot. "none" (<3, including an unrecognized location
    whose loc_count_tr is 0 via the global fallback): too little data to
    say anything neighbourhood-specific -- at n=1 or 2, a single atypical
    listing (or, as found for "Pipeline", a plain data error -- a Nakuru
    listing mislabeled into Nairobi's "Pipeline" bucket) can dominate the
    whole estimate. Recognised-but-sparse and unrecognised both end up
    "none" on purpose: neither has anything trustworthy to say.
    """
    if loc_count_tr >= 10:
        return "high"
    if loc_count_tr >= 3:
        return "low"
    return "none"


# Serving-time location normalization. The training data's location_std is
# already clean (34 canonical names, verified: no two rows differ only by
# case). The free-text location field on PredictionFormActivity/
# PropertyUploadActivity is the actual source of mismatches -- "kilimani",
# "KILIMANI" and "Westland" all used to silently fall back to the global
# mean via an exact-match-only lookup. This is deliberately a small,
# defensible alias table, not fuzzy matching -- every entry is a spelling/
# formatting variant we can justify, not a guess.
LOCATION_ALIASES = {
    "westland": "Westlands",
    "upper hill": "Upperhill",
    "lang'ata": "Langata",
    "southb": "South B",
    "southc": "South C",
    # Jiji sub-area names that are part of a known neighbourhood
    # (approved by Baraka 2026-11-08).
    "kahawa sukari": "Kahawa",
    "dagoretti corner": "Dagoretti",
    "riruta": "Dagoretti",
    "complex utawala": "Utawala",
}


def normalize_location(raw: str, known_locations: list[str]) -> str | None:
    """Map free-text input to one of `known_locations` (case- and
    whitespace-insensitive, plus LOCATION_ALIASES), or None if nothing
    matches. `known_locations` should come from a training-derived source
    (e.g. build_location_lookup() keys) so this can never recognize a
    location the model never saw.
    """
    if not raw:
        return None
    cleaned = " ".join(raw.strip().split()).lower()
    if not cleaned:
        return None

    by_lower = {loc.lower(): loc for loc in known_locations}
    if cleaned in by_lower:
        return by_lower[cleaned]

    alias_target = LOCATION_ALIASES.get(cleaned)
    if alias_target in known_locations:
        return alias_target

    return None


def resolve_location(raw: str, lookup: dict) -> tuple[str, bool]:
    """Resolve free-text user input against a build_location_lookup()
    dict. Returns (resolved_name, recognized): resolved_name is the
    canonical training location if recognized, otherwise the original
    (trimmed) input -- useful for logging even though an unrecognized
    location falls back to the global mean via lookup_location_stats.
    """
    known = [k for k in lookup if k != "__global__"]
    normalized = normalize_location(raw, known)
    if normalized is not None:
        return normalized, True
    return (raw or "").strip(), False


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
