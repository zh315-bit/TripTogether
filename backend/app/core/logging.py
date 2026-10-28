from contextvars import ContextVar
from typing import Optional
import json
import logging
import re
import time
from uuid import uuid4

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response
from app.core.config import _get_setting
from app.db.session import DatabaseUnavailableError


logger = logging.getLogger("triptogether")
access_logger = logging.getLogger("triptogether.access")

# Set by RequestLogMiddleware for the life of one request; every log line
# written while handling it carries the same id, and so does the response.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SLOW_REQUEST_MS = 1000.0
# Liveness probes arrive every few seconds and would drown the access log.
UNLOGGED_PATHS = frozenset({"/health"})


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: what log aggregators index without a parser."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, separators=(",", ":"))


def log_format(environment: Optional[str] = None) -> str:
    environment = environment or _get_setting("APP_ENV", "development")
    value = (_get_setting("LOG_FORMAT", "json" if environment == "production" else "text") or "text")
    return value.strip().lower()


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for handler in root.handlers:
        handler.setFormatter(JsonFormatter() if log_format() == "json" else logging.Formatter(
            "%(levelname)s %(name)s [%(request_id)s] %(message)s"))
        if not any(isinstance(f, RequestIdFilter) for f in handler.filters):
            handler.addFilter(RequestIdFilter())
    logger.setLevel(logging.INFO)
    # Raw access URLs can contain client-supplied secrets in paths/query strings.
    logging.getLogger("uvicorn.access").disabled = True
    # httpx logs full request URLs at INFO; geocoding URLs carry user search text.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


class RequestLogMiddleware:
    """Give every request an id, echo it as X-Request-ID, and log one access line.

    The line names the route template (`/api/v1/trips/{trip_id}`), never the
    query string, so search text and tokens stay out of the logs. Requests
    slower than SLOW_REQUEST_MS are logged as warnings.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = Request(scope).headers.get("x-request-id", "")
        request_id = incoming if REQUEST_ID.match(incoming) else uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            path = scope["path"]
            if path not in UNLOGGED_PATHS:
                route = scope.get("route")
                fields = {
                    "event": "request", "method": scope["method"],
                    "path": getattr(route, "path", None) or path,
                    "status": status, "duration_ms": duration_ms,
                }
                level = logging.WARNING if duration_ms >= SLOW_REQUEST_MS else logging.INFO
                access_logger.log(level, "%s %s -> %s in %sms", fields["method"], fields["path"],
                                  status, duration_ms, extra={"fields": fields})
            request_id_var.reset(token)


class SafeErrorMiddleware:
    """Contain failures before the ASGI server can log credential-bearing tracebacks."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def track_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track_send)
        except Exception as error:
            unavailable = isinstance(error, DatabaseUnavailableError)
            logger.error("Database session unavailable" if unavailable else "Unexpected server error")
            if not started:
                response = error_response(
                    Request(scope), 503 if unavailable else 500,
                    "DATABASE_UNAVAILABLE" if unavailable else "INTERNAL_ERROR",
                    "Database temporarily unavailable" if unavailable else "Internal server error",
                )
                await response(scope, receive, send)
