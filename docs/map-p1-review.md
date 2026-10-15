# Collaborative Map P1: Places and Itinerary Associations

P1 adds storage and integrity constraints only. APIs, geocoding, map UI and
route optimization remain future phases requiring separate authorization.
The final P1 field definitions were supplied in the development chat because
the revised plan had not been saved as a separate file.

## Schema

| `trip_places` column | Type | Nullable | Default |
| --- | --- | --- | --- |
| id | Integer, primary key | No | Identity |
| trip_id | Integer, references trips.id | No | — |
| proposed_by_user_id | Integer, references users.id, indexed | No | — |
| name | String(200) | No | — |
| address | String(500) | Yes | — |
| latitude | Numeric(9,6) | No | — |
| longitude | Numeric(9,6) | No | — |
| provider | String(32) | No | `manual` (database default) |
| provider_place_id | String(256) | Yes | — |
| note | String(500) | Yes | — |
| created_at | DateTime(timezone=True) | No | `now()` |
| updated_at | DateTime(timezone=True) | No | `now()`; SQLAlchemy updates use `statement_timestamp()` |

`itinerary_items.place_id` is a nullable Integer with no default or backfill.
Existing itinerary rows retain all original values and get a NULL association.
The requested UUID types conflict with the repository's Integer/Identity keys;
the implementation keeps the established types without converting existing IDs.
Coordinates use Decimal in Python; NULL and out-of-range values (including NaN)
are rejected. Name and provider must contain non-space text, matching the
existing model constraints. Raw SQL updates do not automatically update
timestamps, consistent with the existing project convention.

## Integrity and Indexes

- `fk_trip_places_trip`: deleting a Trip cascades to its places.
- `uq_trip_places_trip_id_id`: non-deferrable UNIQUE(trip_id, id), providing
  the candidate key needed by the composite itinerary foreign key. Its
  index also serves lookups and cascade deletion by trip_id.
- `fk_trip_places_proposer`: ON DELETE RESTRICT, matching itinerary/expense
  creator references. The proposer drives per-member map colors and must be
  set by the server from the authenticated user, never by the client.
- `ck_trip_places_provider_place_id`: `provider = 'manual'` exactly when
  `provider_place_id IS NULL`, so imported places always carry an external
  identity and cannot bypass deduplication with a NULL identifier.
- `uq_trip_places_provider_place`: UNIQUE(trip_id, provider, provider_place_id).
  PostgreSQL's default NULL-distinct behavior permits multiple manual places;
  non-NULL provider identifiers cannot be imported twice within one Trip.
- `fk_itinerary_trip_place`: FOREIGN KEY(trip_id, place_id) references
  trip_places(trip_id, id), with `ON DELETE SET NULL (place_id)`. Its default
  MATCH SIMPLE permits old unlinked rows. Inserts and updates cannot link a
  different Trip's place or move a linked place/item across Trips.
- `ix_itinerary_items_trip_id_place_id`: supports reference lookup and deletion
  updates. Existing Trip, creator, position and date constraints remain intact.
- Deleting a place preserves the entire itinerary row except place_id, including
  trip_id, location and timestamps. This is enforced by PostgreSQL, including
  direct SQL deletes; deleting a Trip still removes its itinerary items.

## Migration and Readiness

Alembic head was inspected as `0005` before generating revision `0006` with
down_revision `0005`. Previously applied revisions are unchanged. Upgrade
creates the new table, adds the nullable column, and creates its FK/index;
it does not rewrite legacy location text or populate associations.

Column-specific SET NULL requires PostgreSQL 15+ and SQLAlchemy 2.0.40+.
The migration checks the PostgreSQL version before online DDL. CI and Docker
use PostgreSQL 16; local verification uses PostgreSQL 17. Production version
must be checked before a separately authorized release. `/ready` dynamically
requires the new Alembic head and now includes trip_places in its table checks.
Deploying the new backend before migrating would therefore return NOT_READY.

Downgrade drops the new associations and place pool, preserving users, Trips
and itinerary rows/text. It necessarily loses newly created place data; back
that data up before any future downgrade. Upgrade adds constraints/indexes to
itinerary_items and takes DDL locks; schedule a controlled release for a large
database. No production migration or environment change was performed.

## Service Requirements for P2

The composite foreign key enforces consistency, not access control. Future
place operations and itinerary binding must first call the existing Trip
membership/ownership checks, query the place by both trip_id and place_id,
and preserve existing authorization, error and locking conventions. P1 does
not expose place_id in request/response schemas or change any API behavior.

Decisions fixed before P2 (API contract): coordinates are JSON numbers in
responses while storage remains Numeric(9,6); latitude/longitude are immutable
after creation (PATCH may change only name, address and note) so coordinates
can never drift from provider_place_id. To move a place, delete and recreate it.

Revision note: 0006 was amended before it was pushed or applied anywhere
outside disposable test schemas, adding proposed_by_user_id, note and the
provider identity check. Do not amend it after it reaches a shared database.

## Verification

Use a disposable local PostgreSQL database, never production credentials:

```bash
cd backend
RUN_POSTGRES_TESTS=1 python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q tests/test_trip_place_migrations.py
python -m alembic heads
python -m alembic upgrade head
python -m alembic check
# Disposable database only: removes the new place data.
python -m alembic downgrade 0005
python -m alembic upgrade head
python -m alembic check
```

Set DATABASE_URL explicitly to the disposable database. Existing fixtures
migrate private schemas and roll them back. The new tests cover metadata,
defaults, ORM timestamp updates, coordinates and NULLs, provider deduplication,
same-Trip links, cross-Trip inserts/updates, missing references, SQL/ORM deletion,
cascade scope, readiness, and production-0005 upgrade/downgrade preservation.
Existing migration tests were updated to expect the expanded head schema;
none were removed, skipped or weakened. Backend lint/format/typecheck tooling
is not configured; syntax compilation and whitespace checks supplement tests.
