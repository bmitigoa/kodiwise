"""kodiwise-chat: POST /chat. Verifies the Firebase token, applies the daily limits, runs the Gemini
tool loop and returns a short answer plus cards. Stateless: only usage counters are stored."""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Callable, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from agent.core.tools import Tools
from chat.auth import AuthError, TokenVerifier, verify_firebase_token
from chat.engine import ChatEngine, LimitReached, clean_history
from chat.gemini import GeminiBusy, GeminiClient, GeminiError
from chat.limits import Counters, RateLimiter, nairobi_day, pacific_day

log = logging.getLogger("kodiwise.chat")

LIMIT_MESSAGES = {
    "limit_user": "You've used today's free chat messages. The guided Rent Assistant has no limit, and your chat messages reset tomorrow.",
    "limit_global": "The free chat is very busy today and has reached its daily limit. The guided Rent Assistant still works.",
    "busy": "The chat is busy right now. Please try again in a minute, or use the guided Rent Assistant.",
}


@dataclass
class Settings:
    user_daily: int = 15
    global_daily_cap: int = 0          # Gemini requests per day; 0 = refuse (set CHAT_GLOBAL_DAILY_CAP)
    rpm_cap: int = 0                   # per instance; 0 = refuse (set CHAT_RPM_CAP)
    concurrent: int = 3

    @classmethod
    def from_env(cls) -> "Settings":
        instances = max(1, int(os.environ.get("CHAT_MAX_INSTANCES", "2")))
        return cls(user_daily=int(os.environ.get("CHAT_USER_DAILY", "15")),
                   global_daily_cap=int(os.environ.get("CHAT_GLOBAL_DAILY_CAP", "0")),
                   rpm_cap=int(os.environ.get("CHAT_RPM_CAP", "0")) // instances)


class Msg(BaseModel):
    role: Literal["user", "model", "assistant"]
    text: str = Field(..., max_length=2000)


class ChatRequest(BaseModel):
    messages: list[Msg] = Field(..., min_length=1, max_length=20)


class ChatResponse(BaseModel):
    status: Literal["ok", "limit_user", "limit_global", "busy"]
    reply: str
    cards: list[dict] = []
    remaining_today: int = 0
    show_assistant_button: bool = False


def create_app(settings: Settings, counters: Counters, tools: Tools, gemini: GeminiClient,
               verifier: TokenVerifier = verify_firebase_token,
               known_locations: Callable[[], list[str]] | None = None) -> FastAPI:
    app = FastAPI(title="KodiWise chat", docs_url=None, redoc_url=None, openapi_url=None)
    limiter = RateLimiter(settings.rpm_cap)
    slots = threading.BoundedSemaphore(settings.concurrent)

    def user(authorization: str | None = Header(None)) -> dict:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Sign in to use the chat.")
        try:
            return verifier(authorization[7:].strip())
        except AuthError:
            raise HTTPException(401, "Sign in again to use the chat.") from None

    def limit(status: str, remaining: int = 0) -> ChatResponse:
        return ChatResponse(status=status, reply=LIMIT_MESSAGES[status], remaining_today=remaining,
                            show_assistant_button=True)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest, who: dict = Depends(user)) -> ChatResponse:
        keep = known_locations() if known_locations else []
        history = clean_history([m.model_dump() for m in req.messages],
                                known_names=[who["name"]] if who.get("name") else (), keep=keep)
        if not history or history[-1]["role"] != "user":
            raise HTTPException(422, "Send a question.")
        uid, uday, gday = who["uid"], nairobi_day(), pacific_day()
        if settings.global_daily_cap <= 0 or settings.rpm_cap <= 0:
            log.error("chat limits are not configured; refusing")
            return limit("limit_global")
        if not slots.acquire(blocking=False):
            return limit("busy")
        try:
            ok, used = counters.user_take(uid, uday, settings.user_daily)
            if not ok:
                return limit("limit_user")
            remaining = max(0, settings.user_daily - used)

            def take_global() -> bool:
                return counters.global_take(gday, settings.global_daily_cap)

            engine = ChatEngine(tools, gemini, take_global, limiter.allow)
            try:
                result = engine.run(history)
            except LimitReached as lim:
                counters.user_refund(uid, uday)
                return limit(lim.reason)
            except GeminiBusy:
                counters.user_refund(uid, uday)
                counters.global_refund(gday)      # Google did not count a 429
                return limit("busy")
            except GeminiError as exc:
                log.warning("gemini error: %s", exc)
                counters.user_refund(uid, uday)
                raise HTTPException(502, "The assistant could not answer right now.") from None
            return ChatResponse(status="ok", reply=result.reply, cards=result.cards, remaining_today=remaining)
        finally:
            slots.release()

    return app


def build_default_app() -> FastAPI:        # pragma: no cover - wiring for Cloud Run
    from google.cloud import firestore

    from agent.core.client import ApiClient
    from agent.core.listings import FirestoreListingSource
    from chat.limits import FirestoreCounters

    settings = Settings.from_env()
    db = firestore.Client(project="kodiwise-9adab")
    api = ApiClient()
    tools = Tools(api, FirestoreListingSource(client_factory=lambda: db))
    gemini = GeminiClient(os.environ["GEMINI_API_KEY"], os.environ["GEMINI_MODEL"])
    return create_app(settings, FirestoreCounters(db), tools, gemini, known_locations=api.locations)


def __getattr__(name: str):               # `uvicorn chat.main:app` builds the real app lazily
    if name == "app":
        return build_default_app()
    raise AttributeError(name)
