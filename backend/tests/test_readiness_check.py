from typing import Optional
from unittest.mock import MagicMock

import pytest

from app.db import check


def readiness_session(revision: Optional[str], tables: set[str]) -> MagicMock:
    revision_result = MagicMock()
    revision_result.scalar_one_or_none.return_value = revision
    tables_result = MagicMock()
    tables_result.scalars.return_value = tables
    session = MagicMock()
    session.execute.side_effect = [revision_result, tables_result]
    return session


def test_check_schema_accepts_expected_revision_and_core_tables(monkeypatch):
    monkeypatch.setattr(check, "expected_revision", lambda: "expected-head")
    session = readiness_session("expected-head", set(check.CORE_TABLES))

    check.check_schema(session)

    assert session.execute.call_count == 2


@pytest.mark.parametrize("revision", [None, "older-revision"])
def test_check_schema_rejects_missing_or_outdated_revision(monkeypatch, revision):
    monkeypatch.setattr(check, "expected_revision", lambda: "expected-head")
    session = readiness_session(revision, set(check.CORE_TABLES))

    with pytest.raises(RuntimeError, match="revision is not current"):
        check.check_schema(session)


@pytest.mark.parametrize("missing_table", sorted(check.CORE_TABLES))
def test_check_schema_rejects_each_missing_core_table(monkeypatch, missing_table):
    monkeypatch.setattr(check, "expected_revision", lambda: "expected-head")
    tables = set(check.CORE_TABLES) - {missing_table}
    session = readiness_session("expected-head", tables)

    with pytest.raises(RuntimeError, match="Required database tables are missing"):
        check.check_schema(session)
