"""Trip change notifications: staged inside the transaction, published after commit.

A service stages an event on the session while it writes; the session's
after_commit hook hands every staged event to the broker, and a rollback
discards them. Subscribers (the SSE endpoint) therefore never hear about a
change that did not land, and a client that refetches on an event always sees
the committed row. The broker is in-process: one API instance fans out to its
own connections. Several instances would need a shared channel (PostgreSQL
LISTEN/NOTIFY or Redis) behind the same publish/subscribe interface.
"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import logging
from typing import AsyncIterator, Literal, Optional

from sqlalchemy import event
from sqlalchemy.orm import Session


logger = logging.getLogger("triptogether")

Entity = Literal["trip", "itinerary", "expense", "place", "member", "settlement"]
Action = Literal["created", "updated", "deleted", "reordered", "joined"]

# A slow consumer is told to resync rather than allowed to grow without bound.
QUEUE_LIMIT = 64
RESYNC = {"type": "resync"}


@dataclass(frozen=True)
class TripEvent:
    trip_id: int
    entity: Entity
    action: Action
    actor_id: int
    entity_id: Optional[int] = None
    version: Optional[int] = None
    date: Optional[str] = None
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def type(self) -> str:
        return f"{self.entity}.{self.action}"

    def payload(self) -> dict:
        data = asdict(self)
        data["type"] = self.type
        return {key: value for key, value in data.items() if value is not None}


class TripEventBroker:
    """Per-trip fan-out from request threads to streaming responses on the event loop."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queues: dict[int, set[asyncio.Queue]] = {}

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def close(self) -> None:
        """End every open stream; called from the loop thread at shutdown."""
        for queues in list(self._queues.values()):
            for queue in list(queues):
                self._offer(queue, None)
        self._queues.clear()
        self._loop = None

    def subscribers(self, trip_id: int) -> int:
        return len(self._queues.get(trip_id, ()))

    @asynccontextmanager
    async def subscribe(self, trip_id: int) -> AsyncIterator[asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self._queues.setdefault(trip_id, set()).add(queue)
        try:
            yield queue
        finally:
            queues = self._queues.get(trip_id)
            if queues is not None:
                queues.discard(queue)
                if not queues:
                    del self._queues[trip_id]

    def publish(self, events: list[TripEvent]) -> None:
        """Safe from any thread; a no-op when no application loop is running."""
        loop = self._loop
        if not events or loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._dispatch, events)

    def _dispatch(self, events: list[TripEvent]) -> None:
        for item in events:
            payload = item.payload()
            for queue in list(self._queues.get(item.trip_id, ())):
                self._offer(queue, payload)
                if item.entity == "trip" and item.action == "deleted":
                    # Nothing more can happen to this trip: end its streams.
                    self._offer(queue, None)

    @staticmethod
    def _offer(queue: asyncio.Queue, payload: Optional[dict]) -> None:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            # Drop the backlog: one resync is cheaper than replaying it.
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(RESYNC)


broker = TripEventBroker()
STAGED = "trip_events"


def stage(db: Session, trip_event: TripEvent) -> None:
    """Queue an event for publication if, and only if, this transaction commits."""
    if not db.in_transaction():
        # Tie the event to a transaction, so a later rollback can discard it.
        db.begin()
    db.info.setdefault(STAGED, []).append(trip_event)


@event.listens_for(Session, "after_commit")
def _publish_staged(session: Session) -> None:
    staged = session.info.pop(STAGED, None)
    if staged:
        broker.publish(staged)


@event.listens_for(Session, "after_rollback")
def _discard_staged(session: Session) -> None:
    session.info.pop(STAGED, None)


def format_sse(event_name: str, data: str) -> str:
    return f"event: {event_name}\ndata: {data}\n\n"
