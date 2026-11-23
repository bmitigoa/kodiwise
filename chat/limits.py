"""Usage counters. The only thing the chat service stores: counts per user per day and one global
count per day (no message text, nothing else).

* Per user: messages per day, day = Nairobi (UTC+3, no daylight saving).
* Global: Gemini REQUESTS per day, day = Pacific time, because the free-tier daily quota resets at
  Pacific midnight. One chat message can need several Gemini requests (one per tool round).
Both are taken in a Firestore transaction, so parallel requests cannot slip past a limit.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from agent.core import config

NAIROBI = timezone(timedelta(hours=3))


def nairobi_day(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(NAIROBI).date().isoformat()


def pacific_day(now: datetime | None = None) -> str:
    from zoneinfo import ZoneInfo
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()


class Counters(Protocol):
    def user_take(self, uid: str, day: str, limit: int) -> tuple[bool, int]: ...
    def user_refund(self, uid: str, day: str) -> None: ...
    def global_take(self, day: str, cap: int) -> bool: ...
    def global_refund(self, day: str) -> None: ...


class MemoryCounters:
    """Tests and local runs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.users: dict[tuple[str, str], int] = {}
        self.globals: dict[str, int] = {}

    def user_take(self, uid: str, day: str, limit: int) -> tuple[bool, int]:
        with self._lock:
            n = self.users.get((uid, day), 0)
            if n >= limit:
                return False, n
            self.users[(uid, day)] = n + 1
            return True, n + 1

    def user_refund(self, uid: str, day: str) -> None:
        with self._lock:
            self.users[(uid, day)] = max(0, self.users.get((uid, day), 0) - 1)

    def global_take(self, day: str, cap: int) -> bool:
        with self._lock:
            n = self.globals.get(day, 0)
            if n >= cap:
                return False
            self.globals[day] = n + 1
            return True

    def global_refund(self, day: str) -> None:
        with self._lock:
            self.globals[day] = max(0, self.globals.get(day, 0) - 1)


class FirestoreCounters:
    USERS = "chatUsage"
    GLOBAL = "chatGlobal"

    def __init__(self, client) -> None:
        self.db = client

    def _tx_take(self, ref, limit: int, extra: dict) -> tuple[bool, int]:
        from google.cloud import firestore

        @firestore.transactional
        def run(tx):
            snap = ref.get(transaction=tx)
            n = int((snap.to_dict() or {}).get("count", 0)) if snap.exists else 0
            if n >= limit:
                return False, n
            tx.set(ref, {"count": n + 1, **extra})
            return True, n + 1

        return run(self.db.transaction())

    def user_take(self, uid: str, day: str, limit: int) -> tuple[bool, int]:
        ref = self.db.collection(self.USERS).document(f"{uid}_{day}")
        return self._tx_take(ref, limit, {"uid": uid, "day": day,
                                          "expireAt": datetime.now(timezone.utc) + timedelta(days=config.USER_COUNTER_TTL_DAYS)})

    def user_refund(self, uid: str, day: str) -> None:
        from google.cloud import firestore
        self.db.collection(self.USERS).document(f"{uid}_{day}").update({"count": firestore.Increment(-1)})

    def global_take(self, day: str, cap: int) -> bool:
        ref = self.db.collection(self.GLOBAL).document(day)
        return self._tx_take(ref, cap, {"day": day, "expireAt": datetime.now(timezone.utc) + timedelta(days=config.USER_COUNTER_TTL_DAYS)})[0]

    def global_refund(self, day: str) -> None:
        from google.cloud import firestore
        self.db.collection(self.GLOBAL).document(day).update({"count": firestore.Increment(-1)})


class RateLimiter:
    """Sliding one-minute window, per instance. Keeps this instance under its share of the free RPM."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: deque[float] = deque()

    def allow(self) -> bool:
        if self.per_minute <= 0:
            return False
        with self._lock:
            now = self._clock()
            while self._hits and now - self._hits[0] >= 60:
                self._hits.popleft()
            if len(self._hits) >= self.per_minute:
                return False
            self._hits.append(now)
            return True
