# Client Integration Guide

Current client: React + TypeScript + Vite foundation, authentication, Trip
management, collaboration/itinerary and Step16 expense/balance UI.
Steps17-20 are not started.
The web-first roadmap supersedes the earlier HarmonyOS plan without
changing the Step11 API contract or backend behavior.

## Base URL

Formal business base URL in local development:
`http://127.0.0.1:8000/api/v1`.
Use relative paths such as `/auth/login` and `/trips` against that base.
System probes and documentation are outside it:
`http://127.0.0.1:8000/health`, `/ready`, `/docs`, `/openapi.json`.

Step12 configures `VITE_API_BASE_URL` as the backend origin (without `/api/v1`).
Its health adapter uses `/health`; future business adapters pass `/api/v1/...`.
The relative business paths below describe the API contract, not direct arguments
to the current origin-based `apiFetch`. Do not hardcode addresses in
screens. The centralized `frontend/src/api/` client handles transport;
components should not each implement fetch/auth/error handling.
Browser-delivered environment values are public: never include database
credentials or JWT signing secrets. Use HTTPS for deployed credentials.

For cross-origin browser development, set backend CORS_ORIGINS to the actual
frontend origin, including scheme and port; localhost and127.0.0.1 differ.
The examples below use localhost:3000 only as an example, not a configured Vite
server. Step12 uses `http://127.0.0.1:5173`; configure that exact origin
as shown in README. No proxy bypasses browser CORS.
If testing a mobile-width browser on another device later, its loopback is not
the Mac: use a reachable LAN host on a trusted network and configure CORS for
that browser's actual origin. Native clients are deferred future work.

## Web Client Responsibilities

Step12 establishes the React/TypeScript/Vite foundation in `frontend/`;
Step13 implements authentication UI and API integration after deciding token
storage based on web security. Both are implemented; Step13 uses sessionStorage.
Use explicit request/response types, centralized API and authentication layers,
and Loading/Success/Empty/Error states. Prefer React state, Context and custom
hooks rather than an upfront global state library.

React handles interaction, form input and display; the backend remains the
authority for permissions, splitting, balances, settlement suggestions and
database consistency. Do not reproduce these calculations or access PostgreSQL
directly. Follow AGENT.md's responsive, accessibility and browser-verification
rules and README's current Step12-20 roadmap.

## API Contract and Versioning

Success payloads are the schema itself, not `{"data": ...}`. Lists are arrays;
DELETE succeeds with204 and no body. Do not try to JSON-decode204.
Create201, read/update200, invalid credentials401, hidden resources404,
conflicts409, validation422, unexpected failure500, unavailable503.
See api-inventory.md for all27 official operations and request/response models.

Only `/api/v1` is the client API. The25 unprefixed business routes retain legacy
success/status semantics and `detail` errors for compatibility, share the same
implementation, and are omitted from OpenAPI. No retirement date is set.
A future incompatible version can coexist under `/api/v2`; this step adds no
version framework and does not promise every internal change needs a new version.

## Authentication

Register with `POST /auth/register`:

```json
{"username":"alice","email":"alice@example.com","password":"a-disposable-test-password"}
```

Login with JSON (not form data) at `POST /auth/login`:

```json
{"email":"alice@example.com","password":"a-disposable-test-password"}
```

Login200 returns `{"access_token":"<token>","token_type":"bearer"}`.
Send `Authorization: Bearer <token>` on all protected requests. Do not include
the token in URLs, analytics or logs. `/auth/me` gives id/username/email/created_at,
never a hash. Registration creates the user but does not log in.

Passwords are preserved exactly; do not trim them. Registration accepts8-128
characters; login accepts1-128. Email is normalized to lowercase. Username is
trimmed, case-sensitive,1-50 ASCII letters/digits/underscore.

JWT expires (default30 minutes); there is no refresh endpoint. On401, stop
using the credential and ask for login. Local logout discards the token, not
server-side revocation. Step13 stores only the access token in sessionStorage;
restores identity through /me on reload and clears invalid sessions on401.
Transient restore failures retain the token but do not unlock protected pages.
Same-origin JavaScript/XSS can read sessionStorage; no production security claim.
Centralize token
access and Authorization injection rather than repeating them in each page.
No cookies are used. Swagger's Authorize field takes the raw token without
the `Bearer ` prefix. Do not print login responses in shared terminals.

## Error Handling

Every handled formal business error and `/ready` failure has:

```json
{"error":{"code":"TRIP_NOT_FOUND","message":"Trip not found","details":[]}}
```

Use status plus `error.code` for decisions, not English `message`. Unknown codes
should fall back to a generic message. `details` is always an array; each
validation issue contains `loc` (field path), `msg` (reason), `type` (validator
category). Raw input and validator context are intentionally omitted.

| HTTP | Example JSON |
| --- | --- |
| 401 | `{"error":{"code":"INVALID_CREDENTIALS","message":"Invalid or missing authentication credentials","details":[]}}` |
| 404 | `{"error":{"code":"TRIP_NOT_FOUND","message":"Trip not found","details":[]}}` |
| 409 | `{"error":{"code":"EMAIL_ALREADY_EXISTS","message":"Email already registered","details":[]}}` |
| 422 | `{"error":{"code":"VALIDATION_ERROR","message":"Request validation failed","details":[{"loc":["body","email"],"msg":"Field required","type":"missing"}]}}` |
| 503 | `{"error":{"code":"NOT_READY","message":"Application is not ready","details":[]}}` |

401 preserves `WWW-Authenticate: Bearer`. All handled errors use
`Cache-Control: no-store`. A member's owner-only request and an outsider's read
both return404, deliberately hiding the Trip. Do not distinguish them by
guessing IDs. For409, re-read relevant state before deciding what to do.
422 maps field errors; business validation may use `loc:["body"]`.
500/503 return safe messages, never SQL/credentials.

Also handle network errors, timeouts and non-JSON responses: proxies and CORS
preflight can fail before a business route. The planned web client is subject
to browser CORS when calling a different origin. Preflight is transport policy, not the JSON
business contract; denied preflight returns400 plaintext.

Do not automatically retry writes after a timeout: the transaction might have
committed even if the response was lost. Registration may then return409,
accept/reject repeats return409, and duplicate expense POST can double-record.
There are no idempotency keys. A bounded GET retry is safer; never retry401
indefinitely or treat503 as invalid credentials.

## Money

Send and receive decimal strings, for example `"amount":"120.00"`.
Responses use exactly two decimal places for amount/share_amount/paid/share/
balance and settlement amount. Integers and floating JSON numbers are rejected
for input amount. Maximum per expense:9999999999.99; positive, at most two
decimal places, no exponent or silent rounding.

Do not use binary floating point for client financial calculations. Display
server-calculated splits/balances; use a decimal library or integer minor units
only if client arithmetic is necessary. `100.00 / 3` is stored as33.34/33.33/33.33,
not three rounded33.33 values. Currency is a three-uppercase-letter code and
one current-ledger currency per Trip; there is no FX conversion.
An empty ledger returns currency null, zero member balances, no suggestions.

## Dates and PATCH

- Trip dates, itinerary date and expense_date use `YYYY-MM-DD`; these are
  calendar DATE values, not instants to shift through UTC.
- Itinerary time uses local `HH:MM:SS` (optional fractional seconds), no offset
  or timezone. Requests may use `HH:MM`. No overnight item; end needs start.
- created_at, updated_at, joined_at, responded_at are timezone-aware ISO8601
  timestamps. Accept `Z` or an explicit offset; display in the desired timezone.
  responded_at is null until the invitation decision.
- Omitted PATCH fields retain their value. Trip/expense required fields reject
  explicit null. Itinerary location/notes can be cleared with null; time fields
  can also be cleared provided the resulting start/end pair remains valid.
- Unknown/server-controlled input fields are rejected. Never send owner_id,
  created_by_user_id, calculated balance, split amounts or timestamps.
- Empty/unchanged Trip/itinerary/expense PATCH is a no-op where implemented;
  concurrent same-field writes remain Last Write Wins, not conflict detection.

## Main Flow

The web client implements the first collaboration portion of this flow: after
login, open `/trips`, respond to invitations, open `/trips/{id}`, inspect
members, invite registered users as owner, and manage shared itinerary items.
The expense and balance screens now use the existing `/expenses` and
`/balances` API contracts. The browser displays server-calculated shares,
balances and settlement suggestions; it does not calculate money locally.

1. Register/login Alice and Bob; keep each token private.
2. Alice POSTs `/trips` with the following, saves its returned id:

```json
{"name":"Summer Trip","destination":"Tokyo","start_date":"2027-06-10","end_date":"2027-06-15"}
```

3. Alice POSTs `/trips/{id}/invitations` with `{"email":"bob@example.com"}`.
   Bob GETs `/invitations` and POSTs `/invitations/{invitation_id}/accept`.
   Pending invitation alone grants no access. Use reject instead to decline.
4. Both GET `/trips/{id}/members`; member `user_id` values identify payer and
   split participants. Only the owner can edit/delete Trip metadata or invite.
5. Either POSTs `/trips/{id}/itinerary`:

```json
{"title":"Temple","date":"2027-06-10","start_time":"09:30","notes":"Meet outside"}
```

6. GET itinerary returns date/position order. PATCH `/itinerary/reorder` requires
   a date and all that day's item_ids exactly once, not a partial visible page.
7. Either POSTs `/trips/{id}/expenses`, replacing1/2 with real member IDs:

```json
{"description":"Dinner","amount":"120.00","currency":"USD","paid_by_user_id":1,"participant_user_ids":[1,2],"expense_date":"2027-05-01"}
```

8. GET `/trips/{id}/balances`: payer+60.00, other participant-60.00; suggestion
   other->payer60.00. Positive means should receive; negative means owes.
   These are suggestions, not payments or a mark-as-paid workflow.
9. Refresh after writes; no push updates. An accepted member can edit/delete
   any shared itinerary/expense, regardless of creator.

## Local Verification

From backend with configured PostgreSQL and JWT:

```bash
python -m app.db.check
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

In another terminal:

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
curl -i http://127.0.0.1:8000/api/v1/auth/me
curl -i -X OPTIONS http://127.0.0.1:8000/api/v1/trips \
  -H 'Origin: http://localhost:3000' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: Authorization,Content-Type'
```

Expect200ok,200ready,401 envelope respectively. Preflight200 with matching
Allow-Origin requires configuring `CORS_ORIGINS=["http://localhost:3000"]` and
restarting; by default all cross-origin origins are denied. No credentials
header is emitted. An unlisted origin gets400 and no Allow-Origin.

Open `/docs`, follow the flow above with disposable accounts and retain IDs
for cleanup. Do not run broad DELETE statements against existing data.
Manual API requests commit to the development database; tests use isolated
PostgreSQL schemas. To simulate outage without stopping shared PostgreSQL,
start a separate development server with DATABASE_URL pointing to a known
unused local port: health stays200, ready returns503. Restore config afterward.
