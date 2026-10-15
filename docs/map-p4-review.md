# Collaborative Map P4: Straight-Line Routes and Optimization

P4 connects itinerary items to the place pool, reports straight-line route
distances per day, suggests a shorter visiting order, and guards applying it
against concurrent edits. No migration, frontend code or dependency was added.

## API Changes

| Change | Detail |
| --- | --- |
| Itinerary `place_id` | Optional on create/PATCH; must belong to the same Trip (422 otherwise, same message for missing and foreign IDs). Response field added on v1 and legacy paths (additive). |
| `GET /api/v1/trips/{id}/itinerary/route?date=` | Versioned-only, read-only. Stops, legs and totals in km rounded to metres. |
| `POST /api/v1/trips/{id}/itinerary/optimize` | Versioned-only, read-only preview: no lock, no write. |
| Reorder `expected_item_ids` | Optional. Compared under the existing Trip row lock: current == target gives 200 (idempotent), current != expected gives 409 `ITINERARY_CONFLICT`. Omitted means unchanged behavior. |

`route_router` is included before the main itinerary router so `/route` is
not captured by `GET /{item_id}` (which would otherwise reject it as 422).

## Algorithm (`app/services/routing.py`, pure functions)

- Haversine with the IUGG mean Earth radius, clamped for floating-point
  rounding; antimeridian and poles need no special case.
- Anchors: unlocated items, items with `start_time`, and the first item when
  `keep_first` (default). Anchors keep their exact slots; only maximal runs of
  movable items between anchors are reordered, so no item crosses an
  appointment.
- Each run is an open path whose fixed neighbours are the last located stop
  already decided and the next located anchor, if any. Unlocated anchors are
  transparent to distance, matching how `/route` measures.
- Per run: greedy nearest neighbour from every possible first stop, each
  improved by 2-opt; best total wins, ties broken by order so results are
  deterministic. A run with only a fixed end is solved from that end and
  reversed (distances are symmetric).
- Guard: if the proposal is not strictly shorter, the original is returned
  with `changed: false`.
- Cap: 50 items per day (422). 50 free points take under 0.1 s locally.

Measured against brute force on 2,100 seeded random cases with 2-7 points:
98.4% exactly optimal, worst case 10.4% longer. Seeding greedy from every
first stop (not only the fixed start) and solving fixed-end runs in reverse
raised fixed-start cases from 88% to 98.5% optimal.

## Concurrency

Apply goes through the existing reorder path, which locks the Trip row and
validates the complete day. `expected_item_ids` closes the remaining gap: a
preview applied after someone else reordered the same set of items now gets
409 instead of silently overwriting. Added items change the set and also
409. No version column or distributed lock was needed.

## Verification

```bash
cd backend
python -m pytest -q tests/test_routing.py
RUN_POSTGRES_TESTS=1 python -m pytest -q tests/test_itinerary_routes.py
RUN_POSTGRES_TESTS=1 python -m pytest -q
```

New suites: `test_routing.py` (haversine references, brute-force quality,
endpoints, ties, anchors, never-longer property, timing) and
`test_itinerary_routes.py` (binding, snapshot, cross-Trip rejection, route,
preview immutability, timed/unlocated anchors, cap, validation, guarded and
idempotent apply, stale preview). `test_itinerary_concurrency.py` adds a real
two-connection race: one 200, one 409, complete order.

Full backend suite with PostgreSQL: 778 passed, 0 failed.
