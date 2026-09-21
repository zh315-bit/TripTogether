from sqlalchemy import DateTime, Integer, UniqueConstraint

from app.db.base import Base
from app.models import User


def test_user_metadata() -> None:
    table = User.__table__
    assert issubclass(User, Base)
    assert Base.metadata.tables["users"] is table
    assert set(table.columns.keys()) == {
        "id", "username", "email", "password_hash", "created_at"
    }
    assert [column.name for column in table.primary_key] == ["id"]
    assert isinstance(table.c.id.type, Integer)
    assert table.c.id.identity is not None
    assert all(not column.nullable for column in table.columns)
    assert table.c.username.type.length == 50
    assert table.c.email.type.length == 254
    assert table.c.password_hash.type.length == 255
    assert isinstance(table.c.created_at.type, DateTime)
    assert table.c.created_at.type.timezone
    assert str(table.c.created_at.server_default.arg) == "now()"


def test_unique_constraints_without_redundant_indexes() -> None:
    table = User.__table__
    constraints = {
        constraint.name: tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert constraints == {
        "uq_users_username": ("username",),
        "uq_users_email": ("email",),
    }
    # PostgreSQL creates an index for each unique constraint automatically.
    assert not table.indexes
