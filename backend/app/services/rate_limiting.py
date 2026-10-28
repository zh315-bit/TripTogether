"""Fixed-window rate limiting backed by PostgreSQL.

The counter lives in one row per (limit name, client), so the limit holds
across every worker and instance, like the geocoder throttle. A single
upsert either starts a new window or increments the current one and returns
the resulting count, so concurrent requests never double-count or race.
"""
from dataclasses import dataclass
from datetime import timedelta
import math
import re
from typing import Optional

from sqlalchemy import delete, func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import RateLimit


# Rows older than this cannot belong to any live window and are swept when a
# new window starts, so the table stays small without a scheduler.
SWEEP_AFTER = timedelta(days=1)
RULE = re.compile(r"^\s*([1-9][0-9]{0,5})\s*/\s*([1-9][0-9]{0,6})\s*$")


class RateLimitExceededError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Retry after {retry_after}s")
        self.retry_after = retry_after


class RateLimitUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: int


def parse_rule(value: Optional[str]) -> Optional[RateLimitRule]:
    """`"10/60"` means ten requests per sixty seconds; `off` (or empty) disables."""
    if value is None or value.strip().lower() in ("", "off", "0"):
        return None
    match = RULE.match(value)
    if match is None:
        raise ValueError("Rate limit rules look like '<requests>/<seconds>' or 'off'")
    return RateLimitRule(int(match.group(1)), int(match.group(2)))


def enforce(db: Session, key: str, rule: RateLimitRule) -> int:
    """Count one request for `key`; raise once the window holds more than the rule allows.

    Returns the count within the current window. The count is committed on its
    own so that a request which later fails (a wrong password, say) still counts.
    """
    window = timedelta(seconds=rule.window_seconds)
    statement = insert(RateLimit).values(key=key, window_start=func.clock_timestamp(), count=1)
    statement = statement.on_conflict_do_update(
        index_elements=[RateLimit.key],
        set_={
            "count": func.coalesce(
                text("CASE WHEN rate_limits.window_start <= clock_timestamp() - :window "
                     "THEN 1 ELSE rate_limits.count + 1 END").bindparams(window=window), 1),
            "window_start": text(
                "CASE WHEN rate_limits.window_start <= clock_timestamp() - :window "
                "THEN clock_timestamp() ELSE rate_limits.window_start END").bindparams(window=window),
        },
    ).returning(RateLimit.count, RateLimit.window_start, func.clock_timestamp())
    try:
        count, window_start, now = db.execute(statement).one()
        if count == 1:
            db.execute(delete(RateLimit).where(RateLimit.window_start < now - SWEEP_AFTER))
        db.commit()
    except (SQLAlchemyError, ValueError, TypeError):
        # A failed statement, or a session that cannot return the row at all.
        db.rollback()
        raise RateLimitUnavailableError() from None
    if count > rule.limit:
        remaining = window - (now - window_start)
        raise RateLimitExceededError(max(1, math.ceil(remaining.total_seconds())))
    return count
