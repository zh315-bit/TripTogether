# Collaborative Map P3: Geocoding Proxy

P3 adds `GET /api/v1/geocode`, a server-side proxy for explicit place search,
and lets clients save a search result as a deduplicated Trip place. No
frontend code or new dependency was added.

## Policy Compliance (public Nominatim)

Policy: https://operations.osmfoundation.org/policies/nominatim/

| Requirement | Implementation |
| --- | --- |
| Max 1 request/second for the whole application | Single-row `geocoder_throttle` table; one atomic `UPDATE ... WHERE next_allowed_at <= clock_timestamp() RETURNING` per upstream call, shared by every worker and instance. Losers get 429 immediately; nothing sleeps or holds a connection. |
| Identifying User-Agent | `GEOCODER_USER_AGENT` required; library defaults and the example placeholder are rejected. |
| Cache results | Per-process TTL+LRU cache (24 h, 1000 entries) keyed by provider, whitespace/case-normalized query and limit; empty results cached, failures not. |
| No autocomplete | API documented as explicit-search only; P5 UI will search on button/Enter only. |
| Switch off without a release | `GEOCODER_PROVIDER=disabled` (the default) plus restart returns 503 `GEOCODER_DISABLED`. |
| Back off when refused | Upstream 403/429 sets a shared 60 s cooldown. No automatic retries. |
| Attribution | Client guidance requires "© OpenStreetMap contributors" near results. |

## Design

- `GeocodingProvider` protocol with `NominatimProvider` (httpx, connect 3 s /
  read 5 s, no redirects), `FakeProvider` (offline, rejected in production)
  and disabled (`None`). Invalid configuration fails closed to disabled in
  development and aborts production startup.
- Stable identity: `provider_place_id` is OSM type initial + OSM id
  (`N123`, `W456`, `R789`); Nominatim's own `place_id` differs between servers.
- Coordinates are rounded half-even to six decimals (the Numeric(9,6) storage
  scale) and range-checked; malformed rows are skipped and duplicate OSM
  objects collapsed.
- Logging: httpx/httpcore request logs are raised to WARNING because URLs
  contain user search text. Warnings never include the query.
- Saving results: `TripPlaceCreate` accepts `provider` (`nominatim` only) and
  `provider_place_id` together, or neither (manual). A repeat inside one Trip
  is 409 `PLACE_DUPLICATE`; the Trip row lock serializes the pre-check. This
  supersedes the P2 note that clients cannot send provider fields.

## Migration 0007

Creates `geocoder_throttle (id SMALLINT PK CHECK id = 1, next_allowed_at
TIMESTAMPTZ NOT NULL)` seeded with `(1, '-infinity')`. A missing row makes
every search 429 (fails closed). `/ready` now requires nine core tables.
Downgrade drops the table only.

## Verification

```bash
cd backend
RUN_POSTGRES_TESTS=1 python -m pytest -q tests/test_geocoding.py
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m alembic upgrade head && python -m alembic check
```

`tests/test_geocoding.py` uses `httpx.MockTransport` only; CI makes no
external request. It covers parsing, request parameters and User-Agent,
refusal vs failure, single-attempt failures, timeouts, cache TTL/LRU,
configuration validation, production startup, log suppression, the endpoint
contract, the shared throttle and cooldown across provider instances, an
eight-thread race on independent connections (exactly one slot), the
fail-closed missing row, and saved-result deduplication.

Full backend suite with PostgreSQL: 723 passed, 0 failed.
