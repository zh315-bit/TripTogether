import re
from typing import Optional

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import JWTConfigurationError
from app.api.errors import APIError
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.db.session import get_db
from app.models import User
from app.services.authentication import (
    AuthenticationUnavailableError,
    InvalidCredentialsError,
    find_current_user,
)


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
