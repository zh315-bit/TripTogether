import sys
from functools import lru_cache
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_engine, get_session_factory


CORE_TABLES = frozenset({
    "users", "trips", "trip_members", "trip_invitations",
    "itinerary_items", "expenses", "expense_splits",
})


@lru_cache(maxsize=1)
def expected_revision() -> str:
    migrations = Path(__file__).resolve().parents[2] / "migrations"
    heads = ScriptDirectory(str(migrations)).get_heads()
    if len(heads) != 1:
        raise RuntimeError("Expected exactly one migration head.")
    return heads[0]


def check_connection(session: Session) -> None:
    if session.execute(text("SELECT 1")).scalar_one() != 1:
        raise RuntimeError("Unexpected database connectivity check result.")


def check_schema(session: Session) -> None:
    revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if revision != expected_revision():
        raise RuntimeError("Database migration revision is not current.")
    tables = set(session.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
    )).scalars())
    if not CORE_TABLES.issubset(tables):
        raise RuntimeError("Required database tables are missing.")


def main() -> int:
    try:
        engine = get_engine()
        try:
            with get_session_factory()() as session:
                check_connection(session)
        finally:
            engine.dispose()
    except (ValueError, SQLAlchemyError, RuntimeError):
        # Driver errors can contain connection details; do not print them.
        print(
            "PostgreSQL connectivity check failed. Check DATABASE_URL, "
            "credentials, and server availability.",
            file=sys.stderr,
        )
        return 1
    print("PostgreSQL connectivity check passed (SELECT 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
