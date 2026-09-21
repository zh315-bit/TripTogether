# Development Record

## 2026-09-19 — Repository Initialization and Minimal Backend Skeleton

### What Was Implemented

- Initialized a local Git repository on `main`, without making a commit.
- Added a minimal FastAPI application and `GET /health`.
- Added a Pydantic response model and one endpoint test.
- Added backend requirements, `.gitignore`, and a comment-only `.env.example`.
- Normalized the overview and development record filenames.
- No database, authentication, JWT, Trip functionality, client, or Docker.

### Files to Review

- `backend/app/main.py`
- `backend/app/__init__.py`
- `backend/tests/test_health.py`
- `backend/requirements.txt`
- `.gitignore`
- `.env.example`
- `README.md`

### Key Code to Understand

`FastAPI(title="TripTogether")` creates the application. The `@app.get`
decorator connects HTTP GET requests for `/health` to the `health` function.
`HealthResponse` defines the response shape. `Literal["ok"]` restricts its
status to that exact value. FastAPI validates and serializes the model to JSON.
The endpoint is async but performs no external I/O.

`TestClient` calls the application without a network server. The test checks
HTTP status 200 and the complete JSON body. HTTPX is required by TestClient;
pytest runs the test. Uvicorn serves the application for real HTTP requests.
The package marker `app/__init__.py` makes `app` an explicit Python package.

### Architecture Concept

Begin with a small application entry point. A static health check needs no
service or database layer; introduce those modules only when needed.
This health check confirms the app responds, not database readiness.

### How to Test

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
python -m pytest -q
python -m uvicorn app.main:app --reload
```

In another terminal, run `curl -i http://127.0.0.1:8000/health`.
Expect HTTP `200 OK` and `{"status":"ok"}`. A browser can open the same address.
Stop the server with `Ctrl+C`. No environment variables are required.

Verification on Python 3.9.6 using the temporary environment described below:

- `python -m pytest -q`: 1 passed.
- `python -m pip check`: no broken requirements found.
- Real HTTP request through Uvicorn: 200 OK, `{"status":"ok"}`.
- Tested direct dependencies: FastAPI 0.128.8, Pydantic 2.13.5,
  Uvicorn 0.39.0, pytest 8.4.2, HTTPX 0.28.1.

### Problems Encountered

The supplied overview was `read.md`, not `README.md`, and `record.md` was empty.
Both were read before changes. The case-only record rename did not persist on
this filesystem, so `RECORD.md` was created explicitly.

The external drive generated a `._distutils-precedence.pth` metadata file in
the virtual environment. Python tried to read it as text and failed with
`UnicodeDecodeError`. Verification used an internal-filesystem environment:

```bash
python3 -m venv /private/tmp/triptogether-step1-venv
source /private/tmp/triptogether-step1-venv/bin/activate
```

Use these instead of the first two setup commands on this machine. Temporary
environments may be removed by the OS and can be recreated.
Sandbox permissions were also needed for Git initialization, package downloads,
and localhost HTTP verification.

### What I Learned

- HTTP methods and paths map to Python functions.
- Pydantic describes and validates outgoing data.
- Endpoint tests can check HTTP behavior without opening a network port.
- Virtual environments isolate dependencies from system Python.
- Git ignore rules exclude local secrets and generated files.

### Next Step

Configure PostgreSQL connectivity, without adding database models yet.

## 2026-09-19 — PostgreSQL Connection Infrastructure

### What Was Implemented

- Added environment-based PostgreSQL configuration with root `.env` fallback.
- Added a lazy, reusable SQLAlchemy Engine and Session Factory.
- Added `get_db`, a FastAPI session dependency with cleanup on success/error.
- Added an independent CLI check executing `SELECT 1` without business tables.
- Added configuration, lifecycle, CLI, health-isolation, and opt-in live tests.
- Kept `main.py` and the existing `/health` response unchanged.
- Added SQLAlchemy, psycopg binary, and python-dotenv only.
- **Step 2 completed.** Implementation and live PostgreSQL acceptance are
  complete, based on the developer's manually verified results reported below.

### Files to Review

- `backend/app/core/__init__.py`: configuration package marker.
- `backend/app/core/config.py`: environment precedence and URL validation.
- `backend/app/db/__init__.py`: database package marker.
- `backend/app/db/session.py`: engine, factory, and request-scoped sessions.
- `backend/app/db/check.py`: independent read-only connectivity check.
- `backend/tests/test_database.py`: isolated configuration and lifecycle tests.
- `backend/tests/test_postgres_integration.py`: explicitly enabled real check.
- `backend/tests/test_health.py`: database-independent health regression test.
- `backend/requirements.txt`: three new infrastructure dependencies.
- `.env.example`: placeholder connection URL, not real credentials.
- `README.md`: configuration, verification, and limitations.
- `RECORD.md`: this entry.

### Key Code to Understand

`get_database_url()` reads `DATABASE_URL` from the environment, falling back to
the repository-root `.env`. SQLAlchemy parses the URL, which must specify
`postgresql+psycopg` and a database name. Configuration errors do not echo
credentials. No real `.env` was created in this task; existing ignore rules
already exclude it.

`get_engine()` caches the Engine, which manages connection pooling and dialect
behavior. Creating an Engine does not immediately connect. A real connection
is acquired when SQL executes. `pool_pre_ping=True` checks pooled connections
before reuse; a five-second driver connection timeout bounds individual
connection attempts. Cached configuration requires a process restart to change.

`get_session_factory()` caches `sessionmaker`, not a Session. Each call to the
factory creates a separate Session. A Session represents a unit of database
work and manages transaction state; it is not the underlying network connection.
`get_db()` yields one Session to an endpoint and closes it afterward even when
the endpoint raises an exception. Closing releases its connection to the pool
and rolls back unfinished transactions. This dependency never auto-commits.

For a future synchronous endpoint, `db: Session = Depends(get_db)` asks FastAPI
to run `get_db`, pass its yielded Session as `db`, and perform cleanup afterward.
The request flows through endpoint/business code, Session, Engine, psycopg,
and PostgreSQL. A Session must not be shared between requests or concurrent work.
Synchronous database calls belong in synchronous endpoints, not directly in
async endpoints where they would block the event loop.

`check_connection()` executes SQLAlchemy `text("SELECT 1")` and requires the
scalar result to equal 1. The CLI uses the same factory as the dependency,
closes the Session, disposes the Engine, and returns a nonzero code on failure.
It does not print driver exceptions that might expose connection details.

### Architecture Concept

Configuration and database infrastructure stay separate from HTTP liveness.
SQLAlchemy supplies SQL/transaction/pool abstractions, while psycopg implements
the PostgreSQL connection protocol. FastAPI handles HTTP and dependency
injection; it could call a driver directly, but using one shared infrastructure
module keeps connection and transaction policy consistent.

No model, repository, migration, authentication, or business API was added.
The `.env.example` is a safe template; `.env` is local configuration containing
secrets and must not be committed. Process environment variables allow deployment
without keeping credentials in Python source.

### How to Test

Activate the internal-filesystem virtual environment described in Step 1 and
install the updated requirements from the repository root:

```bash
source /private/tmp/triptogether-step1-venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
python -m pytest -q
python -m app.db.check
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m uvicorn app.main:app --reload
```

The live check/test requires a running PostgreSQL server and an existing
database/login configured in `DATABASE_URL` or the root `.env`. See README
for preparation. In another terminal, run
`curl -i http://127.0.0.1:8000/health`; expect 200 and `{"status":"ok"}`.

Initial verification results (before local PostgreSQL setup):

- Full default suite: **18 passed, 1 skipped** (the opt-in PostgreSQL test).
- `pip check`: no broken requirements.
- Uvicorn startup succeeded without database configuration.
- Real HTTP `/health`: **200 OK**, `{"status":"ok"}`.
- CLI without configuration: failed with exit code 1 as expected.
- CLI using the sample URL against localhost: failed with exit code 1.
- Outside-sandbox TCP probe to `127.0.0.1:5432`: connection refused (errno 61).
- At that time, successful real PostgreSQL connectivity was not verified.
  Mock-based tests verified code behavior only, not PostgreSQL availability.
- Tested new dependency versions: SQLAlchemy 2.0.54, psycopg/psycopg-binary
  3.2.13, python-dotenv 1.2.1, with Python 3.9.6.

Final acceptance results (manually verified and reported by the developer):

- PostgreSQL 17 is running locally.
- The `triptogether` database has been created.
- `python -m app.db.check`:
  `PostgreSQL connectivity check passed (SELECT 1).`
- `RUN_POSTGRES_TESTS=1 python -m pytest -q`: **19 passed**.
- FastAPI starts normally.
- `GET /health`: **HTTP 200**, response `{"status":"ok"}`.
- Real PostgreSQL connectivity is now verified; **Step 2 is complete**.
  These results were supplied by the developer, not rerun during this
  documentation-only update.

### Problems Encountered

Initially, no PostgreSQL tools were found in PATH or the checked common installation
locations, no real DATABASE_URL or root `.env` was present, and the local
PostgreSQL port refused connections. This acceptance blocker is now resolved:
the developer configured local PostgreSQL 17 and the `triptogether` database,
then successfully ran the real connectivity check and all 19 tests. No SQLite,
Docker, hidden database installation, or business tables were introduced.

Reused the internal temporary environment to avoid the external-drive metadata
issue recorded in Step 1. Network installation and localhost verification
required sandbox approval. The verification server was stopped after testing.

### What I Learned

- An Engine is reusable infrastructure, not one fresh connection per request.
- A Session manages database work and transactions; a factory creates Sessions.
- `yield` dependencies provide deterministic request-resource cleanup.
- Successful configuration parsing is not proof of a working database.
- Real integration tests must be distinguishable from mocks and skipped tests.
- Keep liveness independent from external dependencies and credentials private.

### Next Step

The previously recommended local PostgreSQL setup and connectivity acceptance
are complete. Step 3 has not been started; await the developer's instructions.

## 2026-09-19 — Step 3A: SQLAlchemy Base, User Model, and Alembic

### What Was Implemented

- **Step 3A completed.** Re-read README, AGENT, RECORD and all backend code
  before changes; confirmed Step 1/2 and repeated the real connectivity check.
- Added one shared Declarative Base and the first business model, `User`.
- Added Alembic configuration using existing environment-based database
  configuration, without credentials in migration files or INI configuration.
- Generated revision `0001` using autogenerate, manually reviewed its columns,
  types, defaults, constraints and reversal, then formatted the migration.
- Applied the migration to local PostgreSQL 17.11, database `triptogether`.
- Verified upgrade, downgrade, and re-upgrade; final database is at `0001`.
- Added metadata and PostgreSQL migration/constraint tests.
- Added only Alembic as a direct dependency (tested version 1.16.5).
- No registration, login, hashing, JWT, other models, or client functionality.

### Files to Review

- `backend/app/db/base.py`: shared Declarative Base.
- `backend/app/models/__init__.py`: import/register User.
- `backend/app/models/user.py`: the five-column User mapping.
- `backend/alembic.ini`: script location and Python import path, no database URL.
- `backend/migrations/env.py`: metadata registration, existing Engine reuse,
  offline SQL generation, and an externally supplied test connection.
- `backend/migrations/script.py.mako`: template for future revision files.
- `backend/migrations/versions/0001_create_users_table.py`: reversible schema.
- `backend/tests/test_user_model.py`: metadata and uniqueness assertions.
- `backend/tests/test_user_migrations.py`: actual PostgreSQL migrations,
  constraints, defaults, ORM reads, and isolated round-trip checks.
- `backend/requirements.txt`: Alembic dependency.
- `README.md`: current status and migration instructions.
- `RECORD.md`: this development entry.

### Key Code to Understand

`Base(DeclarativeBase)` provides one shared model registry and `Base.metadata`,
the in-memory collection of table definitions. `User(Base)` adds `users` to
that collection. Importing a model registers metadata; it does not create a
database table. `app/models/__init__.py` imports User, and Alembic's `env.py`
imports that package before reading `Base.metadata`.

| Field | Definition and purpose |
| --- | --- |
| id | INTEGER Identity primary key, NOT NULL; generated unique row identifier |
| username | VARCHAR(50), NOT NULL, named UNIQUE constraint |
| email | VARCHAR(254), NOT NULL, named UNIQUE constraint |
| password_hash | VARCHAR(255), NOT NULL; reserved for a future password hash |
| created_at | TIMESTAMP WITH TIME ZONE, NOT NULL, server default now() |

`Identity()` makes PostgreSQL generate IDs when omitted; IDs may have gaps.
The primary key identifies a row independently of a changeable username/email.
Both unique constraints create supporting B-tree indexes automatically, so no
duplicate index definitions are needed. Unique comparisons are case-sensitive
under the current ordinary string types; no normalization policy is added.
Application-level existence checks alone cannot prevent simultaneous requests
from inserting duplicates; the database constraint enforces that invariant.
Extra indexes cost disk space and slow writes, so they should support actual
query needs rather than be added indiscriminately.

`DateTime(timezone=True)` plus `server_default=func.now()` uses PostgreSQL
`timestamptz`: an absolute instant represented internally in UTC, displayed in
the connection's timezone. It avoids naive local timestamps and works for
inserts outside Python. `now()` uses transaction start time. Convert aware
Python values to UTC for display when needed; this field does not force the
connection's display timezone. Tests explicitly set their local timezone to UTC.

No hash algorithm or plaintext-password API was implemented. The string column
alone cannot distinguish a hash from plaintext; future password handling must
hash before persistence. Tests use only a non-secret hash-placeholder string.

`env.py` supplies `target_metadata=Base.metadata`, type/default comparison,
and the existing Engine to Alembic. A supplied Connection lets tests use one
outer transaction without touching ordinary application tables. Offline mode
uses the existing parsed URL; neither mode copies secrets into the INI file.

Revision `0001` has no parent. `upgrade()` creates `users` with the specified
constraints; `downgrade()` drops it. Dropping a table also deletes its rows:
re-upgrading restores structure, not lost data.

### Architecture Concept

ORM means mapping an object-oriented model to relational storage: User is the
class mapping, `users` is the table, and a persisted User instance corresponds
to a row identified by its primary key. Merely constructing a User object does
not save it; a Session must persist it.

Models describe the desired current structure; migrations describe ordered
changes between versions. Alembic records the applied revision in
`alembic_version`. This makes the same evolution reproducible on another
developer's database or a deployment, unlike undocumented manual ALTER TABLEs.

Autogenerate compares imported metadata with the live database and proposes
migration operations. It does not apply them or prove they are safe. Missing
imports, column renames, data transformations, and destructive changes require
human review. A future schema version must be a new revision, not an edit to
the already-applied `0001`. No `create_all()` startup shortcut was added.

### How to Test

With the Step 1 virtual environment active, install updated requirements from
the project root and run:

```bash
python -m pip install -r backend/requirements.txt
cd backend
python -m app.db.check
python -m alembic upgrade head
python -m alembic current
python -m alembic check
RUN_POSTGRES_TESTS=1 python -m pytest -q
```

Connect psql to the same host/role/database as DATABASE_URL, then execute
`\dt`, `\d users`, and `SELECT version_num FROM alembic_version;`.
Expected version: `0001`. Expected tables: `users`, `alembic_version`.
Check field lengths, NOT NULL, identity, unique constraints and time default
against the model and migration. `alembic check` must report no differences.

Actual verification:

- Initial database inspection: no tables; PostgreSQL 17.11 (Homebrew).
- `python -m app.db.check`: passed before and after migrations.
- `python -m alembic upgrade head`: succeeded.
- Real `psql \dt`: public.users and public.alembic_version.
- Real `psql \d users`: all five expected columns, identity PK, two named UNIQUE
  constraints with B-tree indexes, NOT NULL on every column, timestamptz/now().
- Version query returned `0001`; users count was zero before reversal.
- Locked users and rechecked zero rows inside a transaction before calling
  Alembic downgrade to base; verified users was removed and committed.
- Re-ran CLI upgrade to head successfully, restoring users.
- `python -m alembic check`: `No new upgrade operations detected.`
- Full PostgreSQL-enabled suite: **30 passed, 0 skipped, 0 failed**.
- Default suite: **20 passed, 10 skipped** (explicit PostgreSQL opt-in).
- Existing connection and `/health` tests passed unchanged.
- `python -m pip check`: no broken requirements.

The nine new live test cases run migrations in a unique private schema inside
an outer transaction and roll back all test DDL/data afterward. They verify
upgrade/downgrade/upgrade, metadata agreement, defaults and ORM reads,
duplicate username/email rejection, and NULL rejection for all five columns.
Together with the existing connection test, ten tests require PostgreSQL.
Tests require CREATE SCHEMA permission and never substitute SQLite.
They never downgrade public.users; use them for routine reversibility checks.

### Problems Encountered

README still described Step 2 as pending after the previous RECORD-only update.
The completed Step 2 entry and a fresh successful connection check established
the actual state; README now reflects current verified functionality.

On the external drive, macOS generated `._0001_create_users_table.py` beside
the real migration. Alembic attempted to load that binary metadata as Python,
causing the initial nine migration test setup errors (21 other tests passed).
Removed only AppleDouble metadata using `dot_clean -m migrations/versions`;
the real migration was preserved and the full rerun passed. The issue can recur
after edits/copies on this filesystem; README documents the targeted cleanup.
No Alembic internals were patched to work around filesystem behavior.

Package download and localhost access required sandbox approval. Existing
database credentials were reused without printing or modifying `.env`.
The existing `.gitignore` ignores `.env` and AppleDouble files, not migrations.
No existing business data was removed: the initial database and pre-downgrade
users table were empty, and automated migration tests were isolated.

### What I Learned

- Base.metadata is a schema description, not a live database.
- ORM objects become persisted rows through a Session, not class definition.
- Database constraints protect invariants even during concurrent requests.
- Unique constraints already provide lookup indexes in PostgreSQL.
- Server-generated timezone-aware timestamps avoid naive local-time ambiguity.
- Alembic tracks schema history, and autogenerated changes still need review.
- Reversible schema operations do not imply reversible data deletion.
- Real PostgreSQL tests can be isolated with schemas and transactions.

### Next Step

Implement user registration with password hashing using the existing User model;
do not add login or JWT in that task.

## 2026-09-19 — Step 4: User Registration and Password Hashing

### What Was Implemented

- **Step 4 completed.** Reviewed README, AGENT, RECORD and the actual backend
  before edits; confirmed Steps 1, 2 and 3A and current revision `0001`.
- Reviewed OpenTrip as a reference before implementation, without copying code.
- Added `POST /auth/register`, returning 201 with four safe user fields.
- Added separate Pydantic request/response schemas, email normalization,
  bounded username/password validation, and rejection of unexpected fields.
- Added Argon2id password hash/verify helpers; no plaintext persistence.
- Added one registration service using existing request-local `get_db`.
- Added duplicate pre-checks, real PostgreSQL UNIQUE fallback, rollback and
  credential-safe error responses; `/health` remains unchanged.
- Added regression, hashing and real PostgreSQL registration tests.
- Kept User fields and migration `0001` unchanged; no empty/new migration.
- Did not implement login, JWT, OAuth, sessions, roles, or Trip functionality.

### Files to Review

- `backend/app/api/__init__.py`: HTTP package marker.
- `backend/app/api/auth.py`: thin registration router, response schemas/statuses.
- `backend/app/api/errors.py`: validation redaction and documented error shapes.
- `backend/app/core/security.py`: Argon2id hash and verify wrappers.
- `backend/app/schemas/__init__.py`: schema package marker.
- `backend/app/schemas/user.py`: UserRegister and UserResponse.
- `backend/app/services/__init__.py`: service package marker.
- `backend/app/services/registration.py`: duplicate checks and transactions.
- `backend/app/main.py`: registers router and safe validation error handler.
- `backend/requirements.txt`: adds email-validator and argon2-cffi only.
- `backend/tests/conftest.py`: shared isolated PostgreSQL migration fixture.
- `backend/tests/test_user_migrations.py`: uses the extracted fixture; assertions
  and migration behavior remain unchanged.
- `backend/tests/test_registration.py`: input/error schemas, registration,
  duplicate conflicts, rollback, persistence and sensitive-field protection.
- `backend/tests/test_security.py`: salt behavior, Argon2id parameters, mismatch,
  malformed hash and long Unicode password tests.
- `README.md`: current development commands and API policy.
- `docs/step4-review.md`: detailed reference review, six-file reading guide,
  request flow, security rationale and twelve interview Q&As.
- `RECORD.md`: this entry.

### Key Code to Understand

`UserRegister` accepts username/email/password, not a User ORM object.
Username is trimmed, 1-50 ASCII letters/digits/underscores, case-sensitive.
Restricting this identifier avoids invisible/control characters and keeps the
rule simple. Email uses Pydantic EmailStr with email-validator, then lowercases
the entire address and enforces the existing 254-character column limit.
Case-insensitive email is an explicit application policy, not a claim about all
mail systems; plus tags and dots are not removed. Direct SQL bypasses this
policy, so other writers must maintain canonical email values themselves.

The password is SecretStr with 8-128 Unicode characters. It is never trimmed
or normalized. Invalid surrogate characters are rejected before hashing;
maximum UTF-8 input is 512 bytes, safely below Argon2's input limit. The policy
bounds request work without bcrypt-style 72-byte truncation. SecretStr masks
routine representations but does not guarantee erasure of Python memory.

`hash_password()` uses argon2-cffi's RFC_9106_LOW_MEMORY profile: Argon2id,
64 MiB, 3 iterations, parallelism 4, fresh 16-byte random salt and 32-byte hash.
The encoded output fits the existing password_hash column. `verify_password`
checks that encoding, returning false for mismatches or invalid hashes.
No login route was added merely to exercise verification.

The request flow is:

```text
POST /auth/register -> UserRegister validation -> thin router + get_db
-> registration service -> SELECT duplicate checks -> hash_password
-> User(password_hash=...) -> db.add -> db.commit -> PostgreSQL
-> db.refresh -> UserResponse -> HTTP 201
```

`db.add()` makes the object pending; commit flushes INSERT and commits the
transaction. Refresh reloads generated/default values. The dependency closes
the Session after the request. UserResponse uses from_attributes and returns
only id, username, email and created_at, never password or password_hash.

Pre-checks improve error messages, but two requests can both see no existing
row. PostgreSQL UNIQUE is the final guarantee. IntegrityError handling first
rolls back, then maps only SQLSTATE 23505 and the known constraints
`uq_users_username` / `uq_users_email` to a 409. Other database or hashing
failures receive a generic 503, with no raw SQL, exception or bound values.
Application duplicate errors also end the transaction with rollback.

FastAPI's default validation errors can include raw inputs, including the
whole request body for a missing field. The registered handler returns only
loc/msg/type with 422; input/context are removed even for malformed JSON.
OpenAPI explicitly documents these safe 422 fields plus 409 and 503 shapes.

### Architecture Concept

Pydantic schemas describe HTTP boundaries; the SQLAlchemy model describes
persistence. Input may contain a password, persistence contains its hash, and
output contains neither. A thin router delegates one cohesive service; there
is no repository/manager/factory hierarchy for this small workflow.
The synchronous route suits synchronous database and hashing calls.

OpenTrip reference checkout: `stvlynn/OpenTrip`, commit
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`. Inspected infrastructure/auth/auth.ts,
interfaces/http/app.ts, errors.ts, response.ts, Prisma User/Account definitions,
the frontend AuthForm, and profile display-name validation.
Borrowed separation of HTTP/auth/application responsibilities, explicit public
data selection and expected-error translation.

Not adopted: Better Auth/Hono/Prisma, OAuth, OTP/email verification,
two-factor, session management, Cloudflare infrastructure, sample-trip hooks,
profile projections, or extra User fields. They exceed the current scope and
do not fit this backend's deliberately small architecture.

The reference delegates signup to Better Auth: no project-owned signup
duplicate-check or password-hashing implementation was found. Its precise
dependency-internal algorithm, duplicate statuses, and complete auth response
filtering were not verified. User has unique email but not our unique username;
Account holds credential fields separately. Explicit public projections omit
credentials, but this review does not certify every reference route.
Full source paths and limitations are recorded in `docs/step4-review.md`.

### How to Test

With the existing virtual environment active:

```bash
python -m pip install -r backend/requirements.txt
cd backend
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m app.db.check
python -m alembic current
python -m alembic check
python -m uvicorn app.main:app --reload
```

Open `/docs`, expand POST /auth/register, choose Try it out and supply a
disposable username/email and a password entered locally. Success is 201.
Repeat a username/email for 409, malformed email or short password for 422.
GET /health must remain 200 with `{"status":"ok"}`.

The default suite needs no database and skips PostgreSQL cases explicitly.
Integration tests reuse the Step 3A unique-schema outer transaction, now in
conftest. Each API request gets a Session with
`join_transaction_mode="create_savepoint"`: service commit releases only its
savepoint, not the outer transaction; service rollback does not destroy the
test schema. Final fixture rollback removes test tables/data. No SQLite.

Actual verification:

- Default suite: **44 passed, 15 skipped, 0 failed**.
- Full PostgreSQL suite: **59 passed, 0 skipped, 0 failed**.
- Original health, connection, User metadata and Alembic tests still passed.
- Password tests verify Argon2id, random salts, correct/wrong passwords, invalid
  hashes and significance of the final character of a long multibyte password.
- Two fallback tests force duplicate pre-checks to report no row, then actual
  PostgreSQL rejects INSERT. Both return 409 and call rollback; a subsequent
  valid request succeeds. These simulate a race outcome deterministically,
  not a simultaneous-request load test.
- Connection CLI succeeded; migration current remained **0001 (head)**.
- Uvicorn was actually started with --reload.
- Actual HTTP POST returned **201**, with only the four public fields.
- Actual duplicate email (case variant) and username each returned **409**.
- Browser Swagger Try it out submission returned **201**.
- SQL SELECT retrieved both manual test rows, hashes and timestamps internally;
  hashes differed from plaintext and verification succeeded. Output exposed
  only boolean verification results, not passwords or hash strings.
- GET /health returned **200**, `{"status":"ok"}`.
- Before manual tests: 0 users, 0 noncanonical email rows. Exactly two manual
  test users were created and then removed using exact id/username matches.
  Final users count returned to 0; the identity sequence was not reset.
- Final PostgreSQL inspection: 0 remaining test schemas, 0 users, revision 0001.
- `alembic check`: no new upgrade operations; `pip check`: no broken requirements.
- The temporary Uvicorn server and Swagger browser tab were closed after
  verification. No password or hash appeared in the inspected server logs.

### Problems Encountered

The web lookup returned no usable content for the reference. Cloned the public
repository into a temporary directory with network approval and inspected the
pinned checkout directly. Read the official argon2-cffi 25.1.0 API documentation;
tested new dependencies are argon2-cffi 25.1.0 and email-validator 2.3.0.

A malformed-Unicode test initially failed in HTTPX's JSON encoder before
reaching the server. Changed the test to send escaped JSON; the actual API now
gets exercised and safely returns 422. No hashing failure is exposed to clients.

Swagger originally described FastAPI's default validation payload containing
input/context, despite the new redacted handler. Added small explicit error
schemas so documentation and actual responses agree.

Reused the internal-filesystem virtual environment to avoid the earlier
external-drive metadata issue. The existing migration was not edited and no
new migration was needed. Local connections/package downloads required sandbox
approval; `.env` was neither printed nor modified. Production HTTPS, load
limits and abuse controls remain deployment considerations, not Step 4 features.

### What I Learned

- Hashing verifies a secret without recovering it; encryption is reversible.
- Password-specific Argon2id is deliberately costly, unlike plain SHA-256.
- Random salt makes identical passwords produce different stored encodings.
- Separate input, persistence and output types prevent credential leakage.
- A response whitelist is necessary even when the stored password is hashed.
- Validation errors, not only success responses, can leak raw request input.
- Duplicate SELECT checks cannot replace database UNIQUE under concurrency.
- add, commit, refresh and rollback have different transaction responsibilities.
- Savepoints let tests exercise commits and failures without polluting dev data.

### Next Step

Step 5: implement Login + JWT Authentication using the existing User model and
password verification helper. Do not begin it automatically.

## 2026-09-19 — Step 5: Login and JWT Authentication

### What Was Implemented

- **Step 5 completed.** JSON `POST /auth/login`, Argon2id verification, signed
  expiring JWT access tokens, reusable current-user dependency, and protected
  `GET /auth/me`. Browser Authorize interaction has the limitation noted below.
- Read the required project documents and Step 4 code before implementation.
- Rechecked OpenTrip remote HEAD before implementation: unchanged at
  `cfc78a04d0eeba3daaec4b755b110d89938ae4fc`. Reviewed Better Auth configuration,
  Hono session context and guards, frontend signIn.email, Prisma
  User/Account/Session definitions, and auth-session documentation.
- Centralized environment configuration, reused email normalization and the
  existing password verification helper, and added safe uniform 401 responses.
- Added direct JWT tests and real PostgreSQL register/login/me integration
  tests using existing private-schema transactions and request savepoints.
- Preserved registration, `/health`, User model and revision `0001`.
  No schema change or migration; JWT is not stored in PostgreSQL.
- No refresh, logout, blacklist, OAuth, session table, permissions or Trip code.

### Files to Review

- `backend/app/api/auth.py`: login/me routes and safe response/error mapping.
- `backend/app/api/dependencies.py` (new): Bearer extraction, token validation
  and reusable get_current_user.
- `backend/app/services/authentication.py` (new): password login and user lookup.
- `backend/app/core/security.py`: token creation/validation; Argon2 helpers reused.
- `backend/app/core/config.py`: lazy JWT settings and shared environment reader.
- `backend/app/schemas/user.py`: UserLogin, TokenResponse and shared normalization.
- `backend/requirements.txt`: adds only PyJWT as a new direct dependency.
- `.env.example`: placeholder JWT secret, HS256 and 30-minute lifetime.
- `backend/tests/conftest.py`: shared request-session fixture and isolated keys.
- `backend/tests/test_registration.py`: uses shared fixture; removes outdated
  assertion that login does not exist.
- `backend/tests/test_jwt.py` (new): configuration and direct security tests.
- `backend/tests/test_authentication.py` (new): endpoint/lifecycle/error tests.
- `README.md`: current status, configuration, login/me and verification commands.
- `docs/step5-review.md` (new): reference review, six-file guide, concepts and
  fourteen interview questions with answers.
- `RECORD.md`: this development entry.

### Key Code to Understand

Login: JSON -> UserLogin -> normalized email -> authenticate_user -> SELECT User
-> verify_password(input, stored Argon2id hash) -> create_access_token(user.id)
-> TokenResponse with access_token and token_type bearer.

UserRegister inherits the shared email normalization and password encoding
validation from UserLogin. Registration still requires 8-128 password characters;
login accepts 1-128 so a short incorrect password receives 401, not registration
policy enforcement. Password content is never normalized or trimmed.

Unknown email and wrong password return the same 401 message and
WWW-Authenticate: Bearer. A dummy Argon2 hash is verified for unknown email;
this reduces an obvious timing shortcut, not all account enumeration or timing
differences. Existing registration conflict behavior remains unchanged.

JWTSettings reads process environment before root `.env` and hides the secret
from repr. The placeholder, missing/short key and unsupported algorithms fail
closed. Use a cryptographically random key with at least 32 UTF-8 bytes;
minimum length alone cannot establish randomness. HS256 is the only supported
algorithm. ACCESS_TOKEN_EXPIRE_MINUTES defaults to 30 and permits 1-1440.
JWT configuration is lazy, leaving /health and registration independent.
Configuration failures in token operations return safe 503 responses.

create_access_token signs only sub=str(user.id) and an aware-UTC-derived exp.
decode_access_token fixes the allowed algorithm from server configuration,
requires both claims, checks signature/expiry and validates a canonical positive
decimal subject within PostgreSQL INTEGER range. Invalid types, overflowing IDs,
missing claims, tampering and expiry become credential-safe errors.
PyJWT handles JWT encoding and cryptography, not users or HTTP policy.

Protected flow: Authorization Bearer -> HTTPBearer -> get_token_user_id
-> decode/validate -> get_db -> find_current_user -> PostgreSQL -> UserResponse.
Invalid tokens fail before database access. Valid signatures do not establish
that a user still exists; deleted/missing users return 401. SQL failures roll
back and become generic 503 responses without raw SQL or credentials.
get_current_user supplies the resolved User through Depends to /auth/me.
The existing yielding database dependency closes the request-local Session.

UserResponse still exposes only id, username, email and created_at.
Token and current-user success responses use Cache-Control: no-store.
Password inputs remain SecretStr and validation errors omit raw input.
No real secrets, password hashes or complete JWTs are included in this record.

### Architecture Concept

OpenTrip uses Better Auth with persisted sessions, browser cookies and native
Bearer session credentials. Bearer transport does not itself mean JWT.
TripTogether keeps the concepts of isolated auth, current user, protected
boundaries and safe projections but implements them using FastAPI dependencies,
SQLAlchemy, Argon2id and PyJWT. No Better Auth/TypeScript code was transplanted.
No project-owned JWT login implementation was found in inspected OpenTrip code;
Better Auth internal password verification/error behavior was not independently
verified. Full reference paths and review limitations are in step5-review.md.

JWT is Header.Payload.Signature. The header identifies the algorithm; our
payload contains only stable identity and expiry. These parts are encoded,
not encrypted. HS256 authenticates header and payload with the server secret;
changing sub from "1" to "2" without a matching signature is rejected.
The server temporarily receives a submitted password but does not recover the
original password from its Argon2 encoding.

JWT validation is stateless: no server token/session store is required.
The current-user SQL lookup answers a different question: does this identity
still exist? PostgreSQL remains the source of truth, so there is no contradiction.
Authentication identifies a user; future authorization checks whether that user
may act on a particular Trip. This step implements only authentication.

Expiry limits stolen-token lifetime but cannot selectively revoke tokens.
Rotating the shared signing key invalidates old tokens globally. Bearer tokens
are replayable credentials, so production HTTPS and careful client storage
remain necessary. No refresh/revocation/rate-limiting features were added.

### How to Test

Activate the existing virtual environment. Configure DATABASE_URL and a secure
JWT_SECRET_KEY locally, using the README process-environment example or ignored
root `.env`. Never use the template placeholder. From the project root:

```bash
python -m pip install -r backend/requirements.txt
cd backend
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m app.db.check
python -m alembic current
python -m alembic check
python -m uvicorn app.main:app --reload
```

Open /docs, register a disposable user, then POST /auth/login using JSON email
and password. Expect 200 with access_token and token_type bearer. Select
Authorize and enter the raw token without a Bearer prefix. GET /auth/me should
return the same public user. Without credentials or with an invalid/expired
token, expect 401 and WWW-Authenticate: Bearer. Wrong password and unknown email
must return identical errors. GET /health remains 200 with {"status":"ok"}.
README also contains an HTTPX example that keeps the token out of console output.

Actual final verification on local September 19, 2026:

- Default suite: **106 passed, 20 skipped, 0 failed**.
- PostgreSQL-enabled suite: **126 passed, 0 skipped, 0 failed**.
- Direct tests cover key/config precedence, required claims, expiration,
  tampering, wrong keys/algorithms, invalid subjects and payload types.
- API tests cover registration/login/me, normalization, identical login errors,
  missing/deleted users, safe validation/DB errors, and sensitive-field exclusion.
- Existing health, registration, hashing, duplicates, model, migration and
  database-connectivity tests all pass. No SQLite is used.
- `python -m app.db.check`: SELECT 1 passed.
- Database revision: **0001**. `alembic check`: no new upgrade operations.
- `pip check`: no broken requirements. Tested new dependency: PyJWT **2.14.0**.
- Uvicorn actually started with --reload and a random process-only signing key.
- Real HTTP: register **201**, normalized-email login **200**, token_type bearer,
  /auth/me **200** matching the public registration response.
- Real HTTP: wrong password/unknown email identical **401**; missing/invalid
  token **401**, with Bearer challenge header.
- Real HTTP: /health **200**, {"status":"ok"}; /docs **200**; OpenAPI contains
  BearerAuth and marks /auth/me protected while login remains public.
- Interactive Swagger Authorize -> /auth/me was **not completed**: the browser
  tool failed after interruption with unsupported authentication method.
  HTTP and OpenAPI validation do not substitute for that UI interaction.
- Removed only the two exact task-created manual users using ID/name matches,
  including the account left by the interrupted verification. Final counts:
  **0 users, 0 test schemas**. No identity sequence reset.
- Real `.env` was not changed or printed; `git check-ignore .env` confirms ignore.
- The resumed verification's temporary Uvicorn server was stopped afterward.

### Problems Encountered

The interrupted run no longer had a running test server, so a fresh temporary
server used port 8015 and a random key kept only in its process environment.
Its manual test user and the previous interrupted test user were cleaned up
with exact identifiers; no unrelated data was deleted.

The browser automation runtime could not recover the earlier Swagger tab:
`unsupported Codex auth method: apikey`. UI authorization remains a documented
manual verification limitation. The HTTP lifecycle, docs availability and
OpenAPI Bearer security contract were separately verified successfully.

Local PostgreSQL, local HTTP and dependency/reference access required sandbox
approval. Reused the internal-filesystem virtual environment to avoid earlier
AppleDouble issues. Consulted the official PyJWT API documentation and pinned
the reference review to the actual checked remote commit.

### What I Learned

- A signed JWT is not an encrypted container; secrets never belong in claims.
- Signature validity, expiry and current database identity all need checks.
- Algorithm selection must be server-controlled, not trusted from a token.
- Argon2 verification reuses the stored salt/parameters instead of rehash-and-compare.
- Shared schema validation preserves one email policy across registration/login.
- Invalid client credentials and unavailable server configuration are distinct.
- Stateless token verification can coexist with a current-user database query.
- Existing schema/transaction/savepoint fixtures support real authentication tests.

### Next Step

Step 6: Trip CRUD. Not started or implemented in this task.

## 2026-09-19 — Step 6: Trip Model, CRUD and Owner Authorization

### What Was Implemented

- **Step 6 completed.** Added Trip model, revision 0002, create/list/detail/
  partial-update/delete APIs, and owner-only authorization.
- Fully reviewed required project documentation and current backend before edits.
  Rechecked OpenTrip remote HEAD and analyzed Trip domain before implementation.
- Current reference remains `cfc78a04d0eeba3daaec4b755b110d89938ae4fc`.
  Reviewed Prisma Trip/Member/child schemas, domain types/create/permissions,
  application TripService, HTTP schemas/routes, DTOs and SQL persistence.
- Reused existing JWT current-user and request-local Session dependencies.
  No new dependencies or authentication behavior changes.
- Added strict input/output schemas, final-state date validation, database
  constraints, row-locked updates and credential-safe rollback/error handling.
- Preserved User migration 0001 byte-for-byte; applied new 0002 to development
  PostgreSQL and verified reversal only in isolated test schemas.
- No TripMember, invitations, roles, itinerary, map, expenses, booking,
  refresh/logout, client or other future-stage functionality.

### Files to Review

- `backend/app/models/trip.py` (new): eight fields, constraints, index, owner ORM link.
- `backend/app/models/__init__.py`: registers Trip in shared metadata.
- `backend/app/schemas/trip.py` (new): create/update validation and safe response.
- `backend/app/services/trips.py` (new): CRUD, owned lookup, locks and transactions.
- `backend/app/api/trips.py` (new): five authenticated routes and HTTP errors.
- `backend/app/main.py`: mounts Trip router; health behavior unchanged.
- `backend/migrations/versions/0002_create_trips_table.py` (new): reviewed
  autogenerated forward/reverse schema evolution.
- `backend/tests/test_trip_model.py` (new): metadata and schema boundaries.
- `backend/tests/test_trip_migrations.py` (new): real constraints, timestamps,
  relationship and isolated migration reversal.
- `backend/tests/test_trips.py` (new): lifecycle, Alice/Bob isolation, PATCH,
  anonymous access, forbidden input, SQL failures and OpenAPI.
- `backend/tests/test_user_migrations.py`: advances head/table expectations to
  0002; preserves existing full migration reversal checks.
- `README.md`: status, Trip API, create example, migration/test commands.
- `docs/step6-review.md` (new): detailed reference review, field rationale,
  seven-file reading guide, concepts and sixteen interview Q&As.
- `RECORD.md`: this entry.

### Key Code to Understand

Trip fields: integer Identity id; required trimmed name (120) and destination
(200); start_date/end_date DATE; required owner_id FK to users.id; timezone-aware
created_at/updated_at with database now() defaults. An owner index serves the
scoped list query. A date CHECK and nonblank text CHECKs protect direct writes.
No unused status, map coordinates or metadata JSON were introduced.

DATE represents calendar days, not moments needing timezone conversion.
created_at follows User's timestamptz strategy. updated_at uses SQLAlchemy
onupdate=statement_timestamp(), so it advances on actual ORM UPDATE even within
a long transaction. This is not a DB trigger; handwritten SQL must set it.
Empty/identical PATCH is a no-op and preserves updated_at.

Trip.owner provides the only new relationship. ForeignKey is a PostgreSQL
constraint preventing nonexistent owners; relationship is ORM object navigation.
Many trips may have the same owner_id, expressing User 1 -> many Trips without
an unused inverse collection. ON DELETE RESTRICT prevents orphaning trips by
deleting an owner; no user-delete endpoint or implicit cascade was added.

Creation flow: JWT -> current_user -> TripCreate -> router/service ->
Trip(owner_id=current_user.id) -> Session add/commit/refresh -> TripResponse.
Client id/owner_id/timestamps and unknown fields are rejected, not trusted.

get_owned_trip always queries by BOTH id and owner_id. Detail/PATCH/DELETE
share this helper. Missing or non-owned resources return the same 404.
Collection SQL includes owner_id=current_user.id; other users' trips are never
loaded just to discard them in Python. Lists use deterministic ID order.

TripUpdate distinguishes omitted fields from explicit null. Omitted means
preserve, null is rejected. For PATCH the service locks the owned row with
SELECT FOR UPDATE, merges the supplied dates with the stored counterpart and
validates the complete pair before assignments. This prevents concurrent
partial edits from validating stale dates. No optimistic versioning is added;
same-field changes remain last-writer-wins.

Service owns SQL, authorization and transactions. A small shared error context
rolls back SQLAlchemy failures (including IntegrityError) and raises a safe
service exception; route context translates to generic 503. Expected absent/
unauthorized resources become 404 and invalid dates safe 422. No raw database
error or request values are exposed. Hard DELETE returns 204 without a body.

### Architecture Concept

OpenTrip's actual Trip fields include string id/title/start_date/end_date/status,
currency/cover_color/owner_id/created_at/version/agent_seed_pending/cover_url/intake.
Owner comes from auth context and becomes the first owner-role member. Its
Prisma owner_id is nullable String without a declared User FK.
Destination is an intake label with optional geocoded coordinates, also used
for itinerary city. Dates are strings with optional unknown values and schedule
fallbacks; no Trip-level timezone field was found.
Status type is active/planning/settled, create defaults planning. No complete
Trip lifecycle transitions or whole-Trip delete endpoint/service were found
in the inspected current Trip modules. Child ON DELETE CASCADE is not proof of
a user-facing Trip deletion feature.

Borrowed authenticated ownership, isolated services, transactional writes,
safe responses and inaccessible-resource 404. OpenTrip permits member-based
access (404 nonmembers, 403 read-only editors) and has a legacy/demo listing
fallback. TripTogether deliberately uses strict owner SQL filtering instead.
Members/roles, aggregate repositories, day/stop graphs, covers/maps, bookings,
expenses, invitations and agent/realtime state were not adopted.

Authentication answers "Who are you?" using JWT. Authorization answers "Does
this user own this Trip?" at the service query boundary. Body owner_id would
let a caller choose another identity, so it is server-controlled.

CRUD maps to POST, GET collection/resource, PATCH and DELETE. PATCH preserves
unsent fields, unlike a replacement-oriented PUT. 403 acknowledges forbidden
access; our uniform 404 conceals whether someone else's resource exists.
Migration history now evolves users/0001 -> users+trips/0002 without rewriting
what existing installations already applied.

### How to Test

Using the existing virtual environment and local DATABASE_URL/JWT configuration:

```bash
cd backend
python -m alembic upgrade head
python -m app.db.check
python -m alembic current
python -m alembic check
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m uvicorn app.main:app --reload
```

Open /docs, register and login Alice/Bob. With Alice's Bearer token POST /trips
using name, destination and YYYY-MM-DD start/end dates. Expect 201 and Alice's
owner_id. Alice list/detail returns it; Bob list omits it, Bob GET/PATCH/DELETE
returns 404. A single-date PATCH producing start > end returns 422 without
changing the row. Alice PATCH succeeds, then DELETE returns empty 204 and GET
returns 404. Anonymous calls to all five routes return 401.
Use psql `\d trips` and SELECT all eight Trip fields to inspect persistence.
README supplies a concrete create body and exact API paths.

Actual final verification (local September 19, 2026):

- Default suite: **167 passed, 48 skipped, 0 failed**.
- Real PostgreSQL suite: **215 passed, 0 skipped, 0 failed**.
- Includes all original health/auth/registration/hash/database/model/migration
  tests plus Trip schemas, SQL constraints, lifecycle, isolation and rollback.
- Isolated migration tests verify fresh head, 0002 -> 0001 -> head, preserved
  User data and restored trips; no development-schema downgrade.
- `alembic upgrade head` applied successfully to development PostgreSQL.
- `alembic current`: **0002 (head)**.
- `alembic check`: **No new upgrade operations detected.**
- `app.db.check`: **PostgreSQL connectivity check passed (SELECT 1).**
- `psql \d trips`: eight NOT NULL columns, INTEGER Identity PK, DATE pair,
  timestamptz defaults, owner B-tree index, three CHECKs, named users FK RESTRICT.
- Actual Uvicorn --reload server started on port 8016 with a process-only
  generated JWT key; no real .env modification or credential output.
- Real HTTP: both Alice/Bob register **201**, login **200**.
- Alice Trip create **201**, list/detail/PATCH **200**, delete **204** with
  empty body, subsequent get **404**.
- Bob list empty; Bob GET/PATCH/DELETE Alice's Trip all **404**.
- Anonymous all five routes **401**. Injected owner and invalid merged dates
  **422**; invalid PATCH left the stored trip unchanged.
- SQL SELECT confirmed all eight fields, owner_id corresponding to Alice's
  actual users.id, date values, unchanged created_at and advancing updated_at.
- `/health` still **200**, {"status":"ok"}.
- Manual data cleanup targeted only task-created users/trips. Baseline/final:
  **0 users, 0 trips**; no remaining test schemas; no identity sequence reset.
- Original 0001 SHA-256 remained
  `560f98ed9cc4baf6d26dbf990f73ac293694049c48676bb04f68300de5e21f61`.
- Temporary verification server stopped after the tests.

### Problems Encountered

Autogeneration on the external disk created AppleDouble metadata
`._0002_create_trips_table.py`. Alembic interpreted this binary file as Python,
causing integration fixture setup errors. Removed generated metadata using the
already-documented dot_clean command; kept actual migration files unchanged.
This filesystem issue can recur after copies/edits.

New invalid-token tests initially omitted the existing random-key fixture,
so the missing JWT configuration correctly returned 503 instead of the intended
401 token failure. Added jwt_environment to those tests, without changing
production auth behavior. Complete default/live reruns then passed.

The original User migration test hardcoded head 0001/users-only. Updated only
its expected latest revision/table set and retained full reversal assertions.
Network and local database/HTTP verification required sandbox approval.
No new dependency, SQLite substitution, secret exposure or unrelated refactor.

### What I Learned

- FK constraints and ORM relationships operate at different layers.
- Owner identity must come from authentication, not client-controlled input.
- A multi-user API needs scoped SQL for both collections and single resources.
- Partial update validation must check the final state, not just supplied fields.
- Row locks serialize related mutations; CHECK constraints protect final storage.
- DATE and timestamptz serve different business meanings.
- onupdate is not a trigger; timestamp behavior must be documented and tested.
- New migrations preserve history; reversal tests must isolate destructive DDL.

### Next Step

Step 7: Trip Membership + Invitation. Not started or implemented in this task.

## 2026-09-19 — Step 7: Membership, Invitations and Member-Aware Authorization

### What Was Implemented

- **Step 7 completed.** TripMember, TripInvitation, registered-user invitations,
  recipient inbox, accept/reject, participant list and member-readable Trips.
- Reviewed README, AGENT, RECORD, Step 6 review and actual code before changes.
  Reviewed current OpenTrip before selecting this step's domain design.
- Kept Trip.owner_id authoritative. New Trip creation atomically adds its Owner
  membership; migration 0003 backfills Owners for existing Trips.
- Owners and members can read/list Trips and members. Only Owners can PATCH,
  DELETE and invite; inaccessible operations retain the uniform 404 policy.
- Added strict invitation state transitions, private recipient lookup, partial
  pending uniqueness, transaction rollback and consistent lock ordering.
- Tested separate-connection concurrent invitations/responses against PostgreSQL.
- No new dependencies. No public links, email sending, unregistered invites,
  remove/leave/transfer, extra roles, itinerary, expenses or other future work.

### Files to Review

New files:

- `backend/app/models/trip_member.py`: association object and constraints.
- `backend/app/models/trip_invitation.py`: recipient invitation and pending index.
- `backend/app/schemas/membership.py`: email input and explicit safe responses.
- `backend/app/services/memberships.py`: access-checked member projection.
- `backend/app/services/invitations.py`: rules, locks, atomic decisions and errors.
- `backend/app/api/invitations.py`: four authenticated invitation routes.
- `backend/migrations/versions/0003_create_membership_and_invitations.py`:
  reviewed autogenerated schema plus manual Owner data backfill.
- `backend/tests/test_membership.py`: lifecycle, privacy, decisions, rollback.
- `backend/tests/test_membership_migrations.py`: metadata, backfill and constraints.
- `backend/tests/test_membership_concurrency.py`: real concurrent HTTP transactions.
- `docs/step7-review.md`: full reference review, eight-file guide, concepts and
  eighteen interview Q&As.

Modified files:

- `backend/app/models/__init__.py`: registers both new models.
- `backend/app/schemas/user.py`: extracts existing email normalization into
  shared NormalizedEmail; registration/login semantics are preserved.
- `backend/app/services/trips.py`: Owner membership creation and OR/EXISTS reads.
- `backend/app/api/trips.py`: accessible detail and new members route.
- `backend/app/main.py`: registers invitation routes.
- `backend/tests/test_user_migrations.py`, `test_trip_migrations.py`: new head/table
  expectations; previous downgrade/upgrade assertions remain.
- `README.md`: API workflow, permissions, migration and test commands.
- `RECORD.md`: this entry.

### Key Code to Understand

TripMember has integer Identity id, trip_id, user_id, role and joined_at.
The pair (trip_id,user_id) is UNIQUE; role is VARCHAR with owner/member CHECK;
joined_at follows the existing timezone-aware now() strategy. Trip FK cascades;
User FK restricts deletion. One User may participate in multiple Trips, and
each Trip may have many users. Role/joined_at make this an association object.

TripInvitation has id, trip_id, inviter_id, invitee_id, status, created_at and
responded_at. Status is VARCHAR with pending/accepted/rejected CHECK and default
pending. Additional checks forbid self-invites and require responded_at to be
NULL exactly while pending. Trip FK cascades; both User FKs use RESTRICT.
The unique partial index covers (trip_id,invitee_id) WHERE status='pending':
only one active request per recipient/Trip, without prohibiting rejected history.

Trip.owner_id remains the only ownership authority. Stored roles classify
participants but never grant Owner permissions. Normal application writes
create owner for the actual owner and member on acceptance; no role-edit or
owner-transfer endpoint exists. Member-list effective role is derived from
owner_id, not blindly copied from role. Direct SQL writers must maintain this
cross-table consistency; no synchronization trigger was introduced.
A regression test corrupts Bob's stored role and confirms no write escalation.

Creation: current_user -> Trip insert/flush -> Owner member insert -> one commit.
Read scope: Trip.owner_id=user_id OR EXISTS matching membership, in SQL.
EXISTS does not duplicate Trip rows when the Owner is also a member.
get_owned_trip stays separate from get_accessible_trip so member read access
does not accidentally broaden metadata-write privileges.

Invite: owner-only Trip lock -> shared normalized email -> registered User ->
reject self/existing member/pending -> insert pending -> commit.
Inviter comes from current_user, not input. Missing registered user returns 404
after ownership is checked; conflicts return 409. The existing-user lookup
does expose registration existence to authorized Owners; it is not claimed to
be enumeration-proof. No email or public token is generated.

GET /invitations filters by current recipient and returns all three statuses.
Accept/reject lookup includes both invitation ID and current invitee ID; others
receive the same 404 as unknown invitations. Pending grants no Trip access.

Response lock order is Trip first, Invitation second, consistent with Trip
mutations/deletion. After waiting, the invitation is reread with populate_existing
and must still be pending. Accept INSERTs/flushed Member, updates invitation
status/responded_at and commits once. Reject updates only status/responded_at.
Repeat accept/reject after either terminal state is 409, not idempotent success.
Rejection permits a new invitation row later.

If either write fails, SQLAlchemy rollback undoes the whole decision. Expected
unique violations for member/pending constraints translate to safe 409; other
DB failures become generic 503 without SQL or internal details.
A deliberate UPDATE failure after real Member INSERT verifies atomic rollback.

### Architecture Concept

OpenTrip HEAD remained `cfc78a04d0eeba3daaec4b755b110d89938ae4fc`.
Inspected Prisma, Trip domain/types, TripService, invitation domain/service,
HTTP routes, Trip/invite SQL repositories, DTO/validation and invitation tests.

OpenTrip creates an Owner member in the same transaction as the Trip. Its
trip_members carries display metadata, optional user_id, owner/editor/viewer,
can_invite, and UNIQUE(trip_id,user_id). Owner/member permissions come from the
member record; legacy/demo trips have a permissive fallback.
Its invitations are random-token links with stored token_hash, anyone or
restricted-email scope, editor/viewer, can_invite, active/revoked and expiry.
Acceptance history and allowed emails are separate tables. Repeated acceptance
is idempotent. Member insertion and acceptance logging are separate service
repository calls; a shared transaction covering both was not found there.
The inspected tests use fake repositories, not our PostgreSQL race mechanism.
No remove-member, leave or ownership-transfer workflow was found in the inspected
current modules, nor a per-recipient pending/reject inbox equivalent.

Borrowed association uniqueness, Owner participation, isolated invitation
domain and authenticated identities. Did not adopt link/token/expiry workflows,
extra permissions, legacy access, profile copies, realtime or idempotent accept.
Reference concepts informed design, but no source code was copied.

Many-to-many is represented by one association per User/Trip pair.
Composite uniqueness constrains the pair, not either column separately.
Invitation is a state machine driven by actions, not arbitrary client status.
Transactions preserve consistency across two table writes.
Application pre-checks alone cannot stop races: per-Trip locking serializes
mutations and database unique constraints remain the final invariant.

Schema migration creates tables; data migration makes pre-existing Trips
satisfy the new Owner-membership rule. 0003 INSERT SELECT copies trip.id,
owner_id and original created_at into owner rows, with ON CONFLICT DO NOTHING.
Alembic applies the revision once; repeated upgrade head is a no-op.
Downgrade removes only new tables/indexes, preserving Users/Trips but deleting
membership/invitation history. Re-upgrade restores Owners, not lost history.
0001/0002 were not changed.

Authorization evolves per operation: Owner OR Member reads; Owner-only writes
and invites. Membership is not an implicit blanket permission to edit.

### How to Test

With the existing local environment and database/JWT configuration, from backend:

```bash
python -m alembic upgrade head
python -m app.db.check
python -m alembic current
python -m alembic check
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m uvicorn app.main:app --reload
```

Register/login Alice/Bob/Charlie. Alice creates a Trip, then POSTs
/trips/{id}/invitations with only {"email":"bob@example.com"}.
Bob GET /invitations sees pending, then POST /invitations/{id}/accept.
Bob can list/read the Trip and GET /trips/{id}/members; PATCH/DELETE/invite
remain 404. Charlie cannot read Trip/members or answer Bob's invitation.
Alice/Bob lists show Alice owner and Bob member, with safe fields only.
Rejecting another invitation creates no membership and allows later reinvitation.
Owner deletion removes memberships and all invitation history.

Inspect psql `\d trip_members`, `\d trip_invitations`, and SELECT each table.
README includes exact commands and the missing-Owner-row audit query.

Actual final verification, local September 19, 2026:

- Default suite: **186 passed, 82 skipped, 0 failed**.
- PostgreSQL suite: **268 passed, 0 skipped, 0 failed**.
- All prior health/registration/login/JWT/auth-me/Trip/date/database/migration
  regressions included. No SQLite substitution.
- Normal tests reuse private-schema outer transactions and request savepoints.
- Race tests alone create committed random private schemas with independent
  connections, synchronize two requests before the Trip lock, then clean up.
- Concurrent duplicate invite: **one 201, one 409**, exactly one pending.
- Concurrent accept/accept and accept/reject: **one 200, one 409**, one terminal
  decision and exactly the corresponding membership count.
- Fault after Member INSERT but before invitation UPDATE: **503**, no added
  member and original pending invitation; a later retry succeeds.
- Fault creating Owner member rolls back new Trip creation as well.
- Isolated old-Trip backfill and 0002 -> 0003 -> 0002 -> head cycles pass,
  preserving Users/Trips and preventing duplicate Owner rows.
- Development DB: inserted one task-owned old Trip at 0002, upgraded using
  actual `alembic upgrade head`, verified exactly one Owner row and matching
  joined_at=Trip.created_at, then cleaned only that task data.
- Actual `psql \d` confirmed table columns, timestamps, FK CASCADE/RESTRICT,
  role/status checks, composite unique and pending partial unique index.
- SQL SELECT during HTTP showed Alice owner/Bob member and accepted, rejected,
  pending invitations with correct response-time NULL/non-NULL behavior.
- `alembic current`: **0003 (head)**; `alembic check`: no new upgrade operations.
- `app.db.check`: SELECT 1 passed; `pip check`: no broken requirements.
- Actual Uvicorn --reload started on port 8017 with a process-only generated key.
- Actual HTTP: all three registration/login pairs **201/200**; invitation **201**;
  Bob inbox/accept/Trip list/detail/member list **200**.
- Bob PATCH/DELETE/invite **404**; Charlie Trip/member reads and accept/reject
  of Bob's invitation **404**. Owner list includes its Trip only once.
- Repeated pending invite and terminal response **409**. Charlie reject **200**
  with no membership, followed by successful fresh invitation **201**.
- Anonymous all five new routes **401**. `/health` and `/auth/me` remain **200**.
- Owner DELETE **204** and DB confirmed both child-table sets were removed.
- Manual data cleanup used only exact task-created identities. Final:
  **0 users, 0 trips, 0 members, 0 invitations, 0 test schemas**.
- Real `.env` stayed unchanged/ignored; no passwords, JWTs or secrets printed.
  Identity sequences were not reset; temporary Uvicorn server was stopped.
- Original migration hashes unchanged:
  0001 `560f98ed9cc4baf6d26dbf990f73ac293694049c48676bb04f68300de5e21f61`;
  0002 `cafaa934b6b0a8c3ffc0553aebce4d82cb92309937acefe62f153d960e45db50`.

### Problems Encountered

The ordinary fixture's single uncommitted connection cannot demonstrate
concurrent independent transactions. Added a narrow race-test fixture with
its own committed private schema; no production-schema cleanup or general
testing-framework replacement was needed.

External-drive AppleDouble files remain a known migration hazard. Used the
existing documented dot_clean metadata cleanup before migration runs.
Existing migration tests assumed the old head; advanced only head/table
expectations while preserving their reversal assertions.
Network and local database/HTTP access required sandbox approval.
No implementation/test failures occurred in the completed default/live runs.

### What I Learned

- Association objects describe participation plus metadata, not ownership alone.
- Keep one ownership authority even when an Owner also has membership.
- SQL EXISTS expresses participation without duplicate parent rows.
- Partial uniqueness preserves terminal history while forbidding pending duplicates.
- Response actions and state guards are clearer than arbitrary status PATCH.
- One commit must cover membership creation and invitation acceptance.
- A consistent parent-first lock order coordinates with cascade deletion.
- Real race tests require independent visible transactions, not one shared Session.
- Schema changes need data backfills when old records acquire new invariants.
- Read permissions can evolve without broadening write permissions.

### Next Step

Step 8: Shared Itinerary. Not started or implemented in this task.

## 2026-09-19 — Step 8: Shared Itinerary

### What Was Implemented

- **Step 8 completed.** Shared itinerary CRUD, complete daily reordering,
  position compaction, date moves, merged time validation and Trip-date protection.
- Read project instructions/history and Step 6/7 implementation; reviewed current
  OpenTrip planning code before explaining and implementing the minimal design.
- Added ItineraryItem and reviewed autogenerated migration 0004; applied to real
  PostgreSQL. Historical migrations 0001-0003 remain unchanged.
- Owner and accepted Member can create/read/edit/delete/reorder any Trip item,
  regardless of creator. Trip metadata writes/deletion/invitations stay Owner-only.
- Added real PostgreSQL lifecycle, constraints, reversal, failure rollback and
  independent-connection concurrency tests, plus actual network HTTP verification.
- No new dependency, realtime/push, version column, maps, rich text, booking,
  expenses, client or other next-stage feature.

### Files to Review

New files:

- `backend/app/models/itinerary_item.py`: 12 fields, FK/CHECK/UNIQUE and timestamps.
- `backend/app/schemas/itinerary.py`: strict create/update/response/reorder inputs.
- `backend/app/services/itinerary.py`: participant access, ordering and transactions.
- `backend/app/api/itinerary.py`: six authenticated endpoints and safe errors.
- `backend/migrations/versions/0004_create_itinerary_items.py`: new table/index.
- `backend/tests/test_itinerary.py`: collaborative workflow and atomic rollback.
- `backend/tests/test_itinerary_migrations.py`: isolated reversal and actual constraints.
- `backend/tests/test_itinerary_concurrency.py`: parallel writes on separate connections.
- `docs/step8-review.md`: full report, eight-file learning guide and twenty Q&As.

Modified files:

- `backend/app/models/__init__.py`: metadata registration.
- `backend/app/main.py`: itinerary router, unchanged health behavior.
- `backend/app/services/trips.py`: optional accessible-parent lock and date-shrink guard.
- `backend/app/api/trips.py`: 409 response for existing itinerary/date conflict.
- `backend/tests/test_user_migrations.py`, `test_trip_migrations.py`:
  latest head/table expectations only, preserving old reversal assertions.
- `README.md`: current state, API contract, manual flow and commands.
- `RECORD.md`: this entry.

### Key Code to Understand

Trip 1 -> many ItineraryItems through required trip_id. Model fields:
INTEGER Identity id; trip_id FK CASCADE; title VARCHAR160 nonblank; nullable
location VARCHAR200; DATE; nullable start/end TIME without timezone; nullable
plain notes VARCHAR2000; positive INTEGER position; creator User FK RESTRICT;
created_at/updated_at TIMESTAMPTZ with now() defaults. The creator index supports
FK lookup; unique (trip_id,date,position) already supports Trip/day listing.
updated_at uses the existing ORM statement_timestamp onupdate, not a trigger.

Schema input is separate from storage/response. Client cannot set id, trip_id,
position, creator or timestamps. Title is trimmed and bounded; date is strict
YYYY-MM-DD; times are local HH:MM or HH:MM:SS with optional microseconds, no offset.
Start-only is allowed; end requires start and end >= start. Overnight items fail.
PATCH distinguishes omission from null and validates the final old+new time pair.
Nullable fields may clear; title/date may not. Empty/identical PATCH is a no-op.

get_accessible_trip uses owner OR EXISTS member for all six item endpoints.
find_item also scopes by trip_id, not only item_id or creator. Creator is audit
attribution, so Bob can edit/delete Alice's item and Alice can edit Bob's.
get_owned_trip remains the authority for Trip metadata PATCH/DELETE and invites.
Other/pending users get 404; anonymous 401; malformed/business inputs safe 422.

Every itinerary mutation locks the accessible Trip first, before reading items,
max position, or current day membership. Trip date edits/deletion already lock
the same parent. Under default READ COMMITTED, waiting writers re-read current
state before validating/mutating. This coordinates dates, ordering and deletion.
Service checks inclusive Trip date boundaries. Trip update rejects an existing
out-of-range item with 409 rather than silently moving/deleting it.

Creation appends max+1. Delete flushes removal then compacts the day to 1..N.
Moving dates appends at destination max+1, flushes the move and compacts the source.
Reorder requires exactly every current day ID, once; missing/unknown/foreign/
wrong-day/duplicate IDs fail. SQL list order is date ASC, position ASC.
An empty list only works for an empty day inside the Trip's date range.

assign_positions avoids immediate UNIQUE swap conflicts by moving the complete
day list above its previous max, flushing, then assigning final 1..N and flushing.
Both rounds remain inside one transaction and one commit. Temporary values are
positive to satisfy CHECK. A second-round failure rolls everything back,
including earlier deletion/move and timestamps. Safe 503 never exposes SQL.
Full-list and compaction operations are O(N) for that day, sufficient for this MVP.

### Architecture Concept

OpenTrip HEAD rechecked:
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`. Inspected Prisma, Trip domain/types,
DTO, operation schemas, HTTP, service, persistence, realtime object and tests.
It models plans using trip_days and stops, not an ItineraryItem class.
Stops have name/area, string time/duration, day, coordinates, note, creator,
category/cost and global sort_order. Insert/move splices the aggregate array
and rewrites zero-based order; persistence queries sort_order and transactionally
replaces aggregate stops. DTO preserves list order without returning order.
Trip/day dates are strings, not our DATE/TIME pair. Destination intake contains
text and optional coordinates; no external place ID found in the Stop model.

Reference loadReadable/loadEditable enforce members, owner/editor editing and
viewer restrictions, with a legacy/demo fallback we do not adopt. No standalone
Stop delete route was found in inspected code; deleting a day removes its stops.
It has actual Durable Object/WebSocket changes, sequences and replay. Version
supports change revisions/invalidation; its presence is not proof of conflict
resolution. Tests check ordering/moves and notification-after-save semantics.
Reference tests were read, not executed; no source was copied.

Borrowed explicit ordering, participant access, service validation and transactions.
Simplified to one Item table, plain optional location/notes, daily position and
individual ORM updates. Did not adopt day entities, whole-aggregate rewrites,
maps/media/comments/votes/AI/prices/booking/realtime/version.

Shared state means Alice/Bob access one PostgreSQL row; Alice sees Bob's committed
change on the next GET. Real-time push is a separate unimplemented capability.
One-to-many is encoded by a required FK, not by unused ORM collection properties.
CHECK/FK/UNIQUE protect storage invariants; cross-table Trip date boundaries and
continuous positions are service rules. Raw SQL writers must preserve them and
updated_at themselves.

Concurrency remains explicitly **Last Write Wins**. Parent locks prevent illegal
interleavings but do not know a client's stale read. A later same-field update
can overwrite the earlier user's intent; no optimistic locking or merge is claimed.
Per-Trip serialization is a deliberate small-MVP throughput tradeoff.

### How to Test

With the existing virtual environment and local DATABASE_URL/JWT configuration:

```bash
cd backend
python -m alembic upgrade head
python -m app.db.check
python -m alembic current
python -m alembic check
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m uvicorn app.main:app --reload
```

In /docs, register/login Alice/Bob/Charlie; Alice creates a Trip June 10-15,
invites Bob and Bob accepts. Alice POSTs /trips/{id}/itinerary with
{"title":"Senso-ji","date":"2027-06-10","start_time":"09:30"}.
Bob GETs/PATCHes the item; Alice GETs updated content. Bob creates another,
Alice PATCHes /reorder with date and all real item_ids; Bob sees that order.
Charlie gets 404 on six routes; anonymous 401. Bob Trip metadata writes/invite
stay 404. Try an end-only or overnight time (422), foreign reorder ID (422),
or shrinking Trip dates around existing items (409). Bob may delete Alice's
item (204); Owner deletes Trip (204) with child cascade.

Run psql `\d itinerary_items`, then:

```sql
SELECT id, trip_id, title, location, date, start_time, end_time, notes,
       position, created_by_user_id, created_at, updated_at
FROM itinerary_items ORDER BY date, position;
```

Actual verification, local September 19, 2026:

- Default suite: **231 passed, 121 skipped, 0 failed**.
- PostgreSQL suite: **352 passed, 0 skipped, 0 failed**.
- 84 added cases, all prior health/auth/Trip/membership/invitation regressions pass.
- Real constraints, defaults, protected fields, boundaries, merged PATCH times,
  creator-independent collaboration, invalid ordering, move/delete compaction.
- Second UPDATE fault injection during reorder/delete/move yields safe 503 and
  unchanged full original rows, proving rollback across flush boundaries.
- Concurrent create: both 201, positions exactly 1/2. Concurrent PATCH and
  reorder: both 200, valid final state. Concurrent shrink/create yields only
  [200,422] or [409,201], never out-of-range data.
- Ordinary tests use existing outer transaction/savepoint fixtures; concurrency
  reuses Step 7 committed private schemas and separate connections. No SQLite.
- Isolated 0004 -> 0003 -> head verifies User/Trip preservation and restored
  structure; development schema never downgraded.
- Real `alembic upgrade head` succeeded; current **0004 (head)**; check reports
  **No new upgrade operations detected.** SELECT 1 passed; pip check healthy.
- Actual psql structure confirms 12 columns, Identity, DATE/TIME/TIMESTAMPTZ,
  3 CHECKs, 2 FKs with CASCADE/RESTRICT, daily unique and creator index.
- Real Uvicorn --reload started at port 8018 with process-only random JWT key.
- Actual HTTP: registration/login **201/200** for all three; auth/me **200**;
  Alice creates Trip/invitation **201**; Bob accepts **200**.
- Alice Item POST **201**, Bob GET/PATCH **200**, Alice GET **200**, identical
  updated content. Bob Item POST **201**; Alice reorder/Bob ordered GET **200**.
- Charlie all six Item routes **404**; anonymous all six **401**.
- Bob Trip PATCH/DELETE/invite **404**. Item date move **200**, Trip shrink **409**.
- SQL SELECT showed Lunch June10/position1 and edited Senso-ji June14/09:30-10:00/
  position1, correct immutable creators, notes and updated timestamps.
- Bob deletes Alice's item **204**; Owner Trip DELETE **204**; members/invitations/
  items confirmed removed. `/health` remains **200**, {"status":"ok"}.
- Precise task-data cleanup restored baseline: all five business tables **0**,
  residual test schemas **0**. No sequence reset, .env edit or secret output.
- Temporary verification Uvicorn server stopped; no browser UI claim.

### Problems Encountered

The first model used date both as column name and annotation type; Python 3.9
class-scope evaluation shadowed the type with mapped_column, causing TypeError
before autogeneration. Aliased the imported type to CalendarDay and retried
successfully. No database operation happened on the failed attempt.

Used existing dot_clean cleanup for external-disk AppleDouble metadata before
tests. No Alembic patch or historical migration edit. Existing migration tests
hardcoded 0003; updated latest-head expectations only.
Web fetch returned no usable reference content; verified current git HEAD and
read local source. Local network/DB checks needed sandbox approval.
pip's unwritable cache warning disabled caching only; dependency check passed.

### What I Learned

- Shared state does not imply live notification or collaborative merge.
- Creator attribution and permission ownership are distinct concepts.
- Parent row locks coordinate related operations across child tables.
- Partial time updates must validate old and new values together.
- Cross-table date rules need both forward and reverse validation.
- Explicit daily positions support untimed plans and user-controlled ordering.
- Temporary positive positions avoid uniqueness collisions during swaps.
- Multiple flushes can remain one atomic transaction; fault injection proves it.
- UNIQUE prevents duplicates, not position gaps or lost user intent.
- LWW must be documented honestly even when structural concurrency is safe.
- Tests must use independent transactions to demonstrate actual concurrency.

### Next Step

Step 9: Expense System. Recommended only; not started or implemented.

## 2026-09-19 — Step 9: Expense System

### What Was Implemented

- **Step 9 completed.** Expense and ExpenseSplit, five shared CRUD endpoints,
  exact equal splitting, deterministic remainder distribution and migration 0005.
- Reviewed project instructions/history, Step 7/8 and current code before edits;
  reviewed actual OpenTrip expenses before explaining the chosen design.
- Decimal throughout Python/ORM, PostgreSQL NUMERIC(12,2), JSON decimal strings
  only. No float arithmetic, silent fractional rounding or client-supplied splits.
- Payer/participants must belong to Trip; creator is authenticated recorder,
  independent of payer. Payer need not be among split participants.
- Owner/accepted Member may edit/delete each other's expenses; Trip management
  stays Owner-only. Dates outside Trip range are allowed for prepaid bookings.
- Current Trip ledger is single-currency without adding a Trip currency column.
- Parent locking, atomic split replacement, safe errors and single-snapshot reads.
- No added dependencies. No Step 10 balance/settlement, FX, custom splits,
  payments, realtime notifications, receipt features or client.

### Files to Review

New:

- `backend/app/models/expense.py`: ten fields and ordered split relationship.
- `backend/app/models/expense_split.py`: four fields, nonnegative/unique/FK rules.
- `backend/app/schemas/expense.py`: money strings, exact types and input/output.
- `backend/app/services/expenses.py`: equal_split, identity/currency validation,
  create/update transactions and complete response snapshots.
- `backend/app/api/expenses.py`: five thin routes and safe HTTP mapping.
- `backend/migrations/versions/0005_create_expenses_and_splits.py`: reviewed
  autogenerated forward/reverse schema.
- `backend/tests/test_expenses.py`: exact math, schemas, shared integration,
  rejection, creator/payer separation and injected failure recovery.
- `backend/tests/test_expense_migrations.py`: real SQL invariants and reversal.
- `backend/tests/test_expense_concurrency.py`: independent transaction races.
- `docs/step9-review.md`: complete report, eight-file guide, twenty-two Q&As.

Modified:

- `backend/app/models/__init__.py`, `backend/app/main.py`: model/router registration.
- `backend/tests/test_user_migrations.py`, `test_trip_migrations.py`,
  `test_itinerary_migrations.py`: new head/table expectations only.
- `README.md`: current status, API, money/currency policies and commands.
- `RECORD.md`: this entry.

Trip, old migrations, auth, invitations and itinerary business code unchanged.

### Key Code to Understand

Expense stores required integer Identity id, Trip FK CASCADE, description(200),
NUMERIC(12,2) amount, currency(3), payer User FK RESTRICT, expense_date DATE,
creator User FK RESTRICT, created/updated timestamptz defaults. CHECKs bound
positive finite amount <=9999999999.99, nonblank description and currency format.
ExpenseSplit has Identity id, Expense FK CASCADE, User FK RESTRICT and exact
nonnegative share_amount. UNIQUE(expense_id,user_id) also supplies the leading
expense lookup index. Separate Trip and user-reference indexes serve actual
list/reference queries; not every column is indexed.

JSON amount must be a plain decimal string with at most two places, no signs,
exponents, NaN/Infinity, whitespace or JSON numeric/bool. Pydantic holds Decimal;
SQLAlchemy Numeric returns Decimal; response model holds Decimal and emits
fixed two-place strings. Protected fields/custom splits and explicit PATCH null
are rejected. Description trims and rejects blank/invalid Unicode/NUL.

equal_split is a pure function: sort participant IDs, convert exact amount to
integer hundredths, divmod by count, give one extra unit to the first remainder
IDs, convert each result to Decimal. 120/2 -> 60/60; 100/3 -> 33.34/33.33/33.33;
0.01/3 -> 0.01/0/0. Same set always yields same result; sums match exactly.
This uses integers transiently for division but NUMERIC/Decimal for storage.

All expense writes reuse get_accessible_trip(for_update=True). The same parent
lock serializes currency checks and split replacement with existing Trip writes.
validate_people compares requested payer/participants with current TripMember IDs
plus authoritative owner_id. Unknown and non-member IDs uniformly return 422.
Caller not authorized sees 404 before expense lookup; anonymous sees 401.
Creator comes from current_user, not request; creator never owns edit permission.

No Trip currency field existed. Under parent lock, all other existing expenses
must match the requested currency, otherwise 409. First expense establishes
current-ledger currency; a sole expense can be relabeled without conversion;
after all are deleted a different currency can be chosen. This avoids a hidden
Trip refactor and explicitly is not a permanent Trip.currency setting.
Codes validate three uppercase ASCII letters, not a registry. All amounts use
two-place accounting precision, not official per-currency minor-unit semantics.

expense_date accepts a strict calendar date, not a timestamp, but may lie outside
Trip dates because flights/hotels can be paid earlier or later. No new expense
date restriction is coupled to the existing itinerary date-shrink guard.

Create persists parent and splits in one transaction. PATCH merges final state,
validates payer/participants/currency, and recalculates if amount or participant
set changed. Old split pairs are deleted/flushed before replacement insertion
to avoid UNIQUE collision. One commit covers all changes; any error rolls back.
Split-only edits advance parent updated_at; empty/identical updates are no-ops.
SQLAlchemy onupdate=statement_timestamp is not a DB trigger.

GET joins parent/splits in one SQL snapshot to avoid mixing an old amount with
new splits between separate READ COMMITTED queries. Writes construct a detached
Pydantic response snapshot while holding the lock, then commit before returning.
This avoids post-commit lazy loads racing another editor.
List order is expense_date DESC, created_at DESC, id DESC; splits user_id ASC.

### Architecture Concept

OpenTrip remote HEAD verified unchanged:
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`. Inspected Prisma expenses/participants,
Trip domain/types, service/DTO/routes/repository, settlement.ts and expense tests.
Reference has string expense/member IDs, integer amount, payer_id, currency,
category/when_label/order. Participants are separate ID associations without
stored share_amount. Domain validates members and rounds TypeScript number.
Its computeBudget divides amount by participant count and later rounds aggregate
shares/net balances; it does not persist our deterministic per-expense remainder.
Trip has currency and individual expenses may override it. Inspected budget
aggregation has no currency partition/conversion; we do not claim it safely
settles mixed currencies. Owner/editor can add/update, viewer is denied.
No independent Expense DELETE was found in inspected routes/service.
Reference tests were read, not run; no code copied or settlement logic added.

Borrowed separate payer/participation, service authorization and transaction
boundaries. Chose our own Decimal + persisted exact splits instead of reference
number arithmetic, aggregate replacement, budget/settlement or realtime.

Expense describes actual payment; Split describes responsibility. User may pay
for others without consuming, and another member may record that payment.
Binary float approximates common decimal fractions; Decimal from strings and
NUMERIC avoid that approximation within the chosen bounds. Decimal's default
context suffices for 12-digit inputs; application does not alter that context.

PK/FK/CHECK/UNIQUE are database invariants. Membership, one-ledger currency,
nonempty splits and cross-row sum equality are service invariants maintained
by pure math, locks and atomic transactions. Raw SQL can bypass service rules
and must maintain totals and timestamps itself. NUMERIC storage may round raw
overprecision SQL; the API rejects it before writing.

Shared State is one PostgreSQL record read by all participants, not push.
Concurrent same-field editing remains Last Write Wins. Locking preserves each
committed Expense/split set, not stale-client intent. No version/merge mechanism.

### How to Test

With existing local DB/JWT settings and the existing virtual environment:

```bash
cd backend
python -m alembic upgrade head
python -m app.db.check
python -m alembic current
python -m alembic check
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m uvicorn app.main:app --reload
```

In /docs register/login Alice/Bob/Charlie, Alice creates Trip and invites Bob,
Bob accepts. Alice POSTs /trips/{trip_id}/expenses with description Dinner,
amount "120.00", currency USD, paid_by_user_id Alice, expense_date "2027-05-01",
participant_user_ids [Alice,Bob] using actual IDs. Expect 201 and "60.00" each.
Bob GETs and PATCHes amount "150.00"; Alice GET sees "75.00" each. Charlie's
all five requests return 404; anonymous 401. Bob may delete Alice's expense.
psql: `\d expenses`, `\d expense_splits`, then SELECT amounts/payers/creators and
SELECT expense_id,user_id,share_amount ordered by expense_id,user_id.
README/review contain runnable examples and a cross-row total audit query.

Actual final results, local September 19, 2026:

- Default: **293 passed, 162 skipped, 0 failed**.
- Real PostgreSQL: **455 passed, 0 skipped, 0 failed**.
- 103 new cases; all existing health/auth/Trip/membership/invitation/itinerary
  ordering/date-protection regressions pass. No SQLite.
- Pure algorithm tests include three examples, maximum amount, 100 amounts x
  ten participant counts, sum conservation and maximum one-unit share difference.
- Tests verify Decimal in schema/ORM/response and string JSON representation.
- DB tests verify null, FK, CHECK, NaN exclusion, split uniqueness and cascade.
- Isolated 0005 -> 0004 -> head preserves existing Trip and restores new tables.
- Injected Split INSERT failure after Expense INSERT/UPDATE causes safe 503;
  original whole record/splits preserved and retry succeeds.
- Independent concurrent PATCHes both return 200 with consistent response totals;
  final DB total also equals amount. Different first currencies: one 201/one 409.
- Real development upgrade succeeded; current **0005 (head)**.
- Alembic check: **No new upgrade operations detected.** SELECT 1 succeeds.
- Actual psql confirms expenses ten columns and splits four columns, NUMERIC,
  DATE/TIMESTAMPTZ, identity, constraints, indexes and FK actions.
- Uvicorn --reload started on 8019, with process-only random signing key.
- Actual HTTP all three registration/login **201/200**, /auth/me and /health **200**;
  Alice Trip/invitation **201**, Bob accept **200**.
- Alice Expense **201**, 60.00 each; Bob GET/PATCH **200**, amount150/splits75 each;
  Alice GET **200**, same updated values.
- Charlie all five Expense routes **404**, anonymous all five **401**.
- Nonmember payer/participant **422**, mixed currency **409**, numeric JSON amount **422**.
- Bob records Alice's payment for Bob alone **201**: creator Bob, payer Alice,
  one split Bob50. SQL SELECT confirms both records and zero inconsistent totals.
- Bob Expense DELETE **204**, Owner Trip DELETE **204**, both cascade checks pass.
- Exact task-data cleanup restores baseline: seven business tables all **0**;
  no .env edits/credential output, no sequence reset. Temporary server stopped.

### Problems Encountered

Existing Trip has no currency, so a hidden model change was avoided by explicitly
defining the current-ledger single-currency policy. Uniform two-place precision
and lack of official currency-specific rules remain documented limitations.
Cross-row sums cannot be protected by ordinary CHECK alone; independent math
tests, transaction rollback and concurrency tests cover the service invariant.

The first formatting patch attempted delete/add of the same migration path and
was rejected before modifying anything. Retried with an ordinary update patch;
reviewed migration content and reran the entire suite.
Used the existing dot_clean cleanup for external-drive AppleDouble metadata.
Updated only current-head assertions in older migration tests. No old migration
was edited and no implementation/test failures occurred in completed runs.
Reference web fetch had no body; git source inspection provided actual evidence.
Local PostgreSQL/HTTP/reference network operations required sandbox approval.

### What I Learned

- Payment, recording identity and responsibility are distinct relationships.
- Exact monetary representation must start at the JSON boundary.
- Decimal/NUMERIC still need range, finiteness and precision validation.
- Integer quotient/remainder makes deterministic equal splits conserve money.
- Zero split amounts are valid even though the payment must be positive.
- Replacing child rows requires handling unique keys within one transaction.
- Locking a parent can coordinate ledger-wide currency and child changes.
- One SQL snapshot avoids mixed-version parent/child reads.
- Database constraints and service-level cross-row invariants complement each other.
- LWW protects storage consistency without resolving conflicting client intent.

### Next Step

Step 10: Balance Calculation. Recommended only; not started or implemented.

## 2026-09-19 — Step 10: Balance Calculation and Settlement Suggestions

### What Was Implemented

- **Step 10 completed.** Read required project documents, Step9 review, actual
  Expense/split/membership/auth code and tests before edits.
- Reviewed actual OpenTrip balance/settlement implementation and tests; verified
  current remote HEAD `cfc78a04d0eeba3daaec4b755b110d89938ae4fc`. No code copied.
- Added GET /trips/{trip_id}/balances: all current participants, currency,
  paid/share/net and deterministic settlement suggestions.
- Dynamic source-of-truth aggregation of Expense + stored ExpenseSplit; no
  repeated equal split, balance table, payment table, cache or new dependency.
- Exact Decimal calculation and two-decimal JSON strings. Positive receives,
  negative owes, zero is net-settled. No expense returns null currency and zeros.
- Single authorized SQL statement for membership, grouped amounts and ledger
  checks; pure settlement function separately testable.
- Strict global conservation, per-expense totals, single currency and financial
  identity checks. Inconsistent ledger fails closed without suggestions.
- Real PostgreSQL, pure algorithm, SQL-count, fault and independent-transaction
  concurrency tests, plus actual network HTTP multiplayer acceptance.
- No migration required; schema remains 0005. No actual payments, mark-paid,
  custom splits, FX, notifications, member removal, client or Step11 changes.

### Files to Review

New:

- `backend/app/services/balances.py`: grouped snapshot, net formula, invariant
  checks, pure suggestion matching and safe exceptions.
- `backend/app/schemas/balance.py`: public member/suggestion/response types.
- `backend/app/api/balances.py`: authenticated GET, no-store and HTTP errors.
- `backend/tests/test_balance_algorithm.py`: examples, invariant-style checks,
  deterministic results, invalid inputs, large totals and local precision.
- `backend/tests/test_balances.py`: real stored-split aggregation, authorization,
  modification/deletion, inconsistency and constant SQL-query count.
- `backend/tests/test_balance_concurrency.py`: old/new complete read snapshots
  during independent concurrent expense writes.
- `docs/step10-review.md`: complete report, seven-file learning guide, reproducible
  manual verification, reference comparison and 22 interview questions/answers.

Modified:

- `backend/app/main.py`: router import/registration only.
- `README.md`: Step10 state, API, formula, limitations and actual checks.
- `RECORD.md`: this entry.

No models, expense/auth/membership business modules, requirements or migration
files were modified. Existing services/expenses.py remains the upstream source
of exact stored splits and is the seventh recommended learning file.

### Key Code to Understand

`balance_query` builds one SQL statement with named CTEs. `balance_trip` reuses
the existing `accessible_to` Owner OR EXISTS Member rule. Participants are
Owner UNION TripMember so the owner appears exactly once, even if its redundant
membership row is absent. All expense/split queries are scoped through that
authorized Trip, not filtered afterward in Python.

SUM(amount) GROUP BY payer and SUM(share_amount) GROUP BY split user are computed
independently before joining. Joining payments to raw splits before SUM would
multiply a payment by its participant count. Missing aggregates become Decimal
zero. Financial user IDs are included for auditing, not silently discarded if
membership was changed through raw SQL.

The same statement checks distinct currencies and each expense's stored split
total. Missing splits fail too. Two offsetting per-expense errors cannot hide
behind a correct global total. The service computes net=paid-share and the pure
function requires SUM(net)==0 exactly. Inconsistent data returns generic409;
SQLAlchemy failures rollback and return generic503 without SQL/credentials.

`suggest_settlements` accepts an ID-to-Decimal mapping and does not mutate it.
It rejects non-Decimal, nonfinite and overprecision amounts, checks conservation,
sorts positive creditors/absolute negative debtors by amount DESC then ID ASC,
and advances two pointers while transferring min(remaining debt, remaining credit).
Sorting happens initially only, not again after every transfer. Each positive
transfer clears at least one side; conservation ensures both sides end at zero.
It is deterministic matching, not a proven globally minimum-transaction solution.

Sorting O(n log n), matching O(n), space/output O(n), for n participants.
SQL aggregation cost is separate and depends on relevant expenses/splits.
An authenticated successful request performs two queries regardless of member
count: current user lookup plus the entire authorized balance statement.
No GET row lock, commit, business-table write or lazy per-member query.

Money stays NUMERIC/Decimal and reuses MoneyResponse fixed two-place string
serialization. Stored 100/3 shares 33.34/33.33/33.33 are summed directly.
Aggregate amounts can exceed one Expense's limit. Service local precision50
covers current database bounds; pure matching sizes its local precision from
values/count. The global Decimal context is unchanged.

### Architecture Concept

Expense + ExpenseSplit are Source Data; balances and suggestions are Derived
Data. Recomputing avoids synchronizing redundant tables after PATCH/DELETE.
The modular monolith remains Router -> Service -> PostgreSQL, with pure math
inside the service module and explicit response schemas at the HTTP boundary.

OpenTrip reference settlement.ts computes paid/share/net dynamically from a
Trip snapshot, using TypeScript number, per-expense division and Math.round.
Its Trip.budget() feeds the DTO; Prisma stores Int expense amounts and
participant IDs, not exact share amounts. It initially sorts/matches debtors
and creditors, but no explicit ID tie-break or proof of transaction optimality
was found. Tests cover double-entry examples and seed totals with tolerance<=1.
No settlement/payment persistence was found in the inspected schema/workflow.
Currency exists in the data but computeBudget does not partition or convert it;
it is not evidence of correct mixed-currency settlement. Reference tests were
read, not executed. We adopted domain concepts, not its arithmetic or source.

Under READ COMMITTED, separate SELECTs could observe different committed
versions. One statement gives authorization, membership, amounts and splits
the same snapshot without blocking writers through a Trip read lock.
The next GET reflects commits completed before its query; an in-flight response
can legitimately represent the earlier snapshot. There is no promise of live
push or response-time linear freshness. Expense same-field writes remain LWW.

Limitations: one current-ledger currency, uniform two-decimal accounting,
no official currency minor-unit registry, FX, actual repayments or global
transaction-minimality guarantee. Leave/remove-member is not supported; future
historical participant identity must be designed before adding those workflows.

### How to Test

With the existing environment and local DB/JWT configuration, from backend:

```bash
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m app.db.check
python -m alembic current
python -m alembic check
python -m uvicorn app.main:app --reload
```

In /docs register/login Alice/Bob/Carol. Alice creates Trip, invites both, each
accepts. Record Hotel300 paid by Alice, Dinner90 by Bob, Tickets60 by Alice,
all split three ways. GET balances: paid360/90/0, share150 each, net210/-60/-150.
Suggestions: Carol->Alice150, Bob->Alice60. PATCH Dinner150 gives190/-20/-170;
delete Tickets gives150/0/-150. Anonymous401, outsider/pending404, after Trip
deletion404. Independent SQL SUM/GROUP BY queries are in the full review.

Actual final results, local September19,2026:

- Default: **315 passed, 178 skipped, 0 failed**.
- PostgreSQL: **493 passed, 0 skipped, 0 failed**.
- 38 new cases: 22 default and16 live, including all required examples, payer
  outside splits, single/zero participants' balances, stored remainder,
  two offsetting corruptions, mixed currency and historical identity handling.
- Query-count test verifies exactly two data queries at both2 and10 members,
  with no INSERT/UPDATE/DELETE/COMMIT/FOR UPDATE.
- Two independent-transaction tests pause a writer after split deletion and a
  reader after its SQL executes; only complete old snapshots return, followed
  by complete new balances on the next GET.
- All prior health/auth/JWT/Trip/invitation/itinerary/ordering/expense regressions
  pass. Ordinary integration uses private schema/savepoints; races use committed
  private schemas and independent connections. No SQLite.
- SELECT1 passed; Alembic current **0005(head)**; check **No new upgrade operations
  detected**; pip check healthy. All five migration hashes unchanged.
- Actual Uvicorn started at127.0.0.1:8020 with a random process-only JWT key.
- Real HTTP: four registration/login pairs201/200; Trip/invitations201;
  Bob/Carol pending reads404, accept200; three expenses201.
- All three participants' balances200 with identical expected content.
  Independent SQL aggregates match paid/share before and after modifications.
- Dinner PATCH200, Tickets DELETE204, balances update as specified.
  Outsider404, anonymous401; Trip DELETE204 then balances404; health200.
- Public schema still has seven business tables plus alembic_version.
  Precise cleanup restored baseline/final seven business-table counts all0;
  no sequence reset, .env changes or secret output. Temporary server stopped.
- Temporary HTTP verification script is outside the repo under /private/tmp.
  No claim of interactive Swagger UI verification.

### Problems Encountered

Separate aggregates would risk mixed-version reads and a false conservation
failure; solved by single-statement CTEs, without global isolation changes.
Global totals alone would miss offsetting corrupt expenses; per-expense audit
was added and tested. These were design issues, not observed production incidents.

Reference web fetch returned no useful body, so actual git checkout/remote HEAD
provided evidence. A test tidy-up patch had mismatched context and changed
nothing; corrected patch applied. The first temporary-script write approval
timed out; verified absence and retried once successfully.
pip cache was unwritable, but its dependency check passed. No failed tests in
completed runs. Local DB/HTTP/reference access used sandbox approvals.

### What I Learned

- Net balance is responsibility versus actual payment, not bank-account money.
- Stored exact splits, not a second equal division, determine current shares.
- SQL GROUP BY avoids N+1; pre-aggregation avoids multiplying parent amounts.
- Global conservation and per-expense validity are different checks.
- Derived data eliminates redundant synchronization without eliminating
  the need for a coherent concurrent read snapshot.
- Positive transfer plus strict zero conservation gives exact settlement.
- Stable tie-breaks make outputs reproducible, not globally optimal.
- Tests should verify general invariants as well as specific examples.
- Suggested settlement is neither payment processing nor repayment history.
- Full concepts and 22 concise interview Q&As are in docs/step10-review.md.

### Next Step

Step 11 — Backend MVP Hardening & API Integration Readiness.
Recommended only; not started. Do not automatically enter HarmonyOS.

## 2026-09-20 — Step 11: Backend MVP Hardening & API Integration Readiness

### What Was Implemented

Completed Step 11 only. Audited the existing Step 1-10 backend and all actual
routes before changing code. Pre-change inventory:26 operations (25 business
plus health); final official API:27 (25 business under /api/v1 plus health/ready).
The25 original business paths remain hidden compatibility aliases, sharing
the same routers/services and preserving legacy detail errors.

Added stable machine-readable APIError codes and a uniform v1/ready error
envelope. Validation retains loc/msg/type while removing raw input/context.
Existing success models,201/200/204 semantics, hidden404 authorization and
financial/transaction rules remain unchanged.

Added centralized APP_ENV/CORS_ORIGINS, explicit origin validation, safe
production configuration checks, minimal Python logging, unexpected500 and
session503 handling, and no-SQL liveness versus SELECT1 readiness.
OpenAPI now publishes only formal routes with tags, readable summaries,
explicit models, stable error schema and23 protected operations.

Reviewed authentication, authorization matrix, transactions, session lifecycle,
queries/N+1, direct requirements, sensitive fields/logs, .env/.gitignore,
unbounded lists and deployment readiness. Fixed an observed reorder-response
N+1 via a bulk final snapshot without changing itinerary ordering behavior.
No models/migrations or expense/balance/settlement algorithms changed.

Inspected OpenTrip engineering reference at actual remote/checkout commit
cfc78a04d0eeba3daaec4b755b110d89938ae4fc. Reviewed Hono route organization,
/api prefix, DTO projection, errors, Better Auth, trusted-origin CORS,
typed config, redacted observability, handwritten API docs and node/worker
deployment structure. Adopted design ideas only; no copied source or reference
test execution. Kept FastAPI/JWT and deferred unrelated infrastructure.

Added contract, configuration, CORS, readiness, logging and query regression
tests. Reworked README into an entry point, archived its historical walkthroughs,
and supplied API inventory, authorization matrix, client integration guide,
known limitations and a full Step11 review with24 interview Q&As.
No new/removed dependency (requirements comment only), Docker or client work.

### Files to Review

- `backend/app/main.py`: app factory/lifespan, shared legacy/v1 registration,
  OpenAPI metadata, CORS and safe error boundary.
- `backend/app/core/config.py`: environment precedence, production JWT checks,
  APP_ENV and exact origin parsing.
- `backend/app/core/logging.py`: new minimal safe logging/middleware.
- `backend/app/api/errors.py`: schemas, APIError, validation/HTTP rendering.
- `backend/app/api/system.py`: new health/readiness routes.
- `backend/app/api/dependencies.py`: stable codes on shared authentication.
- `backend/app/api/auth.py`, `trips.py`, `invitations.py`, `itinerary.py`,
  `expenses.py`, `balances.py`: explicit business error codes.
- `backend/app/db/session.py`: safe factory initialization, pool wait timeout
  and hidden SQL parameters; request-local Session remains.
- `backend/app/services/registration.py`: duplicate field -> stable code.
- `backend/app/services/itinerary.py`: bulk reorder response refresh/snapshot.
- `backend/tests/test_api_contract.py`, `test_app_hardening.py`,
  `test_query_audit.py`: new tests.
- `backend/tests/test_authentication.py`, `test_registration.py`,
  `test_trips.py`, `test_balances.py`: existing OpenAPI path assertions updated.
- `.env.example`, `.gitignore`, `backend/requirements.txt`: configuration
  descriptions/placeholders, coverage ignores, dependency comment.
- `README.md`, `docs/api-inventory.md`, `docs/authorization-matrix.md`,
  `docs/client-integration.md`, `docs/known-limitations.md`,
  `docs/step11-review.md`, `docs/legacy-development-guide.md`, `RECORD.md`.

No real .env, AGENT rules, model/schema definitions or migration files changed.
The full review selects ten code files with exact function/line reading points.

### Key Code to Understand

main.create_app includes the existing routers twice, not their logic twice.
Legacy paths are hidden from OpenAPI; v1 changes only the HTTP contract boundary.
Business errors carry a code at the raise site; error_response selects the
envelope by request path. Validation preserves useful fields without inputs.
SafeErrorMiddleware catches unexpected HTTP failures before Uvicorn can log
raw exceptions; CORSMiddleware wraps those responses. No body/header/URL or
exception text is logged. Raw Uvicorn access logging is disabled.

get_app_settings accepts exact HTTP(S) origins and requires HTTPS in production.
Production lifespan validates DB URL/JWT config without connecting or migrating.
health has no database dependency; ready executes SELECT1 using get_db and
validates JWT config. Engine/factory are reused, Sessions are request-local;
services commit writes and rollback failures, context close releases resources.

reorder_items still locks the Trip, validates every day's ID exactly once and
assigns positions transactionally. Before committing it bulk-loads final rows
with populate_existing, including generated updated_at, then constructs detached
Pydantic snapshots. This avoids per-row lazy refresh and post-commit mixed reads.
The10-item changed/no-op response uses4 SELECTs, not13.

### Architecture Concept

An API contract includes types/status/error/auth semantics, not just URL names.
Versioning supports independently released clients without duplicating domains.
DTO/response models are a deliberate public-data boundary; ORM models are not
automatically safe public JSON.

Authentication proves identity; authorization scopes a resource. All23 protected
operations share get_current_user, while SQL owner/member/recipient checks
enforce the matrix. Pending invitees are not members; shared expenses/itinerary
remain collaboratively editable; owner-only Trip mutations stay strict.

Transactions preserve multi-row invariants. Invite acceptance and expense/split
replacement remain atomic; a request Session is not a global DB connection.
Liveness and readiness answer different operational questions. CORS governs
browsers, not native network access or identity. Configuration and secrets
belong outside business code.

Query-count tests can detect accidental N+1, but do not prove unlimited
scalability. Pagination and capacity limits are documented future work;
balance aggregation stays one SQL snapshot plus current-user lookup.
OpenTrip's stable boundary/config ideas fit; its Better Auth/Hono/cookie and
multi-runtime deployment choices do not justify replacing this MVP stack.

### How to Test

From backend with the existing activated environment and local DB/JWT settings:

```bash
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m app.db.check
python -m alembic current
python -m alembic check
python -m pip check
python -m uvicorn app.main:app --reload
```

Actual final results (work crossed September19/20 local midnight):

- Default: **354 passed, 184 skipped, 0 failed**.
- Real PostgreSQL: **538 passed, 0 skipped, 0 failed**.
- 45 new cases versus Step10:39 default,6 live. No SQLite.
- Contract tests:27 unique official operations,23 protected operations reject
  anonymous before DB access; exact success/error JSON, money strings,
  timestamps, legacy compatibility, member/recipient boundaries and safe
  401/404/405/409/422/500/503.
- CORS permitted/denied origins and methods; production configuration,
  liveness/no SQL, readiness available/unavailable, sensitive failure redaction.
- Query audit: Trips2, Members3, Itinerary3, Expenses3, Balances2 SELECTs including
  User. New test grows itinerary/expense collections1->10; Step10 separately
  checks balances with2/10 members. Reorder10 items unchanged/reversed:4.
- All prior auth/authorization/race/rollback/ordering/expense/balance tests pass.
- SELECT1 passed; Alembic **0005(head)** and **No new upgrade operations detected**.
  pip check: **No broken requirements found**. Five migration hashes unchanged.
- Actual Uvicorn --reload at127.0.0.1:8021 with random process-only key.
  HTTP health/ready/docs/openapi200; OpenAPI27; allowed preflight200,
  unlisted origin400 with no Allow-Origin/credentials.
- Two users register201/login200/me200; createTrip201; pending Bob404;
  invite201/inbox200/accept200/repeated-accept409; members200.
- Member itinerary201; numeric expense amount422; string120.00 expense201,
  splits60/60; balances200 with+60/-60 and Bob->Alice60 suggestion.
  Legacy balance success equals v1; Trip delete204, subsequent read404.
- Temporary HTTP script outside repo: /private/tmp/triptogether-step11-verify.py.
  Only its exact-ID/name records cleaned; all seven table counts restored0->0.
  No sequence reset, credential printing, broad data deletion or .env edits.
  Temporary server stopped and shutdown log observed.
- DB-outage503 is an automated injected failure test, not a manual shutdown of
  the user's PostgreSQL. No interactive Swagger, load, penetration or real
  HarmonyOS-device testing is claimed.

For manual repetition, follow docs/client-integration.md with disposable
accounts and returned IDs. Formal business base: http://127.0.0.1:8000/api/v1.
System probes remain /health and /ready. Mobile loopback may not reach the Mac;
the future client must centrally configure its reachable development base URL.

### Problems Encountered

Four pre-existing OpenAPI assertions expected old paths; updated them to the
published v1 contract, keeping legacy behavior tests. The new reorder regression
reproduced13 SELECTs. A pre-commit DTO-only fix missed expired updated_at on
changed order; adding one bulk final read fixed both changed and no-op cases.
All final tests pass.

Reference web fetch had no useful body; actual git inspection supplied evidence.
pip cache path was unwritable but dependency check passed. Local DB/network
checks needed sandbox permissions. Repository files were all untracked, so
source inspection, not a commit diff, defined the change baseline; no commit
or reset performed.

Known limitations are explicit: no refresh/revocation/reset/email verification,
rate limits, realtime, pagination, member leave/removal, FX or actual payments.
LWW, public docs, minimal diagnostics and production deployment gaps remain.
Readiness does not validate migrations/capacity; secret length cannot prove
randomness. This is scoped MVP hardening, not a "production secure" claim.

### What I Learned

- Stable codes let a client localize errors without matching English messages.
- A compatibility alias can share logic while preserving its original contract.
- Validation should retain field/reason but not sensitive raw input.
- CORS, JWT authentication and resource authorization solve different problems.
- Healthy process, valid configuration and reachable database are distinct.
- Closing a Session and committing a business transaction are not synonyms.
- ORM expiration can create N+1 even without lazy relationships; generated
  timestamps need deliberate response snapshot handling.
- Constant query count does not bound data size, SQL cost or lock waiting.
- Logs and automatic server tracebacks both need a sensitive-data review.
- A useful client guide covers transport failure/retry, dates, null/omission
  and money representation as well as the happy path.
- The full review contains14 concept explanations and24 project-specific Q&As.

### Next Step

Step 12 — HarmonyOS Client Foundation.
Recommended only; not started. Do not automatically begin Step12.

## 2026-09-20 — Roadmap Migration — Web Frontend Decision

### What Was Implemented

Documentation and roadmap migration only. Updated the current project
positioning to a full-stack collaborative travel planning web application,
while preserving all completed Step1-11 backend history and evidence.
No frontend directory, React scaffold, Node dependencies, Docker or deployment
was created. None of Steps12-20 has started.

### Decision

HarmonyOS client development has been deferred.
TripTogether will first be completed as a full-stack web application.
This decision supersedes the historical Step11 Next Step recommendation above;
the original entry is retained unchanged as the decision context at that time.

### Reason

Prioritize easier portfolio demonstration, a browser-accessible live demo,
simpler recruiter evaluation and faster end-to-end MVP completion.
This is a change in project priorities, not a negative judgment of HarmonyOS.
A native/mobile client remains possible future work.

### New Stack

- Planned frontend: React, TypeScript, Vite, under `frontend/` (NOT STARTED).
- Implemented backend: Python/FastAPI, Pydantic, SQLAlchemy, Alembic,
  PostgreSQL, JWT and Argon2id, with pytest-backed regression coverage.
- Flow: React -> REST/JSON /api/v1 -> FastAPI -> Service -> SQLAlchemy
  -> PostgreSQL. The diagram is a target architecture, not a deployment claim.

### New Roadmap

| Step | Task | Status |
| --- | --- | --- |
| 1-11 | Backend MVP | COMPLETE |
| 12 | React + TypeScript Frontend Foundation | NOT STARTED |
| 13 | Authentication UI + API Integration | NOT STARTED |
| 14 | Trip Dashboard + Trip Management | NOT STARTED |
| 15 | Collaboration + Shared Itinerary UI | NOT STARTED |
| 16 | Expense + Balance UI | NOT STARTED |
| 17 | Frontend Polish + E2E Integration | NOT STARTED |
| 18 | Docker + Deployment | NOT STARTED |
| 19 | GitHub README + Live Demo | NOT STARTED |
| 20 | Resume + Interview Preparation | NOT STARTED |

Step19 is the final portfolio/demo presentation; normal documentation updates
continue throughout. Token storage is deferred to the web-security decision in
Step13, not chosen or implemented during this migration.

### Backend Impact

No backend business behavior changed.
No database migration created.
No API contract changed.
No backend code, tests, models, dependencies, configuration or database data
was modified by this task. Expense/balance algorithms and JWT behavior remain
unchanged. The27 formal operations, /api/v1, unified errors, CORS, logging,
health/readiness, OpenAPI and authorization matrix remain valid.

### Files to Review

- `README.md`: web positioning, implemented/planned distinction, architecture,
  current Step12-20 roadmap and future work; backend accomplishments retained.
- `AGENT.md`: React/TypeScript/Vite, future directory, centralized API/auth,
  explicit types, money-string boundary, environment rules, simple state,
  UI states, responsive/accessibility rules, testing and user browser acceptance.
- `docs/client-integration.md`: browser origin/base URL guidance, central client
  responsibilities and Step13 token-storage decision; API examples unchanged.
- `docs/known-limitations.md`: current web-client status and deferred native work.
- `docs/step11-review.md`: historical notice only; original audit/results retained.
- `docs/legacy-development-guide.md`: historical notice only; archive retained.
- `RECORD.md`: this appended decision, not rewritten Step1-11 entries.

### Key Code to Understand

No code was added. The important boundary is future React Component -> shared
API client -> existing /api/v1, never direct PostgreSQL or a second backend.
The API client centralizes base URL, Bearer header and stable error handling.
TypeScript request/response definitions must match the actual contract.
Frontend money stays string input/display; splitting, balance calculation and
settlement suggestions remain authoritative backend results.

### Architecture Concept

Changing client technology does not require replacing a stable REST backend.
UI, interaction and form/loading/empty/error state belong to React; security,
authorization, transactions and financial business rules stay in services.
The modular monolith, PostgreSQL/SQLAlchemy/Alembic, JWT, Decimal and testing
rules remain. Existing source-of-truth API models guide the planned client.

The current rules favor React state/Context/hooks without speculative global
state infrastructure. Every visual step needs automated checks plus a running
URL, manual test instructions/expected results and explicit user acceptance
status; passing tests alone does not prove the browser experience is complete.
OpenTrip remains a design reference, not a source-code template.

### How to Test

Actual command from backend using the existing Python environment:

```bash
python -m pytest -q
```

Result: **354 passed, 184 skipped, 0 failed** in1.85 seconds.
The184 live PostgreSQL cases remain intentionally skipped in default mode.
The expensive live suite was not rerun for documentation-only changes; the
Step11 result538 passed remains historical evidence, not a new execution.

Ran `git diff --stat` and `git status`. Status reports branch main, no commits
yet, all existing project files untracked; diff-stat is therefore empty, not
proof of no changes. Independently compared the sorted SHA256 manifest digest
of all rg-listed backend files before/after editing:
`e830138090ee225eb4216191794df6af0910d651bf0dbca8181ba72f2113dde4`.
It is unchanged. Confirmed `frontend/` does not exist.

Consistency search covered HarmonyOS, ArkTS, ArkUI, mobile client and Step12-14
across the repository, also accepting optional spaces in step names.
Active README/AGENT/client guide/limitations now describe the web plan.
Remaining mobile references are explicit deferral/future work or historical
review/archive/RECORD content; Step11 and the archived guide have prominent
supersession notices. Step10's historical "not started" statements are retained.

The pre-append RECORD was118809 bytes, SHA256
`d7ad3bc255b01db634805c2772ed8ed624dc507c4564578491ee4778fc23f10c`;
that original byte prefix is preserved, providing an independent historical
integrity check despite the missing Git baseline.

### Problems Encountered

Git has no tracked baseline, so ordinary diff-stat cannot isolate this task;
used backend hashes and the original RECORD prefix to verify scope instead.
An initial multi-file patch had an unmatched archive context and made no
changes; corrected the context and reapplied.

AGENT still used early "invitation codes" and "expense_participants" wording.
Corrected those descriptions to existing registered-user invitations and
expense_splits (and listed trip_invitations), without changing the backend.
Preserved historical review text rather than globally replacing HarmonyOS
and misrepresenting earlier decisions.

### What I Learned

- A roadmap is a prioritized plan, not proof of implemented features.
- Preserve historical decisions; append a superseding decision instead.
- An API contract can serve a new client without changing business rules.
- Browser CORS and public frontend configuration need explicit guidance;
  server secrets must never enter a frontend bundle.
- Token storage belongs to a deliberate web-security decision, not a casual
  choice during project scaffolding or documentation migration.
- Automated checks and user browser acceptance are complementary.

### Next Step

Step 12 — React + TypeScript Frontend Foundation.
Recommended only; NOT STARTED. Do not automatically begin Step12.

## 2026-09-20 — Step 12: React + TypeScript Frontend Foundation

### What Was Implemented

Goal: establish the first React/TypeScript/Vite frontend without business UI.
Implementation and automated checks are complete; user browser acceptance is
pending. This entry supersedes the previous NOT STARTED status, not the
historical work. Step13 has not started.

Created `frontend/` with the official React/TypeScript Vite scaffold, replaced
the demo with a minimal TripTogether shell, `/` and Not Found routes, native
fetch API client, typed health/error contracts, a real health indicator and
retry behavior. Added strict type checking, ESLint, Vitest/Testing Library,
environment example, ignores and setup documentation. No auth/token storage,
business pages, Docker, database changes or backend behavior changes.

### Environment

Actual versions: Node24.21.0, npm11.19.0, React/ReactDOM19.3.0,
TypeScript6.0.3, Vite8.3.0, React Router7.18.4, Vitest5.0.1, jsdom30.1.0,
ESLint10.11.0. npm only, one package-lock.json.
Node was available and compatible before frontend implementation.

### OpenTrip Reference Review

Inspected checkout `/private/tmp/triptogether-opentrip-reference` at
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`: `apps/web/src/app/router.tsx`,
`App.tsx`, `AppErrorBoundary.tsx`, `app/providers/index.tsx`,
`shared/api/client.ts`, `shared/config/index.ts`,
`widgets/app-sidebar/AppSidebar.tsx`, and `pages/trips/TripsPage.tsx`.
Referenced routing, component boundaries, central transport, request states and
responsive organization. No source, CSS, branding or assets copied.
Did not adopt Better Auth/cookies, React Query, provider layers, sidebar or
business dashboard: they are unnecessary or inconsistent with this step.

### Files to Review

Seven priority files with responsibilities and key sections:

1. `frontend/src/main.tsx`: createRoot and StrictMode mount/cleanup behavior.
2. `frontend/src/App.tsx`: shell composition, BrowserRouter and Link.
3. `frontend/src/types/api.ts`: HealthResponse and backend error issue types.
4. `frontend/src/api/client.ts`: getBaseUrl, ApiError, apiFetch and getHealth;
   configuration, HTTP and actual health schema validation are separate.
5. `frontend/src/components/BackendStatus.tsx`: loading/success/error union,
   effect cancellation, ignoring stale responses and manual retry.
6. `frontend/src/api/client.test.ts`: public contract tests including malformed
   JSON,204, network failure, headers and environment handling.
7. `frontend/vite.config.ts`: React transform, jsdom setup and metadata exclusion.

### Files Created

`frontend/package.json`, `package-lock.json`, `index.html`, `tsconfig.json`,
`tsconfig.app.json`, `tsconfig.node.json`, `vite.config.ts`,
`eslint.config.js`, `.gitignore`, `.env.example`, `README.md`;
`src/main.tsx`, `App.tsx`, `index.css`, `App.css`, `types/api.ts`,
`api/client.ts`, `api/client.test.ts`, `components/BackendStatus.tsx`,
`App.test.tsx`, `test/setup.ts`.
Removed generated logos, counter, hero and sprite demo content.

Updated root `.gitignore`, `README.md`, current status in `AGENT.md`,
`docs/client-integration.md`, `docs/known-limitations.md`, and this record.
Created `docs/step12-review.md` with the full report, reading guide and learning
material. No backend files or actual `.env` were changed.

### Key Code to Understand

The component calls getHealth rather than assembling fetch calls.
The client accepts a configured HTTP(S) origin only, merges Headers, handles
JSON/error envelopes, returns undefined for204, and bounds requests to10 seconds.
ApiError carries status/code/message/details. getHealth validates the runtime
payload; a TypeScript generic alone cannot validate server JSON.
Effect cleanup aborts obsolete work. The component ignores cancelled results
and a Retry action initiates another attempt without reloading the document.

### Architecture Concept

React component -> shared API client -> FastAPI -> Service -> SQLAlchemy ->
PostgreSQL is the future business chain. This step's public `/health` stops at
FastAPI and is deliberately independent of SQL/auth readiness.
Frontend owns interaction/display; backend retains all rules and authority.
Native fetch and component state suffice; no global state or data-fetch library.
Routes `/` and `*` are client-side UI routes, separate from API routes.
No speculative domain types or empty architecture directories were added.

### API Client

Centralized URL, headers, JSON decoding, status/error parsing, network failure,
timeout and cancellation. No Axios or automatic write retries.
Non-JSON errors use a safe HTTP fallback; invalid success health bodies do not
show Connected. Error details are structurally checked.
Future Step13 can extend the shared header boundary for Bearer authentication;
no token header, token storage or auth mechanism implemented now.

### Environment Configuration

`VITE_API_BASE_URL` is required, with no application-code address fallback.
It is the backend origin, not `/api/v1`; `/health` is public, future business
adapters must use `/api/v1/...`. `frontend/.env.example` contains a public
localhost example. Real frontend/root `.env` are ignored and untouched.
All VITE values are public build inputs; no database/JWT secrets belong there.
Restart Vite after configuration changes; rebuild for new production settings.

### Backend Connectivity

Actual Uvicorn startup succeeded at `http://127.0.0.1:8000`.
Actual Vite startup succeeded at `http://127.0.0.1:5173`.
GET /health returned200 `{"status":"ok"}`. Native Chrome displayed
TripTogether and Connected, with a readable desktop screenshot.
Both temporary processes started by the agent were stopped after verification.

### CORS

Used process-only
`CORS_ORIGINS=["http://127.0.0.1:5173","http://localhost:5173"]`,
not wildcard and not a change to real .env.
Health GET returned matching Access-Control-Allow-Origin.
OPTIONS `/api/v1/trips` for POST/Authorization/Content-Type returned200 with
matching origin; unlisted `http://unlisted.test` returned400 without Allow-Origin.
No Allow-Credentials header. Real browser success confirms the response can be
read from the frontend origin, beyond just curl transport success.

### Routing and UI States

Home plus Not Found, no business placeholders. Client Link returns home.
Checking..., Connected, Unavailable/error message and Retry are covered.
Semantic headings/status, keyboard focus and responsive plain CSS are present.
No list means Empty is not applicable. This is a mount/retry check, not polling:
after stopping backend, refresh to initiate a new request before expecting error.

### How to Test

From `frontend`: `npm ci`, `cp -n .env.example .env`, `npm test`,
`npm run typecheck`, `npm run lint`, `npm run build`.
Use the existing backend environment in a separate terminal.
Full copy-ready startup commands and expected browser results are in root
README, frontend/README and docs/step12-review.md.

Actual final results:

- Frontend: **25 passed,0 failed**,2 test files.
- ESLint: **passed**,0 errors/warnings.
- TypeScript strict application check: **passed**,0 errors.
- Configured production build: **passed**, HTML0.48kB/CSS2.19kB/JS262.96kB.
- Backend default regression: **354 passed,184 skipped**,2.60s.
- Live PostgreSQL suite not rerun: backend code unchanged; historical538
  result is not reported as newly executed.

Backend file SHA256 manifest unchanged:
`e830138090ee225eb4216191794df6af0910d651bf0dbca8181ba72f2113dde4`.

### Manual Verification

Open the actual Vite address after starting both servers per README.
Confirm Connected; stop backend and refresh to see Unavailable; restart backend
and Retry to recover. Visit `/missing`, Return home, check keyboard focus and
desktop/mobile widths. PostgreSQL running as a background service needs no
separate terminal. Stop both dev servers with Ctrl+C when done.

User acceptance remains pending. Agent browser connectivity and desktop
inspection succeeded; mobile-width and browser outage/recovery remain for the
user to verify because the user was interacting with Chrome during automation.
Automated error/retry tests passed but do not substitute for visual acceptance.

### Problems Encountered

- Tool rejected a combined same-file delete/add patch; split it, with no
  partial edits from the rejected patch.
- Missing npm scripts and parameter-property syntax with erasableSyntaxOnly
  blocked early checks; corrected scripts and explicit class fields.
- External disk AppleDouble `._*.test.*` files caused2 false test suites with
  null-byte parse errors; kept default Vitest excludes and added `**/._*`.
  Final result is25 passing tests, no failed suites.
- Current scaffold used Oxlint; replaced it with requested ESLint and removed
  the redundant dependency.
- Browser connector auth was unavailable; native Chrome provided real
  connectivity evidence. Later user activity stopped additional UI operations.
- Optional fsevents install-script warning remains; no blanket script approval
  was needed for successful dev/test/build verification.
- No Git baseline exists. `git diff --stat` is empty because files are
  untracked, not because no work occurred. Used inventory/hash/ignore checks.

### What I Learned

React component/state/effect boundaries separate display from transport.
StrictMode exposes unsafe cleanup; aborting old requests prevents stale updates.
TypeScript is compile-time help, not runtime JSON validation.
VITE settings are public and frozen into built code.
CORS origin matching differs from auth and must be tested in a browser.
Health is not DB readiness. Development and production builds are separate.
External-disk metadata can affect test discovery even when ignored by Git.

### Concepts to Understand

`docs/step12-review.md` explains16 project-specific concepts in Chinese:
React, SPA, Vite, TypeScript, Component, Props, State, Effect, lifecycle,
API client, CORS, Origin, environment variables, public VITE values,
build vs dev server, and client-side routing.

### Interview Questions

The same review supplies16 concise Q&As covering framework choices, typed
contracts, SPA flow, fetch, centralized errors, environment/CORS, failure states,
StrictMode, build, future JWT boundary and health-vs-readiness.

### Known Limitations and Git Status

No user visual acceptance yet, no E2E framework, no automatic polling,
no business UI/auth/deployment. Modern AbortSignal APIs required.
Generic success payloads beyond health require endpoint-level checks.
Repository has no initial commit; all project files remain untracked.
Verified node_modules/dist/coverage/real frontend .env are ignored, while
.env.example and source/lockfile remain eligible. No commit created.

### Next Step

Step 13 — Authentication UI + API Integration, after Step12 user acceptance.
Recommended only; NOT STARTED. Do not automatically begin Step13.

## 2026-09-20 — Step 12: Local Frontend Configuration Fix

### What Was Implemented

Investigated the user's Unavailable screenshot showing CONFIG_ERROR.
`frontend/.env` and all mode-specific local environment files were absent.
Created ignored `frontend/.env` containing only the public backend origin:
`VITE_API_BASE_URL=http://127.0.0.1:8000`.
No business code, backend configuration or running user processes were changed.

### Files to Review

- `frontend/.env`: local configuration, excluded from Git.
- `frontend/.env.example`: existing setup template, unchanged.
- `frontend/src/api/client.ts`: existing configuration validation, unchanged.

### Key Code to Understand

getBaseUrl rejects missing configuration before issuing fetch.
The displayed message therefore identified a configuration failure, not evidence
of backend downtime. The example file alone does not configure the application.

### Architecture Concept

Local frontend settings and backend connectivity are separate checks.
The previous agent validation supplied the origin through process environment;
that setting did not persist into the user's later Vite process.

### How to Test

Actual running backend: GET /health returned200 `{"status":"ok"}` with
Access-Control-Allow-Origin `http://127.0.0.1:5173`.
After creating frontend/.env, the running Vite server's transformed
`/src/api/client.ts` contained the correct VITE_API_BASE_URL, confirming reload.
Refresh the browser and expect Connected. If needed, restart the frontend
with the README command. Browser confirmation remains pending.
No code changed, so the unit suites were not rerun for this configuration fix.

### Problems Encountered

Missing local environment file caused the error. Sandbox networking initially
could not reach localhost; an approved local request confirmed the backend
and CORS were already healthy. No server restart or CORS modification needed.

### What I Learned

Temporary process environment and .env.example do not replace a persistent,
ignored local .env. Diagnose the displayed error before assuming CORS failure.

### Next Step

Step 13 — Authentication UI + API Integration, after Step12 user acceptance.
Recommended only; not started.

## 2026-09-20 — Step 13: Authentication UI + API Integration

### What Was Implemented

Implemented the web authentication flow against the existing FastAPI contract:
registration, JSON login, JWT access-token storage, `/auth/me` verification,
session restoration, protected `/account`, local logout, safe form errors and
loading states. Step14 trip UI was not started.

Step12 browser acceptance was treated as complete because the user confirmed
the real frontend-to-backend health connection before this task. Step13 browser
acceptance remains pending.

### Files to Review

- `frontend/src/api/client.ts`: optional Bearer header and public/authenticated transport.
- `frontend/src/api/auth.ts`: register, login and current-user API adapters.
- `frontend/src/auth/AuthContext.tsx`: centralized auth state and lifecycle.
- `frontend/src/auth/tokenStorage.ts`: sessionStorage boundary.
- `frontend/src/auth/ProtectedRoute.tsx`: loading, error and redirect guard.
- `frontend/src/components/AuthForm.tsx`: form validation and safe error display.
- `frontend/src/components/LogoutButton.tsx`: coordinated local logout/navigation.
- `frontend/src/pages/LoginPage.tsx`, `RegisterPage.tsx`, `AccountPage.tsx`.
- `frontend/src/App.tsx`: provider scope and route tree.
- `frontend/scripts/verify_auth.py`: opt-in live PostgreSQL/authentication check.

Detailed code explanations, security review and interview questions are in
`docs/step13-review.md`.

### Key Code to Understand

The flow is:

```text
Login/Register Page
    -> AuthProvider
    -> auth API adapter
    -> centralized API client
    -> FastAPI JWT endpoint
    -> PostgreSQL-backed User
```

Registration returns a User and does not log in. Login stores only the returned
access token in `sessionStorage`, then calls `/api/v1/auth/me`; a token alone
never grants authenticated UI. Refresh repeats `/me`. A clear 401 removes the
session; network/503 restore failures preserve the candidate token and offer
retry. Logout removes the client token only; the backend has no revocation API.

### Backend Contract

- `POST /api/v1/auth/register`: JSON `username`, `email`, `password`; returns201 User.
- `POST /api/v1/auth/login`: JSON `email`, `password`; returns200 bearer TokenResponse.
- `GET /api/v1/auth/me`: `Authorization: Bearer <token>`; returns200 User.

User fields are `id`, `username`, `email`, `created_at`. Passwords and hashes
are never returned. Backend error envelopes use `code`, `message`, and `details`.
Client validation improves UX; backend validation remains authoritative.

### OpenTrip Reference Review

Reviewed the reference auth form, auth page, session-state helper and auth
client. Reused ideas about labels, loading feedback, focused forms and
session-resolution boundaries. Did not copy Better Auth, cookies, OAuth, OTP,
MFA, CAPTCHA, password reset, source code, CSS or branding.

### Authentication Architecture

`AuthProvider` owns `user` status, login, restore, logout and authenticated
request handling. Pages consume `useAuth()` and do not call `fetch`.
`apiFetch` accepts an explicit `accessToken`; it does not know about routing.
`ProtectedRoute` is a UX boundary, while FastAPI remains the actual security
boundary.

### Token Storage Decision

The access token is stored only in `sessionStorage` under
`triptogether.accessToken`. This supports reload restoration without choosing
long-lived `localStorage`. It is not fully secure: same-origin JavaScript/XSS
can read it, and logout does not revoke a copied JWT. No refresh token, cookie
session, OAuth, MFA, password reset or email verification was added.

### Registration and Login

Registration validates obvious client errors, submits JSON, disables duplicate
submission, clears the password input and navigates to login with a boolean
success state. Login uses email/password, stores no password, obtains a JWT,
verifies `/me`, and only then navigates to `/account`.

### Protected Route and Logout

`/account` waits at `Checking session...`, redirects anonymous users to `/login`,
and shows a retry action for temporary restore errors. Shared logout clears
sessionStorage, aborts active auth work, clears the user and navigates home.
No `/logout` request is sent because the backend does not expose one.

### Error Handling and Security

Known backend codes map to safe messages and field errors. HTML-like messages
render as text. Public login401 remains a form error; authenticated request401
clears the session; 503 and network errors do not falsely log out the user.
The client does not decode/verify JWT signatures, hash passwords, log tokens,
place tokens in URLs, or put secrets in Vite environment configuration.

### How to Test

```bash
cd /Volumes/Elements/TripTogether/frontend
npm test
npm run lint
npm run build
```

For the real flow:

```bash
cd /Volumes/Elements/TripTogether
/private/tmp/triptogether-step1-venv/bin/python frontend/scripts/verify_auth.py
```

The script starts an isolated temporary backend with a random temporary JWT
key, uses the existing PostgreSQL schema, creates a unique test user, runs
registration/login/me/restore/logout/invalid-credential checks, deletes only
that exact user, and stops the temporary backend.

### Tests

- Frontend normal suite: **62 passed, 0 failed, 1 opt-in live test skipped**.
- Frontend live authentication integration: **1 passed, 0 failed**.
- ESLint: **passed**, no warnings/errors.
- TypeScript/production build: **passed**.
- Backend PostgreSQL auth/API regression: **102 passed, 0 failed**.
- PostgreSQL connectivity: `PostgreSQL connectivity check passed (SELECT 1).`

The backend source manifest remains unchanged:
`e830138090ee225eb4216191794df6af0910d651bf0dbca8181ba72f2113dde4`.

### Problems Encountered

- Local backend `/ready` initially returned503 because the ignored root `.env`
  had no `JWT_SECRET_KEY`. Generated a random missing key without printing or
  overwriting an existing value; `/ready` then returned200.
- Logout initially raced with the protected-route redirect and landed on
  `/login`; a shared coordinated `LogoutButton` and regression test fixed it.
- The task referenced `backend/app/core/errors.py`, but the actual error module
  is `backend/app/api/errors.py`; implementation followed the real code.
- Native browser automation was interrupted by concurrent user activity.
  Desktop login layout was inspected; mobile/full browser acceptance remains
  for the user.

### Important Code

The ten files in `docs/step13-review.md` are the recommended reading order.
Start with `api/client.ts`, `api/auth.ts`, `AuthContext.tsx`,
`tokenStorage.ts`, `ProtectedRoute.tsx`, `AuthForm.tsx`, the three auth pages,
and `App.tsx`.

### Concepts to Understand

The review explains authentication vs authorization, JWT/Bearer/access tokens,
signatures, sessionStorage vs localStorage, `/auth/me`, Context/Provider/hooks,
protected routes, redirects,401 vs403, account enumeration, XSS and why the
frontend does not hash or verify passwords.

### Interview Questions

`docs/step13-review.md` contains **20** project-specific questions with concise
answers covering the complete authentication flow and its limitations.

### Known Limitations

No refresh token, server-side revocation, OAuth, MFA, email verification,
password reset, cross-tab logout or continuous expiry polling. sessionStorage
remains readable by same-origin JavaScript. Live integration uses real HTTP and
PostgreSQL but jsdom is not a real browser. Manual browser acceptance is pending.

### RECORD.md

This Step13 entry has been appended according to `AGENT.md`; historical entries
were not rewritten.

### Git Status

No commit was created; the repository has no tracked baseline. Real `.env`,
`node_modules`, `dist` and coverage remain ignored. No generated JWT, password,
private key or database credential was added to source or documentation.

### Next Step

Step14 — Trip Dashboard + Trip Management, after Step13 browser acceptance.
Recommended only; NOT STARTED. Do not automatically begin Step14.

## 2026-09-20 — Step 14: Trip Dashboard + Trip Management

### What Was Implemented

Implemented the authenticated Trip Dashboard and Trip management workflow.
Users can list owned and joined trips, create a trip, open trip details, edit
owned trip metadata and delete owned trips. Joined trips remain view-only in
the UI. This step did not add invitations, members, itinerary, expenses or
balances UI.

Step13 browser acceptance was supplied by the user and is now recorded as
complete. Step14 automated verification is complete; browser acceptance remains
pending user confirmation.

### Files to Review

- `frontend/src/api/trips.ts`
- `frontend/src/types/trip.ts`
- `frontend/src/pages/TripsPage.tsx`
- `frontend/src/pages/TripDetailPage.tsx`
- `frontend/src/components/TripForm.tsx`
- `frontend/src/pages/TripManagement.test.tsx`
- `frontend/scripts/verify_trips.py`
- `docs/step14-review.md`

### Key Code to Understand

`TripsPage` loads `/api/v1/trips` through the authenticated request dependency,
renders loading, empty, error and list states, and sends validated create
requests. `TripDetailPage` loads one trip, compares `owner_id` with the current
user id, and only renders edit/delete controls for the owner. Delete requires
confirmation and keeps API failures visible instead of producing an unhandled
rejection.

`TripForm` validates required fields, server limits and date ordering before
calling the API adapter. `api/trips.ts` validates successful response shapes so
malformed backend data cannot silently become trusted UI state. All trip
requests use `AuthContext.request`, which centralizes the Bearer token and
protected 401 handling.

### Architecture Concept

This step demonstrates a typed client adapter and protected feature workflow:
React pages handle presentation and state, the form handles user input, the API
adapter handles the REST contract, and `AuthContext` handles authentication
transport. UI owner checks improve usability, while backend authorization
remains the actual security boundary.

### How to Test

```bash
cd /Volumes/Elements/TripTogether/frontend
npm test
npm run lint
npm run typecheck
npm run build
```

For a real PostgreSQL-backed API check:

```bash
cd /Volumes/Elements/TripTogether
/private/tmp/triptogether-step1-venv/bin/python frontend/scripts/verify_trips.py
```

For browser acceptance, start the backend and Vite using the README commands,
log in, create a trip, open it, edit it, delete it, and verify that a joined
member can view details without owner-only controls.

### Problems Encountered

The first delete implementation allowed a rejected request to escape the click
handler. It was corrected with local pending/error state and a regression test.
Existing authentication tests also assumed login navigated to `/account`; they
were updated because the dashboard is now the post-login destination. No
business backend code or schema was changed.

### What I Learned

The frontend should consume the established versioned API instead of recreating
business rules. Client-side ownership checks are presentation logic, not a
replacement for server-side authorization. Response validation and explicit
loading/error states make network-backed screens predictable.

### Next Step

Step 15 — Collaboration + Shared Itinerary UI. Recommended only; do not begin
it automatically.

## 2026-09-20 — Step 15: Collaboration + Shared Itinerary UI

### What Was Implemented

Implemented the frontend collaboration workflow using the existing backend
contract. Trip details now display members, owners can invite registered users,
and recipients can accept or reject invitations from the Dashboard inbox.
Accepted members see the Trip after the list refreshes automatically.

Implemented shared itinerary management for accepted owners and members:
date-grouped list, create, edit, delete with confirmation, local time
validation, and complete-day up/down reordering through the backend reorder API.
Expense and Balance UI were not implemented.

Step 15 automated verification is complete; browser acceptance remains pending
user confirmation. No backend business logic, schema or dependency was changed.

### Files to Review

- `frontend/src/api/collaboration.ts`
- `frontend/src/types/collaboration.ts`
- `frontend/src/components/MembersPanel.tsx`
- `frontend/src/components/InvitationInbox.tsx`
- `frontend/src/components/ItineraryPanel.tsx`
- `frontend/src/pages/TripDetailPage.tsx`
- `frontend/src/pages/TripsPage.tsx`
- `frontend/src/pages/Collaboration.test.tsx`
- `frontend/scripts/verify_collaboration.py`
- `docs/step15-review.md`

### Key Code to Understand

`collaboration.ts` maps the Step 7/8 REST endpoints and validates member,
invitation and itinerary response shapes. `MembersPanel` exposes the owner-only
invitation action while keeping the member list available to every accessible
Trip user. `InvitationInbox` calls accept/reject as the authenticated recipient
and asks the Dashboard to reload Trips after a successful decision.

`ItineraryPanel` groups server-returned items by calendar date. It sends
complete-day `item_ids` to `/itinerary/reorder` and uses the server response as
the new order. Itinerary fields are kept as local form values until submit;
empty optional text/time fields become `null`, matching the backend contract.

### Architecture Concept

This step demonstrates feature composition around a stable API boundary.
Authentication and transport remain centralized in `AuthContext`, API shape
validation remains in adapters, and focused components own local loading,
pending, error and success state. Authorization is still enforced by FastAPI;
frontend role checks only control the user experience.

### How to Test

```bash
cd /Volumes/Elements/TripTogether/frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Real PostgreSQL/FastAPI collaboration verification:

```bash
cd /Volumes/Elements/TripTogether
/private/tmp/triptogether-step1-venv/bin/python frontend/scripts/verify_collaboration.py
```

For browser acceptance, use two disposable accounts. Invite and accept a
member, verify the member list and Dashboard refresh, then create, edit,
reorder and delete itinerary items from both accepted users.

### Problems Encountered

The initial UI test exposed a duplicate DOM id between the itinerary section
heading and the Title input. Renaming the section heading id fixed the label
association and improved keyboard/screen-reader behavior. Existing Step14
tests were adjusted for the new invitation and collaboration requests.

### What I Learned

Invitation status and membership are separate backend concepts: a pending
invitation must not be treated as Trip access. Reordering is also a server
contract, not a client-only array operation, because the backend validates the
complete day and persists positions transactionally.

### Next Step

Step 16 — Expense + Balance UI. Recommended only; do not begin it automatically.

## 2026-09-20 — Step 16: Expense + Balance UI

### What Was Implemented

Implemented the frontend Expense and Balance workflow using the existing Step
9/10 backend APIs. Accepted Trip members can create, edit and delete shared
expenses, select a payer and participant set, and view the server-returned
equal split values.

Trip details now show member balances and suggested settlements. Balance data is
refreshed after every successful expense write. Settlement suggestions are
displayed as guidance only; no payment or repayment workflow was added.

Step 16 automated and real PostgreSQL verification is complete. Browser
acceptance remains pending user confirmation. No backend business logic,
database schema or dependency was changed.

### Files to Review

- `frontend/src/api/finance.ts`
- `frontend/src/types/finance.ts`
- `frontend/src/components/ExpensePanel.tsx`
- `frontend/src/components/BalancePanel.tsx`
- `frontend/src/pages/TripDetailPage.tsx`
- `frontend/src/components/Finance.test.tsx`
- `frontend/src/api/finance.test.ts`
- `frontend/scripts/verify_finance.py`
- `docs/step16-review.md`

### Key Code to Understand

`finance.ts` validates exact money strings, expense splits, signed balances and
settlement suggestions before data reaches the UI. `ExpensePanel` sends
decimal strings and member IDs to the existing API. It never calculates equal
shares locally; it renders the exact `splits` returned by the backend.

`BalancePanel` renders `paid`, `share`, `balance` and suggested transfers from
the authoritative balance response. `TripDetailPage` increments a refresh key
after expense create/update/delete so the balance view cannot remain stale.

### Architecture Concept

This step demonstrates a strict financial boundary: React owns input and
presentation, while FastAPI owns currency consistency, equal splitting,
balance calculation and settlement matching. Money remains a string at the
client boundary, avoiding binary floating-point errors.

### How to Test

```bash
cd /Volumes/Elements/TripTogether/frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Real PostgreSQL/FastAPI verification:

```bash
cd /Volumes/Elements/TripTogether
/private/tmp/triptogether-step1-venv/bin/python frontend/scripts/verify_finance.py
```

For browser acceptance, create a Trip with two accepted members, add a
100.00 expense split between them, verify exact shares and balances, edit the
expense, then delete it and confirm balances refresh.

### Problems Encountered

The first balance response validator accepted only unsigned money strings even
though member balances can be negative. It was corrected to accept signed
two-decimal balance values while keeping expense amounts and shares unsigned.
Existing Step14 tests also needed finance endpoint defaults so their response
queues remained isolated from the new Trip detail panels.

### What I Learned

Equal split results and settlement suggestions are derived financial data, not
UI calculations. The frontend must preserve decimal strings, display stored
remainders exactly, and refresh derived balances after every ledger mutation.

### Next Step

Step 17 — Frontend Polish + E2E Integration. Recommended only; do not begin it
automatically.

## 2026-09-20 — Step 17: Frontend Polish + E2E Integration

### Completed Content

- Replaced the development-health landing page with a product landing page and role-aware application shell.
- Polished dashboard cards with owner/member roles and retained invitation refresh behavior.
- Organized Trip Detail into Overview, Itinerary, Expenses, and Members section navigation without changing API contracts.
- Kept date-grouped itinerary, exact backend money strings, balance semantics, deletion confirmations, responsive styles, and accessible labels/focus handling.
- Updated README and added the Chinese Step 17 learning review with 22 interview questions.

### Modified Files

- `frontend/src/App.tsx`, `frontend/src/App.css`, `frontend/src/App.test.tsx`
- `frontend/src/pages/TripsPage.tsx`, `frontend/src/pages/TripDetailPage.tsx`
- `frontend/src/components/BalancePanel.tsx`
- `README.md`, `docs/step17-review.md`, `RECORD.md`

### UI Architecture

`App.tsx` owns the shared shell and client-side routes. Feature panels retain their existing API adapters and backend authority. Trip detail uses in-page semantic section navigation rather than a new router or UI framework.

### E2E Flow

The established real PostgreSQL verification scripts cover the Alice/Bob equivalent flow: account registration/login, trip creation, invite/accept, shared itinerary changes, expense create/edit/delete, balances, and clean-up. Frontend Vitest coverage validates the routing and component interactions at the browser boundary.

### Tests

Frontend: `npm test`, `npm run lint`, `npm run typecheck`, and `npm run build` are required after this change. Backend: `pytest` and opt-in `RUN_POSTGRES_TESTS=1 pytest` remain the regression suite.

### Real PostgreSQL Verification

`verify_auth.py`, `verify_trips.py`, `verify_collaboration.py`, and `verify_finance.py` start temporary FastAPI instances against the configured PostgreSQL database, create unique disposable data, and remove it in `finally` blocks. No SQLite fallback is used.

### Problems Encountered

Vitest does not support Jest's `--runInBand` option; run the project-defined `npm test` command instead. No application defect was associated with that command-line incompatibility.

### Concepts to Understand

Application Shell, SPA navigation, client-side routing, responsive layouts, empty/loading/error states, exact decimal presentation, backend authorization, and the boundary between unit, integration, and E2E verification are explained in `docs/step17-review.md`.

### Interview Questions

The Step 17 review contains 22 short questions and answers covering Steps 12–17, authentication, routing, collaboration, financial correctness, testing, Git hygiene, and build verification.

### Known Limitations

There is no deployment, real payment rail, refresh-token/revocation flow, maps, booking, chat, WebSocket updates, or real-browser automation suite. Those are deliberately outside the MVP scope.

### Next Step

Step 18 — Deployment and demo operations planning. Recommended only; do not begin automatically.

## 2026-09-20 — Product UI/UX Redesign

### Completed Content

- Rebuilt the visual system around a calm light-blue palette, neutral surfaces, consistent spacing, compact radii, and accessible focus states.
- Redesigned the public landing page, authentication cards, dashboard trip cards, and Trip Detail workspace while preserving the React routes and API calls.
- Converted Trip Detail into keyboard-accessible Overview, Itinerary, Expenses, and Members tabs; existing collaboration, itinerary, expense, balance, and authorization behavior remains in its original feature components.
- Added member initial avatars and a password show/hide control. No UI dependency, backend endpoint, schema, authentication contract, or money calculation changed.

### Verification

Frontend checks passed: 80 tests passed (1 skipped), ESLint passed, TypeScript typecheck passed, and the production Vite build passed. The final browser visual QA report is stored in `design-qa.md`.

### Design Direction

The reference was used only as a visual direction for an editorial, collaborative travel workspace. The implementation uses the product's real data and actions—no copied source code, image assets, misleading product claims, or simulated money calculations were introduced.

## 2026-09-21 — Step 18: Deployment Preparation

### What Was Implemented

Added Docker-based deployment preparation without changing any domain behavior. The backend image installs the existing Python requirements and starts Uvicorn without reload. The frontend uses a Node multi-stage build and Nginx SPA fallback. Docker Compose models PostgreSQL, a one-shot controlled migration job, backend, and frontend.

### Files to Review

- `backend/Dockerfile`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `docker-compose.yml`
- `.dockerignore`
- `.env.example`
- `README.md`

### Key Code to Understand

`docker-compose.yml` makes `migrate` finish successfully before `backend` starts, so migrations are an explicit single release step rather than a side effect of every API process. The frontend Docker build requires `VITE_API_BASE_URL`; Vite embeds this public value during `npm run build`. The backend continues to obtain secrets only from its environment/configuration source.

### Architecture Concept

Deployment preparation separates build-time public configuration from runtime secrets. Browser code may contain the API origin but never the database URL or JWT secret. Readiness confirms configuration plus database connectivity, while liveness remains independent of the database.

### How to Test

Run the frontend build, backend tests, `python -m alembic check`, and `pip check`. When Docker is installed, run `docker compose config`, then `docker compose up --build` with a local `.env` that supplies `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, exact localhost CORS origins, and `VITE_API_BASE_URL`.

### Verification

The frontend suite passed with 80 tests passing and 1 skipped; ESLint, TypeScript typecheck, and the Vite production build passed. Backend regression passed with 354 tests passing and 184 skipped; PostgreSQL integration passed with 538 tests passing. `alembic check` reported no new upgrade operations and `pip check` found no broken requirements. A clean temporary virtual environment installed `backend/requirements.txt`, passed `pip check`, started a non-reloading `APP_ENV=production` Uvicorn process, and returned `{"status":"ready"}` from `/ready`. The first production-mode process also returned `{"status":"ok"}` from `/health`. A Vite production preview served the SPA route successfully. The disposable real PostgreSQL/FastAPI verification scripts passed for auth, trip CRUD, collaboration plus itinerary, and expense plus balance flows.

### Problems Encountered

Docker is not installed on this machine, so Docker image builds and Compose startup cannot be claimed as verified here. The files were statically inspected instead. The local Compose simulator defaults to development CORS semantics because its browser URL is HTTP; a real production release must set `APP_ENV=production` and exact HTTPS origins.

### What I Learned

Production readiness is not the same as cloud deployment. A reliable release defines configuration ownership, migration ordering, liveness/readiness checks, image build boundaries, and a repeatable local simulation before selecting a hosting provider.

### Next Step

Step 19 — Production Deployment. Recommended only; do not begin automatically.

## 2026-09-21 — Step 19A: Production Deployment Planning

### What Was Implemented

Prepared the Vercel frontend and Render backend deployment plan without
creating cloud resources. Added Vercel SPA rewrites and Node 24 metadata,
documented the manual Vercel → Render → PostgreSQL sequence, and normalized
standard hosted PostgreSQL URLs to the existing psycopg SQLAlchemy driver.

### Files to Review

- `frontend/vercel.json`
- `frontend/package.json`
- `backend/app/core/config.py`
- `backend/tests/test_database.py`
- `docs/deployment-checklist.md`
- `README.md`

### Key Code to Understand

The Vercel rewrite sends deep client routes to `index.html`, allowing React
Router to select the page. `get_database_url()` accepts provider-standard
`postgres://` and `postgresql://` inputs and converts only the SQLAlchemy
driver name to `postgresql+psycopg`, preserving the host, credentials, query
parameters, and local development behavior.

### Architecture Concept

The frontend has a build-time public dependency on the Render HTTPS origin;
the backend has runtime secret dependencies on PostgreSQL and JWT values.
Deployment therefore has an intentional ordering: establish database and API,
build Vercel with the API origin, then set exact backend CORS to the final
Vercel origin.

### How to Test

Run the existing frontend and backend suites. Before actual deployment, follow
`docs/deployment-checklist.md` manually; do not put generated secrets in Git.

### Verification

Frontend tests passed with 80 tests passing and 1 skipped; ESLint, TypeScript
typecheck, and the production build passed. Backend regression passed with 356
tests passing and 184 skipped; the opt-in PostgreSQL suite passed with 540
tests. `alembic check`, `pip check`, and `frontend/vercel.json` parsing passed.
The Git ignore audit confirmed local environment, build, dependency, cache, and
AppleDouble paths are ignored. The repository's current Git status shows all
project files as untracked baseline content, so the project owner must review
and intentionally stage the initial repository contents before any GitHub push.

### Problems Encountered

Render's free PostgreSQL tier currently expires after 30 days and lacks
backups, so it is not recommended for a persistent portfolio demo. No Render
or Vercel account was accessed in this planning step.

### What I Learned

Provider connection strings are configuration inputs, not domain data. A small
normalization boundary avoids forcing a hosting provider to emit a specific
SQLAlchemy dialect string while retaining a single explicit database driver in
the application.

### Next Step

Step 19B — Production Deployment. Recommended only; do not begin automatically.

## 2026-09-21 — Step 19B.1: GitHub Production Repository Preparation

### What Was Implemented

Audited the repository for public GitHub readiness without staging, committing,
pushing, or creating cloud resources. The README now has a concise portfolio
description, an accurate deployment-in-progress statement, and a screenshot
plan. Added `docs/screenshots/.gitkeep` so the planned screenshot directory is
available without inventing demo imagery.

### Files to Review

- `README.md`
- `docs/screenshots/.gitkeep`
- `.gitignore`
- `RECORD.md`

### Key Code to Understand

Git ignore rules protect local configuration and generated artifacts, while the
README deliberately separates completed capabilities from planned deployment.
The screenshot directory is a repository convention only; screenshots must be
captured from a verified deployment in a later step.

### Architecture Concept

Public repository readiness is a security and communication task: source and
reproducible configuration are included, while credentials, generated output,
and machine-specific metadata are excluded. Clear documentation prevents a
portfolio project from overstating its deployment status.

### How to Test

Run `git status`, `git ls-files`, the secret-keyword scan, and the complete
frontend/backend regression suite. Before the first GitHub push, inspect the
staged file list with `git diff --cached --name-only` and confirm local `.env`
files are absent.

### Verification

The secret audit found only the safe placeholders in `.env.example`; no
non-test source credential pattern was found. Git ignore checks confirmed
`.env`, frontend `.env`, dependencies, build output, caches, and AppleDouble
patterns are ignored. Frontend tests passed with 80 tests passing and 1
skipped; lint, TypeScript, and production build passed. Backend regression
passed with 356 tests passing and 184 skipped; Alembic and pip checks passed;
the opt-in PostgreSQL suite passed with 540 tests. `git diff` and
`git diff --cached` are empty because no project files have been staged yet.

### Problems Encountered

The current Git repository has no tracked project files; all project content
appears as untracked baseline content. A protected `._.git` AppleDouble file
also remains inside the Git metadata area, but it is ignored and cannot be
staged. The project owner must review the initial staged set rather than use a
blind bulk-add command.

### What I Learned

Git ignore rules only prevent future untracked additions; they do not replace a
staging review. A production repository needs both automated exclusions and a
human check of exactly what will become public.

### Next Step

Step 19B.2 — Push Repository to GitHub. Recommended only; do not begin automatically.
