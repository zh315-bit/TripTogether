import secrets
import time

import jwt
import pytest

from app.core.config import JWTConfigurationError, get_jwt_settings
from app.core.security import (
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
)


def test_config_dotenv_defaults_precedence_and_secret_repr(isolated_jwt_config, monkeypatch):
    file_secret = secrets.token_urlsafe(48)
    isolated_jwt_config.write_text(f"JWT_SECRET_KEY={file_secret}\n")
    settings = get_jwt_settings()
    assert settings.secret_key == file_secret
    assert settings.algorithm == "HS256"
    assert settings.expire_minutes == 30
    assert file_secret not in repr(settings)
    environment_secret = secrets.token_urlsafe(48)
    monkeypatch.setenv("JWT_SECRET_KEY", environment_secret)
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    assert get_jwt_settings().secret_key == environment_secret
    assert get_jwt_settings().expire_minutes == 15


@pytest.mark.parametrize("secret", [None, "", "short", "replace-with-a-secure-random-secret"])
def test_missing_or_unsafe_secret(isolated_jwt_config, monkeypatch, secret):
    if secret is not None:
        monkeypatch.setenv("JWT_SECRET_KEY", secret)
    with pytest.raises(JWTConfigurationError):
        get_jwt_settings()


def test_empty_environment_does_not_fall_back(isolated_jwt_config, monkeypatch):
    isolated_jwt_config.write_text(f"JWT_SECRET_KEY={secrets.token_urlsafe(48)}\n")
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    with pytest.raises(JWTConfigurationError):
        get_jwt_settings()


@pytest.mark.parametrize("algorithm", ["none", "HS384", "RS256", ""])
def test_algorithm_allowlist(jwt_environment, monkeypatch, algorithm):
    monkeypatch.setenv("JWT_ALGORITHM", algorithm)
    with pytest.raises(JWTConfigurationError):
        get_jwt_settings()


@pytest.mark.parametrize("value", ["0", "-1", "1441", "NaN", "1.5", ""])
def test_invalid_lifetime(jwt_environment, monkeypatch, value):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", value)
    with pytest.raises(JWTConfigurationError):
        get_jwt_settings()


def test_token_payload_and_configured_expiration(jwt_environment, monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "7")
    before = int(time.time())
    token = create_access_token(12)
    claims = jwt.decode(token, jwt_environment, algorithms=["HS256"])
    assert set(claims) == {"sub", "exp"}
    assert claims["sub"] == "12"
    assert before + 420 <= claims["exp"] <= int(time.time()) + 420
    assert decode_access_token(token) == 12


@pytest.mark.parametrize("value", [0, -1, True, "1", 2147483648])
def test_cannot_issue_invalid_user_id(jwt_environment, value):
    with pytest.raises(ValueError):
        create_access_token(value)


@pytest.mark.parametrize(
    "subject",
    [None, 1, True, "", "0", "-1", "01", "1.0", "alice", " 1", "2147483648", "9" * 100],
)
def test_invalid_subject(jwt_environment, subject):
    token = jwt.encode(
        {"sub": subject, "exp": int(time.time()) + 300}, jwt_environment, algorithm="HS256"
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


@pytest.mark.parametrize("expiration", [None, "9999999999", True, 9999999999.0, [], float("inf")])
def test_invalid_expiration_type(jwt_environment, expiration):
    token = jwt.encode(
        {"sub": "1", "exp": expiration}, jwt_environment, algorithm="HS256"
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


@pytest.mark.parametrize("missing", ["sub", "exp"])
def test_required_claims(jwt_environment, missing):
    payload = {"sub": "1", "exp": int(time.time()) + 300}
    del payload[missing]
    token = jwt.encode(payload, jwt_environment, algorithm="HS256")
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_expired_tampered_wrong_key_and_algorithm(jwt_environment):
    valid = create_access_token(1)
    header, _, signature = valid.split(".")
    other = create_access_token(2)
    tampered = ".".join([header, other.split(".")[1], signature])
    payload = {"sub": "1", "exp": int(time.time()) + 300}
    rejected = [
        "abc123",
        tampered,
        jwt.encode({**payload, "exp": int(time.time()) - 60}, jwt_environment, algorithm="HS256"),
        jwt.encode(payload, secrets.token_urlsafe(48), algorithm="HS256"),
        jwt.encode(payload, jwt_environment, algorithm="HS384"),
        jwt.encode(payload, "", algorithm="none"),
    ]
    for token in rejected:
        with pytest.raises(InvalidAccessTokenError):
            decode_access_token(token)
