from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.errors import APIError, APIErrorResponse
from app.api.dependencies import enforce_rate_limit, get_current_user, unauthorized
from app.core.config import JWTConfigurationError, password_reset_url
from app.core.mail import MailConfigurationError, MailDeliveryError, send_mail
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.user import (
    AcceptedResponse, DemoLogin, DemoTokenResponse, ForgotPasswordRequest, RefreshRequest,
    ResetPasswordRequest, TokenResponse, UserLogin, UserRegister, UserResponse,
)
from app.services.authentication import (
    AuthenticationUnavailableError,
    InvalidCredentialsError,
    authenticate_user,
)
from app.services.demo import DemoDisabledError, DemoUnavailableError, demo_session
from app.services.rate_limiting import RateLimitUnavailableError
from app.services.sessions import (
    InvalidRefreshTokenError, InvalidResetTokenError, SessionsUnavailableError,
    create_reset_token, issue_refresh_token, reset_password, revoke_refresh_token,
    rotate_refresh_token,
)
from app.services.registration import (
    DuplicateUserError,
    RegistrationUnavailableError,
    register_user,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": APIErrorResponse},
        422: {"model": APIErrorResponse},
        429: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def register(payload: UserRegister, request: Request, db: Session = Depends(get_db)) -> UserResponse:
    try:
        enforce_rate_limit("register", request, db)
        user = register_user(db, payload)
    except DuplicateUserError as error:
        raise APIError(status_code=409, detail=str(error), code=error.code) from None
    except (RegistrationUnavailableError, RateLimitUnavailableError):
        raise APIError(
            status_code=503, detail="Registration temporarily unavailable", code="REGISTRATION_UNAVAILABLE",
        ) from None
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": APIErrorResponse},
        422: {"model": APIErrorResponse},
        429: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def login(
    payload: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    try:
        enforce_rate_limit("login", request, db)
        user = authenticate_user(db, payload)
        token = create_access_token(user.id)
        refresh = issue_refresh_token(db, user.id)
        db.commit()
    except InvalidCredentialsError:
        raise unauthorized("Invalid email or password") from None
    except (AuthenticationUnavailableError, RateLimitUnavailableError, SessionsUnavailableError,
            JWTConfigurationError, ValueError):
        raise APIError(status_code=503, detail="Authentication temporarily unavailable",
                       code="AUTHENTICATION_UNAVAILABLE") from None
    no_store(response)
    return TokenResponse(access_token=token, refresh_token=refresh)


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a refresh token for a new pair",
    responses={401: {"model": APIErrorResponse}, 422: {"model": APIErrorResponse},
               429: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse}},
)
def refresh(
    payload: RefreshRequest, request: Request, response: Response, db: Session = Depends(get_db),
) -> TokenResponse:
    """Rotates the refresh token: the presented one stops working, a new one is returned.

    Presenting an already-used token revokes its whole family, since two
    parties evidently hold it.
    """
    try:
        enforce_rate_limit("login", request, db)
        result = rotate_refresh_token(db, payload.refresh_token)
        token = create_access_token(result.user.id)
    except InvalidRefreshTokenError:
        raise APIError(status_code=401, detail="Refresh token is invalid or expired",
                       headers={"WWW-Authenticate": "Bearer"}, code="INVALID_REFRESH_TOKEN") from None
    except (SessionsUnavailableError, RateLimitUnavailableError, JWTConfigurationError, ValueError):
        raise APIError(status_code=503, detail="Authentication temporarily unavailable",
                       code="AUTHENTICATION_UNAVAILABLE") from None
    no_store(response)
    return TokenResponse(access_token=token, refresh_token=result.refresh_token)


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a refresh session",
    responses={422: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse}},
)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)) -> Response:
    """Ends the session the refresh token belongs to; the short-lived access token simply expires."""
    try:
        revoke_refresh_token(db, payload.refresh_token)
    except SessionsUnavailableError:
        raise APIError(status_code=503, detail="Authentication temporarily unavailable",
                       code="AUTHENTICATION_UNAVAILABLE") from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post(
    "/password/forgot",
    response_model=AcceptedResponse, status_code=status.HTTP_202_ACCEPTED,
    summary="Send a password reset link",
    responses={422: {"model": APIErrorResponse}, 429: {"model": APIErrorResponse},
               503: {"model": APIErrorResponse}},
)
def forgot_password(
    payload: ForgotPasswordRequest, request: Request, response: Response, db: Session = Depends(get_db),
) -> AcceptedResponse:
    """Always answers 202, so the response does not reveal whether the address is registered."""
    try:
        enforce_rate_limit("reset", request, db)
        user = db.scalar(select(User).where(User.email == payload.email))
        if user is not None:
            raw = create_reset_token(db, user)
            send_mail(user.email, "Reset your TripTogether password",
                      "Someone asked to reset the password for this account. If that was you, open:\n\n"
                      f"{password_reset_url(raw)}\n\nThe link works once and expires in one hour. "
                      "If you did not ask for this, ignore this message.")
        else:
            # Unknown addresses cost about the same time as known ones.
            db.rollback()
    except MailConfigurationError:
        raise APIError(status_code=503, detail="Password reset is not available on this server",
                       code="PASSWORD_RESET_UNAVAILABLE") from None
    except (MailDeliveryError, SessionsUnavailableError, RateLimitUnavailableError, SQLAlchemyError, ValueError):
        db.rollback()
        raise APIError(status_code=503, detail="Password reset temporarily unavailable",
                       code="PASSWORD_RESET_UNAVAILABLE") from None
    no_store(response)
    return AcceptedResponse()


@router.post(
    "/password/reset", status_code=status.HTTP_204_NO_CONTENT, summary="Set a new password from a reset link",
    responses={400: {"model": APIErrorResponse}, 422: {"model": APIErrorResponse},
               429: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse}},
)
def reset_password_route(
    payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db),
) -> Response:
    """Works once per link; afterwards every existing session of the account is signed out."""
    try:
        enforce_rate_limit("reset", request, db)
        reset_password(db, payload.token, payload.password.get_secret_value())
    except InvalidResetTokenError:
        raise APIError(status_code=400, detail="This reset link is invalid, used or expired",
                       code="INVALID_RESET_TOKEN") from None
    except (SessionsUnavailableError, RateLimitUnavailableError):
        raise APIError(status_code=503, detail="Password reset temporarily unavailable",
                       code="PASSWORD_RESET_UNAVAILABLE") from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post(
    "/demo",
    response_model=DemoTokenResponse,
    summary="Sign in as a demo member",
    responses={
        404: {"model": APIErrorResponse},
        422: {"model": APIErrorResponse},
        429: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def demo(
    payload: DemoLogin, request: Request, response: Response, db: Session = Depends(get_db),
) -> DemoTokenResponse:
    """Issues a session for one of three demo members sharing a ready-made trip.

    Only available when DEMO_MODE is set. The trip is rebuilt when it is more
    than six hours old, so visitors can edit freely. Counted against the login limit.
    """
    try:
        enforce_rate_limit("login", request, db)
        session = demo_session(db, payload.member)
        token = create_access_token(session.user.id)
        refresh = issue_refresh_token(db, session.user.id)
        db.commit()
    except DemoDisabledError:
        raise APIError(status_code=404, detail="The demo is not enabled", code="DEMO_DISABLED") from None
    except (DemoUnavailableError, RateLimitUnavailableError, SessionsUnavailableError,
            JWTConfigurationError, ValueError):
        raise APIError(status_code=503, detail="Demo temporarily unavailable",
                       code="DEMO_UNAVAILABLE") from None
    response.headers["Cache-Control"] = "no-store"
    return DemoTokenResponse(access_token=token, refresh_token=refresh, member=payload.member,
                             username=session.user.username, trip_id=session.trip_id)


@router.get(
    "/me", response_model=UserResponse,
    responses={401: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse}},
)
def me(response: Response, current_user: User = Depends(get_current_user)) -> UserResponse:
    response.headers["Cache-Control"] = "no-store"
    return UserResponse.model_validate(current_user)
