"""Free, local observability: OpenTelemetry spans for every tool call and chat turn.

* Off until configured, so library code can always call `span()` / `event()`; unconfigured calls do nothing.
* MCP server (local): `configure_file(path)` appends one JSON line per span to logs/traces.jsonl.
* Chat service (Cloud Run): `configure_stdout()` prints one JSON line per span to stdout, which Cloud Logging
  reads as structured logs (within its free allowance). `setup_json_logging()` does the same for log records.
* OTLP export is available behind KW_OTLP_ENDPOINT (off by default). It needs the optional
  `opentelemetry-exporter-otlp-proto-http` package; without it a warning is logged and nothing else changes.

Privacy: spans never carry message text, phone numbers, emails or tokens. Attributes go through
`safe_attrs`: sensitive keys are dropped, strings are scrubbed and capped, tool inputs are reduced to numbers,
booleans and lengths (`tool_inputs`).
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

try:                                           # the API and SDK are free, local, open source
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
    from opentelemetry.trace import Status, StatusCode
    HAVE_OTEL = True
except ImportError:                            # pragma: no cover - the code still works, without spans
    HAVE_OTEL = False
    SpanExporter = object                      # type: ignore[assignment, misc]

log = logging.getLogger("kodiwise.telemetry")

MAX_ATTR_CHARS = 120
MAX_TRACE_FILE_BYTES = 5 * 1024 * 1024
DEFAULT_TRACE_FILE = Path(__file__).resolve().parents[2] / "logs" / "traces.jsonl"

_DROP_KEYS = {"text", "message", "messages", "prompt", "reply", "token", "authorization", "api_key", "apikey",
              "key", "email", "phone", "name", "password", "secret", "body", "content", "title", "description"}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
_JWT = re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{4,}\b")
_LONG_SECRET = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{6,}\d(?!\w)")


def scrub(text: str) -> str:
    """Remove emails, links, phone-like numbers and token-like strings from a string."""
    for pat, repl in ((_JWT, "[token]"), (_EMAIL, "[email]"), (_URL, "[link]"), (_LONG_SECRET, "[secret]"),
                      (_PHONE, "[number]")):
        text = pat.sub(repl, text)
    return text


def safe_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in attrs.items():
        if k.lower() in _DROP_KEYS or v is None:
            continue
        if isinstance(v, bool) or isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str):
            out[k] = scrub(v)[:MAX_ATTR_CHARS]
        elif isinstance(v, (list, tuple, set)):
            out[k + "_count"] = len(v)
        else:
            out[k] = scrub(str(v))[:MAX_ATTR_CHARS]
    return out


def tool_inputs(args: dict[str, Any] | None) -> dict[str, Any]:
    """Tool arguments reduced to what is safe to record: numbers and booleans as they are, strings as
    their length only, lists as their size. Area names are typed by users, so they are not recorded."""
    out: dict[str, Any] = {}
    for k, v in (args or {}).items():
        if isinstance(v, bool) or isinstance(v, (int, float)):
            out[f"in.{k}"] = v
        elif isinstance(v, str):
            out[f"in.{k}_len"] = len(v)
        elif isinstance(v, (list, tuple, set)):
            out[f"in.{k}_count"] = len(v)
        elif v is not None:
            out[f"in.{k}_type"] = type(v).__name__
    return out


def user_hash(uid: str) -> str:
    """A short stable label for per-user abuse spotting, not the uid itself."""
    return hashlib.sha256(uid.encode()).hexdigest()[:8]


# -- exporters ---------------------------------------------------------------------------------
class JsonLineExporter(SpanExporter):         # type: ignore[misc, valid-type]
    def __init__(self, write: Callable[[str], None], cloud: bool = False) -> None:
        self._write, self._cloud = write, cloud

    def export(self, spans):
        for s in spans:
            attrs = safe_attrs(dict(s.attributes or {}))
            ok = s.status.status_code != StatusCode.ERROR
            rec: dict[str, Any] = {
                "ts": datetime.fromtimestamp(s.start_time / 1e9, timezone.utc).isoformat(timespec="milliseconds"),
                "span": s.name, "duration_ms": round((s.end_time - s.start_time) / 1e6, 1),
                "status": "ok" if ok else "error", "trace_id": f"{s.context.trace_id:032x}",
                "span_id": f"{s.context.span_id:016x}", **attrs}
            if self._cloud:                     # Cloud Logging reads these two fields
                rec = {"severity": "INFO" if ok else "WARNING", "message": f"span {s.name}", **rec}
            try:
                self._write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
            except Exception:                   # observability must never break a request
                pass
        return SpanExportResult.SUCCESS if HAVE_OTEL else None

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class _FileWriter:
    """Appends lines to one file; moves it aside at 5 MB. The only file this package ever writes."""

    def __init__(self, path: Path) -> None:
        self.path, self._lock = Path(path), threading.Lock()

    def __call__(self, line: str) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > MAX_TRACE_FILE_BYTES:
                os.replace(self.path, self.path.with_suffix(self.path.suffix + ".1"))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


def _stdout_writer(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


# -- provider ----------------------------------------------------------------------------------
class _State:
    provider: Any = None
    tracer: Any = None


_S = _State()


def _install(exporter: Any) -> None:
    if not HAVE_OTEL:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": os.environ.get("KW_SERVICE_NAME", "kodiwise")}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    endpoint = os.environ.get("KW_OTLP_ENDPOINT", "").strip()
    if endpoint:                                # optional, off by default; no paid tracing is configured here
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        except ImportError:
            log.warning("KW_OTLP_ENDPOINT is set but opentelemetry-exporter-otlp-proto-http is not installed")
    _S.provider, _S.tracer = provider, provider.get_tracer("kodiwise")


def configure_file(path: Path | str | None = None) -> Path:
    """MCP server: local JSON-lines traces. Returns the file used."""
    target = Path(path or os.environ.get("KODIWISE_TRACE_FILE") or DEFAULT_TRACE_FILE)
    _install(JsonLineExporter(_FileWriter(target)))
    return target


def configure_stdout() -> None:
    """Chat service: one structured JSON line per span, picked up by Cloud Logging."""
    _install(JsonLineExporter(_stdout_writer, cloud=True))


def configure_exporter(exporter: Any) -> None:
    """Tests: any SpanExporter (for example an in-memory one)."""
    _install(exporter)


def reset() -> None:
    if _S.provider is not None:
        with contextlib.suppress(Exception):
            _S.provider.shutdown()
    _S.provider = _S.tracer = None


def enabled() -> bool:
    return _S.tracer is not None


class _NoSpan:
    def put(self, **attrs: Any) -> None: ...


class SpanHandle:
    def __init__(self, span: Any) -> None:
        self._span = span

    def put(self, **attrs: Any) -> None:
        for k, v in safe_attrs(attrs).items():
            self._span.set_attribute(k, v)


@contextlib.contextmanager
def span(name: str, **attrs: Any) -> Iterator[SpanHandle | _NoSpan]:
    """Time a block. Attributes are redacted. An exception marks the span as an error (type name only)."""
    if _S.tracer is None:
        yield _NoSpan()
        return
    with _S.tracer.start_as_current_span(name) as sp:
        for k, v in safe_attrs(attrs).items():
            sp.set_attribute(k, v)
        try:
            yield SpanHandle(sp)
        except Exception as exc:
            sp.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            sp.set_attribute("error_type", type(exc).__name__)
            raise


def mark_error(handle: Any, error_type: str) -> None:
    """Mark the current span as failed without an exception (a tool returned a friendly error)."""
    sp = getattr(handle, "_span", None)
    if sp is not None:
        sp.set_status(Status(StatusCode.ERROR, error_type))
        sp.set_attribute("error_type", error_type)


def event(name: str, **attrs: Any) -> None:
    """A point-in-time record (for example an injection attempt). Same redaction as spans."""
    if _S.tracer is None:
        return
    with span(f"event.{name}", **attrs):
        pass


def traced_tool(name: str, args: dict[str, Any] | None, fn: Callable[[], Any], surface: str) -> Any:
    """Run one tool call inside a span: tool name, redacted inputs, output size, status, duration."""
    t0 = time.perf_counter()
    with span("tool.call", tool=name, surface=surface, **tool_inputs(args)) as sp:
        result = fn()
        failed = isinstance(result, dict) and "error" in result
        try:
            size = len(json.dumps(result, default=str))
        except (TypeError, ValueError):
            size = -1
        sp.put(output_chars=size, result="error" if failed else "ok", elapsed_ms=round((time.perf_counter() - t0) * 1000, 1))
        if failed:
            mark_error(sp, "tool_error")
        return result


# -- structured logs for Cloud Run -----------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    LEVELS = {"WARNING": "WARNING", "ERROR": "ERROR", "CRITICAL": "CRITICAL", "INFO": "INFO", "DEBUG": "DEBUG"}

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"severity": self.LEVELS.get(record.levelname, "DEFAULT"), "logger": record.name,
                           "message": scrub(record.getMessage())[:500]}, ensure_ascii=False, separators=(",", ":"))


def setup_json_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root.addHandler(h)
    root.setLevel(level)
