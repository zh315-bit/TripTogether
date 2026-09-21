import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_engine, get_session_factory


def check_connection(session: Session) -> None:
    if session.execute(text("SELECT 1")).scalar_one() != 1:
        raise RuntimeError("Unexpected database connectivity check result.")


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
