"""A ready-made demo trip so a visitor can try the app without registering.

Three demo members share one Kyoto trip with places, a routed itinerary and
expenses split three different ways. `POST /auth/demo` signs the visitor in
as one of them. The trip is rebuilt from scratch when it is missing or older
than RESET_AFTER, so visitors' edits never pile up for long. Enabled only when
DEMO_MODE is set; production without it answers 404.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import secrets
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import _get_setting
from app.core.security import hash_password
from app.models import Trip, TripMember, User
from app.schemas.expense import ExpenseCreate
from app.schemas.itinerary import ItineraryItemCreate
from app.schemas.trip import TripCreate
from app.schemas.trip_place import TripPlaceCreate
from app.services.expenses import create_expense
from app.services.itinerary import create_item
from app.services.trip_places import create_place
from app.services.trips import create_trip


DemoMember = Literal["mika", "jonas", "aiko"]
MEMBERS: dict[str, str] = {"mika": "Mika", "jonas": "Jonas", "aiko": "Aiko"}
USERNAME = "{}_demo"
EMAIL = "{}@demo.triptogether.app"
TRIP_NAME = "Kyoto long weekend"
RESET_AFTER = timedelta(hours=6)
START = date(2027, 4, 2)

# (name, latitude, longitude, proposed by)
PLACES = [
    ("Fushimi Inari Taisha", 34.9671, 135.7727, "mika"),
    ("Kiyomizu-dera", 34.9949, 135.7850, "mika"),
    ("Nishiki Market", 35.0050, 135.7649, "aiko"),
    ("Kinkaku-ji", 35.0394, 135.7292, "jonas"),
    ("Arashiyama Bamboo Grove", 35.0170, 135.6717, "jonas"),
]
# (title, day offset, start time, place name or None, notes)
ITEMS = [
    ("Torii gates at sunrise", 0, "07:30:00", "Fushimi Inari Taisha", "Go early; the upper trail is quiet before 9."),
    ("Kiyomizu-dera and Sannenzaka", 0, "13:00:00", "Kiyomizu-dera", None),
    ("Dinner at Nishiki Market", 0, "18:30:00", "Nishiki Market", "Aiko booked the counter seats."),
    ("Golden Pavilion", 1, "09:00:00", "Kinkaku-ji", None),
    ("Bamboo grove walk", 1, "14:00:00", "Arashiyama Bamboo Grove", "Rent bikes at the station."),
    ("Pack and check out", 2, "10:00:00", None, None),
]


class DemoDisabledError(Exception):
    pass


class DemoUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class DemoSession:
    user: User
    trip_id: int


def demo_enabled() -> bool:
    return str(_get_setting("DEMO_MODE", "0") or "").strip().lower() in ("1", "true", "yes")


def _users(db: Session) -> dict[str, User]:
    users = {}
    for key, name in MEMBERS.items():
        user = db.scalar(select(User).where(User.username == USERNAME.format(key)))
        if user is None:
            # Nobody signs in with this password: demo sessions are issued directly.
            user = User(username=USERNAME.format(key), email=EMAIL.format(key),
                        password_hash=hash_password(secrets.token_urlsafe(32)))
            db.add(user)
            db.flush()
        users[key] = user
    db.commit()
    return users


def _demo_trip(db: Session, owner: User) -> Optional[Trip]:
    return db.scalar(select(Trip).where(Trip.owner_id == owner.id, Trip.name == TRIP_NAME)
                     .order_by(Trip.id.desc()))


def _seed_trip(db: Session, users: dict[str, User]) -> Trip:
    mika, jonas, aiko = users["mika"], users["jonas"], users["aiko"]
    trip = create_trip(db, TripCreate(
        name=TRIP_NAME, destination="Kyoto, Japan", start_date=START, end_date=START + timedelta(days=2),
    ), mika.id)
    for member in (jonas, aiko):
        db.add(TripMember(trip_id=trip.id, user_id=member.id, role="member"))
    db.commit()
    places = {}
    for name, latitude, longitude, who in PLACES:
        places[name] = create_place(db, trip.id, users[who].id, TripPlaceCreate(
            name=name, latitude=latitude, longitude=longitude)).id
    for title, offset, start, place, notes in ITEMS:
        create_item(db, trip.id, mika.id, ItineraryItemCreate(
            title=title, date=START + timedelta(days=offset), start_time=start,
            place_id=places.get(place), notes=notes, location=place,
        ))
    create_expense(db, trip.id, mika.id, ExpenseCreate(
        description="Ryokan night", amount="180.00", currency="USD", paid_by_user_id=mika.id,
        expense_date=START, split_method="shares",
        splits=[{"user_id": mika.id, "weight": 1}, {"user_id": jonas.id, "weight": 2}, {"user_id": aiko.id, "weight": 1}],
    ))
    create_expense(db, trip.id, jonas.id, ExpenseCreate(
        description="Kaiseki dinner", amount="110.00", currency="USD", paid_by_user_id=jonas.id,
        expense_date=START, split_method="exact",
        splits=[{"user_id": mika.id, "amount": "30.00"}, {"user_id": jonas.id, "amount": "50.00"},
                {"user_id": aiko.id, "amount": "30.00"}],
    ))
    create_expense(db, trip.id, aiko.id, ExpenseCreate(
        description="Bus day passes", amount="21.00", currency="USD", paid_by_user_id=aiko.id,
        expense_date=START + timedelta(days=1), participant_user_ids=[mika.id, jonas.id, aiko.id],
    ))
    return trip


def ensure_demo(db: Session, reset: bool = False) -> tuple[dict[str, User], Trip]:
    """Create the demo members once, and rebuild the demo trip when stale or asked to."""
    try:
        users = _users(db)
        trip = _demo_trip(db, users["mika"])
        if trip is not None and (reset or datetime.now(timezone.utc) - trip.created_at > RESET_AFTER):
            db.delete(trip)
            db.commit()
            trip = None
        if trip is None:
            trip = _seed_trip(db, users)
        return users, trip
    except SQLAlchemyError:
        db.rollback()
        raise DemoUnavailableError() from None


def demo_session(db: Session, member: str) -> DemoSession:
    if not demo_enabled():
        raise DemoDisabledError()
    users, trip = ensure_demo(db)
    return DemoSession(user=users[member], trip_id=trip.id)
