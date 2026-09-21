# Step 7: Membership, Invitations and Member-Aware Authorization

## Completed

Implemented TripMember, TripInvitation, owner backfill, owner membership on
creation, registered-user invitations, recipient inbox, accept/reject, member
list and member-readable Trip APIs. No new dependencies. No Step 8 features.

## OpenTrip Reference Review

Read the required project documents and Step 6 implementation first.
Verified current remote HEAD of `https://github.com/stvlynn/OpenTrip.git`:
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`, unchanged. The web tool returned no
usable content; approved git access and the local pinned checkout supplied
actual source. No reference code was copied.

Inspected:

- `apps/api/prisma/schema.prisma`: trip_members, trips, trip_invites,
  trip_invite_allowed_emails and trip_invite_acceptances.
- `apps/api/src/domain/trip/trip.ts` and `types.ts`: create, initial owner
  member, memberByUserId, permissionsFor and addMember.
- `apps/api/src/application/use-cases.ts`: readable/editable service boundaries.
- `apps/api/src/application/invite-service.ts`: create/regenerate/preview/accept.
- `apps/api/src/domain/invite/invite.ts` and `types.ts`: usability and states.
- `apps/api/src/infrastructure/persistence/trip-repository.db.ts`: transactional
  Trip creation and member insertion with conflict-ignore.
- `apps/api/src/infrastructure/persistence/invite-repository.db.ts`: hashed-token
  lookup, invite creation, allowed emails and acceptance records.
- `apps/api/src/interfaces/http/app.ts`: validation and authenticated invitation
  routes, actor from auth context.
- `apps/api/test/invite-service.test.ts` and related Trip member tests: permission,
  expiry, email restrictions, repeat acceptance and regeneration expectations.

### Owner and Membership

Trip.create sets ownerId to the authenticated actor and creates a first member
with userId=owner.id, role=owner, canInvite=true. Repository create inserts Trip,
members and days in one transaction.
Prisma trip_members fields are id, trip_id, name, short_name, initials,
avatar_bg, avatar_fg, is_current_user, sort_order, image, can_invite, role,
user_id. user_id is optional; there is a unique (trip_id,user_id) constraint
and a Trip FK with cascade. No User FK is declared there.
This represents participation by linking real users to trips, with extra
support for demo members. Roles are owner/editor/viewer, not our owner/member.

permissionsFor is based on the matching membership: any non-viewer can edit;
canInvite is a separate flag. Pure legacy/demo trips have a permissive fallback.
TripService uses 404 for nonmembers and 403 for read-only mutations.
We do not adopt the legacy fallback or their more permissive edit policy.

### Invitations

There is a separate trip_invites model: string id, trip_id, token_hash,
created_by, access_scope, role, can_invite, status, expires_at, created_at.
Allowed email addresses and acceptance history are separate tables.
Create generates a random opaque token, stores its SHA-256 hash, and returns
the plaintext once for a link. Access can be anyone or restricted_emails.
Invited roles are editor/viewer. States are active/revoked, with expiry checked
from expires_at. They are not pending/accepted/rejected per-recipient records.

Accept uses the authenticated actor. Existing members receive successful
idempotent acceptance (joined=false). A new member is added, then an acceptance
record is written. In the inspected service these are separate repository calls;
we did not find one shared transaction around both, and do not assume one.
Repository member insertion uses composite uniqueness/conflict-ignore.
Tests inspected use in-memory repositories; they do not demonstrate our required
real PostgreSQL concurrent HTTP behavior.

Current inspected code did not contain member removal, leave-trip or ownership
transfer workflows. No per-recipient pending inbox/reject workflow like this
task's design was found. We do not infer those features from invite-link support.

Adopted: owner included among participants, association uniqueness, separate
invitation concepts, authenticated actor identity, centralized access helpers.
Not adopted: public links/tokens, expiry/revocation, email allowlists, extra roles,
canInvite permissions, legacy users, UI profile copies, realtime or their
idempotent acceptance semantics. Our required strict state machine differs.

## Domain Design

```text
User ----< TripMember >---- Trip
            role
            joined_at

User (inviter / invitee) ----< TripInvitation >---- Trip
                                status
                                responded_at
```

One user can participate in many Trips; one Trip has many users. A single
Trip.member_id would represent only one participant, so it cannot model this.
TripMember has role and joined_at, making it an association object, not just
a two-key association table.

Trip.owner_id is the only authoritative ownership value (Option A). Membership
role is a stored classification maintained by application creation/acceptance
and the backfill, never an alternate authorization source. Member list output
derives effective owner/member from Trip.owner_id so even corrupt role data
does not masquerade as owner. A test changes Bob's stored role to owner and
confirms his write remains forbidden and displayed role remains member.

We do not add cross-table synchronization triggers or ownership transfer.
Direct SQL writers must maintain membership consistency; CHECK constraints
alone cannot prove that a stored owner role matches another table's owner_id.
API clients cannot assign roles, owners, inviters, invitees or statuses.

## Files Changed

New:
- `backend/app/models/trip_member.py`, `trip_invitation.py`: persistence.
- `backend/app/schemas/membership.py`: validated request and safe response types.
- `backend/app/services/memberships.py`: scoped safe member listing.
- `backend/app/services/invitations.py`: invitation rules, transactions/errors.
- `backend/app/api/invitations.py`: four thin invitation endpoints.
- `backend/migrations/versions/0003_create_membership_and_invitations.py`.
- `backend/tests/test_membership.py`, `test_membership_migrations.py`,
  `test_membership_concurrency.py`.
- `docs/step7-review.md`.

Modified:
- `backend/app/models/__init__.py`: metadata registration.
- `backend/app/schemas/user.py`: extracts the same email policy into a shared
  NormalizedEmail annotation; registration/login behavior is unchanged.
- `backend/app/services/trips.py`: atomic Owner member creation and SQL access scope.
- `backend/app/api/trips.py`: member-readable detail and member-list route.
- `backend/app/main.py`: mounts invitation router.
- `backend/tests/test_user_migrations.py`, `test_trip_migrations.py`: advance
  latest-head expectations, preserving previous reversal checks.
- `README.md`, `RECORD.md`: usage, verification and development record.

## TripMember Model

| Field | Type | Constraint | Purpose |
| --- | --- | --- | --- |
| id | INTEGER Identity | PK, NOT NULL | stable association ID |
| trip_id | INTEGER | NOT NULL, FK trips.id CASCADE | participating Trip |
| user_id | INTEGER | NOT NULL, FK users.id RESTRICT, index | participant |
| role | VARCHAR(6) | NOT NULL, CHECK owner/member | stored classification |
| joined_at | TIMESTAMPTZ | NOT NULL, default now() | participation timestamp |

UNIQUE(trip_id,user_id) allows Alice in Trip 1 and Trip 2, but not Alice twice
in Trip 1. Its index also supports Trip member lookup.
Strings plus CHECK are readable in SQL and straightforward to evolve with
Alembic without managing a separate PostgreSQL enum type.

## Invitation Model

| Field | Type | Constraint | Purpose |
| --- | --- | --- | --- |
| id | INTEGER Identity | PK, NOT NULL | invitation identity |
| trip_id | INTEGER | NOT NULL, FK CASCADE, index | target Trip |
| inviter_id | INTEGER | NOT NULL, User FK RESTRICT | verified Owner actor |
| invitee_id | INTEGER | NOT NULL, User FK RESTRICT, index | registered recipient |
| status | VARCHAR(8) | NOT NULL, default pending, CHECK | pending/accepted/rejected |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | sent timestamp |
| responded_at | TIMESTAMPTZ | nullable only while pending | decision timestamp |

Additional checks forbid self-invites and require response time iff terminal.
A unique partial index on (trip_id,invitee_id) WHERE status='pending' preserves
decision history while allowing a new invitation after rejection.
User deletion is not implemented; RESTRICT avoids silently discarding history.
Trip deletion cascades both memberships and invitation history.

## Migration 0003

Autogenerated then manually reviewed/formatted. Creates the two tables,
indexes, FKs, NOT NULL/CHECK/unique constraints. Backfill:

```sql
INSERT INTO trip_members (trip_id, user_id, role, joined_at)
SELECT id, owner_id, 'owner', created_at FROM trips
ON CONFLICT (trip_id, user_id) DO NOTHING;
```

Schema migration creates storage; data migration populates pre-existing Trips.
Backfill uses original Trip creation time, not the moment the feature deploys.
The INSERT tolerates existing pairs; Alembic revision history ensures the
whole table-creation migration runs once. Re-running upgrade head does not
rerun CREATE TABLE. Downgrade drops only the new tables/indexes and their data,
leaving Users and Trips. Re-upgrade restores Owner memberships, not lost
ordinary memberships/invitation history.
0001/0002 are unchanged. Tests cycle 0002 -> 0003 -> 0002 with old Trips,
preserve Users/Trips and verify another upgrade produces one Owner row per Trip.

## API

| Method and Path | Permission | Success |
| --- | --- | --- |
| POST /trips/{id}/invitations | Owner; body email only | 201 InvitationResponse |
| GET /invitations | Current recipient only, all statuses | 200 list |
| POST /invitations/{id}/accept | Pending invitation's recipient | 200 updated invitation |
| POST /invitations/{id}/reject | Pending invitation's recipient | 200 updated invitation |
| GET /trips/{id}/members | Owner or member | 200 safe member list |

All require JWT. Trip list/detail now allow owned OR joined Trips; PATCH,
DELETE and invite remain Owner-only. There is no membership creation endpoint
that bypasses acceptance. Lists are deliberately simple, ID-ordered and unpaginated.

## Invitation Flow

Alice login -> owned Trip lock -> normalized Bob email -> registered Bob lookup
-> reject self/already member/duplicate pending -> pending invitation -> commit.
Bob inbox -> accept -> scoped recipient lookup -> locks -> new member plus
accepted/responded_at -> commit -> Bob can read Trip and members.

Unknown registered invitee: 404 after Owner authorization. Self/member/pending
conflicts: 409. Another user's invitation or inaccessible Trip: 404.
Invalid schemas: redacted 422. Unexpected SQL failures: generic 503.
The Owner-only email lookup can reveal account existence to that Owner; this
is inherent in this existing-user MVP, not a claim of enumeration-proof design.

## Authorization

| Actor | Trip/Member Read | Trip PATCH/DELETE | Invite | Respond |
| --- | --- | --- | --- | --- |
| Owner | yes | yes | yes | only own received invitations |
| Member | yes | no, 404 | no, 404 | only own received invitations |
| Other | no, 404 | no, 404 | no, 404 | only own received invitations |

An invitation being pending grants no Trip read access. A recipient must
accept before membership grants access.
get_owned_trip still checks Trip.owner_id; get_accessible_trip checks
owner OR matching membership. The latter does not imply metadata write access.

## Transaction Design

Accept flushes INSERT TripMember, changes status/responded_at, then commits once.
Any error before commit rolls both back. A crash before commit likewise leaves
neither persisted; commit makes both durable. A fault-injection test fails the
invitation UPDATE after the member INSERT really ran and verifies pending plus
no new member, then retries successfully.
Trip creation similarly flushes Trip, adds Owner membership and commits once.
Reject changes only the pending invitation; no member is created.

## Race Condition Protection

All membership writes use a consistent lock order: Trip row first, invitation
row second. Trip CRUD already locks the Trip for mutations/deletion. This
avoids taking child locks then waiting on a parent while deletion waits on the
child. The initial recipient-scoped ID lookup acquires no write lock.

Duplicate invite: the second request waits for the Trip lock, then rechecks
membership/pending under PostgreSQL's default READ COMMITTED isolation. The
pending partial unique index is the final guarantee even if a pre-check is
bypassed. Known duplicate constraints map to 409 after rollback, not 500.

Double accept (or accept racing reject): the second waiter rereads the locked
invitation (populate_existing), observes the terminal state and returns 409.
Membership uniqueness provides an additional storage invariant.
Serializing writes per Trip is a conscious simple MVP tradeoff; it is not a
fine-grained high-throughput locking framework.

Dedicated race tests synchronize two independent connections before the Trip
FOR UPDATE query, then run actual TestClient HTTP requests simultaneously.
They verify one 201/one 409 for invites and one 200/one 409 for responses, with
exactly one final decision and the corresponding membership count.
These tests use a committed private schema because one outer uncommitted
transaction cannot be shared as concurrent visible data across connections.
All ordinary tests continue using the established schema/savepoint fixture.

## Data Isolation

Trip access is one SQL OR/EXISTS expression. Owner membership cannot duplicate
the Trip row, unlike concatenating owner/member lists or a multiplying JOIN.
Invitation inbox and response lookups include invitee_id=current_user.id.
Membership listing first checks accessible Trip and then selects only safe
User columns. Password/hash and auth secrets are never serialized.

## Database Verification

Real development upgrade 0002 -> 0003 passed. A task-created old Trip inserted
before upgrade received exactly one Owner row, matching owner_id/created_at;
the row and temporary owner were cleaned up afterward. No existing data was removed.
The query for Trips missing Owner membership returned zero.
psql `\d trip_members` / `\d trip_invitations` confirmed FK actions, composite
unique, partial unique, CHECKs and timezone-aware timestamps.
Actual SQL SELECT during HTTP verification showed Alice owner, Bob member,
accepted Bob invite, rejected Charlie invite and a fresh pending Charlie invite.
Current is 0003 (head); alembic check has no differences; SELECT 1 succeeds.

## Tests

Default suite: 186 passed, 82 skipped, 0 failed.
PostgreSQL-enabled suite: 268 passed, 0 skipped, 0 failed.
Both include prior health, registration, JWT, Trip CRUD, date and migration
regressions. No SQLite substitution.
New tests include safe payloads, identity injection, shared normalization,
privacy, strict terminal states, reinvitation, membership projection, rollback,
backfill/reversal, real SQL constraints, cascade and concurrent HTTP.

## Manual Verification

Started real Uvicorn --reload on port 8017 with a process-only random JWT key.
Registered/logged in Alice/Bob/Charlie. Alice created a Trip with Owner member,
invited Bob (201), Bob saw pending and accepted (200). Lists contained one Trip
for both Alice and Bob; Bob detail/members were 200 but writes/invite were 404.
Charlie Trip/member reads and responses to Bob's invitation were 404.
Repeat response and pending invite were 409.
Charlie rejection created no membership and permitted a new pending invite.
Anonymous new routes were 401; health and auth/me passed.
Owner Trip DELETE returned 204 and removed both child tables' related rows.

Only task-created data was cleaned up with exact identities. Final counts:
0 users, 0 trips, 0 memberships, 0 invitations; 0 remaining test schemas.
Identity sequences were not reset. No secrets or tokens were printed or saved
in documentation. Temporary verification server stopped afterward.

## Important Code

Read these eight files in order:

1. `backend/app/models/trip_member.py`: composite uniqueness and FK actions;
   connects User/Trip while storing participation metadata.
2. `backend/app/models/trip_invitation.py`: partial unique index and status/
   response checks; compare with invitation service invariants.
3. `backend/migrations/versions/0003_create_membership_and_invitations.py`:
   distinguish table creation from Owner INSERT SELECT backfill.
4. `backend/app/services/trips.py`: atomic creation and accessible_to EXISTS;
   see why Owner write lookup remains separate from member reads.
5. `backend/app/services/memberships.py`: authorization then safe joined projection,
   with effective role derived from the authoritative owner_id.
6. `backend/app/services/invitations.py`: start at respond_to_invitation;
   follow recipient scope, lock order, state guard, flush and single commit.
7. `backend/tests/test_membership.py`: read lifecycle then rollback test;
   API behavior is verified against real PostgreSQL via existing fixtures.
8. `backend/tests/test_membership_concurrency.py`: independent sessions,
   barrier before lock acquisition, 201/409 and 200/409 outcome checks.

Schemas and routers remain small boundaries; their details are listed above.

## Concepts to Understand

- Many-to-many needs a separate membership row per User/Trip pair.
- Association object adds role/joined_at to the link, rather than only two FKs.
- Composite uniqueness constrains the pair, not either ID individually.
- State machine permits only pending -> accepted/rejected; actions decide
  transitions rather than a general user-supplied status update.
- Transaction makes member insertion and invitation decision all-or-nothing.
- Race conditions mean two requests can pass a pre-check; locks plus unique
  constraints protect the invariant even when requests overlap.
- Data migration makes old data satisfy a new model; DDL alone cannot do that.
- Authorization evolves by operation: member-readable is not member-writable.

## OpenTrip Comparison

Both designs have Owner participants, unique memberships, explicit invitations
and centralized permission boundaries. OpenTrip offers link-based sharing,
optional email restrictions, editor/viewer/canInvite, expiry/revoke, idempotent
acceptance and legacy members. TripTogether deliberately uses existing-user
recipient records, owner/member, strict accept/reject and one atomic transaction.
Public sharing/extra collaboration permissions may be reconsidered only when
requested; they are not implemented now. This is design reference, not copied code.

## Interview Questions

1. Why TripMember? A Trip can contain many users and a user can join many Trips.
2. What is many-to-many here? Each User/Trip pair is represented by one row.
3. Why association object? It carries role/joined_at beyond the two foreign keys.
4. Why composite UNIQUE? Alice may join many Trips but only once per Trip.
5. How prevent duplicate invitations? Locked pre-check plus partial pending
   unique index; rejected history does not block a fresh invitation.
6. Why transactional accept? Member and accepted status must persist together;
   a failure after INSERT rolls the INSERT back.
7. How protect Bob's invitation? SQL response lookup also requires Bob's user ID.
8. How did authorization evolve? Reads became owner OR member; writes stayed owner.
9. Why read-only members? This step grants participation, not metadata control.
10. How migrate old Trips? 0003 INSERT SELECT creates owner memberships.
11. Schema versus data migration? CREATE TABLE defines storage; backfill creates rows.
12. How handle double accept? Lock Trip then invitation, recheck pending; loser
    gets 409, and membership UNIQUE prevents a second association.
13. Why no client owner/inviter ID? Security identity must come from verified JWT.
14. What happens on Trip deletion? PostgreSQL cascades members and invitations.
15. How test collaboration? Real Alice/Bob/Charlie HTTP flows plus separate-
    connection concurrent tests verify visibility and denials.
16. Why no duplicate owned Trip in lists? SQL EXISTS tests membership without
    multiplying the Trip row when the Owner is also a member.
17. Why retain owner_id? Step 6's ownership remains authoritative; role is not
    a second source of write permissions.
18. Why VARCHAR + CHECK? It keeps small allowed sets explicit without an extra
    PostgreSQL enum lifecycle; Pydantic also restricts output values.

## Problems Encountered

External-drive AppleDouble metadata is a known Alembic hazard. Cleaned generated
metadata with the existing documented dot_clean command before migration runs.
Concurrency tests needed a small dedicated fixture: normal savepoint fixtures
share one connection and cannot demonstrate independent transaction contention.
No wholesale test architecture redesign. Earlier migration head expectations
were advanced to 0003; historical migrations were never edited.

## RECORD.md

The Step 7 entry records the implementation, design, verified outcomes and limits.

## Next Step

Step 8: Shared Itinerary. Not started.
