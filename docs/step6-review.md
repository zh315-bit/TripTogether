# Step 6: Trip Model, CRUD and Owner Authorization

## OpenTrip Reference Review

Before edits, read README, AGENT, RECORD, Step 4/5 reviews and the existing
backend. Rechecked remote HEAD of `https://github.com/stvlynn/OpenTrip.git`:
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`, unchanged from Step 5.
The web tool returned no usable content; approved git access verified HEAD and
the existing local checkout supplied actual source. No implementation was copied.

Inspected sources:

- `apps/api/prisma/schema.prisma`: trips, trip_members, trip_days, stops,
  expenses, reservations and their relations.
- `apps/api/src/domain/trip/types.ts`: TripSnapshot, TripStatus, MemberSnapshot,
  TripIntake and day/stop/expense snapshots.
- `apps/api/src/domain/trip/trip.ts`: create, resolveCreateSchedule, permissions,
  rename and child resource operations.
- `apps/api/src/application/use-cases.ts`: TripService creation, list, detail,
  rename, readable/editable boundaries and geo/cover enrichment.
- `apps/api/src/application/dto.ts`: safe aggregate-to-HTTP projection.
- `apps/api/src/interfaces/http/app.ts`: guarded Trip routes and input schemas.
- `apps/api/src/infrastructure/persistence/trip-repository.db.ts`: SQL listing,
  transactional Trip/member/day creation, persisted edits.

### Actual Model and Ownership

Prisma trips fields: id, title, start_date, end_date, status, currency,
cover_color, owner_id, created_at, version, agent_seed_pending, cover_url, intake.
Related collections: agent_messages, agent_suggestions, expenses, reservations,
stops, trip_days, trip_invites, trip_members.

IDs are strings. owner_id is nullable String with no Prisma User relation/FK
declared. The authenticated HTTP user becomes TripOwner; domain create assigns
ownerId and creates a first member with userId, role owner and canInvite true.
trip_members has role/editor/viewer/owner semantics, optional user_id, display
metadata and unique (trip_id,user_id). This does not justify copying its nullable
owner or credential-free legacy/demo paths into TripTogether.

### Dates, Destination and Lifecycle

Trip start/end and day dates are strings, documented as ISO calendar dates;
unknown dates can be empty strings. The create schedule derives day count,
uses server-local today as a fallback, and UTC arithmetic for day offsets.
Trip-level timezone field was not found. Reservations have their own timestamps
and timezone, which is a separate concept and outside our scope.

Destination is not a dedicated Trip column: it is an intake JSON label with
optional destinationLat/Lng, also used for the first day's city. The service
can enrich it through geo lookup and cover images; stops have coordinates.
TripTogether needs a plain destination label now, not those map dependencies.

TripStatus is active | planning | settled; create sets planning. No complete
Trip lifecycle transition workflow, draft/completed/archived state model, or
whole-Trip DELETE route/service was found in the inspected current Trip modules.
Do not confuse DELETE day/reservation with deleting the Trip itself.
The schema has ON DELETE CASCADE on Trip child resources, but that alone is not
evidence of an exposed deletion workflow or an archive strategy.
Trips has created_at but no updated_at column; version is a mutation counter.

### CRUD and Authorization

HTTP guards require a session. Create validates input, builds TripOwner from
the authenticated user, creates the aggregate and persists Trip/member/days
in a transaction. PATCH supports rename or clearing the agent-seed flag,
not TripTogether's four-field partial update.
loadReadable denies nonmembers with 404; loadEditable denies nonmembers with
404 and read-only members with 403.

The list query filters membership but also allows trips without any real-user
member (legacy/demo compatibility). We deliberately do not adopt that fallback.
TripTogether queries strictly by owner_id.

Adopted: authenticated ownership, domain/service validation, transactional
mutations, explicit response schemas, and 404 to conceal inaccessible resources.
Not adopted: aggregate snapshots/repositories, members/roles, demo fallbacks,
itinerary days/stops, currency/expenses, booking, map enrichment, covers, voting,
comments, invitations, agents/realtime/versioning. These are not needed for the
requested owner-only CRUD workflow.

## TripTogether Design

| Field | PostgreSQL Type | Constraint | Why Needed |
| --- | --- | --- | --- |
| id | INTEGER Identity | PK, NOT NULL | stable identity matching User convention |
| name | VARCHAR(120) | NOT NULL, nonblank CHECK | readable trip name |
| destination | VARCHAR(200) | NOT NULL, nonblank CHECK | simple place label without maps |
| start_date | DATE | NOT NULL | first calendar day |
| end_date | DATE | NOT NULL, >= start_date CHECK | inclusive last day; same-day allowed |
| owner_id | INTEGER | NOT NULL, FK users.id RESTRICT, index | ownership and SQL-filtered access |
| created_at | TIMESTAMPTZ | NOT NULL, now() default | creation instant |
| updated_at | TIMESTAMPTZ | NOT NULL, now() default | latest actual ORM edit instant |

No status workflow is needed for CRUD, so no unused status/metadata/JSON fields.
Dates are required for this first API; no uncertain-date planning semantics.
Name/destination trim edges and reject blank/overlong text, null characters and
invalid Unicode. The database CHECK protects empty/space-only strings; API
validation additionally handles Unicode whitespace.

created_at uses the same strategy as User. SQLAlchemy onupdate sets updated_at
to database statement_timestamp() when an UPDATE occurs. Transaction-start
now() would not advance across savepoints in a long transaction. An empty or
identical PATCH emits no UPDATE and preserves the timestamp. This is not a
database trigger; direct handwritten SQL writers must update the field themselves.

Only Trip.owner is mapped for navigating from Trip to its authenticated owner.
ForeignKey creates a PostgreSQL constraint; relationship() provides Python object
navigation and does not replace that constraint. No inverse User.trips collection
or cascade behavior was necessary. RESTRICT preserves referential integrity:
deleting a User who still owns Trips fails, rather than orphaning/deleting them.
No user-delete API was added.

## Migration Evolution

Autogenerated and manually reviewed revision 0002, parent 0001.
Upgrade creates trips, the owner index, FK, nonblank/date CHECKs, NOT NULL
columns and timestamp defaults. Downgrade drops only its index and trips.
0001 remains byte-for-byte unchanged.

Changing an already-applied 0001 would make old installations and fresh
installations disagree. A new ordered revision lets both reach the same schema.
Reversibility restores structure, not deleted trip data. Tests downgrade only
private schemas and confirm an existing User survives 0002 -> 0001 -> 0002.

## Request Flow and Policy

```text
JWT -> get_current_user -> TripCreate -> Router -> create_trip
-> owner_id from current_user.id -> Session -> PostgreSQL -> TripResponse

PATCH -> current_user -> owned row SELECT FOR UPDATE
-> merge only supplied fields -> validate final date pair
-> ORM UPDATE -> commit -> refresh -> TripResponse
```

Schemas reject id, owner_id and timestamps as extra input. Ownership is a
server-controlled security field, never chosen from a request body.
All five routes use the existing get_current_user and get_db dependencies.
FastAPI shares that request's dependency result; Sessions are not global.

get_owned_trip queries both trip ID and owner ID. Missing and other-owner
resources use identical 404 responses for read/update/delete. A 403 means
"known resource, forbidden"; our 404 avoids exposing whether a guessed ID exists.
Lists apply owner filtering in SQL, never load all users' trips then filter in
Python. The owner index supports that repeated query. Lists are currently
unpaginated and ordered by id; pagination is not silently introduced.

Authentication answers who the JWT identifies; authorization checks whether
that identity owns this Trip. No TripMember or general permissions framework.

PATCH means partial modification; omitted fields retain their values. PUT
would describe replacement with the full representation. Explicit null is
invalid for these required fields. Empty PATCH is an authenticated, authorized
no-op returning the current Trip.

Both create schema and database check enforce end >= start. PATCH must merge
the stored opposite date before checking: moving only start beyond old end is
invalid. Locking the owned row serializes simultaneous PATCH/DELETE mutations,
so a waiting PATCH reads the preceding committed state before merging.
There is no version-based stale-client detection; same-field writes are
last-writer-wins. The CHECK remains a final guard against invalid direct writes.

Service functions own queries, ownership, mutations and transactions.
A small shared context manager rolls back SQLAlchemy errors (including
IntegrityError) and raises a safe service exception. Another local router
context manager consistently maps expected errors to HTTP 404/422/503.
No raw SQL, driver exception or constraint name is exposed.
Delete is a hard delete returning 204 with no body; no child resources exist yet.

## Seven Files to Read

1. `backend/app/models/trip.py`: start with table constraints and owner_id,
   then DATE/timestamp mapping and owner relationship. This is persistence.
2. `backend/migrations/versions/0002_create_trips_table.py`: compare upgrade
   to that model, then downgrade. This is how the actual schema evolves.
3. `backend/app/schemas/trip.py`: inspect TripCreate/TripUpdate, forbidden
   extras, null rejection, dates and TripResponse. This is the HTTP boundary.
4. `backend/app/services/trips.py`: start at get_owned_trip, then update_trip.
   Follow owner-filtered SQL, row locking, merged validation, commit/rollback.
5. `backend/app/api/trips.py`: trace get_current_user into service owner_id,
   then the shared error mapping and 201/204 statuses.
6. `backend/tests/test_trips.py`: read Alice/Bob lifecycle/isolation, invalid
   single-date PATCH, server-field injection and anonymous-route tests.
7. `backend/tests/test_trip_migrations.py`: review private-schema reversal,
   database NOT NULL/FK/CHECK rejection, relationship and timestamp tests.

## Verification

README contains runnable startup/migration/test commands and create JSON.
Final default suite: 167 passed, 48 skipped, 0 failed.
Final PostgreSQL suite: 215 passed, 0 skipped, 0 failed.
All prior authentication/registration/database/migration tests are included.
No SQLite. Live tests reuse the existing schema/transaction/savepoint fixtures.

Real development DB upgrade, current 0002, alembic check and SELECT 1 succeeded.
psql `\d trips` confirmed eight columns, identity PK, owner index, three CHECKs
and owner FK ON DELETE RESTRICT. A SQL SELECT during the real HTTP workflow
confirmed dates, owner-to-User identity, preserved created_at and later updated_at.
Alice create/list/detail/update/delete, Bob's three 404 denials and anonymous
five-route 401 denials passed. Owner injection and invalid merged dates got 422.
Temporary manual users/trips were cleaned up by exact task-created identities;
baseline/final counts were 0/0 and no test schemas remained.

No real secrets, hashes or JWTs were printed. The temporary Uvicorn server used
a process-only generated key and was stopped after verification.

## Problems Encountered

The external disk again produced `._0002_create_trips_table.py`. Alembic tried
to import binary metadata, failing setup. Removed generated AppleDouble
metadata with the already-documented `dot_clean -m migrations/versions`;
did not patch Alembic or alter 0001.
The new invalid-token test initially forgot the existing jwt_environment
fixture, so it got configuration-missing 503. Added the fixture; production
auth behavior was not changed. Reruns passed completely.
The older migration test assumed head was 0001/users-only; advanced its head
expectation to 0002/users+trips while preserving its full reversal assertions.

## Interview Questions

1. How are User and Trip related? One User owns many Trips through owner_id;
   each Trip has one required owner.
2. What is a foreign key? trips.owner_id must reference an existing users.id.
3. ForeignKey vs relationship? PostgreSQL enforces the former; Trip.owner is
   Python ORM navigation provided by the latter.
4. Why forbid client owner_id? Otherwise Alice could assign or impersonate Bob;
   the router uses the verified current_user.id.
5. How is cross-user access prevented? SQL includes owner_id on collection and
   individual lookup; mutations reuse get_owned_trip.
6. Authentication vs authorization? JWT identifies Alice; owner filtering
   decides whether Alice can access this particular Trip.
7. Why PATCH? A name-only edit should preserve destination and dates, without
   requiring a full replacement body as PUT would.
8. Why 404 instead of 403? Bob receives the same answer for Alice's ID and a
   nonexistent ID, reducing resource-existence disclosure.
9. How validate one-date PATCH? Lock/load the owned row, merge supplied fields
   with stored values, then check end >= start before changing the ORM object.
10. What does 0002 do? Adds trips, constraints and owner index; reversal leaves
    users intact. It does not rewrite 0001.
11. How guarantee referential integrity? A real PostgreSQL FK rejects missing
    owners and RESTRICT prevents deleting referenced users.
12. How test isolation? Register/login Alice and Bob in PostgreSQL, create both
    trips, compare lists and reject Bob's GET/PATCH/DELETE of Alice's Trip.
13. Why DATE? Travel days are calendar dates, not timezone-specific seconds.
14. Does updated_at have a trigger? No: SQLAlchemy renders statement_timestamp()
    on actual updates. Raw SQL must explicitly maintain it.
15. What happens on DB failure? Roll back the session and return generic 503;
    never expose driver SQL or internal constraint details.
16. Why not filter in Python? SQL filtering avoids loading other users' rows
    and keeps the access boundary close to the data query.

## Next Step

Step 7: Trip Membership + Invitation. Not implemented here.
