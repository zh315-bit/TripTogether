import logging

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.errors import error_response
from app.db.session import DatabaseUnavailableError


logger = logging.getLogger("triptogether")


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logger.setLevel(logging.INFO)
    # Raw access URLs can contain client-supplied secrets in paths/query strings.
    logging.getLogger("uvicorn.access").disabled = True


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
