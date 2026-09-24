from contextlib import asynccontextmanager
import logging

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.api.errors import APIErrorResponse, http_error_handler, validation_error_handler
from app.api.trips import router as trips_router
from app.api.invitations import router as invitations_router
from app.api.itinerary import router as itinerary_router
from app.api.expenses import router as expenses_router
from app.api.balances import router as balances_router
from app.api.system import router as system_router
from app.core.config import get_app_settings, get_database_url, get_jwt_settings
from app.core.logging import SafeErrorMiddleware, configure_logging


logger = logging.getLogger("triptogether")


@asynccontextmanager
async def lifespan(application: FastAPI):
    configure_logging()
    if application.state.settings.environment == "production":
        try:
            get_database_url()
            get_jwt_settings()
        except ValueError:
            logger.error("Production configuration invalid")
            raise RuntimeError("Production configuration invalid") from None
    logger.info("Application startup")
    try:
        yield
    finally:
        logger.info("Application shutdown")


def create_app() -> FastAPI:
    settings = get_app_settings()
    application = FastAPI(
        title="TripTogether", version="1.0.0", lifespan=lifespan,
        description="Client API: /api/v1. Bearer JWT; decimal money strings; "
                    "uniform error envelope. Legacy paths remain compatibility aliases.",
        openapi_tags=[
            {"name": name, "description": description} for name, description in (
                ("auth", "Registration, JSON login and current user"),
                ("trips", "Owned/joined trips; owner-only metadata changes"),
                ("invitations", "Owner invitations and recipient decisions"),
                ("itinerary", "Shared items and complete daily ordering"),
                ("expenses", "Single-currency expenses with exact stored splits"),
                ("balances", "Read-only balances and suggested settlements"),
                ("system", "Liveness and readiness"),
            )
        ],
    )
    application.state.settings = settings
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_error_handler)
    versioned = APIRouter(prefix="/api/v1")
    for router in (auth_router, trips_router, invitations_router, itinerary_router,
                   expenses_router, balances_router):
        application.include_router(router, include_in_schema=False)
        versioned.include_router(router)
    # Existing routers describe legacy errors; v1 documents the new envelope.
    for route in versioned.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/"):
            for status in set(route.responses) | {500, 503}:
                if int(status) >= 400:
                    route.responses[status] = {"model": APIErrorResponse}
            route.summary = f"{route.tags[0].capitalize()}: {route.name.replace('_', ' ')}"
    application.include_router(versioned)
    application.include_router(system_router)
    application.add_middleware(SafeErrorMiddleware)
    application.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"], max_age=600,
    )
    return application


app = create_app()
