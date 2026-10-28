"""Trip change notifications: staged inside the transaction, published after commit.

A service stages an event on the session while it writes; the session's
after_commit hook hands every staged event to the broker, and a rollback
discards them. Subscribers (the SSE endpoint) therefore never hear about a
change that did not land, and a client that refetches on an event always sees
the committed row.

Two backends share this interface. `memory` (the default) fans out inside one
API instance. `postgres` sends each staged event as `pg_notify` inside the
writing transaction, so PostgreSQL delivers it to every instance only when
that transaction commits, and a relay task on each instance feeds the
notifications to its local subscribers. The relay reconnects with backoff and
tells its subscribers to resync, since notifications sent while it was away
are gone.
"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import AsyncIterator, Literal, Optional

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.config import _get_setting


logger = logging.getLogger("triptogether")

Entity = Literal["trip", "itinerary", "expense", "place", "member"]
Action = Literal["created", "updated", "deleted", "reordered", "joined"]

# A slow consumer is told to resync rather than allowed to grow without bound.
QUEUE_LIMIT = 64
RESYNC = {"type": "resync"}
CHANNEL = "triptogether_events"
BACKENDS = ("memory", "postgres")


def realtime_backend() -> str:
    """`memory` fans out inside one instance; `postgres` relays through LISTEN/NOTIFY."""
    value = (_get_setting("REALTIME_BACKEND", "memory") or "memory").strip().lower()
    if value not in BACKENDS:
        raise ValueError("REALTIME_BACKEND must be memory or postgres.")
    return value


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
        loop.call_soon_threadsafe(self.dispatch, [item.payload() for item in events])

    def dispatch(self, payloads: list[dict]) -> None:
        """Deliver already-serialised events; call on the loop thread."""
        for payload in payloads:
            for queue in list(self._queues.get(payload.get("trip_id"), ())):
                self._offer(queue, payload)
                if payload.get("type") == "trip.deleted":
                    # Nothing more can happen to this trip: end its streams.
                    self._offer(queue, None)

    def resync_all(self) -> None:
        """Every subscriber refetches: used after the relay missed notifications."""
        for queues in list(self._queues.values()):
            for queue in list(queues):
                self._offer(queue, RESYNC)

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


@event.listens_for(Session, "before_commit")
def _notify_staged(session: Session) -> None:
    """With the postgres backend, hand staged events to PostgreSQL inside the transaction.

    NOTIFY is delivered only if the transaction commits, so every instance's
    relay sees exactly the changes that landed. The events are then no longer
    published locally: this instance's relay receives them like any other.
    """
    staged = session.info.get(STAGED)
    if not staged or realtime_backend() != "postgres":
        return
    for item in staged:
        session.execute(text("SELECT pg_notify(:channel, :payload)"), {
            "channel": CHANNEL, "payload": json.dumps(item.payload(), separators=(",", ":")),
        })
    session.info[STAGED] = []


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


def listen_dsn() -> str:
    """The libpq form of DATABASE_URL for the relay's own connection."""
    from app.core.config import get_database_url

    return get_database_url().set(drivername="postgresql").render_as_string(hide_password=False)


class PostgresRelay:
    """One LISTEN connection per instance, feeding notifications to the local broker.

    Runs as a task on the application loop. A lost connection is retried with
    backoff; once it is back every local subscriber gets a `resync`, because
    PostgreSQL does not replay notifications sent while nobody was listening.
    """

    def __init__(self, dsn: str, target: TripEventBroker, channel: str = CHANNEL,
                 retry: float = 1.0, max_retry: float = 30.0) -> None:
        self.dsn = dsn
        self.target = target
        self.channel = channel
        self.retry = retry
        self.max_retry = max_retry
        self.connected = False
        self.connections = 0
        self._connection = None

    async def run(self) -> None:
        import psycopg

        delay = self.retry
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(self.dsn, autocommit=True) as connection:
                    self._connection = connection
                    await connection.execute(f"LISTEN {self.channel}")
                    self.connections += 1
                    self.connected = True
                    delay = self.retry
                    if self.connections > 1:
                        self.target.resync_all()
                    logger.info("Realtime relay listening on %s", self.channel)
                    async for notification in connection.notifies():
                        self.deliver(notification.payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Realtime relay disconnected; retrying in %ss", delay)
            finally:
                self.connected = False
                self._connection = None
            await asyncio.sleep(delay)
            delay = min(delay * 2, self.max_retry)

    def deliver(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except ValueError:
            logger.warning("Realtime relay ignored a malformed notification")
            return
        if isinstance(data, dict) and isinstance(data.get("trip_id"), int) and isinstance(data.get("type"), str):
            self.target.dispatch([data])

    async def disconnect(self) -> None:
        """Drop the current connection (tests simulate an outage this way)."""
        connection = self._connection
        if connection is not None:
            await connection.close()
