import pytest
from argon2 import extract_parameters
from argon2.low_level import Type

from app.core.security import hash_password, verify_password


def test_argon2id_random_salt_and_verification() -> None:
    password = "fake-test-password-123"
    first = hash_password(password)
    second = hash_password(password)
    assert first != second
    assert first != password
    assert len(first) <= 255
    parameters = extract_parameters(first)
    assert parameters.type == Type.ID
    assert parameters.memory_cost == 65536
    assert parameters.time_cost == 3
    assert parameters.salt_len == 16
    assert verify_password(password, first)
    assert verify_password(password, second)
    assert not verify_password("wrong-fake-password", first)


def test_long_unicode_password_is_not_truncated() -> None:
    password = "\u00e9" * 127 + "x"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("\u00e9" * 127 + "y", hashed)


@pytest.mark.parametrize("value", ["", "not-a-password-hash", "$argon2id$invalid"])
def test_invalid_hash_is_rejected(value: str) -> None:
    assert not verify_password("fake-test-password", value)
