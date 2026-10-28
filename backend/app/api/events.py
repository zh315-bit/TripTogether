"""Server-sent events: one stream per open trip, authenticated like every other route.

SSE rather than WebSocket because the traffic is one-way (server to client) and
the client only needs a nudge to refetch; fetch-based SSE keeps the Bearer
header, the CORS policy and the JSON error envelope of the rest of the API.
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_current_user
from app.api.errors import APIErrorResponse
from app.api.trips import TripID, trip_http_errors
from app.db.session import get_db
from app.models import User
from app.realtime import broker, format_sse
from app.services import trips


router = APIRouter(prefix="/trips/{trip_id}/events", tags=["events"], responses={
    401: {"model": APIErrorResponse}, 404: {"model": APIErrorResponse},
    422: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse},
})

# Below common proxy idle timeouts; a comment line keeps the connection alive.
HEARTBEAT_SECONDS = 20.0


async def event_stream(trip_id: int, user_id: int, heartbeat: Optional[float] = None):
    async with broker.subscribe(trip_id) as queue:
        yield format_sse("ready", json.dumps({"trip_id": trip_id, "user_id": user_id}))
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), heartbeat or HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if item is None:  # application shutdown
                return
            yield format_sse(item["type"], json.dumps(item, separators=(",", ":")))


@router.get(
    "", response_model=None, response_class=StreamingResponse,
    responses={200: {
        "description": "A text/event-stream of trip changes. Each event is named after its "
                       "type (itinerary.updated, expense.created, place.deleted, trip.updated, "
                       "member.joined, resync) and carries a JSON body; clients refetch the "
                       "affected list. A `ready` event opens the stream.",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }},
)
async def stream(
    trip_id: TripID,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> StreamingResponse:
    """Live change notifications for one trip; members only."""
    with trip_http_errors():
        await run_in_threadpool(trips.get_accessible_trip, db, trip_id, current_user.id)
    # Long-lived: hand the pooled connection back before streaming.
    db.close()
    return StreamingResponse(
        event_stream(trip_id, current_user.id), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
