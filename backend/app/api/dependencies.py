import re
from typing import Optional

from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import JWTConfigurationError, get_rate_limit_rule, trust_proxy_headers
from app.api.errors import APIError
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.db.session import get_db
from app.models import User
from app.services.authentication import (
    AuthenticationUnavailableError,
    InvalidCredentialsError,
    find_current_user,
)
from app.services.pagination import Page
from app.services.rate_limiting import RateLimitExceededError, enforce, parse_rule


bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")


def unauthorized(detail: str = "Invalid or missing authentication credentials") -> APIError:
    return APIError(
        status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_token_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> int:
    if credentials is None:
        raise unauthorized()
    try:
        return decode_access_token(credentials.credentials)
    except InvalidAccessTokenError:
        raise unauthorized() from None
    except JWTConfigurationError:
        raise APIError(status_code=503, detail="Authentication temporarily unavailable",
                       code="AUTHENTICATION_UNAVAILABLE") from None


def get_current_user(
    user_id: int = Depends(get_token_user_id),
    db: Session = Depends(get_db),
) -> User:
    try:
        return find_current_user(db, user_id)
    except InvalidCredentialsError:
        raise unauthorized() from None
    except AuthenticationUnavailableError:
        raise APIError(status_code=503, detail="Authentication temporarily unavailable",
                       code="AUTHENTICATION_UNAVAILABLE") from None


IF_MATCH_PATTERN = re.compile(r'"?([1-9][0-9]{0,9})"?')


def if_match_version(
    if_match: Optional[str] = Header(
        default=None, alias="If-Match",
        description='The entity version last seen, as an ETag such as "3". '
                    "A newer stored version answers 412 instead of overwriting it.",
    ),
) -> Optional[int]:
    """Optional optimistic check; omitting the header keeps last-write-wins."""
    if if_match is None or if_match.strip() == "*":
        return None
    match = IF_MATCH_PATTERN.fullmatch(if_match.strip())
    if match is None or int(match.group(1)) > 2147483647:
        raise APIError(status_code=400, detail='If-Match must be an entity version such as "3"',
                       code="INVALID_IF_MATCH")
    return int(match.group(1))


def etag(version: int) -> str:
    return f'"{version}"'


def page_params(
    limit: Optional[int] = Query(
        None, ge=1, le=200, description="Page size; omit for the whole list."),
    offset: int = Query(0, ge=0, le=2_000_000_000, description="Rows to skip."),
) -> Page:
    """Optional pagination for list routes; the total is returned as X-Total-Count."""
    return Page(limit=limit, offset=offset)


def client_address(request: Request) -> str:
    """The client's address, taken from X-Forwarded-For only when a trusted proxy sets it."""
    if trust_proxy_headers():
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:100]
    return (request.client.host if request.client else "unknown")[:100]


def enforce_rate_limit(name: str, request: Request, db: Session) -> None:
    """Count this request against `RATE_LIMIT_<NAME>` for the client; 429 once over.

    Called after body validation inside the route, so a malformed request is
    answered 422 without touching the database, as before. A database failure
    surfaces as RateLimitUnavailableError for the route to report as its own
    503, since the user-facing meaning is the same: not possible right now.
    """
    try:
        rule = parse_rule(get_rate_limit_rule(name))
    except ValueError:
        raise APIError(status_code=503, detail="Rate limit configuration invalid",
                       code="RATE_LIMITER_UNAVAILABLE") from None
    if rule is None:
        return
    try:
        enforce(db, f"{name}:{client_address(request)}", rule)
    except RateLimitExceededError as error:
        raise APIError(
            status_code=429, detail="Too many attempts; try again shortly",
            headers={"Retry-After": str(error.retry_after)}, code="RATE_LIMITED",
        ) from None
