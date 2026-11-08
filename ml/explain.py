"""Plain-language explanations of a single prediction.

Uses LightGBM's built-in tree SHAP (``pred_contrib=True``) on the booster
inside the saved pipeline -- no extra dependency. Contributions are in
log space (the model predicts log1p(rent)); they sum, with the bias, to the
model's log prediction exactly.

Raw features are folded into a few factors a user understands. A factor with
log contribution ``c`` is reported as the approximate KES effect
``P * (1 - exp(-c))``: how much lower the estimate would be if that factor
were at the dataset average. This is order-independent but does NOT add up
exactly in KES (log space), and the response says so.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

FACTOR_GROUPS: dict[str, list[str]] = {
    "Location": ["loc_mean_tr", "loc_median_tr", "loc_count_tr", "loc_mean_spatial_tr",
                 "lat", "lon", "dist_cbd_km", "dist_westlands_km", "dist_upperhill_km",
                 "dist_jkia_km", "dist_thika_rd_km", "dist_mombasa_rd_km"],
    "Size": ["sq_m"],
    "Bedrooms/Bathrooms": ["bedrooms_num", "bathrooms_num", "rooms_total", "bath_per_bed"],
    "Property type": ["is_apartment", "is_house", "is_bedsitter"],
    "Furnished": ["is_furnished"],
    "Amenities": ["has_generator", "has_borehole", "has_cctv", "has_dsq", "has_play_area", "has_garden"],
}
FEATURE_TO_GROUP = {f: g for g, fs in FACTOR_GROUPS.items() for f in fs}

MAX_FACTORS = 5
MIN_EFFECT_SHARE = 0.02      # hide factors below max(2% of the estimate, ...
MIN_EFFECT_KES = 1000.0      # ... KES 1,000)

AMENITY_LABELS = {
    "has_generator": "generator", "has_borehole": "borehole", "has_cctv": "CCTV",
    "has_dsq": "servant quarter", "has_play_area": "play area", "has_garden": "garden",
}

NOTE = (
    "Approximate. Each effect is how much lower the estimate would be if that "
    "factor were average, worked out on a log scale, so the effects do not add up "
    "exactly in KES. 'Baseline' is a typical rent with nothing known about the "
    "home, not the average of all rents. Not a valuation."
)


def group_of(feature: str) -> str:
    """Factor name for a raw feature; raises for a feature with no group so
    that a new feature can never silently go unexplained."""
    try:
        return FEATURE_TO_GROUP[feature]
    except KeyError:
        raise KeyError(f"feature {feature!r} has no explanation group") from None


def contributions(pipe, row: pd.DataFrame) -> tuple[list[str], np.ndarray, float]:
    """(raw feature names, per-feature log contributions, bias) for one row."""
    pre = pipe.named_steps["pre"]
    booster = pipe.named_steps["m"].regressor_.booster_
    names = [n.split("__", 1)[-1] for n in pre.get_feature_names_out()]
    x = pre.transform(row)
    contrib = booster.predict(x, pred_contrib=True)[0]
    return names, np.asarray(contrib[:-1], dtype=float), float(contrib[-1])


def kes_effect(point: float, c: float) -> float:
    return point * (1.0 - math.exp(-c))


def _label(group: str, ctx: dict) -> str:
    if group == "Location":
        loc = ctx.get("location")
        if not (loc and ctx.get("location_recognised")):
            return "Location (area average used)"
        if ctx.get("location_confidence") in ("low", "none"):
            return f"{loc} location (limited local data)"
        return f"{loc} location"
    if group == "Size":
        sq = ctx.get("sq_m")
        return f"Size ({sq:.0f} m²)" if sq is not None else "Size (not given, typical size used)"
    if group == "Bedrooms/Bathrooms":
        b, ba = ctx["bedrooms_num"], ctx["bathrooms_num"]
        bed = "Studio" if b == 0 else f"{b} bedroom" + ("s" if b != 1 else "")
        return f"{bed}, {ba} bathroom" + ("s" if ba != 1 else "")
    if group == "Property type":
        t = ctx.get("property_type")
        return t.capitalize() if t else "Property type (not given)"
    if group == "Furnished":
        fur = ctx.get("is_furnished")
        if fur is None:
            return "Furnishing (not given)"
        return "Furnished" if fur else "Not furnished"
    # Amenities. A missing field is not the same as "no": say so, never show
    # "none listed" as a fact when the user was never asked / gave nothing.
    given = {k: ctx.get(k) for k in AMENITY_LABELS}
    if all(v is None for v in given.values()):
        return "Amenities (not given)"
    have = [AMENITY_LABELS[k] for k, v in given.items() if v]
    return "Amenities: " + ", ".join(have) if have else "No extra amenities listed"


def build_explanation(names: list[str], contrib: np.ndarray, bias: float,
                      point: float, ctx: dict) -> dict:
    by_group: dict[str, float] = {}
    for n, c in zip(names, contrib):
        g = group_of(n)
        by_group[g] = by_group.get(g, 0.0) + float(c)
    floor = max(MIN_EFFECT_SHARE * point, MIN_EFFECT_KES)
    rows = []
    for g, c in by_group.items():
        eff = kes_effect(point, c)
        if abs(eff) >= floor:
            rows.append({"name": g, "label": _label(g, ctx),
                         "direction": "+" if eff > 0 else "-", "effect_kes": round(eff, 0)})
    rows.sort(key=lambda r: abs(r["effect_kes"]), reverse=True)
    return {
        "baseline_rent_kes": round(math.expm1(bias), 0),
        "factors": rows[:MAX_FACTORS],
        "note": NOTE,
    }
