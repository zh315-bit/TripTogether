from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    AfterValidator,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
)


def normalize_email(value: str) -> str:
    # Product policy shared by registration, login and invitations.
    normalized = value.lower()
    if len(normalized) > 254:
        raise ValueError("Email must be at most 254 characters")
    return normalized


NormalizedEmail = Annotated[EmailStr, AfterValidator(normalize_email)]


class UserLogin(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    email: NormalizedEmail
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_encoding(cls, value: SecretStr) -> SecretStr:
        try:
            value.get_secret_value().encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Password must contain valid Unicode characters") from None
        return value


class UserRegister(UserLogin):
    username: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=50,
            pattern=r"^[A-Za-z0-9_]+$",
        ),
    ]
    password: SecretStr = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str = Field(repr=False)
    token_type: Literal["bearer"] = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    created_at: datetime
