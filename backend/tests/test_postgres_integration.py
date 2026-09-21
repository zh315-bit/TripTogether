import os

import pytest

from app.db.check import check_connection
from app.db.session import get_engine, get_session_factory


@pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_TESTS") != "1",
    reason="Set RUN_POSTGRES_TESTS=1 with a real PostgreSQL DATABASE_URL.",
)
def test_real_postgres_connection() -> None:
    """Opt-in: never replace PostgreSQL with SQLite or a mock."""
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    engine = get_engine()
    try:
        assert engine.dialect.name == "postgresql"
        with get_session_factory()() as session:
            check_connection(session)
    finally:
        engine.dispose()
        get_session_factory.cache_clear()
        get_engine.cache_clear()
