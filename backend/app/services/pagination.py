from dataclasses import dataclass
from typing import Optional, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


T = TypeVar("T")


@dataclass(frozen=True)
class Page:
    """Optional `limit`/`offset` for a list. Without either, the whole list is returned."""

    limit: Optional[int] = None
    offset: int = 0

    @property
    def requested(self) -> bool:
        return self.limit is not None or self.offset > 0


def paginate(db: Session, statement: Select, page: Page, unique: bool = False) -> tuple[list, int]:
    """Return the page's rows and the total count the client needs to page further.

    An unpaged list is one query, as before. A paged list counts separately
    inside the same transaction so `X-Total-Count` matches the rows returned.
    """
    if page.requested:
        total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
        statement = statement.offset(page.offset).limit(page.limit)
        rows = fetch(db, statement, unique)
        return rows, int(total or 0)
    rows = fetch(db, statement, unique)
    return rows, len(rows)


def fetch(db: Session, statement: Select, unique: bool) -> list:
    if unique:
        # Joined collection loads need unique(); a LIMIT is applied to a subquery.
        return list(db.execute(statement).unique().scalars().all())
    return list(db.scalars(statement).all())
