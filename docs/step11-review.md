# Step 11 Review: Backend MVP Hardening & API Integration Readiness

Historical review: the later "Roadmap Migration - Web Frontend Decision" in
RECORD.md supersedes this review's HarmonyOS next-step recommendation.
The current next task is Step12, React + TypeScript Frontend Foundation
(NOT STARTED); see README.md and AGENT.md. Step11 facts, results and the
original decision context below are preserved.

Completed September 20, 2026 (America/New_York). Work began September19.
This is a backend-only hardening step; no new domain, migration, dependency,
Docker, deployment or HarmonyOS implementation.

## Completed

Added formal `/api/v1`, legacy compatibility, stable errors, centralized
environment/CORS settings, production startup validation, safe minimal logging,
readiness, OpenAPI/contract tests and client documentation. Found and fixed
an actual itinerary reorder response N+1 without changing the ordering rules.
Full default and PostgreSQL regressions and real Uvicorn HTTP smoke passed.

## Backend Audit

Read README, AGENT, RECORD, Step4-10 reviews and actual application, routers,
schemas, services, models and tests before implementation. Steps1-10 were
complete; Step10 had493 PostgreSQL tests and schema0005.

The pre-change inventory was derived from FastAPI APIRoute instances and
router source, not the proposed roadmap:26 operations,25 business plus health.
All protected operations used get_current_user. Explicit response models were
present except intentionally empty204 responses. Existing redacted validation
errors were `detail` lists, business errors were `detail` strings; no stable
client codes, version prefix, CORS policy or readiness endpoint existed.

Kept the modular monolith, synchronous SQLAlchemy sessions, current service
boundaries and test fixtures. No directory migration for aesthetics.

## OpenTrip Engineering Review

Reference repository: `https://github.com/stvlynn/OpenTrip.git`.
Actual remote HEAD was checked and matched the inspected checkout:
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`.
Evidence is pinned to that commit, not a claim about future repository changes.
Reference tests were read where relevant, not executed; no source was copied.

| Question / Area | Evidence from OpenTrip | TripTogether decision |
| --- | --- | --- |
| How is API organized? | `apps/api/src/interfaces/http/app.ts` uses Hono createApp, public/auth endpoints, guarded business router, application/domain/infrastructure layers | Keep small FastAPI routers -> services -> SQLAlchemy |
| Common prefix? | `app.route("/api", guard)`, `/api/auth/*`, `/api/health`; no v1 prefix in inspected organization | Explicit `/api/v1` for new mobile clients; retain old aliases |
| Errors? | `interfaces/http/errors.ts` maps known errors to status/code; unknown failures use safe500 and logging/capture | Explicit APIError code at router boundary, central render, generic safe500 |
| DTO/response? | `application/dto.ts` projects data; `interfaces/http/response.ts` uses `{data}` success and `{error:{code,message}}` failure | Keep existing Pydantic success shapes; adopt stable error envelope with field details |
| Authentication? | Better Auth getSession populates context; own auth paths bypass middleware; guarded routes require identity; cookie/native Bearer support | Keep verified PyJWT HS256 plus DB User lookup, not Better Auth |
| CORS? | Trusted origins, credentials enabled for cookie design in app.ts | Exact configured origins; Bearer-only design, credentials disabled |
| Environment/config? | `infrastructure/config.ts` loads supplied env into typed config; DB/auth secret/base URL/storage are required; trusted origins and observability environment configured; separate node/worker runtimes | Process env > root .env; explicit development/production validation with no new settings library |
| Logging? | `infrastructure/observability/core.ts` redacts sensitive keys/text/URLs, structured logger; HTTP middleware records request ID/method/route/status/duration | Minimal static safe messages; do not copy observability stack |
| Documentation? | `docs/backend/api/conventions.md` and route/platform docs are handwritten; no OpenAPI/Swagger generator found in searched API source/docs | FastAPI-generated OpenAPI with tested schemas/auth/tags/IDs |
| Health/deployment? | `/api/health` static response; session middleware precedes it, so do not infer end-to-end no-DB behavior. Node-server and Worker entry points; Node Dockerfile and Cloudflare config | Independent no-SQL health plus SELECT1 readiness; defer Docker/deployment |

Useful ideas: explicit HTTP boundary, DTO projection, stable codes, configuration
validation, trusted origins, safe logs and documented contracts. Unsuitable
for this MVP: replacing FastAPI/JWT with Hono/Better Auth, success-envelope
breaking changes, storage/agent infrastructure, Sentry/worker/node deployment
matrix or cookie CORS policy without a cookie authentication requirement.

Development/production in the reference is not inferred from a magic universal
NODE_ENV switch: configuration includes observability environment and separate
runtime entry points. TripTogether's APP_ENV policy is its own simpler choice.
The reference web fetch yielded no useful body; git checkout/remote inspection
provided the evidence.

## API Inventory

See api-inventory.md for full pre/post tables and framework routes.
Official27 operations: Auth3, Trips5, Members1, Invitations4, Itinerary6,
Expenses5, Balances1, System2. Runtime also keeps25 hidden legacy business
aliases, for52 API operations, plus four framework documentation paths.
No OAuth implementation is implied by FastAPI's docs/oauth2-redirect helper.

## API Versioning

`main.create_app` includes each original router without OpenAPI visibility and
includes the same router again through APIRouter(prefix="/api/v1"). This is
shared implementation, not duplicated business logic or mounted subapps.
It preserves dependency overrides and old tests/consumers.

Formal clients depend only on v1. Success schemas and business behavior did not
change. Legacy errors retain `{"detail": ...}`; v1 and `/ready` use the new
envelope. A future incompatible v2 can coexist while old clients migrate.
No removal date or complex version framework was invented.

## Error Contract

`APIError` subclasses HTTPException, carries a stable code and original detail.
The central handler chooses legacy or v1 output using the request path.
Codes are explicit at raise sites; registration duplicate codes derive from
the constrained field name, not a comparison with English error text.

| HTTP | Example |
| --- | --- |
| 401 | `{"error":{"code":"INVALID_CREDENTIALS","message":"Invalid or missing authentication credentials","details":[]}}` |
| 404 | `{"error":{"code":"TRIP_NOT_FOUND","message":"Trip not found","details":[]}}` |
| 409 | `{"error":{"code":"EMAIL_ALREADY_EXISTS","message":"Email already registered","details":[]}}` |
| 422 | `{"error":{"code":"VALIDATION_ERROR","message":"Request validation failed","details":[{"loc":["body","email"],"msg":"Field required","type":"missing"}]}}` |

503 uses the affected service's safe code, DATABASE_UNAVAILABLE for session
initialization, or NOT_READY for probe failure. Unexpected500 is INTERNAL_ERROR.
Framework v1 404/405 are also normalized. Validation retains loc/msg/type but
not raw input or ctx. Clients can identify fields without echoing passwords.
One VALIDATION_ERROR code avoids a huge validator-specific code enum.
Error responses are no-store and401 preserves WWW-Authenticate: Bearer.

Create201; successful reads/updates200; delete204 without body; invalid auth401;
hidden resources404; state conflict409; invalid input422; unavailable503.
Not every possible status needs a domain endpoint:403/400 are fallback mappings.
CORS preflight400 is transport middleware plaintext, not a business JSON error.

## Configuration

Central `core/config.py` retains actual existing names DATABASE_URL,
JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES. It adds APP_ENV and
CORS_ORIGINS, rather than renaming existing keys to the task's illustrative names.
Process variables override root .env; explicitly empty variables do not fallback.
AppSettings is a small frozen dataclass, no new settings dependency.

Development lets health/docs start without DB/JWT. Production startup validates
PostgreSQL URL shape and JWT configuration, fails with a generic message on
invalid config, and does not silently choose a default secret. This does not
test connectivity or run migrations. JWT remains HS256 only,1-1440minutes,
at least32 UTF-8 bytes, rejects blank/placeholder. Entropy is an operator duty.
`.env.example` contains only placeholders and descriptions; real .env unchanged.
Engine/factory caching means restart after changing database config.

## CORS

CORS_ORIGINS is a JSON list of exact HTTP(S) origins, default[].
Reject wildcard, credentials, paths, query, fragment, whitespace, bad ports
and malformed values; production requires HTTPS origins.
Allow GET/POST/PATCH/DELETE and Authorization/Content-Type; credentials=false.
Preflight max-age600. Allowed-origin headers also wrap safe500 responses.
Origin includes scheme/host/port: localhost and127.0.0.1 differ.
Native HarmonyOS HTTP is not subject to browser CORS; authorization still is.

## Logging

Python logging records startup, shutdown, service/readiness/session failure and
unexpected errors using static messages only. No formal server print logging;
the pre-existing CLI connectivity command deliberately prints command output.
Uvicorn raw access logging is disabled because even URLs may contain secrets.
No extra request logger or logging dependency was added.

SafeErrorMiddleware catches unhandled HTTP errors before the ASGI server logs
raw tracebacks; clients get safe500/503. It does not log the exception, body,
Authorization header, token, query string, password/hash or connection URL.
SQLAlchemy hide_parameters adds protection for parameter representations.
Tests inject sensitive exception/query/header values and assert no leakage in
application records or responses. This is scoped protection, not an audit of
all future third-party or deployment logs. Post-response/streaming failure
handling and diagnostic detail remain limitations.

## Health & Readiness

`GET /health`:200 `{"status":"ok"}`; no database/auth dependency. It proves the
process can serve this endpoint, not every business operation is available.

`GET /ready`: validates JWT configuration and executes SELECT1 through the
request Session. Success200 `{"status":"ready"}`, failures503 safe envelope,
no-store. Failed query rolls back. It does not create business rows, validate
schema revision or prove database write permissions. DB/session factory errors
are also contained. Connect/pool waits are bounded to five seconds each;
there is no global statement/lock timeout.

## OpenAPI

`/openapi.json` and `/docs` remain public and generate successfully.
Explicit tags:auth,trips,invitations,itinerary,expenses,balances,system;
members remain under trips. Summaries use tag plus readable operation name.
All27 operation IDs are unique; all23 protected operations show BearerAuth.
Response models remain explicit (except204), v1 error models are
APIErrorResponse, shared description documents prefix/auth/money/error policy.
Legacy aliases are hidden to prevent client generators choosing old paths.
Four old tests' OpenAPI path assertions were migrated to v1; runtime legacy
success/error tests were retained, not weakened to accept both shapes.

## Authentication Audit

All23 protected v1 operations use get_current_user. Tokens are verified for
signature/expiry/valid subject before database lookup; the current User must
exist. No owner/user ID from the request replaces authenticated identity.
Registration and login alone are public business operations.

Argon2id password hashing/verification, dummy hash for missing email, generic
login credential error, strict HS256 and exp/sub checks remain unchanged.
Public UserResponse excludes password_hash; password SecretStr/input redaction
and response schemas protect the serialization boundary.
The token is a signed credential, not encrypted storage or revocable session.
No refresh/logout/reset feature was added.

## Authorization Matrix

See authorization-matrix.md. Owner and accepted Member read Trip, members,
itinerary, expenses and balances; either edits shared itinerary/expenses.
Only Owner patches/deletes Trip or invites. Invitation decisions belong to
the recipient, not the owner. Pending does not confer membership.
Wrong/missing resource IDs yield the same404; anonymous gets401.
Member email visibility is documented existing policy.

Existing role and cross-Trip tests remain; the new all-protected-route loop
closes a route-registration coverage gap. A real v1 workflow verifies pending/
outsider/recipient/owner/member boundaries through the formal prefix.

## Transaction Audit

| Operation | Existing boundary and verification |
| --- | --- |
| Registration | Insert one user, commit once; pre-check plus named UNIQUE constraints handle races; failures rollback |
| Trip create | Trip and owner membership committed together |
| Invitation accept | Lock parent Trip then invitation, insert membership + set status/responded_at in one transaction |
| Itinerary reorder | Lock parent, validate complete day set, two-phase position flush, one commit; failure rolls back both phases |
| Expense create | Lock parent, validate participants/currency, expense+exact splits in one transaction |
| Expense update | Delete/flush old splits then insert replacements and snapshot response before one commit |
| Balance read | Read-only single statement snapshot, no lock/commit/business write |

Engine and sessionmaker are cached factories, not a global Session. Each
request gets one Session through get_db; FastAPI caches the shared dependency
within that request. Services explicitly commit writes and rollback handled
failures. Closing the dependency's context releases the connection and rolls
back uncommitted work on other failures. The dependency never auto-commits.
Earlier rollback/race tests all still pass; no broad service rewrite.

## Query / N+1 Audit

Collection SELECT counts including current-user lookup:

| Operation | Count | Observation |
| --- | --- | --- |
| Trips list | 2 | SQL owner/EXISTS member filter; no per-row query |
| Members list | 3 | User + authorized Trip + joined member query |
| Itinerary list | 3 | User + authorized Trip + ordered items |
| Expenses list | 3 | User + authorized Trip + joined expenses/splits |
| Balances | 2 | User + complete CTE aggregation/snapshot |
| Reorder response | 4 | User + locked Trip + day + bulk final snapshot |

The new collection test adds1 and10 itinerary/expense records; it does not
pretend to vary every other collection size. Existing Step10 tests separately
verify balance counts with2 and10 members. Query counts are a sanity check,
not a throughput benchmark or proof that unbounded results are cheap.

Actual issue: reorder returned ORM rows after commit. Serializing10 items
triggered13 SELECTs because commit expires rows. An initial pre-commit DTO
fix worked for no-op reorder, but changed order still produced13 SELECTs:
server-generated updated_at values expired after UPDATE and refreshed per row.

Final fix: one ordered SELECT with populate_existing under the same Trip lock,
build detached Pydantic response snapshots, then commit and return. Both
unchanged and reversed10-item reorder now use4 SELECTs. Position validation,
flush sequence, timestamp/no-op semantics and transaction boundaries stay intact.
There are still O(n) writes for n reordered rows; that is not this SELECT bug.
Expense splitting, balances and settlement algorithms were not modified.

Pagination is deferred to avoid a client-contract expansion: Trip/invitation/
expense lists are early candidates, with member/itinerary bounds later. Reorder
requires a whole day and balances a whole ledger, regardless of display pages.

## Security Audit

Reviewed password/hash/token/secret occurrences, dependency chains, SQL
construction, public response schemas, logs, .env/.gitignore and constraints.
ORM binds values; no client-provided SQL fragments are interpolated.
Only whitelisted validated request fields become updates; response models
prevent unintended ORM attribute serialization. Financial values remain exact.

Implemented protections: Argon2id, signed expiring JWT, membership/owner checks,
hidden404, typed validation, safe exception mapping, restricted CORS, no
default production secret, no sensitive request logging and parameter hiding.
The claim is **MVP security hardening completed for the implemented threat
surface**, not production secure. See known-limitations.md for abuse,
revocation, account enumeration, deployment and logging limitations.

## Client Integration Readiness

The backend contract is ready for a client foundation. client-integration.md
covers centralized base URL, token acquisition/header, secure handling,
expiration without refresh, no blind write retries, money strings, calendar
dates versus timestamp/time, PATCH omission/null, role rules and full flow.

HarmonyOS still needs its project, transport layer, storage, typed contracts
and screens. Device loopback is not the host Mac; choose its LAN address or
documented emulator bridge and configure once. This step did not configure a
phone/emulator or implement ArkTS/ArkUI.

## Documentation

- README.md: concise what/architecture/features/stack/setup/env/migration/run/
  tests/docs/status entry point with two simple Mermaid diagrams.
- docs/api-inventory.md: pre-change26 and final27 operations, aliases,
  documentation paths, errors.
- docs/authorization-matrix.md: all actual role/recipient rules and evidence.
- docs/client-integration.md: formal consumer contract and manual steps.
- docs/known-limitations.md: real gaps, not features silently added now.
- docs/step11-review.md: this full audit and learning guide.
- docs/legacy-development-guide.md: archived original README with historical
  warning, preserving walkthroughs without presenting old roadmap as current.
- RECORD.md: dated entry in AGENT's exact eight-part structure.

### Code and Test Files Changed

| Files | Purpose |
| --- | --- |
| backend/app/main.py | App factory/lifespan, dual routing, OpenAPI metadata and middleware |
| backend/app/core/config.py | APP_ENV/CORS validation and blank-secret rejection |
| backend/app/core/logging.py (new) | Safe minimal logging and unexpected-error boundary |
| backend/app/api/errors.py | APIError, envelope schemas, central legacy/v1 rendering |
| backend/app/api/system.py (new) | Health/readiness routers and response models |
| backend/app/api/dependencies.py | Stable auth error codes, same identity dependency |
| backend/app/api/auth.py, trips.py, invitations.py, itinerary.py, expenses.py, balances.py | Explicit business error codes, unchanged success contracts |
| backend/app/db/session.py | Safe initialization failure, pool timeout, hidden SQL parameters |
| backend/app/services/registration.py | Stable duplicate field/code with legacy message preserved |
| backend/app/services/itinerary.py | Bulk final reorder snapshot fix |
| backend/tests/test_api_contract.py (new) | Formal contract, auth coverage, OpenAPI and safe errors |
| backend/tests/test_app_hardening.py (new) | Configuration, CORS, logging, startup and readiness |
| backend/tests/test_query_audit.py (new) | Collection/reorder query-count regression |
| backend/tests/test_authentication.py, test_registration.py, test_trips.py, test_balances.py | Four existing OpenAPI assertions use formal paths |
| .env.example, .gitignore | Placeholder descriptions, CORS/env defaults, coverage ignores |
| backend/requirements.txt | Comment clarification only; no dependency added/removed |

All direct dependencies remain used: FastAPI/Pydantic, Uvicorn,
SQLAlchemy/psycopg, python-dotenv, Alembic, email-validator, argon2-cffi, PyJWT,
pytest/httpx. No unused direct dependency was confirmed, so none was removed.
No models, schema definition files, migrations or AGENT rules changed.

## Tests

Actual completed full runs, no failures hidden:

| Mode | Passed | Skipped | Failed |
| --- | ---: | ---: | ---: |
| `python -m pytest -q` | 354 | 184 | 0 |
| `RUN_POSTGRES_TESTS=1 python -m pytest -q` | 538 | 0 | 0 |

Relative to Step10:45 new cases (39 default,6 PostgreSQL). Existing tests still
cover auth/roles/migrations/ordering/invitation races/expense splits/balance
conservation and snapshots. No SQLite replacement.

New coverage includes27 unique documented operations, all23 protected routes
reject anonymous before DB access, real v1 workflow, success shapes,
timezone-aware timestamps, exact money strings, redacted422, stable
401/404/405/409/422/500/503, rollback, CORS allowed/denied origins/methods and
headers, production startup, readiness success/failure, log redaction and
reorder no-op/changed-order query counts.

Other actual checks: SELECT1 passed; Alembic0005(head); no new upgrade
operations; pip check: no broken requirements. All five migration SHA256 values
match the prior step. Local .env and OS metadata remain ignored and unchanged.

The reference project's tests were not run. No load, penetration, real
HarmonyOS-device or interactive Swagger-browser test is claimed.

## Manual Verification

From the configured backend environment:

```bash
python -m app.db.check
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -m uvicorn app.main:app --reload
```

Follow client-integration.md's curl probes and Swagger flow, supplying actual
returned IDs, not hardcoded examples. Default tests do not require PostgreSQL;
manual business operations and RUN_POSTGRES_TESTS=1 do.

Actual verification used a real Uvicorn reloader at127.0.0.1:8021, a random
process-only JWT secret, localhost:3000 CORS and existing PostgreSQL17.
The temporary script `/private/tmp/triptogether-step11-verify.py` sent HTTP
requests, not TestClient calls. It is diagnostic material outside the repo,
not a required installed tool.

Observed:

- health200ok, ready200ready, docs200, openapi200 and27 official operations.
- Allowed preflight200 with exact origin/no credentials; denied origin400.
- Anonymous trips401; two register201/login200/me200 pairs.
- Trip create201; Bob before acceptance404; invitation201, inbox200,
  accept200, repeat accept409; member list200.
- Member itinerary create201; numeric expense amount422; exact-string expense201.
- USD120 split60/60; balances+60/-60 and Bob->Alice60 suggestion200.
- Legacy balance response matched v1 success; Trip delete204 and later read404.
- Exact-ID cleanup restored all seven business-table counts from0 to0.
  No sequences reset, no user data broadly deleted, no .env/token output.
- Temporary server stopped; startup and shutdown log messages observed with no
  raw access URLs or credential-bearing traces.

Unavailable DB/readiness503, config failure503 and unexpected500 were exercised
by injected automated tests; no outage of the user's running PostgreSQL server
was induced. This distinction avoids claiming a manual outage test occurred.

## Important Code

Read these ten files in order. Paths are repository-relative; line numbers
refer to the Step11 implementation, not a future immutable API.

| File / Entry | What to understand and why |
| --- | --- |
| backend/app/main.py:26,42 | lifespan validates production; create_app reuses routers and wires CORS outside safe errors. This is composition, not business logic |
| backend/app/core/config.py:16,50,78 | Environment precedence, JWT checks and exact-origin validation; avoid hidden defaults and scattered getenv |
| backend/app/api/errors.py:45,58,80 | Error carries code; one serializer selects legacy/v1; validation keeps field/reason without input |
| backend/app/core/logging.py:13,20 | Static logging and ASGI response boundary prevent raw credential-bearing exception logs |
| backend/app/api/dependencies.py:28,42 | Signature/expiry first, User lookup second; reusable authentication for every protected route |
| backend/app/db/session.py:12,23,31 | Reusable Engine/factory, request-local Session and deterministic close; dependency does not commit |
| backend/app/api/system.py:29,36 | Health is independent; readiness consumes a real DB session and safely reports503 |
| backend/app/services/trips.py:40,64,71 | Owner versus membership predicates are authorization, separate from JWT identity |
| backend/app/services/itinerary.py:148 | Lock, full-day validation, bulk refresh and DTO before commit fix the actual N+1 |
| backend/tests/test_api_contract.py:39,71,118 | Assert published contract, every protected operation and full client-visible workflow |

## Concepts to Understand

1. **API Contract:** agreed paths, status, JSON fields/types, auth and error
   semantics. Here money strings and204-empty are as important as endpoint names.
2. **API Versioning:** `/api/v1` names the contract a shipped client consumes.
   Future incompatible v2 can coexist; internal refactors can stay in v1.
3. **CORS:** a browser decides whether JavaScript may read a cross-origin
   response. Our allowlist is not a login system or native-device firewall.
4. **Dependency Injection:** FastAPI calls get_current_user/get_db for the
   endpoint, caches dependencies within the request and closes yielded resources
   afterward. Endpoints receive a validated User and request-local Session.
5. **Authentication vs Authorization:** JWT answers who; SQL owner/member
   predicates answer whether that person can act on this Trip.
6. **HTTP Status Code:** coarse outcome category:201 created,204 no body,
   401 credentials,404 missing/hidden,409 conflict,422 invalid input,503 unavailable.
7. **Error Code:** stable application cause such as EXPENSE_CURRENCY_CONFLICT;
   clients do not branch on localized English wording.
8. **Liveness:** `/health` says the process serves requests. It deliberately
   stays200 during DB outage to avoid confusing dependency failure with death.
9. **Readiness:** `/ready` says required basic JWT/DB checks pass now; an
   orchestrator could withhold traffic on503. It is not a complete health proof.
10. **OpenAPI:** FastAPI derives the machine-readable specification from route
    metadata, Pydantic models and dependencies; tests catch drift and ID conflicts.
11. **N+1 Query:** a list operation silently queries once per row. Our reorder
    regression caught10 refresh SELECTs; one bulk snapshot fixes that.
12. **Transaction Boundary:** the set of changes that commit or rollback
    together. Invitation accept cannot persist a member without its decision;
    expense update cannot leave half-replaced splits.
13. **Environment Configuration:** host, secret and browser-origin policy vary
    by deployment without edits to business code. Process env overrides root.env.
14. **Secret Management:** .env is local/private, .env.example teaches names
    without real values, logs avoid secrets, and production validates presence.
    Generation, storage, access and rotation are still operator responsibilities.

## Interview Questions

1. **Why version this API?** A HarmonyOS build may remain installed after the
   backend changes. `/api/v1` fixes its contract; a future v2 can coexist.
2. **What is this project's API contract?** Paths/methods, JWT requirement,
   status, response fields, decimal strings, dates and error envelope, asserted
   in test_api_contract.py and described in the client guide.
3. **How are errors kept consistent?** APIError supplies stable code/detail;
   centralized HTTP/validation handlers render APIErrorResponse for v1; safe
   middleware catches otherwise unhandled HTTP failures.
4. **Why machine-readable codes?** A client can handle EMAIL_ALREADY_EXISTS
   without comparing "Email already registered" or depending on translation.
5. **What is CORS?** Browser cross-origin response-access policy; our middleware
   allows only configured exact origins and explicit methods/headers.
6. **Why avoid unrestricted production CORS?** It unnecessarily grants arbitrary
   browser sites response access. We use exact HTTPS origins and no credentialed
   cookie mode; authorization is still mandatory.
7. **Liveness versus readiness?** Health proves request handling; readiness
   additionally validates JWT config and executes SELECT1 through PostgreSQL.
8. **Why not query PostgreSQL in health?** A dependency outage should produce
   not-ready, not label an otherwise running process dead; health stays cheap.
9. **How does FastAPI generate OpenAPI?** From route methods/status/metadata,
   response/input models and security dependencies. Our tests assert27 operations,
   unique operation IDs and23 Bearer-protected operations.
10. **How does JWT work here?** Login verifies Argon2id, signs string sub plus
    UTC exp using configured HS256; subsequent requests verify claims then load
    the User. Missing/tampered/expired tokens return401.
11. **Authentication versus authorization?** get_current_user identifies Alice;
    get_owned_trip/accessible_to decides whether Alice can edit or read this Trip.
12. **How prevent unauthorized Trip access?** Filter by owner or EXISTS accepted
    member in SQL; owner-only mutations use the stricter predicate. Hidden and
    missing resources both return404; pending invitations grant nothing.
13. **How manage environment-specific configuration?** One config module reads
    process env first, root.env second; APP_ENV controls production checks,
    CORS_ORIGINS varies without changing routers.
14. **How protect secrets?** Ignore.env, ship placeholder example, validate JWT
    configuration, avoid raw exception/body/header logs and require operational
    HTTPS/random stable keys. Length checks cannot prove randomness.
15. **How do Sessions map to requests?** get_db yields one Session; Engine and
    sessionmaker are reusable, but the Session is not shared globally. Its
    context closes on success or failure.
16. **How does rollback work?** Services catch known domain/SQL failures and
    rollback; dependency close also rolls back uncommitted work. Multi-row
    operations commit once, and race/failure tests check atomicity.
17. **What actual N+1 did you find?** Reorder serialized expired ORM rows and
    expired updated_at attributes. Ten rows caused13 SELECTs; bulk refresh and
    detached response snapshot make it4, including authentication.
18. **How did you test the client contract?** OpenAPI assertions, all-protected
    route auth loop, errors401/404/409/422/503 and a real PostgreSQL v1 workflow
    checking exact fields, money strings, timestamps and role behavior.
19. **Why serialize money as strings?** It preserves exact decimal representation
    across language JSON runtimes. Stored Decimal splits, not binary float or
    repeated client division, determine balances.
20. **What remains before production?** Deployment HTTPS/secrets/backups,
    resource/abuse limits, reproducible dependency review, bounded lists and
    operational monitoring; no claim that Step11 alone solves those.
21. **Why keep old paths?** Existing tests/consumers use them. Shared router
    registration preserves legacy behavior while OpenAPI exposes only the new
    contract. There is no silent switch of old error shapes.
22. **Does constant query count mean scalable?** No. A two-query balance endpoint
    can still scan a large ledger. Count regression removes obvious N+1, not
    result-size, CPU or lock-wait limits.
23. **Can clients retry expense POST after timeout?** Not blindly: it may already
    have committed. There are no idempotency keys; reconcile state first.
24. **Why not copy OpenTrip's CORS/auth stack?** Its Better Auth cookie/runtime
    choices justify credentialed CORS; our small Bearer FastAPI backend has
    different requirements and existing tested authentication.

## Known Limitations

See known-limitations.md. No refresh/revocation/reset/email verification/rate
limits/realtime/pagination/member leave/FX/payments. LWW remains. Native client
and deployment are not implemented. Readiness is connectivity/configuration,
not schema/capacity validation. Logs trade diagnostics for safe minimalism.
These limitations were recorded, not implemented under the name of hardening.

## Problems Encountered

- Four initial OpenAPI assertions used legacy paths; they failed after formal
  docs moved to v1. Updated only those assertions, preserving compatibility tests.
- Reorder query regression failed13 versus expected3. A DTO-before-commit fix
  passed the no-op test but still failed changed-order due to updated_at refresh.
  Bulk final read solved both; final explicit budget is4.
- Reference web fetch returned no useful content; checked actual git reference
  instead. No unsupported claim about reference tests or API documentation.
- pip's cache directory was not writable; pip check still completed and reported
  no broken requirements. No permission change or sudo installation was needed.
- Repository is fully untracked, so no reliable git baseline diff exists.
  Changes were kept scoped from source inspection; no commit/reset performed.
- Local DB/network needed sandbox approval. All final checks completed; no
  remaining blocker. Existing AppleDouble hazard is documented, not a newly
  observed Step11 migration failure.

## RECORD.md

Updated using the exact AGENT sections: What Was Implemented, Files to Review,
Key Code to Understand, Architecture Concept, How to Test, Problems Encountered,
What I Learned, Next Step. Dates and results reflect completed checks, not plans.

## Next Step

**Step 12 - HarmonyOS Client Foundation.**
Recommended only; not started.
