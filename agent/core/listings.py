"""Read-only access to approved listings.

Security rules do not apply to server-library access with user credentials
(IAM governs it), so the guarantees are enforced here in code:
  * the query is status == "approved" and the status is re-checked per row;
  * only SAFE_FIELDS are requested (field projection) and only a fixed set of
    output fields is ever copied, so owner ids, emails, admin notes and image
    URLs cannot reach a tool result;
  * titles are cleaned (agent.core.safe_text) and descriptions are never read.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Protocol

from agent.core.safe_text import clean_title

PROJECT_ID = "kodiwise-9adab"
COLLECTION = "properties"
FETCH_LIMIT = 200

# Fields requested from Firestore. "status" is only used to re-check approval.
SAFE_FIELDS = ["title", "locationName", "quotedRent", "bedrooms", "bathrooms", "sq_m",
               "predictedLow", "predictedHigh", "locationConfidence", "status"]


class ListingSource(Protocol):
    def fetch(self) -> list[dict]: ...


class FirestoreListingSource:
    """Approved listings from Firestore using Application Default Credentials.

    The quota project is set on this client's credential only (not on the
    global ADC) so other tools that share the login keep their own quota project.
    """

    def __init__(self, project: str = PROJECT_ID, quota_project: str = PROJECT_ID,
                 client_factory: Callable[[], Any] | None = None, limit: int = FETCH_LIMIT) -> None:
        self.project = project
        self.quota_project = quota_project
        self.limit = limit
        self._factory = client_factory or self._default_client
        self._client: Any = None

    @staticmethod
    def adc_file() -> Path | None:
        """The user's Application Default Credentials file, if there is one."""
        env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if env and Path(env).is_file():
            return Path(env)
        base = os.environ.get("APPDATA")
        folder = Path(base) / "gcloud" if base else Path.home() / ".config" / "gcloud"
        p = folder / "application_default_credentials.json"
        return p if p.is_file() else None

    def _default_client(self) -> Any:
        import google.auth
        from google.cloud import firestore
        scopes = ["https://www.googleapis.com/auth/datastore"]
        path = self.adc_file()
        if path is not None:
            # Load the file directly. google.auth.default() would run a `gcloud`
            # subprocess to look up a project, which hangs inside a stdio MCP
            # server. The quota project goes on this credential only.
            # Scopes are applied only where the credential supports them: a
            # user's ADC refresh token keeps the scope it was granted, and asking
            # for a narrower one makes the token refresh fail (and retry forever).
            creds, _ = google.auth.load_credentials_from_file(
                str(path), quota_project_id=self.quota_project)
            creds = google.auth.credentials.with_scopes_if_required(creds, scopes)
        else:   # e.g. Cloud Run: the metadata server supplies the credentials
            creds, _ = google.auth.default(scopes=scopes, quota_project_id=self.quota_project)
        return firestore.Client(project=self.project, credentials=creds)

    def fetch(self) -> list[dict]:
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter
        if self._client is None:
            self._client = self._factory()
        q = (self._client.collection(COLLECTION)
             .where(filter=FieldFilter("status", "==", "approved"))
             .order_by("createdAt", direction=firestore.Query.DESCENDING)
             .limit(self.limit)
             .select(SAFE_FIELDS))
        return [d.to_dict() or {} for d in q.stream()]


class StaticListingSource:
    """Fixtures for tests (the properties collection can be empty)."""

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs

    def fetch(self) -> list[dict]:
        return list(self.docs)


# -- the app's badge rule (RentRange.position in the Android app) -------------------

def badge(quoted: float, low: float | None, high: float | None, confidence: str | None) -> str | None:
    if low is None or high is None:
        return None
    if low <= 0 or high < low or quoted <= 0:
        return None
    if confidence == "none":
        return None
    if quoted > high:
        return "above_estimated_range"
    if quoted < low:
        return "below_estimated_range"
    return "within_estimated_range"


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def to_safe_listing(doc: dict) -> dict | None:
    """Fixed-shape, safe view of one document, or None if it must not be shown."""
    if doc.get("status") != "approved":
        return None
    rent = _num(doc.get("quotedRent"))
    if rent is None or rent <= 0:
        return None
    low, high = _num(doc.get("predictedLow")), _num(doc.get("predictedHigh"))
    conf = doc.get("locationConfidence") if doc.get("locationConfidence") in ("high", "low", "none") else None
    size = _num(doc.get("sq_m"))
    return {
        "title": clean_title(doc.get("title")),
        "area": clean_title(doc.get("locationName")),
        "rent_kes": int(round(rent)),
        "bedrooms": int(doc["bedrooms"]) if isinstance(doc.get("bedrooms"), (int, float)) else None,
        "bathrooms": int(doc["bathrooms"]) if isinstance(doc.get("bathrooms"), (int, float)) else None,
        "size_m2": int(round(size)) if size and size > 0 else None,
        "badge": badge(rent, low, high, conf),
        "estimated_range_low_kes": int(round(low)) if low is not None else None,
        "estimated_range_high_kes": int(round(high)) if high is not None else None,
        "location_confidence": conf,
    }


def search(source: ListingSource, location: str | None, max_rent: float | None,
           bedrooms: int | None, limit: int = 10) -> tuple[list[dict], int]:
    """(listings, total_matches). Cheapest first."""
    out = []
    for doc in source.fetch():
        item = to_safe_listing(doc)
        if item is None:
            continue
        if location and item["area"].casefold() != location.casefold():
            continue
        if max_rent is not None and item["rent_kes"] > max_rent:
            continue
        if bedrooms is not None and item["bedrooms"] != bedrooms:
            continue
        out.append(item)
    out.sort(key=lambda i: i["rent_kes"])
    return out[:limit], len(out)
