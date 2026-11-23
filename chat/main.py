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
from chat.engine import ChatEngine, Lane, LimitReached, clean_history
from chat.gemini import GeminiBusy, GeminiClient, GeminiError
from chat.limits import Counters, RateLimiter, nairobi_day, pacific_day

log = logging.getLogger("kodiwise.chat")
log.setLevel(logging.INFO)
if not log.handlers and not logging.getLogger().handlers:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

LIMIT_MESSAGES = {
    "limit_user": "You've used today's free chat messages. The guided Rent Assistant has no limit, and your chat messages reset tomorrow.",
    "limit_global": "The free chat is very busy today and has reached its daily limit. The guided Rent Assistant still works.",
    "busy": "The chat is busy right now. Please try again in a minute, or use the guided Rent Assistant.",
}


@dataclass
class Settings:
    user_daily: int = 10
    global_daily_cap: int = 0          # Gemini requests per day PER MODEL; 0 = refuse (CHAT_GLOBAL_DAILY_CAP)
    rpm_cap: int = 0                   # requests per minute per model, per instance; 0 = refuse (CHAT_RPM_CAP)
    concurrent: int = 3
    models: tuple[str, ...] = ()       # primary first, then the fallback (CHAT_MODELS, comma separated)

    @classmethod
    def from_env(cls) -> "Settings":
        instances = max(1, int(os.environ.get("CHAT_MAX_INSTANCES", "2")))
        models = tuple(m.strip() for m in os.environ.get("CHAT_MODELS", "").split(",") if m.strip())
        return cls(user_daily=int(os.environ.get("CHAT_USER_DAILY", "10")),
                   global_daily_cap=int(os.environ.get("CHAT_GLOBAL_DAILY_CAP", "0")),
                   rpm_cap=int(os.environ.get("CHAT_RPM_CAP", "0")) // instances, models=models)


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


def create_app(settings: Settings, counters: Counters, tools: Tools, clients: dict[str, GeminiClient],
               verifier: TokenVerifier = verify_firebase_token,
               known_locations: Callable[[], list[str]] | None = None) -> FastAPI:
    app = FastAPI(title="KodiWise chat", docs_url=None, redoc_url=None, openapi_url=None)
    order = [m for m in (settings.models or tuple(clients)) if m in clients]
    limiters = {m: RateLimiter(settings.rpm_cap) for m in order}
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
        if settings.global_daily_cap <= 0 or settings.rpm_cap <= 0 or not order:
            log.error("chat limits are not configured; refusing")
            return limit("limit_global")
        if not slots.acquire(blocking=False):
            return limit("busy")
        try:
            ok, used = counters.user_take(uid, uday, settings.user_daily)
            if not ok:
                return limit("limit_user")
            remaining = max(0, settings.user_daily - used)

            def lane(model: str) -> Lane:
                key = f"{gday}_{model}"          # each model has its own free daily quota
                return Lane(model, clients[model],
                            take_global=lambda: counters.global_take(key, settings.global_daily_cap),
                            allow_rate=limiters[model].allow,
                            refund_global=lambda: counters.global_refund(key))

            engine = ChatEngine(tools, [lane(m) for m in order])
            try:
                result = engine.run(history)
            except LimitReached as lim:
                counters.user_refund(uid, uday)
                return limit(lim.reason)
            except GeminiBusy:                    # every model said 429 (the engine refunded those requests)
                counters.user_refund(uid, uday)
                return limit("busy")
            except GeminiError as exc:
                log.warning("gemini error: %s", exc)
                counters.user_refund(uid, uday)
                raise HTTPException(502, "The assistant could not answer right now.") from None
            log.info("chat ok: model=%s fallback=%s tool_calls=%d guard_failed=%s", result.model,
                     result.fallback_used, result.tool_calls, result.guard_failed)
            if result.guard_failed:               # no model left to ask: friendly message, not a user message used
                counters.user_refund(uid, uday)
                return limit("busy", remaining + 1)
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
    key = os.environ["GEMINI_API_KEY"]
    clients = {m: GeminiClient(key, m) for m in settings.models}
    return create_app(settings, FirestoreCounters(db), tools, clients, known_locations=api.locations)


def __getattr__(name: str):               # `uvicorn chat.main:app` builds the real app lazily
    if name == "app":
        return build_default_app()
    raise AttributeError(name)
