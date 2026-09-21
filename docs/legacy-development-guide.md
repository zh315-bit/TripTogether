# Historical Development Guide (Through Step 10)

The later Web Frontend Decision defers HarmonyOS. Its roadmap supersedes the
mobile-oriented plans preserved below; see the root README and AGENT.md.
React + TypeScript Frontend Foundation is the current Step12, NOT STARTED.

Archived during Step 11 to preserve earlier walkthroughs, not a current API
specification. Some roadmap sections below were aspirational even at Step 10.
Use the root README, api-inventory.md and client-integration.md for current
paths, configuration, error contracts and project status. New clients must
use /api/v1; the unprefixed examples below are compatibility paths only.

# TripTogether

TripTogether is a collaborative travel planning application designed for small groups to organize trips, manage shared itineraries, and split expenses in one place.

The project is built as a full-stack mobile application with a HarmonyOS client, a FastAPI backend, and PostgreSQL for persistent data storage.

> **Current Status:** Step 10 complete: registration/JWT, Trip CRUD, memberships, invitations, shared itinerary, exact expense splits, dynamic member balances and settlement suggestions. Database revision remains `0005`. Owners and members can edit itinerary/expenses and read balances; only owners can edit/delete the Trip or invite. Actual payments, realtime, currency conversion, public invite links, refresh tokens and logout are not implemented. Next recommendation: Step 11, Backend MVP Hardening & API Integration Readiness; not started.

## Local Backend Quick Start

From the project root (Python 3.9+):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
python -m pytest
python -m uvicorn app.main:app --reload
```

In another terminal:

```bash
curl -i http://127.0.0.1:8000/health
```

Expect HTTP `200 OK` and `{"status":"ok"}`. Interactive API documentation is
available at `http://127.0.0.1:8000/docs`. Stop the server with `Ctrl+C`.
No environment variables or external services are needed for `/health`.

On a macOS external drive, virtual environments may fail with a
`UnicodeDecodeError` caused by `._*.pth` metadata files. In that case, replace
the first two setup commands with the following, then continue with installation:

```bash
python3 -m venv /private/tmp/triptogether-step1-venv
source /private/tmp/triptogether-step1-venv/bin/activate
```

This temporary environment may be removed by the OS; recreate it when needed.

The backend now includes `app/core/config.py` and `app/db/` for database
configuration, sessions, and an independent connectivity check. The expanded
architecture below is the roadmap, not a list of implemented features.

## PostgreSQL Configuration and Verification

Provide a running PostgreSQL server, a login role, and an existing empty
`triptogether` database owned by that role. This application does not install
PostgreSQL or create roles/databases. Business tables are managed by Alembic.
For an existing local server with administrator access, these PostgreSQL tools
can create a dedicated role and database (do not repeat if they already exist):

```bash
createuser --pwprompt triptogether_app
createdb --owner=triptogether_app triptogether
```

From the repository root, copy `.env.example` to `.env` only if `.env` does not
already exist, then edit the placeholders locally:

```bash
cp -n .env.example .env
```

Set `DATABASE_URL` to your PostgreSQL URL using the `postgresql+psycopg` driver.
Use the role above or your existing role, its password, and the actual
host/port/database. URL-encode special characters in credentials.
Never commit `.env` or paste real credentials into development records.

Configuration reads the process environment first, then the repository-root
`.env`, regardless of the current working directory. An explicitly empty
environment value is an error, not a fallback. Engine and session factory
are created lazily and reused; restart the process after changing configuration.
The database dependency does not auto-commit; registration explicitly commits
its transaction and rolls back failures.

With your virtual environment activated:

```bash
cd backend
python -m app.db.check
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
```

The check executes `SELECT 1` through a real SQLAlchemy Session and psycopg
connection. Success prints `PostgreSQL connectivity check passed (SELECT 1).`
and exits with code 0. Failure prints a credential-safe message and exits 1;
check the URL, login permissions, and server availability.

Default tests run without PostgreSQL and explicitly skip the live tests.
`RUN_POSTGRES_TESTS=1` requires a real configured PostgreSQL server; missing
configuration or connection failure fails that test rather than silently
skipping it. No SQLite substitution is used.

PostgreSQL 17 connectivity has been verified, including the first `users`
migration. Full live tests also exercise uniqueness, NOT NULL, automatic
defaults, ORM reads, and migration reversibility. Migration tests create a
random private schema in an outer transaction and roll it back afterward;
they do not drop or modify the normal `public.users` table. The test role
therefore needs permission to create schemas in the development database.

## Registration

On this Homebrew development machine, start PostgreSQL if necessary with
`brew services start postgresql@17`. Configure the root `.env` as above, then
activate your virtual environment and run from the repository root:

```bash
python -m pip install -r backend/requirements.txt
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`, expand `POST /auth/register`, select
**Try it out**, enter your local test values and select **Execute**.
Alternatively, run this from another activated terminal; the password is
prompted without echo rather than put into shell history:

```bash
python - <<'PY'
from getpass import getpass
import httpx

payload = {
    "username": input("Username: "),
    "email": input("Email: "),
    "password": getpass("Password: "),
}
response = httpx.post("http://127.0.0.1:8000/auth/register", json=payload)
print(response.status_code, response.json())
PY
```

Success is **201** with only `id`, `username`, `email`, `created_at`.
Duplicate username/email returns **409**; invalid input **422**; database or
hashing failure **503** without internal details. Validation responses omit
raw inputs to avoid exposing passwords.

Username: trimmed, 1-50 ASCII letters/digits/underscores, case-sensitive.
Email: validated with Pydantic EmailStr, normalized to lowercase, at most 254
characters. The full address is treated as case-insensitive by product policy.
Password: 8-128 Unicode characters, preserved exactly (no trim/normalization);
the limit bounds input size, with no bcrypt-style 72-byte truncation.
Only an Argon2id hash is stored. Do not put real passwords or hashes in logs,
documentation, or bug reports. Use localhost for development and HTTPS when
deployed; no login/session/token is issued by registration.

From `backend`, verify with:

```bash
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m app.db.check
python -m alembic current
```

Registration integration tests reuse the private-schema transaction fixture
and request-local Session savepoints. Even application `commit()` cannot commit
the outer test transaction, which rolls back all test data. Manual Swagger/API
requests do commit to your development database; use disposable test accounts.

## Login and JWT Authentication

Install the updated requirements; PyJWT is the only new direct dependency.
Keep DATABASE_URL configured as above. Add JWT settings from `.env.example`
to your existing local `.env`, or export them in the server terminal:

```bash
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export JWT_ALGORITHM=HS256
export ACCESS_TOKEN_EXPIRE_MINUTES=30
cd backend
python -m uvicorn app.main:app --reload
```

The export command does not display the generated key. For persistent local
use, store a securely generated key in the ignored root `.env`; all server
workers must share it. Do not regenerate it for each request. Restarting with
a different key invalidates existing tokens. The example placeholder is rejected.
Process environment takes precedence over `.env`; an empty value is not a
fallback. HS256 is the only accepted algorithm; lifetime is 1-1440 minutes,
default 30. The key must have at least 32 UTF-8 bytes; length alone does not
guarantee randomness. Missing JWT configuration does not break health or
registration, but token operations fail closed with a safe 503.

After registering a disposable account, use `/docs`:

1. Execute `POST /auth/login` with JSON `email` and `password`.
2. Expect 200 with `access_token` and `token_type: bearer`.
3. Select **Authorize**, enter only the token (without the `Bearer ` prefix),
   then select Authorize and Close.
4. Execute `GET /auth/me`; expect 200 with the registered user's four public
   fields. Swagger sends `Authorization: Bearer <token>` for this endpoint.
5. Clear authorization and repeat; expect 401 and `WWW-Authenticate: Bearer`.

Alternatively, this verifies login and `/auth/me` without printing the token:

```bash
python - <<'PY'
from getpass import getpass
import httpx

with httpx.Client(base_url="http://127.0.0.1:8000") as client:
    response = client.post("/auth/login", json={
        "email": input("Email: "), "password": getpass("Password: "),
    })
    print("Login:", response.status_code)
    response.raise_for_status()
    token = response.json()["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    print("Current user:", response.status_code, response.json())
PY
```

Unknown email and wrong password both return the same 401 message. Login
reuses registration's email normalization; it accepts 1-128 password characters
so a short incorrect password is an authentication failure, not a registration
policy error. Passwords are never trimmed. Invalid input returns redacted 422.
JWT contains only string `sub` (User ID) and integer `exp` (UTC expiry).
Signature/expiry are verified before querying PostgreSQL for the current User.
Missing, tampered, expired, malformed tokens and missing users return 401.
Database failures return a generic 503, not connection details.

JWT payloads are encoded, not encrypted. Bearer tokens are credentials: anyone
holding one can use it until expiry; use HTTPS outside localhost and never
paste tokens into logs or Git. Expiration does not selectively revoke stolen
tokens. There is no token/session table, refresh token, or logout endpoint.
Login and current-user success responses use `Cache-Control: no-store`.

From `backend`, run:

```bash
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q tests/test_jwt.py tests/test_authentication.py
```

Live tests reuse private PostgreSQL schemas, outer transactions and request
savepoints, not SQLite. See `docs/step5-review.md` for the reference review,
six-file reading guide, JWT explanation, and interview questions.

## Trip CRUD

With the existing database and JWT configuration, run from `backend`:

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -m uvicorn app.main:app --reload
```

Revision `0002` adds `trips`; it does not rewrite `0001` or change `users`.
Log in and authorize in `/docs` as above. All five endpoints require
`Authorization: Bearer <token>`:

| Method | Path | Success |
| --- | --- | --- |
| POST | /trips | 201, created trip |
| GET | /trips | 200, owned or joined trips, once each, ordered by ID |
| GET | /trips/{trip_id} | 200, owned or joined trip |
| PATCH | /trips/{trip_id} | 200, updated trip |
| DELETE | /trips/{trip_id} | 204, empty body |

Example create body:

```json
{
  "name": "Japan Summer Trip",
  "destination": "Tokyo, Japan",
  "start_date": "2027-06-10",
  "end_date": "2027-06-20"
}
```

Name (1-120 characters) and destination (1-200) are trimmed and required.
Dates must be real `YYYY-MM-DD` calendar dates, with end >= start; same-day trips
are allowed. Dates are PostgreSQL DATE, not moments in a timezone.
Ownership comes exclusively from the authenticated user. Client-supplied
id/owner_id/created_at/updated_at or unknown fields return 422.

PATCH accepts any subset of the four input fields, for example
`{"name":"Updated Japan Trip"}`. Explicit null is rejected; omission preserves
the old value. Empty/unchanged PATCH succeeds as a no-op without advancing
updated_at. A date-only change is validated against the other stored date.
Concurrent edits lock the owned row before merging; same-field writes remain
last-writer-wins, not optimistic version conflict detection.

Missing and inaccessible trips return the same 404. Members can read but
cannot modify/delete/invite; those owner-only operations also return 404.
Anonymous requests return 401. Invalid input returns safe 422; database errors
are rolled back and translated to generic 503. Lists are filtered in SQL, not
after loading other users' data. SQL EXISTS prevents duplicate owner entries.
Deletion is a hard delete; PostgreSQL cascades memberships, invitations, itinerary,
expenses and their splits.
The owner foreign key uses RESTRICT, preventing orphan trips on user deletion.

created_at/updated_at use timezone-aware database timestamps and defaults.
On actual SQLAlchemy UPDATE, updated_at uses PostgreSQL statement_timestamp()
(not transaction-start now(), which stays fixed within the test transaction).
This is SQLAlchemy onupdate, not a database trigger: hand-written SQL must
maintain updated_at itself. Only Trip.owner is mapped; no unused User.trips
collection or cascade deletion was added.

Verify with all regressions:

```bash
python -m app.db.check
python -m alembic current
python -m alembic check
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
```

For a manual isolation check, register/login Alice and Bob. Create a trip as
Alice; before accepting an invitation, Bob's list must omit it and Bob's
GET/PATCH/DELETE must return 404. After acceptance only GET becomes allowed.
Alice can PATCH and DELETE it; subsequent GET returns 404. Try a PATCH moving
start_date beyond the stored end_date: 422, with the original trip unchanged.
In psql, `\d trips` and the following query verify persistence:

```sql
SELECT id, name, destination, start_date, end_date, owner_id,
       created_at, updated_at FROM trips;
```

The integration suite uses isolated PostgreSQL schemas and savepoints, including
`0002 -> 0001 -> 0002` without downgrading the development schema.
See `docs/step6-review.md` for the reference analysis, model design and Q&A.

## Membership and Invitations

Run `python -m alembic upgrade head` from `backend` before starting the updated
application. Revision 0003 creates trip_members/trip_invitations and backfills
every existing Trip owner as a member. Historical migrations are unchanged.
New Trip creation commits the Trip and its Owner membership together.

All endpoints below require `Authorization: Bearer <token>`:

| Method | Path | Who / Result |
| --- | --- | --- |
| POST | /trips/{trip_id}/invitations | Owner only, 201 |
| GET | /invitations | Current recipient's full history, 200 |
| POST | /invitations/{invitation_id}/accept | Recipient only, 200 |
| POST | /invitations/{invitation_id}/reject | Recipient only, 200 |
| GET | /trips/{trip_id}/members | Owner or member, 200 |

Invitation create accepts only:

```json
{"email": "bob@example.com"}
```

The normalized email must belong to an existing registered user. No email is
sent and no public link/code is created. A missing registered user returns 404
after checking the caller owns the Trip. Self-invites, existing members,
duplicate pending invites and responses to terminal invitations return 409.
Client inviter_id/invitee_id/status/role fields are rejected with 422.

Responses contain id, trip_id, inviter_id, invitee_id, status, created_at and
responded_at. Lists include pending/accepted/rejected history in ID order,
not invitations sent by the current user. Other users cannot accept/reject
someone else's invitation: they receive the same 404 as for an unknown ID.
Pending alone does not grant Trip or member-list access.

Only pending -> accepted or pending -> rejected is permitted. Accept inserts
one member and sets status/responded_at in one transaction; reject creates no
member. Repeating either action after a decision returns 409 (not idempotent
success). Rejection allows the owner to send a new invitation row later.
A partial unique index prevents concurrent pending duplicates while preserving
history; a composite unique constraint prevents duplicate members.

Trips.owner_id remains the sole ownership authority. Stored member roles are
owner/member only; application writes keep them aligned. Member-list display
roles are derived from owner_id, and role never grants owner write permission.
There is no transfer/remove/leave API or cross-table role synchronization trigger.
Direct SQL writers must preserve Owner membership consistency themselves.

Membership and invitation Trip foreign keys cascade on Trip deletion. User
foreign keys use RESTRICT; no user-deletion workflow is added. Deleting a Trip
also deletes its invitation history. Member lists expose only user_id,
username, email, effective role and joined_at to participants.

Manual workflow in `/docs`:

1. Register/login Alice, Bob and Charlie. Keep their tokens private.
2. Authorize Alice, create a Trip, then invite Bob using his email.
3. Authorize Bob; GET /invitations shows pending. Accept its ID.
4. Bob's GET /trips and GET /trips/{id} now include Alice's Trip.
5. Bob can GET /trips/{id}/members but cannot PATCH/DELETE/invite (404).
6. Charlie cannot read the Trip/members or respond to Bob's invitation (404).
7. Alice and Bob's member lists show Alice owner and Bob member.
8. To test rejection, invite Charlie and reject as Charlie. He gains no access;
   Alice may invite him again. Delete the Trip as Alice to test cascade cleanup.

Inspect in psql:

```sql
\d trip_members
\d trip_invitations
SELECT * FROM trip_members;
SELECT * FROM trip_invitations;
SELECT t.id FROM trips t
WHERE NOT EXISTS (
  SELECT 1 FROM trip_members m
  WHERE m.trip_id = t.id AND m.user_id = t.owner_id AND m.role = 'owner'
);
```

The final query should return no rows for application-managed data.
Run all regression tests with the earlier commands, or focus on this step:

```bash
RUN_POSTGRES_TESTS=1 python -m pytest -q tests/test_membership.py tests/test_membership_migrations.py tests/test_membership_concurrency.py
```

Ordinary tests reuse existing private-schema transactions/savepoints. Only
concurrency tests use committed data in their own random private schemas and
separate connections, then drop those schemas; never the development tables.
See `docs/step7-review.md` for design, locking, migration and learning details.

## Shared Itinerary

From `backend`, using the existing virtual environment and local DB/JWT settings:

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m uvicorn app.main:app --reload
```

Revision 0004 adds only `itinerary_items`. Historical migrations are unchanged.
All routes below require JWT and an owned or accepted-member Trip:

| Method | Path | Success |
| --- | --- | --- |
| POST | /trips/{trip_id}/itinerary | 201, new item |
| GET | /trips/{trip_id}/itinerary | 200, all items ordered by date, position |
| GET | /trips/{trip_id}/itinerary/{item_id} | 200, one item |
| PATCH | /trips/{trip_id}/itinerary/{item_id} | 200, updated item |
| DELETE | /trips/{trip_id}/itinerary/{item_id} | 204, empty body |
| PATCH | /trips/{trip_id}/itinerary/reorder | 200, that day's ordered items |

Create example for a Trip covering June 10, 2027:

```json
{
  "title": "Visit Senso-ji",
  "location": "Asakusa",
  "date": "2027-06-10",
  "start_time": "09:30",
  "end_time": "10:30",
  "notes": "Meet at the gate"
}
```

Only title and date are required. Title is trimmed, nonblank, max 160 characters;
location is optional trimmed text (200); notes are optional plain text (2000).
Time accepts local HH:MM or HH:MM:SS with optional microseconds, not a timezone.
Start alone is valid; end requires start and cannot precede it. No overnight
items. DATE must lie within the inclusive Trip range.

PATCH preserves omitted fields. Null clears location, notes or times, but not
title/date. It validates the merged stored/new times: to clear start while end
exists, clear both in the same PATCH. Empty/identical PATCH is a no-op.
IDs, creator, timestamps and position are server-controlled; supplied extras
return redacted 422. Creator is attribution, not permission authority.

New items append at max(position)+1 within Trip/date. Delete compacts the day;
moving date appends to the destination and compacts the source. Reorder body:

```json
{"date": "2027-06-10", "item_ids": [3, 1, 2]}
```

Replace those IDs with every actual item ID on that date, exactly once.
Missing, duplicate, foreign, wrong-date or unknown IDs return 422. An empty
list is valid only for an empty date within the Trip range. Temporary positive
positions and two flushes avoid unique-position collisions within one commit.

Owner and Member can edit/delete each other's items. Other users and pending
invitees receive 404; anonymous callers receive 401. Trip metadata PATCH/DELETE
and invitations stay Owner-only. Shrinking Trip dates around existing items
returns 409; move or delete those items first. Database failures roll back and
return safe 503 responses.

All itinerary writes lock the parent Trip, coordinating with Trip date changes
and deletion. This serializes writes per Trip; stale same-field updates still
use Last Write Wins. There is no version checking, collaborative merge or push.
Shared means Bob's committed changes become visible on Alice's next GET.
Direct SQL writers must maintain cross-table date boundaries and updated_at.

Manual `/docs` workflow:

1. Register/login Alice, Bob and Charlie; Alice creates a Trip and invites Bob.
2. Bob accepts; Alice creates an item using the JSON above.
3. Authorize Bob, GET the item, PATCH its notes or time.
4. Authorize Alice and GET again: Bob's edit must be visible.
5. Bob creates another item; Alice reorders the two actual IDs; Bob GETs the order.
6. Charlie must receive 404 on all six endpoints; anonymous callers receive 401.
7. Bob deletes Alice's item (204); Alice can delete the whole Trip (204, cascade).

In psql connected to the same development database:

```sql
\d itinerary_items
SELECT id, trip_id, title, location, date, start_time, end_time, notes,
       position, created_by_user_id, created_at, updated_at
FROM itinerary_items ORDER BY date, position;
```

Verification: default **231 passed, 121 skipped, 0 failed**; PostgreSQL
**352 passed, 0 skipped, 0 failed**. Includes isolated 0004 -> 0003 -> head,
constraint checks, rollback injection and independent-connection race tests.
See `docs/step8-review.md` for the full report, eight-file guide and interview Q&A.

## Shared Expenses

With existing DATABASE_URL and JWT settings, activate the virtual environment,
then run from `backend`:

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m uvicorn app.main:app --reload
```

Migration 0005 creates `expenses` and `expense_splits`, without changing Trip
or historical migrations. Owner and accepted Member may operate any expense,
regardless of creator. Other/pending users get 404; anonymous users get 401.
Trip metadata and invitations remain Owner-only.

| Method | Path | Success |
| --- | --- | --- |
| POST | /trips/{trip_id}/expenses | 201 |
| GET | /trips/{trip_id}/expenses | 200, list |
| GET | /trips/{trip_id}/expenses/{expense_id} | 200 |
| PATCH | /trips/{trip_id}/expenses/{expense_id} | 200 |
| DELETE | /trips/{trip_id}/expenses/{expense_id} | 204 |

Create example, replacing IDs with actual Trip participants:

```json
{
  "description": "Dinner",
  "amount": "120.00",
  "currency": "USD",
  "paid_by_user_id": 1,
  "expense_date": "2027-05-01",
  "participant_user_ids": [1, 2]
}
```

All six fields are required. Amount MUST be a decimal string, not a JSON number:
positive, at most two decimal places, maximum `9999999999.99`. No exponent,
NaN, Infinity, silent rounding or binary float conversion. Responses serialize
amount/share_amount as strings with exactly two decimal places. Description
is trimmed, nonblank, at most 200 characters. Unknown/server-controlled fields,
custom splits, empty/duplicate participant lists and explicit nulls are rejected.

Currency is exactly three uppercase ASCII letters; this validates format, not
an official currency registry. This MVP uses a uniform two-decimal accounting
precision, not currency-specific minor-unit rules. No exchange-rate conversion.
Trip has no currency column: the first expense establishes the currency of the
current ledger. Every other existing expense must match. PATCH changing one
currency while other expenses differ returns 409. A sole expense may be
relabeled (not converted); after deleting all expenses a new currency is allowed.

The payer and every split participant must be Owner or accepted Member (otherwise
422), but payer need not participate in the split. Creator always comes from JWT:
Bob may record Alice's payment. Expense dates are strict DATE but may lie outside
Trip dates, because flights/hotels may be paid before departure.

The server divides exact hundredths using integer quotient/remainder, giving
one extra hundredth to the lowest user IDs first:
`120.00/2 -> 60.00,60.00`; `100.00/3 -> 33.34,33.33,33.33`;
`0.01/3 -> 0.01,0.00,0.00`. Sum always equals the recorded amount.
Changing amount or participants recalculates and replaces splits in one
transaction. Omitted PATCH fields stay unchanged; null is not allowed; empty/
identical PATCH leaves timestamps unchanged. Lists use SQL order by expense_date
DESC, created_at DESC, id DESC; splits use user_id ASC.

Writes reuse the parent Trip lock. Same-field concurrent writes are Last Write
Wins, but each committed expense/split set stays internally consistent.
GET fetches expense and splits in one SQL snapshot. Step 10 derives balances
and settlement suggestions from these records; mark-as-paid and real-time push
are not implemented.

Manual `/docs` workflow: Alice creates Trip/invites Bob; Bob accepts. Alice creates
120.00 split across both users. Bob GETs, PATCHes `{"amount":"150.00"}`; Alice
GETs and sees 75.00 each. Charlie cannot access any expense route. Bob may delete
Alice's expense; deleting the Trip cascades all expenses and splits.

In psql connected to the same database:

```sql
\d expenses
\d expense_splits
SELECT id, trip_id, description, amount, currency, paid_by_user_id,
       expense_date, created_by_user_id FROM expenses;
SELECT expense_id, user_id, share_amount
FROM expense_splits ORDER BY expense_id, user_id;
```

Ordinary integration tests use private schema/savepoints; race tests use
independent connections to a committed private schema. No SQLite.
Step 9 verification: default **293 passed, 162 skipped, 0 failed**;
PostgreSQL **455 passed, 0 skipped, 0 failed**.
See `docs/step9-review.md` for the complete report and eight-file learning guide.

## Balances and Settlement Suggestions

`GET /trips/{trip_id}/balances` requires a Bearer token. Owner and accepted
Member receive 200; outsider/pending/missing/deleted Trip receive 404;
anonymous receives 401. All current participants appear, including zero balances.
Only GET is implemented: clients cannot submit paid/share/balance values.

```json
{
  "trip_id": 1,
  "currency": "USD",
  "members": [
    {"user_id": 1, "username": "alice", "paid": "120.00", "share": "60.00", "balance": "60.00"},
    {"user_id": 2, "username": "bob", "paid": "0.00", "share": "60.00", "balance": "-60.00"}
  ],
  "suggested_settlements": [
    {"from_user_id": 2, "to_user_id": 1, "amount": "60.00"}
  ]
}
```

`paid = SUM(expenses.amount)` grouped by payer; `share = SUM(stored
expense_splits.share_amount)` grouped by participant; `balance = paid - share`.
Positive means receive, negative means owe, zero means no remaining net amount.
Stored splits, including the `100/3` remainder, are never recomputed here.
Amounts remain Decimal/NUMERIC and serialize as two-decimal strings.

Balances and suggestions are derived data, not new tables. No migration required.
The service uses one SQL statement for authorized Trip scope, participants,
grouped totals and ledger checks. Together with the current-user lookup, this
is two queries for both two and ten members, not per-member queries.
One PostgreSQL statement snapshot avoids mixing old expenses and new splits.
No read lock, commit, cached balance, payment record or new dependency is added.

The algorithm initially sorts debtors/creditors by amount DESC, user_id ASC,
then matches with two pointers, transferring the smaller remaining amount.
It does not re-sort after each transfer. Sorting costs O(n log n), matching
O(n); it is deterministic, not guaranteed globally transaction-minimal.
Suggestions are not money transfers and cannot be marked paid.

The sum of net balances must be exactly zero. Mixed currencies, missing or
incorrect per-expense totals, and financial users outside current participants
return safe 409 without suggestions; SQL failures return safe 503.
No expenses means currency null, zero balances and no suggestions.
The current single-currency ledger policy is unchanged; there is no FX.
Future leave/remove-member features must address historical financial identity;
this step does not add them.

To verify in `/docs`, register/login Alice, Bob and Carol; create a Trip, invite
both and accept. Create Hotel 300 paid by Alice, Dinner 90 paid by Bob, Tickets
60 paid by Alice, each split among all three. GET balances returns Alice +210,
Bob -60, Carol -150. Suggestions are Carol -> Alice 150 then Bob -> Alice 60.
PATCH Dinner to 150: +190/-20/-170. DELETE Tickets: +150/0/-150.
Each new GET observes committed changes without a balance synchronization job.
Responses include `Cache-Control: no-store`.

With the virtual environment and local DB/JWT configured, from `backend`:

```bash
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m app.db.check
python -m alembic current
python -m alembic check
python -m uvicorn app.main:app --reload
```

Step 10 actual verification: default **315 passed, 178 skipped, 0 failed**;
PostgreSQL **493 passed, 0 skipped, 0 failed**. Real Uvicorn HTTP multiplayer
workflow and independent SQL totals passed. Schema remains `0005`.
See `docs/step10-review.md` for the full report, seven-file reading guide,
manual verification instructions and 22 interview questions with answers.

## User Model and Migrations

The first migration is `backend/migrations/versions/0001_create_users_table.py`.
Its revision is `0001`; it creates only `users`. Alembic maintains its own
`alembic_version` table. From `backend`, with the virtual environment active:

```bash
python -m app.db.check
python -m alembic upgrade head
python -m alembic current
python -m alembic check
RUN_POSTGRES_TESTS=1 python -m pytest -q
```

`alembic check` should report `No new upgrade operations detected.` It compares
the current model metadata with the actual database; it is not a replacement
for reviewing migration code and testing database constraints.

Connect `psql` to the same local database and role as your `DATABASE_URL`
(supply the real role interactively, not a password in shell history):

```bash
psql -h localhost -p 5432 -U YOUR_DATABASE_ROLE -d triptogether
```

Then inspect:

```sql
\dt
\d users
SELECT version_num FROM alembic_version;
```

Expected now: `users`, `trips`, `trip_members`, `trip_invitations`,
`itinerary_items`, `expenses`, `expense_splits` and `alembic_version`; version `0005`.
The original User fields remain:

| Field | PostgreSQL definition |
| --- | --- |
| id | INTEGER, identity, primary key, NOT NULL |
| username | VARCHAR(50), NOT NULL, `uq_users_username` UNIQUE |
| email | VARCHAR(254), NOT NULL, `uq_users_email` UNIQUE |
| password_hash | VARCHAR(255), NOT NULL |
| created_at | TIMESTAMP WITH TIME ZONE, NOT NULL, DEFAULT now() |

Unique constraints already create indexes in PostgreSQL; no redundant indexes
are added. Uniqueness uses the database's normal case-sensitive string behavior;
the registration API lowercases email before querying and storing it. Direct
database writes bypass that application policy and must maintain it themselves.
The password field stores the Argon2id hash produced by registration.
Never insert real plaintext passwords.

The timestamp is generated by PostgreSQL, including for non-ORM inserts.
`TIMESTAMP WITH TIME ZONE` represents an absolute instant stored internally in
UTC; the session timezone controls its display. Python receives an aware
`datetime`; use `.astimezone(timezone.utc)` when UTC presentation is needed.
`now()` is the transaction start time, not a per-row wall-clock timestamp.

For future schema changes, edit the model, import new models in
`app/models/__init__.py`, then generate and review a NEW migration:

```bash
python -m alembic revision --autogenerate -m "describe schema change"
```

Do not use `Base.metadata.create_all()` or manually alter tables as a substitute.
Keep migration files in Git, with no credentials in `alembic.ini`.
Never rewrite an already-applied migration to introduce later schema changes.

The following destructive round trip is only for a disposable development
database with no data to preserve; `downgrade base` deletes the `users` table
and its rows. Prefer the isolated automated tests for routine verification.

```bash
python -m alembic downgrade base
python -m alembic upgrade head
```

On this macOS external drive, AppleDouble files such as
`._0001_create_users_table.py` may be mistaken for migration scripts, causing
`source code string cannot contain null bytes`. From `backend`, remove only
the generated metadata with `dot_clean -m migrations/versions`, then retry.
These files are already Git-ignored. Moving the checkout to an internal
filesystem avoids this recurring filesystem issue.

---

## 1. Project Motivation

Group travel information is often scattered across messaging apps, notes, spreadsheets, and payment records.

TripTogether aims to provide one shared workspace where travelers can:

- Create and manage trips
- Invite friends to collaborate
- Build a shared itinerary
- Record group expenses
- Calculate how much each traveler owes

The goal is not to build a full travel booking platform, but to create a focused and usable collaboration tool for small-group travel.

---

## 2. MVP Scope

The first version focuses only on the core collaboration workflow.

### Authentication

- User registration
- User login
- JWT-based authentication
- Basic user profile

### Trip Management

- Create a trip
- View joined trips
- Edit trip information
- Delete or archive a trip
- Set destination and travel dates

### Trip Collaboration

- Generate trip invitation code
- Join a trip using an invitation code
- View trip members
- Basic member permissions

### Shared Itinerary

- Create itinerary items
- Edit itinerary items
- Delete itinerary items
- Organize activities by date
- Store time, location, and notes

### Shared Expenses

- Add an expense
- Select payer
- Select participating members
- Split expenses equally
- Calculate individual balances
- View expense history

---

## 3. Non-MVP Features

The following features are intentionally excluded from the initial version:

- Real-time chat
- Real-time collaborative editing
- AI itinerary generation
- Map navigation
- Hotel or flight booking
- Payment processing
- Social feed
- Photo sharing
- Recommendation system

These features may be considered only after the MVP is stable.

---

## 4. Tech Stack

### Mobile Client

- HarmonyOS
- ArkTS
- ArkUI

### Backend

- Python
- FastAPI
- RESTful API
- JWT Authentication

### Database

- PostgreSQL
- SQLAlchemy

### Deployment

Planned:

- Docker
- Cloud deployment
- Managed PostgreSQL database

### Development Tools

- Git
- GitHub
- API testing tools

---

## 5. System Architecture

```text
┌──────────────────────┐
│   HarmonyOS Client   │
│    ArkTS / ArkUI     │
└──────────┬───────────┘
           │
           │ HTTPS / REST API
           ▼
┌──────────────────────┐
│   FastAPI Backend    │
│                      │
│ Authentication       │
│ Trip Service         │
│ Itinerary Service    │
│ Expense Service      │
└──────────┬───────────┘
           │
           │ SQLAlchemy
           ▼
┌──────────────────────┐
│     PostgreSQL       │
│                      │
│ Users                │
│ Trips                │
│ Trip Members         │
│ Itinerary Items      │
│ Expenses             │
│ Expense Participants │
└──────────────────────┘
```

---

## 6. Core Data Model

### User

Represents a registered user.

Key fields:

- `id`
- `username`
- `email`
- `password_hash`
- `created_at`

### Trip

Represents a shared trip.

Key fields:

- `id`
- `name`
- `destination`
- `start_date`
- `end_date`
- `owner_id`
- `invitation_code`

### TripMember

Represents the relationship between users and trips.

Key fields:

- `id`
- `trip_id`
- `user_id`
- `role`
- `joined_at`

### ItineraryItem

Represents an activity inside a trip.

Key fields:

- `id`
- `trip_id`
- `title`
- `location`
- `date`
- `start_time`
- `notes`
- `created_by`

### Expense

Represents a shared expense.

Key fields:

- `id`
- `trip_id`
- `payer_id`
- `title`
- `amount`
- `created_at`

### ExpenseParticipant

Represents users participating in an expense.

Key fields:

- `id`
- `expense_id`
- `user_id`
- `share_amount`

---

## 7. Planned API Structure

```text
/api/v1/auth
    POST /register
    POST /login

/api/v1/users
    GET /me

/api/v1/trips
    POST /
    GET /
    GET /{trip_id}
    PATCH /{trip_id}
    DELETE /{trip_id}

/api/v1/trips/{trip_id}/members
    GET /
    POST /join

/api/v1/trips/{trip_id}/itinerary
    POST /
    GET /
    PATCH /{item_id}
    DELETE /{item_id}

/api/v1/trips/{trip_id}/expenses
    POST /
    GET /
    DELETE /{expense_id}

/api/v1/trips/{trip_id}/balances
    GET /
```

The API design may evolve during implementation.

---

## 8. Development Roadmap

### Phase 1 — Project Foundation

- [x] Initialize repository
- [x] Create backend structure
- [x] Configure PostgreSQL
- [x] Configure environment variables
- [ ] Define database models
- [ ] Add database migrations

User, Trip, TripMember, TripInvitation, ItineraryItem, Expense and ExpenseSplit models/migrations are complete;
other business models and their migrations remain planned.

### Phase 2 — Authentication

- [x] User registration
- [x] Password hashing
- [x] User login
- [x] JWT authentication
- [x] Protected API routes

### Phase 3 — Trip Management

- [x] Create trip
- [x] List trips
- [x] View trip details
- [x] Update trip
- [x] Delete trip (hard delete; archive is not implemented)

### Phase 4 — Collaboration

- [x] Invite registered users (public invitation codes remain deferred)
- [x] Join trip by accepting an invitation
- [x] List trip members
- [x] Owner/member authorization rules

### Phase 5 — Shared Itinerary

- [x] Create itinerary item
- [x] Update itinerary item
- [x] Delete itinerary item
- [x] Group itinerary by date and reorder within a day

### Phase 6 — Shared Expenses

- [x] Add expense
- [x] Select payer
- [x] Select participants
- [x] Calculate equal split with exact remainder distribution
- [x] Calculate member balances and deterministic settlement suggestions

### Phase 7 — HarmonyOS Client

- [ ] Login/Register UI
- [ ] Trip list
- [ ] Trip detail
- [ ] Itinerary UI
- [ ] Expense UI
- [ ] Connect client to backend APIs

### Phase 8 — Deployment & Testing

- [ ] Backend tests
- [ ] API integration tests
- [ ] Dockerize backend
- [ ] Deploy backend
- [ ] Deploy PostgreSQL
- [ ] Prepare demo data
- [ ] Add screenshots/demo to README

---

## 9. MVP Definition of Done

The MVP is considered complete when:

1. A user can register and log in.
2. A user can create a trip.
3. Another user can join the trip.
4. Trip members can view and manage a shared itinerary.
5. Trip members can add shared expenses.
6. The system can calculate each member's expense balance.
7. The HarmonyOS client can complete the core workflow using the deployed backend.
8. Core APIs have automated tests.
9. The project can be reproduced from documentation.

---

## 10. Future Improvements

Possible future versions may include:

- Map-based itinerary visualization
- Real-time collaboration using WebSocket
- Push notifications
- Receipt image recognition
- AI-assisted itinerary planning
- Smart expense categorization
- Offline synchronization
- App store release

These features are not part of the initial MVP.

---

## 11. Project Structure

```text
TripTogether/
├── README.md
├── AGENT.md
├── RECORD.md
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   │
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── harmony/
│   └── ...
│
└── docs/
    ├── architecture/
    └── api/
```

The structure may be adjusted as the project evolves.

---

## 12. License

This project is currently developed for educational and portfolio purposes.
