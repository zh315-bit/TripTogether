"""Server-side geocoding proxy.

Public Nominatim usage policy (https://operations.osmfoundation.org/policies/nominatim/):
at most one request per second for the whole application, an identifying
User-Agent, caching, no autocomplete, and the ability to switch the feature off.
"""
from collections import OrderedDict
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from functools import lru_cache
import logging
import threading
import time
from typing import Callable, Optional, Protocol

import httpx
from sqlalchemy import func, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import GeocoderSettings, get_geocoder_settings
from app.models import GeocoderThrottle


logger = logging.getLogger("triptogether")

MIN_INTERVAL = timedelta(seconds=1)
UPSTREAM_COOLDOWN = timedelta(seconds=60)
CACHE_TTL_SECONDS = 24 * 60 * 60
CACHE_MAX_ENTRIES = 1000
TIMEOUT = httpx.Timeout(5.0, connect=3.0)
COORDINATE_STEP = Decimal("0.000001")
OSM_TYPES = {"node": "N", "way": "W", "relation": "R"}


@dataclass(frozen=True)
class GeocodeResult:
    provider: str
    provider_place_id: str
    name: str
    address: Optional[str]
    latitude: Decimal
    longitude: Decimal


class GeocoderDisabledError(Exception):
    pass


class GeocoderBusyError(Exception):
    pass


class GeocoderUnavailableError(Exception):
    pass


class UpstreamRefusedError(GeocoderUnavailableError):
    """Upstream rate limited or blocked us; back off for every instance."""


class GeocodingProvider(Protocol):
    name: str
    throttled: bool

    def search(self, query: str, limit: int) -> list[GeocodeResult]: ...


def clean_query(query: str) -> str:
    return " ".join(query.split())


def parse_coordinate(value: object, bound: int) -> Decimal:
    if not isinstance(value, str):
        raise ValueError()
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError() from None
    if not number.is_finite():
        raise ValueError()
    # Store at the Numeric(9,6) scale used by trip_places.
    number = number.quantize(COORDINATE_STEP, rounding=ROUND_HALF_EVEN)
    if abs(number) > bound:
        raise ValueError()
    return number


def parse_nominatim_item(item: object) -> Optional[GeocodeResult]:
    """Return None for unusable rows rather than failing the whole search."""
    if not isinstance(item, dict):
        return None
    prefix = OSM_TYPES.get(item.get("osm_type"))
    osm_id = item.get("osm_id")
    display = item.get("display_name")
    if prefix is None or type(osm_id) is not int or osm_id <= 0 or not isinstance(display, str):
        return None
    try:
        latitude = parse_coordinate(item.get("lat"), 90)
        longitude = parse_coordinate(item.get("lon"), 180)
    except ValueError:
        return None
    display = display.strip()
    name = item.get("name")
    name = name.strip() if isinstance(name, str) and name.strip() else display.split(",")[0].strip()
    if not name:
        return None
    # Nominatim's own place_id differs between servers; OSM type+id is stable.
    return GeocodeResult(
        provider="nominatim", provider_place_id=f"{prefix}{osm_id}",
        name=name[:200].strip(), address=display[:500].strip() or None,
        latitude=latitude, longitude=longitude,
    )


class NominatimProvider:
    name = "nominatim"
    throttled = True

    def __init__(self, base_url: str, user_agent: str,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        self._client = httpx.Client(
            base_url=base_url, headers={"User-Agent": user_agent}, timeout=TIMEOUT,
            transport=transport, follow_redirects=False,
        )

    def search(self, query: str, limit: int) -> list[GeocodeResult]:
        # No retries: each attempt would spend the shared one-per-second budget.
        try:
            response = self._client.get("/search", params={
                "q": query, "format": "jsonv2", "limit": limit, "addressdetails": 0,
            })
        except httpx.HTTPError:
            raise GeocoderUnavailableError() from None
        if response.status_code in (403, 429):
            raise UpstreamRefusedError()
        if response.status_code != 200:
            raise GeocoderUnavailableError()
        try:
            payload = response.json()
        except ValueError:
            raise GeocoderUnavailableError() from None
        if not isinstance(payload, list):
            raise GeocoderUnavailableError()
        results: dict[str, GeocodeResult] = {}
        for item in payload:
            result = parse_nominatim_item(item)
            if result is not None:
                results.setdefault(result.provider_place_id, result)
        return list(results.values())[:limit]


FAKE_PLACES = (
    ("N1000001", "Senso-ji", "2-3-1 Asakusa, Taito, Tokyo, Japan", "35.714765", "139.796655"),
    ("W1000002", "Tokyo Tower", "4-2-8 Shibakoen, Minato, Tokyo, Japan", "35.658581", "139.745433"),
    ("N1000003", "Shibuya Crossing", "Shibuya, Tokyo, Japan", "35.659482", "139.700553"),
    ("W1000004", "Kyoto Station", "Shimogyo, Kyoto, Japan", "34.985849", "135.758766"),
    ("W1000005", "Eiffel Tower", "Champ de Mars, Paris, France", "48.858370", "2.294481"),
)


class FakeProvider:
    """Deterministic offline provider for development and tests."""
    name = "fake"
    throttled = False

    def search(self, query: str, limit: int) -> list[GeocodeResult]:
        needle = query.casefold()
        return [
            GeocodeResult("fake", place_id, name, address, Decimal(lat), Decimal(lon))
            for place_id, name, address, lat, lon in FAKE_PLACES
            if needle in name.casefold() or needle in address.casefold()
        ][:limit]


class ResultCache:
    """Process-local TTL+LRU cache; a speed and politeness layer, not the rate limiter."""

    def __init__(self, ttl_seconds: float = CACHE_TTL_SECONDS, max_entries: int = CACHE_MAX_ENTRIES,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl, self._max, self._clock = ttl_seconds, max_entries, clock
        self._entries: "OrderedDict[tuple, tuple[float, tuple[GeocodeResult, ...]]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple) -> Optional[tuple[GeocodeResult, ...]]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry[0] <= self._clock():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry[1]

    def put(self, key: tuple, results: tuple[GeocodeResult, ...]) -> None:
        with self._lock:
            self._entries[key] = (self._clock() + self._ttl, results)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def acquire_slot(db: Session) -> bool:
    """Claim the application-wide request slot with one atomic UPDATE; never sleeps."""
    now = func.clock_timestamp()
    try:
        claimed = db.execute(
            update(GeocoderThrottle)
            .where(GeocoderThrottle.id == 1, GeocoderThrottle.next_allowed_at <= now)
            .values(next_allowed_at=now + MIN_INTERVAL)
            .returning(GeocoderThrottle.id)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        # Commit before the HTTP call so no row lock or connection is held during it.
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise GeocoderUnavailableError() from None
    return claimed is not None


def start_cooldown(db: Session) -> None:
    try:
        db.execute(
            update(GeocoderThrottle).where(GeocoderThrottle.id == 1)
            .values(next_allowed_at=func.greatest(
                GeocoderThrottle.next_allowed_at, func.clock_timestamp() + UPSTREAM_COOLDOWN,
            ))
            .execution_options(synchronize_session=False)
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()


class GeocodingService:
    def __init__(self, provider: Optional[GeocodingProvider],
                 cache: Optional[ResultCache] = None) -> None:
        self.provider = provider
        self.cache = cache or ResultCache()

    def search(self, db: Session, query: str, limit: int) -> list[GeocodeResult]:
        if self.provider is None:
            raise GeocoderDisabledError()
        query = clean_query(query)
        key = (self.provider.name, query.casefold(), limit)
        cached = self.cache.get(key)
        if cached is not None:
            return list(cached)
        if self.provider.throttled and not acquire_slot(db):
            raise GeocoderBusyError()
        try:
            results = self.provider.search(query, limit)
        except UpstreamRefusedError:
            # Never log the query: it is user input and may be personal.
            logger.warning("Geocoder upstream refused request; cooling down")
            start_cooldown(db)
            raise
        except GeocoderUnavailableError:
            logger.warning("Geocoder upstream unavailable")
            raise
        self.cache.put(key, tuple(results))
        return results


def build_provider(settings: GeocoderSettings) -> Optional[GeocodingProvider]:
    if settings.provider == "nominatim":
        return NominatimProvider(settings.base_url, settings.user_agent)
    if settings.provider == "fake":
        return FakeProvider()
    return None


@lru_cache(maxsize=1)
def get_geocoding_service() -> GeocodingService:
    """One provider and cache per process; restart after changing configuration."""
    try:
        settings = get_geocoder_settings()
    except ValueError:
        logger.error("Geocoder configuration invalid; geocoding disabled")
        return GeocodingService(None)
    return GeocodingService(build_provider(settings))
