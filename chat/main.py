"""kodiwise-chat: POST /chat. Verifies the Firebase token, applies the daily limits, runs the Gemini
tool loop and returns a short answer plus cards. Stateless: only usage counters are stored."""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Callable, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent.core import config, telemetry
from agent.core.tools import Tools
from chat import scope
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
    user_daily: int = config.CHAT_USER_DAILY
    global_daily_cap: int = 0          # Gemini requests per day PER MODEL; 0 = refuse (CHAT_GLOBAL_DAILY_CAP)
    rpm_cap: int = 0                   # requests per minute per model, per instance; 0 = refuse (CHAT_RPM_CAP)
    concurrent: int = config.CHAT_CONCURRENT
    models: tuple[str, ...] = ()       # primary first, then the fallback (CHAT_MODELS, comma separated)

    @classmethod
    def from_env(cls) -> "Settings":
        instances = max(1, config.CHAT_MAX_INSTANCES)
        models = tuple(m.strip() for m in os.environ.get("CHAT_MODELS", "").split(",") if m.strip())
        return cls(user_daily=config.CHAT_USER_DAILY,
                   global_daily_cap=config.CHAT_GLOBAL_DAILY_CAP,
                   rpm_cap=config.CHAT_RPM_CAP // instances, models=models)


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

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:      # never a stack trace to the client
        log.error("unhandled error in chat: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "The assistant hit a problem. Please try again."})

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

    def areas() -> list[str]:
        try:
            return known_locations() if known_locations else []
        except Exception:                       # the scope guard still works from its rent words
            return []

    def safely(fn: Callable[[], object], what: str) -> None:
        try:
            fn()
        except Exception as exc:                # a counter that cannot be updated must not break the reply
            log.warning("%s failed: %s", what, type(exc).__name__)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    def handle(req: ChatRequest, who: dict, sp) -> ChatResponse:
        keep = areas()
        history = clean_history([m.model_dump() for m in req.messages],
                                known_names=[who["name"]] if who.get("name") else (), keep=keep)
        if not history or history[-1]["role"] != "user":
            raise HTTPException(422, "Send a question.")
        uid, uday, gday = who["uid"], nairobi_day(), pacific_day()
        if settings.global_daily_cap <= 0 or settings.rpm_cap <= 0 or not order:
            log.error("chat limits are not configured; refusing")
            return limit("limit_global")

        # Scope guard: off-topic and non-Nairobi questions are answered here, without a Gemini request and
        # without using up one of the user's messages.
        user_texts = [p["text"] for m in history if m["role"] == "user" for p in m["parts"]]
        verdict = scope.check(user_texts, keep)
        sp.put(scope=verdict.reason)
        if not verdict.allowed:
            used = 0
            try:
                used = counters.user_used(uid, uday)
            except Exception as exc:
                log.warning("counter read failed: %s", type(exc).__name__)
            return ChatResponse(status="ok", reply=verdict.reply, remaining_today=max(0, settings.user_daily - used))

        if not slots.acquire(blocking=False):
            return limit("busy")
        try:
            try:
                ok, used = counters.user_take(uid, uday, settings.user_daily)
            except Exception as exc:            # no counter, no Gemini call (fail closed)
                log.error("counter update failed: %s", type(exc).__name__)
                return limit("busy")
            if not ok:
                return limit("limit_user")
            remaining = max(0, settings.user_daily - used)

            def refund() -> None:
                safely(lambda: counters.user_refund(uid, uday), "user refund")

            def lane(model: str) -> Lane:
                key = f"{gday}_{model}"          # each model has its own free daily quota

                def take() -> bool:
                    try:
                        return counters.global_take(key, settings.global_daily_cap)
                    except Exception as exc:
                        log.error("global counter failed: %s", type(exc).__name__)
                        raise LimitReached("busy") from None

                return Lane(model, clients[model], take_global=take, allow_rate=limiters[model].allow,
                            refund_global=lambda: safely(lambda: counters.global_refund(key), "global refund"))

            engine = ChatEngine(tools, [lane(m) for m in order])
            try:
                result = engine.run(history)
            except LimitReached as lim:
                refund()
                sp.put(requests=engine.requests, limit=lim.reason)
                return limit(lim.reason)
            except GeminiBusy:                    # every model said 429 or was overloaded
                refund()
                sp.put(requests=engine.requests, limit="busy")
                return limit("busy")
            except GeminiError as exc:
                log.warning("gemini error: %s", exc)
                refund()
                sp.put(requests=engine.requests)
                raise HTTPException(502, "The assistant could not answer right now.") from None
            sp.put(model=result.model, requests=result.requests, tool_calls=result.tool_calls,
                   fallback_used=result.fallback_used, guard_failed=result.guard_failed,
                   retries=result.retries, degraded=result.degraded)
            log.info("chat ok: model=%s fallback=%s tool_calls=%d requests=%d guard_failed=%s degraded=%s",
                     result.model, result.fallback_used, result.tool_calls, result.requests, result.guard_failed,
                     result.degraded)
            if result.degraded:                   # no usable model reply: templated answer + the guided assistant
                refund()
                return ChatResponse(status="ok", reply=result.reply, cards=result.cards,
                                    remaining_today=remaining + 1, show_assistant_button=True)
            return ChatResponse(status="ok", reply=result.reply, cards=result.cards, remaining_today=remaining)
        finally:
            slots.release()

    @app.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest, who: dict = Depends(user)) -> ChatResponse:
        with telemetry.span("chat.turn", user=telemetry.user_hash(who["uid"]), messages=len(req.messages)) as sp:
            resp = handle(req, who, sp)
            sp.put(status=resp.status, reply_chars=len(resp.reply), cards=len(resp.cards),
                   remaining=resp.remaining_today, button=resp.show_assistant_button)
            return resp

    return app


def build_default_app() -> FastAPI:        # pragma: no cover - wiring for Cloud Run
    from google.cloud import firestore

    from agent.core.client import ApiClient
    from agent.core.listings import FirestoreListingSource
    from chat.limits import FirestoreCounters

    telemetry.setup_json_logging()          # structured logs for Cloud Logging (free allowance)
    telemetry.configure_stdout()
    settings = Settings.from_env()
    # Listings are read from the Firebase project (read-only role). The usage counters, the only thing this
    # service writes, live in a separate Firestore database in the service's own project, so the account
    # never needs write access to the app's data.
    listings_db = firestore.Client(project="kodiwise-9adab")
    counters_db = firestore.Client(project=os.environ.get("CHAT_COUNTERS_PROJECT", "rent-prediction-ar"),
                                   database=os.environ.get("CHAT_COUNTERS_DATABASE", "kodiwise-counters"))
    api = ApiClient()
    tools = Tools(api, FirestoreListingSource(client_factory=lambda: listings_db))
    key = os.environ["GEMINI_API_KEY"]
    clients = {m: GeminiClient(key, m) for m in settings.models}
    return create_app(settings, FirestoreCounters(counters_db), tools, clients, known_locations=api.locations)


def __getattr__(name: str):               # `uvicorn chat.main:app` builds the real app lazily
    if name == "app":
        return build_default_app()
    raise AttributeError(name)
