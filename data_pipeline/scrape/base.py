"""Polite HTTP fetcher shared by all source scrapers.

Rules (CLAUDE.md rule 7): identify ourselves, >= 3 s between requests,
retry with backoff on transient errors, STOP on 403/429, honour robots.txt.
Raw responses are saved as gzipped snapshots so parsing can be re-run
without re-fetching. Snapshots live under data/raw/ (gitignored) and are
never published.
"""
from __future__ import annotations

import gzip
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import requests

USER_AGENT = "KodiWise/0.1 (+https://github.com/bmitigoa/kodiwise)"
MIN_DELAY_S = 3.0
SNAPSHOT_ROOT = Path("data/raw/snapshots")


class StopScraping(RuntimeError):
    """Raised on 403/429 or a robots.txt disallow: the run must end."""


class Fetcher:
    def __init__(self, source: str, delay_s: float = 3.5, max_retries: int = 3,
                 timeout_s: float = 30.0, snapshot_root: Path = SNAPSHOT_ROOT) -> None:
        if delay_s < MIN_DELAY_S:
            raise ValueError(f"delay_s must be >= {MIN_DELAY_S}")
        self.source = source
        self.delay_s = delay_s
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self.snapshot_root = snapshot_root
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last_request = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.n_requests = 0

    # -- robots ---------------------------------------------------------
    def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        rp = self._robots.get(base)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            resp = self.session.get(base + "/robots.txt", timeout=self.timeout_s)
            rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
            self._robots[base] = rp
            self._last_request = time.monotonic()
        return rp.can_fetch(USER_AGENT, url)

    def _wait(self) -> None:
        gap = time.monotonic() - self._last_request
        if gap < self.delay_s:
            time.sleep(self.delay_s - gap)

    # -- fetch ----------------------------------------------------------
    def get(self, url: str) -> tuple[int, str]:
        """Return (status, text). 404/410 are returned, not raised."""
        if not self._allowed(url):
            raise StopScraping(f"robots.txt disallows {url}")
        for attempt in range(self.max_retries + 1):
            self._wait()
            self._last_request = time.monotonic()
            self.n_requests += 1
            try:
                r = self.session.get(url, timeout=self.timeout_s)
            except requests.RequestException:
                if attempt == self.max_retries:
                    return 0, ""
                time.sleep(2 ** attempt * 5)
                continue
            if r.status_code in (403, 429):
                raise StopScraping(f"HTTP {r.status_code} from {url}")
            if r.status_code >= 500:
                if attempt == self.max_retries:
                    return r.status_code, ""
                time.sleep(2 ** attempt * 5)
                continue
            return r.status_code, r.text
        return 0, ""

    # -- snapshots ------------------------------------------------------
    def snapshot_path(self, day: str, key: str) -> Path:
        return self.snapshot_root / self.source / day / f"{key}.html.gz"

    def save_snapshot(self, day: str, key: str, text: str) -> Path:
        path = self.snapshot_path(day, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(text.encode("utf8")))
        return path


def read_snapshot(path: Path) -> str:
    return gzip.decompress(path.read_bytes()).decode("utf8")
