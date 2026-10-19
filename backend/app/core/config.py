import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        value = dotenv_values(ENV_FILE).get(name, default)
    return value


def get_database_url() -> URL:
    """Read configuration only when database access is requested."""
    value = _get_setting("DATABASE_URL")
    if not value:
        raise ValueError("DATABASE_URL is required for database access.")
    try:
        url = make_url(value)
    except (ArgumentError, ValueError):
        raise ValueError("DATABASE_URL must be a valid PostgreSQL URL.") from None
    # Hosted PostgreSQL providers commonly supply standard postgres:// or
    # postgresql:// URLs. Keep psycopg as the application's explicit driver.
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg" or not url.database:
        raise ValueError(
            "DATABASE_URL must use postgresql+psycopg and name a database."
        )
    return url


class JWTConfigurationError(ValueError):
    """Invalid server configuration, never an invalid client credential."""


@dataclass(frozen=True)
class JWTSettings:
    secret_key: str = field(repr=False)
    algorithm: str = "HS256"
    expire_minutes: int = 30


def get_jwt_settings() -> JWTSettings:
    """JWT configuration is required only when issuing or validating a token."""
    secret = _get_setting("JWT_SECRET_KEY")
    if (
        not secret
        or len(secret.encode("utf-8")) < 32
        or not secret.strip()
        or secret == "replace-with-a-secure-random-secret"
    ):
        raise JWTConfigurationError("JWT_SECRET_KEY must be a secure random secret of at least 32 bytes.")
    algorithm = _get_setting("JWT_ALGORITHM", "HS256")
    if algorithm != "HS256":
        raise JWTConfigurationError("JWT_ALGORITHM must be HS256.")
    try:
        minutes = int(_get_setting("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    except (TypeError, ValueError):
        raise JWTConfigurationError("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer.") from None
    if not 1 <= minutes <= 1440:
        raise JWTConfigurationError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 1440.")
    return JWTSettings(secret_key=secret, algorithm=algorithm, expire_minutes=minutes)


@dataclass(frozen=True)
class AppSettings:
    environment: str = "development"
    cors_origins: tuple[str, ...] = ()


def get_app_settings() -> AppSettings:
    environment = _get_setting("APP_ENV", "development")
    if environment not in ("development", "production"):
        raise ValueError("APP_ENV must be development or production.")
    try:
        origins = json.loads(_get_setting("CORS_ORIGINS", "[]"))
        if not isinstance(origins, list):
            raise ValueError()
        for origin in origins:
            if not isinstance(origin, str) or any(c.isspace() for c in origin):
                raise ValueError()
            url = urlsplit(origin)
            if (url.scheme not in ("http", "https") or not url.hostname
                    or "*" in origin or url.username or url.password
                    or url.path or url.query or url.fragment
                    or url.port == 0 or origin.endswith(":")
                    or (environment == "production" and url.scheme != "https")):
                raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("CORS_ORIGINS must be a JSON array of explicit HTTP(S) origins; "
                         "production requires HTTPS.") from None
    return AppSettings(environment=environment, cors_origins=tuple(dict.fromkeys(origins)))


GEOCODER_PROVIDERS = ("disabled", "fake", "nominatim")
NOMINATIM_PUBLIC_URL = "https://nominatim.openstreetmap.org"


@dataclass(frozen=True)
class GeocoderSettings:
    provider: str = "disabled"
    user_agent: str = ""
    base_url: str = NOMINATIM_PUBLIC_URL


def get_geocoder_settings(environment: Optional[str] = None) -> GeocoderSettings:
    """Disabled by default; operators can switch it off without a code release."""
    environment = environment or _get_setting("APP_ENV", "development")
    provider = (_get_setting("GEOCODER_PROVIDER", "disabled") or "disabled").strip()
    if provider not in GEOCODER_PROVIDERS:
        raise ValueError("GEOCODER_PROVIDER must be disabled, fake or nominatim.")
    if provider == "fake" and environment == "production":
        raise ValueError("GEOCODER_PROVIDER=fake is for development and tests only.")
    user_agent = (_get_setting("GEOCODER_USER_AGENT", "") or "").strip()
    base_url = (_get_setting("GEOCODER_BASE_URL", NOMINATIM_PUBLIC_URL) or "").strip().rstrip("/")
    if provider == "nominatim":
        # Nominatim policy: identify the application; stock library agents are refused.
        if not 8 <= len(user_agent) <= 200 or not user_agent.isprintable() or (
            user_agent.lower().startswith(("python-httpx", "python-requests", "curl/"))
        ) or "you@example.com" in user_agent:
            raise ValueError("GEOCODER_USER_AGENT must identify the application and a contact.")
        url = urlsplit(base_url)
        if (url.scheme != "https" and environment == "production") or url.scheme not in (
            "http", "https",
        ) or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("GEOCODER_BASE_URL must be an HTTP(S) origin; production requires HTTPS.")
    return GeocoderSettings(provider=provider, user_agent=user_agent, base_url=base_url)
