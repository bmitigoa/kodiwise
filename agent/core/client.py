"""Thin HTTPS client for the live kodiwise-api. One source of truth: the model
is never loaded here."""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable

import httpx

from agent.core.errors import KodiWiseError

DEFAULT_API_URL = "https://kodiwise-api-798766993143.africa-south1.run.app"
USER_AGENT = "KodiWise-MCP/0.1 (+https://github.com/bmitigoa/kodiwise)"


class ApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 20.0,
        retries: int = 2,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = (base_url or os.environ.get("KODIWISE_API_URL") or DEFAULT_API_URL).rstrip("/")
        self.retries = retries
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=self.base_url, timeout=timeout, transport=transport,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        self._lock = threading.Lock()
        self._locations: list[str] | None = None
        self._predictions: dict[str, dict] = {}
        self.predict_calls = 0   # real HTTP predictions made (for tests and limits)

    # -- low level ---------------------------------------------------------
    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        last = "the KodiWise service did not answer"
        for attempt in range(self.retries + 1):
            try:
                r = self._http.request(method, path, **kw)
            except (httpx.TimeoutException, httpx.TransportError):
                last = "the KodiWise service did not answer in time"
            else:
                if r.status_code < 500 and r.status_code != 429:
                    return r
                last = f"the KodiWise service is busy or restarting (HTTP {r.status_code})"
            if attempt < self.retries:
                self._sleep(1.0 * (2 ** attempt))
        raise KodiWiseError(f"Sorry, {last}. Please try again in a minute.")

    # -- endpoints ---------------------------------------------------------
    def locations(self) -> list[str]:
        with self._lock:
            if self._locations is not None:
                return list(self._locations)
        r = self._request("GET", "/locations")
        if r.status_code != 200:
            raise KodiWiseError(f"Could not load the neighbourhood list (HTTP {r.status_code}).")
        names = r.json().get("locations", [])
        with self._lock:
            self._locations = names
        return list(names)

    def predict(self, payload: dict) -> dict:
        key = json.dumps(payload, sort_keys=True)
        with self._lock:
            hit = self._predictions.get(key)
        if hit is not None:
            return hit
        r = self._request("POST", "/predict", json=payload)
        if r.status_code == 422:
            raise KodiWiseError("The KodiWise service rejected those inputs. Check the values and try again.")
        if r.status_code != 200:
            raise KodiWiseError(f"The KodiWise service returned an error (HTTP {r.status_code}).")
        data = r.json()
        with self._lock:
            self.predict_calls += 1
            self._predictions[key] = data
            if len(self._predictions) > 512:
                self._predictions.pop(next(iter(self._predictions)))
        return data
