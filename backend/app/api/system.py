import logging
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.errors import APIError, APIErrorResponse
from app.core.config import get_jwt_settings
from app.db.check import check_connection, check_schema
from app.db.session import get_db


logger = logging.getLogger("triptogether")
router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]


@router.get("/health", response_model=HealthResponse, summary="Application liveness",
            description="No database or authentication configuration check.")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse, summary="Application readiness",
            description="Validates JWT configuration, PostgreSQL connectivity, migration revision, and core tables.",
            responses={503: {"model": APIErrorResponse}})
def ready(response: Response, db: Session = Depends(get_db)) -> ReadinessResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        get_jwt_settings()
        check_connection(db)
        check_schema(db)
    except (ValueError, RuntimeError, SQLAlchemyError):
        db.rollback()
        logger.error("Readiness check failed")
        raise APIError(503, "Application is not ready", code="NOT_READY") from None
    return ReadinessResponse(status="ready")
