"""Read-only reference data the agent can read instead of spending tool calls on facts.

    kodiwise://locations         the covered areas with confidence tier and listing count
    kodiwise://model-card        served model version, metrics and known limitations
    kodiwise://area/{name}       centre point, tier, count and nearby areas for one area

Nothing here is computed by a model. The version comes from the live kodiwise-api; counts and metrics
come from the matching version folder under ml/models/ when this machine has it (the MCP server runs
from a checkout), otherwise those fields are left out and `source` says "api-only". Every payload
carries the model version so an answer can cite it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from agent.core import config
from agent.core.errors import KodiWiseError
from agent.core.injection import echo
from agent.core.tools import CENTROIDS_CSV, haversine_km, load_centroids
from agent.core.validate import location_text, suggest

MODELS_DIR = Path(__file__).resolve().parents[2] / "ml" / "models"
MAX_NEARBY = 5

KNOWN_LIMITATIONS = [
    "Estimates are based on advertised (asking) rents from listings, not rents that tenants finally agree. "
    "Agreed rents are often lower after negotiation.",
    "Confidence depends on how many training listings an area has: \"high\" at "
    f"{config.CONFIDENCE_HIGH_MIN_LISTINGS} or more, \"low\" at {config.CONFIDENCE_LOW_MIN_LISTINGS}-"
    f"{config.CONFIDENCE_HIGH_MIN_LISTINGS - 1}, \"none\" below {config.CONFIDENCE_LOW_MIN_LISTINGS} "
    "(the estimate then leans on the Nairobi average). Thin areas change a lot when new listings arrive.",
    "Furnishing has a large effect in the model. Furnished homes are a small share of the training data and "
    "much more expensive, so the model cannot fully separate furnishing from other features; treat that "
    "factor, and furnished estimates, with extra care.",
    "The range is statistical (the 10th to 90th percentile of past prediction error), not a guarantee. "
    "Estimates are not valuations, and 'why' effects in KES are approximate.",
    "Distances between areas are straight-line between neighbourhood centre points, not travel time.",
]


def tier(count: float | None) -> str | None:
    """Same rule as ml.features.location_confidence (a test keeps them equal)."""
    if count is None:
        return None
    if count >= config.CONFIDENCE_HIGH_MIN_LISTINGS:
        return "high"
    return "low" if count >= config.CONFIDENCE_LOW_MIN_LISTINGS else "none"


def _load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class Resources:
    def __init__(self, api: Any, models_dir: Path = MODELS_DIR, centroids_path: Path = CENTROIDS_CSV,
                 centroids: dict[str, tuple[float, float]] | None = None) -> None:
        self.api, self.models_dir, self._cpath, self._cents = api, models_dir, centroids_path, centroids

    # -- sources ---------------------------------------------------------------------------
    def _version(self) -> dict:
        return self.api.model_version()

    def _folder(self, version: str | None) -> Path | None:
        if not version:
            return None
        p = self.models_dir / version
        return p if p.is_dir() else None

    def _counts(self, version: str | None) -> dict[str, int] | None:
        folder = self._folder(version)
        data = _load_json(folder / "location_lookup.json") if folder else None
        if not isinstance(data, dict):
            return None
        return {k: int(v["loc_count_tr"]) for k, v in data.items()
                if isinstance(v, dict) and "loc_count_tr" in v and not k.startswith("__")}

    def _centroids(self) -> dict[str, tuple[float, float]] | None:
        if self._cents is None:
            try:
                self._cents = load_centroids(self._cpath)
            except OSError:
                return None
        return self._cents

    # -- resources -------------------------------------------------------------------------
    def locations(self) -> dict:
        names = self.api.locations()
        version = (self._version() or {}).get("version")
        counts = self._counts(version)
        areas = []
        for n in names:
            c = counts.get(n) if counts else None
            areas.append({"area": n, "confidence": tier(c), "listing_count": c})
        return {"model_version": version, "count": len(areas), "areas": areas,
                "source": "local model files" if counts else "api-only (counts not available here)",
                "listing_count_means": "training listings behind the area's statistics (asking rents)"}

    def model_card(self) -> dict:
        v = self._version() or {}
        version = v.get("version")
        folder = self._folder(version)
        m = _load_json(folder / "metrics.json") if folder else None
        card: dict[str, Any] = {"model_version": version, "feature_set": v.get("feature_set"),
                                "trained_on": v.get("trained_on"), "training_rows": v.get("n_train"),
                                "test_rows": v.get("n_test"),
                                "test_r2": v.get("test_r2"), "test_mape_percent": v.get("test_mape")}
        if isinstance(m, dict):
            cv = m.get("cv_lgbm_log_target") or {}
            card.update({
                "data_date_range": m.get("data_date_range"),
                "test_metrics": m.get("test_metrics"),
                "cv_mean": {k: round(x.get("mean"), 3) for k, x in cv.items() if isinstance(x, dict) and "mean" in x},
                "range_method": (m.get("prediction_interval") or {}).get("method"),
                "median_range_width_kes": (m.get("prediction_interval") or {}).get("median_test_range_width_kes"),
            })
            card["source"] = "local model files"
        else:
            card["source"] = "api-only"
        card["confidence_tiers"] = {"high": f">= {config.CONFIDENCE_HIGH_MIN_LISTINGS} listings",
                                    "low": f"{config.CONFIDENCE_LOW_MIN_LISTINGS}-{config.CONFIDENCE_HIGH_MIN_LISTINGS - 1} listings",
                                    "none": f"< {config.CONFIDENCE_LOW_MIN_LISTINGS} listings"}
        card["known_limitations"] = KNOWN_LIMITATIONS
        card["usage_rules"] = ("Always give the range and the confidence, say it is an estimate, and cite "
                               "model_version and the area.")
        return card

    def area(self, name: str) -> dict:
        place = location_text(name)
        known = self.api.locations()
        by_lower = {k.casefold(): k for k in known}
        key = by_lower.get(place.casefold())
        if key is None:
            tips = suggest(place, known)
            hint = f" Did you mean: {', '.join(tips)}?" if tips else " Read kodiwise://locations for the covered areas."
            raise KodiWiseError(f"I don't recognise '{echo(place)}' as a covered area.{hint}")
        version = (self._version() or {}).get("version")
        counts = self._counts(version)
        c = counts.get(key) if counts else None
        out: dict[str, Any] = {"area": key, "model_version": version, "confidence": tier(c), "listing_count": c}
        cents = self._centroids()
        if cents and key in cents:
            lat, lon = cents[key]
            out["centre"] = {"lat": round(lat, 5), "lon": round(lon, 5)}
            near = sorted(((haversine_km((lat, lon), p), n) for n, p in cents.items() if n != key and n in known))
            out["nearby"] = [{"area": n, "km": round(d, 1)} for d, n in near[:MAX_NEARBY]]
            out["distance_note"] = "straight-line between neighbourhood centre points, not travel time"
        return out


def as_json(fn: Callable[[], dict]) -> str:
    """Run a resource builder; errors become a small JSON error, never an exception."""
    try:
        return json.dumps(fn(), ensure_ascii=False, indent=1)
    except KodiWiseError as exc:
        return json.dumps({"error": str(exc)})
    except Exception:       # network, files: no details
        return json.dumps({"error": "That reference data is not available right now."})
