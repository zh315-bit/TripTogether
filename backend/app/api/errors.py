import logging
from typing import Optional, Union

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


logger = logging.getLogger("triptogether")


class ErrorResponse(BaseModel):
    detail: str


class ValidationIssue(BaseModel):
    loc: list[Union[str, int]]
    msg: str
    type: str


class ValidationErrorResponse(BaseModel):
    detail: list[ValidationIssue]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ValidationIssue] = Field(default_factory=list)


class APIErrorResponse(BaseModel):
    error: ErrorBody


STATUS_CODES = {
    400: "BAD_REQUEST", 401: "INVALID_CREDENTIALS", 403: "FORBIDDEN",
    404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 409: "CONFLICT",
    422: "VALIDATION_ERROR", 500: "INTERNAL_ERROR", 503: "SERVICE_UNAVAILABLE",
}


class APIError(HTTPException):
    """Keep legacy detail while attaching a stable v1 code at the raise site."""

    def __init__(self, status_code: int, detail, headers=None, *, code: Optional[str] = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code or STATUS_CODES.get(status_code, "HTTP_ERROR")


def uses_error_envelope(request: Request) -> bool:
    path = request.scope["path"]
    return path == "/api/v1" or path.startswith("/api/v1/") or path == "/ready"


def error_response(
    request: Request, status_code: int, code: str, message: str,
    details: Optional[list] = None, headers: Optional[dict] = None,
) -> JSONResponse:
    if uses_error_envelope(request):
        content = {"error": {"code": code, "message": message, "details": details or []}}
    else:
        content = {"detail": details if details is not None else message}
    return JSONResponse(status_code=status_code, content=content,
                        headers={**(headers or {}), "Cache-Control": "no-store"})


async def http_error_handler(request: Request, error: StarletteHTTPException) -> JSONResponse:
    code = getattr(error, "code", STATUS_CODES.get(error.status_code, "HTTP_ERROR"))
    if error.status_code >= 500:
        # Only server-selected codes; never SQL exceptions, bodies or credentials.
        logger.error("Service unavailable")
    details = error.detail if isinstance(error.detail, list) else None
    message = "Request validation failed" if details is not None else str(error.detail)
    return error_response(request, error.status_code, code, message, details, error.headers)


async def validation_error_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    # FastAPI's default errors include raw input, possibly an entire password body.
    details = [
        {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
        for item in error.errors()
    ]
    return error_response(request, 422, "VALIDATION_ERROR", "Request validation failed", details)
