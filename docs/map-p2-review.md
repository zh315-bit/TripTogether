# Collaborative Map P2: Trip Place CRUD

P2 exposes the P1 `trip_places` table through five versioned endpoints. It adds
no migration, frontend code, dependency, geocoding call or itinerary binding.

## Endpoints

| Method | Path | Success |
| --- | --- | --- |
| POST | /api/v1/trips/{trip_id}/places | 201 TripPlaceResponse |
| GET | /api/v1/trips/{trip_id}/places | 200 TripPlaceResponse[] ordered by id; `[]` when empty |
| GET | /api/v1/trips/{trip_id}/places/{place_id} | 200 TripPlaceResponse |
| PATCH | /api/v1/trips/{trip_id}/places/{place_id} | 200 TripPlaceResponse |
| DELETE | /api/v1/trips/{trip_id}/places/{place_id} | 204 |

There is no legacy alias. Existing routes and their responses are unchanged.

## Authorization and Isolation

- Every operation first calls `get_accessible_trip`: owner or accepted member.
  Anonymous is 401; pending invitees, outsiders and missing Trips get
  `TRIP_NOT_FOUND` 404.
- Places are looked up by both `trip_id` and `place_id`, so a user who can
  access two Trips still cannot use one Trip's place ID through the other
  (`PLACE_NOT_FOUND` 404, data unchanged).
- Writes lock the parent Trip row (`for_update=True`), like itinerary and
  expense writes. Any member may edit or delete any place, matching the
  documented collaboration model.

## Contract Decisions

- Coordinates: JSON numbers in and out; storage stays Numeric(9,6). Input is
  converted with `Decimal(repr(value))`, so the exact spelling is kept and more
  than six decimal places is rejected rather than silently rounded.
- Coordinates are immutable after creation; PATCH schema forbids them.
- Server-owned fields (`id`, `trip_id`, `proposed_by_user_id`, `provider`,
  `provider_place_id`, timestamps) are rejected as unknown fields (422).
- Text: name 1-200 (trimmed), address 1-500 (trimmed, nullable), note up to
  500 (not trimmed, nullable); valid Unicode, no NUL characters.
- Errors use the v1 envelope. New codes: `PLACE_NOT_FOUND`,
  `PLACES_UNAVAILABLE`. Database failures roll back and expose no SQL.
- Delete relies on `fk_itinerary_trip_place ... ON DELETE SET NULL (place_id)`.

## Files

- `backend/app/schemas/trip_place.py`
- `backend/app/services/trip_places.py`
- `backend/app/api/trip_places.py`
- `backend/app/main.py` (v1-only registration, `places` OpenAPI tag)
- `backend/tests/test_trip_places.py`
- `backend/tests/test_api_contract.py` (operation counts 32/30/28)
- `docs/api-inventory.md`, `docs/authorization-matrix.md`,
  `docs/client-integration.md`

## Verification

```bash
cd backend
RUN_POSTGRES_TESTS=1 python -m pytest -q tests/test_trip_places.py
RUN_POSTGRES_TESTS=1 python -m pytest -q
```

Full backend suite with PostgreSQL: 652 passed, 0 failed.
