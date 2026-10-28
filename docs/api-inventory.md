# API Inventory

## Pre-change Audit

Step 11 implementation前，直接遍历实际 FastAPI APIRoute 并阅读所有 router：
26个业务/系统操作（25个业务 + GET /health），没有 `/api/v1`、CORS 或 readiness。
除 register/login/health 外均使用 get_current_user；删除成功204无body，
其他成功均有明确response_model。以下是审查时的完整路径，不凭路线图推测。

| Method | Existing Path | Auth | Role | Request | Response | Main Errors |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /health | No | Public | None | 200 HealthResponse | None |
| POST | /auth/register | No | Public | UserRegister | 201 UserResponse | 409,422,429,503 |
| POST | /auth/login | No | Public | UserLogin | 200 TokenResponse | 401,422,429,503 |
| GET | /auth/me | JWT | Current user | None | 200 UserResponse | 401,503 |
| POST | /trips | JWT | Any user | TripCreate | 201 TripResponse | 401,422,503 |
| GET | /trips | JWT | Owned/joined only | None | 200 TripResponse[] | 401,503 |
| GET | /trips/{trip_id} | JWT | Owner/Member | None | 200 TripResponse | 401,404,422,503 |
| PATCH | /trips/{trip_id} | JWT | Owner | TripUpdate | 200 TripResponse | 401,404,409,422,503 |
| DELETE | /trips/{trip_id} | JWT | Owner | None | 204 empty | 401,404,422,503 |
| GET | /trips/{trip_id}/members | JWT | Owner/Member | None | 200 TripMemberResponse[] | 401,404,422,503 |
| POST | /trips/{trip_id}/invitations | JWT | Owner | InvitationCreate | 201 InvitationResponse | 401,404,409,422,503 |
| GET | /invitations | JWT | Recipient's inbox | None | 200 InvitationResponse[] | 401,503 |
| POST | /invitations/{invitation_id}/accept | JWT | Recipient | None | 200 InvitationResponse | 401,404,409,422,503 |
| POST | /invitations/{invitation_id}/reject | JWT | Recipient | None | 200 InvitationResponse | 401,404,409,422,503 |
| POST | /trips/{trip_id}/itinerary | JWT | Owner/Member | ItineraryItemCreate | 201 ItineraryItemResponse | 401,404,422,503 |
| GET | /trips/{trip_id}/itinerary | JWT | Owner/Member | None | 200 ItineraryItemResponse[] | 401,404,422,503 |
| GET | /trips/{trip_id}/itinerary/{item_id} | JWT | Owner/Member | None | 200 ItineraryItemResponse | 401,404,422,503 |
| PATCH | /trips/{trip_id}/itinerary/{item_id} | JWT | Owner/Member | ItineraryItemUpdate | 200 ItineraryItemResponse | 401,404,422,503 |
| DELETE | /trips/{trip_id}/itinerary/{item_id} | JWT | Owner/Member | None | 204 empty | 401,404,422,503 |
| PATCH | /trips/{trip_id}/itinerary/reorder | JWT | Owner/Member | ItineraryReorderRequest | 200 ItineraryItemResponse[] | 401,404,409,422,503 |
| POST | /trips/{trip_id}/expenses | JWT | Owner/Member | ExpenseCreate | 201 ExpenseResponse | 401,404,409,422,503 |
| GET | /trips/{trip_id}/expenses | JWT | Owner/Member | None | 200 ExpenseResponse[] | 401,404,422,503 |
| GET | /trips/{trip_id}/expenses/{expense_id} | JWT | Owner/Member | None | 200 ExpenseResponse | 401,404,422,503 |
| PATCH | /trips/{trip_id}/expenses/{expense_id} | JWT | Owner/Member | ExpenseUpdate | 200 ExpenseResponse | 401,404,409,422,503 |
| DELETE | /trips/{trip_id}/expenses/{expense_id} | JWT | Owner/Member | None | 204 empty | 401,404,422,503 |
| GET | /trips/{trip_id}/balances | JWT | Owner/Member | None | 200 BalanceResponse | 401,404,409,422,503 |

Documentation routes also existed: GET /openapi.json, /docs, /docs/oauth2-redirect,
/redoc (public framework documentation, not business APIs).

All request/response type names above refer to actual Pydantic schemas.
Pending invitations do not confer membership. Invitation response permission
is recipient identity, not a Trip role. Forbidden resources remain hidden404.

## Official Client API After Step 11

40 documented operations: Auth7, Trips5, Members1, Invitations4, Itinerary8,
Expenses5, Balances1, Places5, Geocoding1, Events1, System2. Counts are method/path pairs, not distinct URLs.
All official success schemas retain their original fields. All listed errors
use APIErrorResponse; generic unexpected500 and infrastructure503 can occur on
business operations. Framework unknown-path404 and wrong-method405 use the
same envelope inside `/api/v1`.

| Method | Path | Auth | Role | Request | Response | Main Errors |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /health | No | Public | None | 200 HealthResponse | None |
| GET | /ready | No | Public | None | 200 ReadinessResponse | 503 |
| POST | /api/v1/auth/register | No | Public | UserRegister | 201 UserResponse | 409,422,429,503 |
| POST | /api/v1/auth/login | No | Public | UserLogin | 200 TokenResponse (access + refresh) | 401,422,429,503 |
| POST | /api/v1/auth/refresh | No | Public | RefreshRequest | 200 TokenResponse (rotated pair) | 401,422,429,503 |
| POST | /api/v1/auth/logout | No | Public | RefreshRequest | 204 empty | 422,503 |
| POST | /api/v1/auth/password/forgot | No | Public | ForgotPasswordRequest | 202 `{status: accepted}` | 422,429,503 |
| POST | /api/v1/auth/password/reset | No | Public | ResetPasswordRequest | 204 empty | 400,422,429,503 |
| GET | /api/v1/auth/me | JWT | Current user | None | 200 UserResponse | 401,503 |
| POST | /api/v1/trips | JWT | Any user | TripCreate | 201 TripResponse | 401,422,503 |
| GET | /api/v1/trips | JWT | Owned/joined only | None | 200 TripResponse[] | 401,503 |
| GET | /api/v1/trips/{trip_id} | JWT | Owner/Member | None | 200 TripResponse | 401,404,422,503 |
| PATCH | /api/v1/trips/{trip_id} | JWT | Owner | TripUpdate | 200 TripResponse | 401,404,409,412,422,503 |
| DELETE | /api/v1/trips/{trip_id} | JWT | Owner | None | 204 empty | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/members | JWT | Owner/Member | None | 200 TripMemberResponse[] | 401,404,422,503 |
| POST | /api/v1/trips/{trip_id}/invitations | JWT | Owner | InvitationCreate | 201 InvitationResponse | 401,404,409,422,503 |
| GET | /api/v1/invitations | JWT | Recipient's inbox | None | 200 InvitationResponse[] | 401,503 |
| POST | /api/v1/invitations/{invitation_id}/accept | JWT | Recipient | None | 200 InvitationResponse | 401,404,409,422,503 |
| POST | /api/v1/invitations/{invitation_id}/reject | JWT | Recipient | None | 200 InvitationResponse | 401,404,409,422,503 |
| POST | /api/v1/trips/{trip_id}/itinerary | JWT | Owner/Member | ItineraryItemCreate | 201 ItineraryItemResponse | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/itinerary | JWT | Owner/Member | None | 200 ItineraryItemResponse[] | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/itinerary/{item_id} | JWT | Owner/Member | None | 200 ItineraryItemResponse | 401,404,422,503 |
| PATCH | /api/v1/trips/{trip_id}/itinerary/{item_id} | JWT | Owner/Member | ItineraryItemUpdate | 200 ItineraryItemResponse | 401,404,412,422,503 |
| DELETE | /api/v1/trips/{trip_id}/itinerary/{item_id} | JWT | Owner/Member | None | 204 empty | 401,404,422,503 |
| PATCH | /api/v1/trips/{trip_id}/itinerary/reorder | JWT | Owner/Member | ItineraryReorderRequest | 200 ItineraryItemResponse[] | 401,404,409,422,503 |
| GET | /api/v1/trips/{trip_id}/itinerary/route?date= | JWT | Owner/Member | Query date | 200 RouteResponse | 401,404,422,503 |
| POST | /api/v1/trips/{trip_id}/itinerary/optimize | JWT | Owner/Member | ItineraryOptimizeRequest | 200 ItineraryOptimizeResponse | 401,404,422,503 |
| POST | /api/v1/trips/{trip_id}/expenses | JWT | Owner/Member | ExpenseCreate | 201 ExpenseResponse | 401,404,409,422,503 |
| GET | /api/v1/trips/{trip_id}/expenses | JWT | Owner/Member | None | 200 ExpenseResponse[] | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/expenses/{expense_id} | JWT | Owner/Member | None | 200 ExpenseResponse | 401,404,422,503 |
| PATCH | /api/v1/trips/{trip_id}/expenses/{expense_id} | JWT | Owner/Member | ExpenseUpdate | 200 ExpenseResponse | 401,404,409,412,422,503 |
| DELETE | /api/v1/trips/{trip_id}/expenses/{expense_id} | JWT | Owner/Member | None | 204 empty | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/balances | JWT | Owner/Member | None | 200 BalanceResponse | 401,404,409,422,503 |
| GET | /api/v1/trips/{trip_id}/events | JWT | Owner/Member | None | 200 text/event-stream | 401,404,422,503 |
| POST | /api/v1/trips/{trip_id}/places | JWT | Owner/Member | TripPlaceCreate | 201 TripPlaceResponse | 401,404,409,422,503 |
| GET | /api/v1/trips/{trip_id}/places | JWT | Owner/Member | None | 200 TripPlaceResponse[] | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/places/{place_id} | JWT | Owner/Member | None | 200 TripPlaceResponse | 401,404,422,503 |
| PATCH | /api/v1/trips/{trip_id}/places/{place_id} | JWT | Owner/Member | TripPlaceUpdate | 200 TripPlaceResponse | 401,404,412,422,503 |
| DELETE | /api/v1/trips/{trip_id}/places/{place_id} | JWT | Owner/Member | None | 204 empty | 401,404,422,503 |
| GET | /api/v1/geocode?q=&limit= | JWT | Any user | Query q (2-200), limit (1-10, default 5) | 200 GeocodeResultResponse[] | 401,422,429,503 |

Places (map P2) are versioned-only and have no legacy alias. Coordinates are
JSON numbers with at most six decimal places and are immutable after creation;
PATCH accepts only name, address and note. `proposed_by_user_id` is set from the
authenticated user. A saved search result sends `provider` (`nominatim`, or
`fake` in development) and
`provider_place_id` (`N|W|R` + OSM id) together; repeating one inside a Trip is
409 PLACE_DUPLICATE. `provider` must equal the running `GEOCODER_PROVIDER`
(only manual places when it is `disabled`); otherwise 422 with a
`["body","provider"]` reason. Error codes: PLACE_NOT_FOUND (404), PLACE_DUPLICATE (409),
PLACES_UNAVAILABLE (503). Geocoding codes: GEOCODER_BUSY (429, `Retry-After: 1`),
GEOCODER_DISABLED and GEOCODER_UNAVAILABLE (503). CORS exposes `Retry-After`
(`expose_headers`) so a cross-origin browser client can read the delay.

Map P4: itinerary create/update accept optional `place_id` (same Trip only,
else 422; null unlinks) and responses include `place_id` on both v1 and legacy
paths. `route` and `optimize` are versioned-only and read-only. Reorder accepts
optional `expected_item_ids`; if the current order differs from it (and from
the target), the response is 409 ITINERARY_CONFLICT. Omitting it keeps the
previous behavior exactly. PATCH switching `place_id` to a different place
without sending `location` refreshes `location` to the new place name (P5.0).
The web client (P5) uses every endpoint above; no new endpoint was added.

## Compatibility and Documentation Routes

Every business row in the pre-change table remains reachable without `/api/v1`,
with identical role/request/success rules and legacy `{"detail": ...}` errors.
There are25 such hidden aliases, not a second set of business logic.
Runtime has60 API operations (35 official +25 legacy) and four framework
documentation routes; `/health` is not duplicated. No `/api/v1/health` alias.
There is no `/readiness`; the selected path is `/ready`.

| Method | Path | Auth | Role | Request | Response | Main Errors |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /openapi.json | No | Public | None | 200 OpenAPI JSON | Generic framework failure |
| GET | /docs | No | Public | None | 200 Swagger HTML | Generic framework failure |
| GET | /docs/oauth2-redirect | No | Public | None | 200 helper HTML | Generic framework failure |
| GET | /redoc | No | Public | None | 200 ReDoc HTML | Generic framework failure |

Framework documentation routes also accept HEAD. The OAuth2 redirect helper
is installed by FastAPI; it does not mean TripTogether implements OAuth.
CORS middleware can answer OPTIONS preflight independently of operation paths.
Do not count preflight, automatic slash redirects or HEAD as new business APIs.

## Stable Error Codes

| Status | Codes |
| --- | --- |
| 400 | INVALID_RESET_TOKEN, BAD_REQUEST (fallback) |
| 401 | INVALID_CREDENTIALS, INVALID_REFRESH_TOKEN |
| 403 | FORBIDDEN (fallback; resource policy currently uses404) |
| 404 | TRIP_NOT_FOUND, INVITATION_NOT_FOUND, INVITEE_NOT_FOUND, ITINERARY_NOT_FOUND, EXPENSE_NOT_FOUND, NOT_FOUND |
| 405 | METHOD_NOT_ALLOWED |
| 409 | USERNAME_ALREADY_EXISTS, EMAIL_ALREADY_EXISTS, TRIP_ITINERARY_CONFLICT, INVITATION_CONFLICT, EXPENSE_CURRENCY_CONFLICT, LEDGER_INCONSISTENT |
| 422 | VALIDATION_ERROR |
| 429 | RATE_LIMITED (`Retry-After` seconds), GEOCODER_BUSY |
| 500 | INTERNAL_ERROR |
| 503 | PASSWORD_RESET_UNAVAILABLE, RATE_LIMITER_UNAVAILABLE, REGISTRATION_UNAVAILABLE, AUTHENTICATION_UNAVAILABLE, TRIPS_UNAVAILABLE, INVITATIONS_UNAVAILABLE, ITINERARY_UNAVAILABLE, EXPENSES_UNAVAILABLE, BALANCES_UNAVAILABLE, DATABASE_UNAVAILABLE, NOT_READY, SERVICE_UNAVAILABLE (fallback) |

Codes are assigned at business raise sites, not inferred from English strings.
Validation uses one stable code with useful field details rather than a giant
code enumeration. See client-integration.md for complete envelope examples.
Never change a client-facing code casually without checking contract consumers.

## Sessions and Password Reset

Login returns an access token (JWT, 30 minutes) and an opaque `refresh_token`
(30 days by default, `REFRESH_TOKEN_EXPIRE_DAYS`). `POST /auth/refresh`
exchanges a live refresh token for a new pair and spends the presented one;
presenting a spent token again is treated as theft and revokes the whole
family (every rotation of that sign-in), answering `401 INVALID_REFRESH_TOKEN`.
`POST /auth/logout` revokes the family. Only SHA-256 hashes of these tokens
are stored.

`POST /auth/password/forgot` always answers 202; when the address is
registered a one-hour, single-use link is mailed (`MAIL_BACKEND=smtp`, or
written to the log in development). `POST /auth/password/reset` sets the new
password, spends the link and signs the account out everywhere. Both routes
share `RATE_LIMIT_RESET` (default 5 per 60 s per client).

## Rate Limits, Pagination and Request IDs

`POST /auth/login` and `POST /auth/register` are limited per client address
(`RATE_LIMIT_LOGIN`, default 10 per 60 s; `RATE_LIMIT_REGISTER`, default 5 per
60 s). The counter is a fixed window stored in PostgreSQL, so it holds across
every worker and instance. Over the limit the answer is `429 RATE_LIMITED`
with `Retry-After` in seconds; wrong passwords count, malformed bodies (422)
do not. Behind a trusted proxy the client is the first `X-Forwarded-For`
address; otherwise the socket peer.

List routes (`GET /trips`, `/trips/{id}/itinerary`, `/trips/{id}/expenses`,
`/trips/{id}/places`) accept optional `limit` (1-200) and `offset` (>= 0)
query parameters and always return `X-Total-Count`. Without them the whole
list is returned, as before. Pages follow each list's natural order (trips by
id, itinerary by date then position, expenses newest first, places by id).

Every response carries `X-Request-ID`: the client's value when it sent one
matching `[A-Za-z0-9._-]{1,64}`, otherwise a generated id. The same id is on
every log line written while handling the request, including the one access
line per request (`event: request`, method, route template, status,
duration), which never contains the query string. `X-Request-ID` and
`X-Total-Count` are exposed to cross-origin clients.

## Live Updates and Versions

`GET /api/v1/trips/{trip_id}/events` is a long-lived `text/event-stream`. It
opens with `event: ready` and then sends one event per committed change in
that trip: `itinerary.created|updated|deleted|reordered`, `expense.*`,
`place.*`, `trip.updated|deleted` and `member.joined`, each with a JSON body
`{type, trip_id, entity, action, actor_id, entity_id?, version?, date?,
occurred_at}`. A comment line every 20 seconds keeps proxies from closing the
connection. A `resync` event (or a reconnect) means the client should refetch
everything. `trip.deleted` ends the stream.

## Split Methods and Settlement

`ExpenseCreate`/`ExpenseUpdate` take `split_method` (`equal`, the default,
`shares` or `exact`). `equal` uses `participant_user_ids`; `shares` and
`exact` use `splits: [{user_id, weight}]` or `splits: [{user_id, amount}]`
instead (sending both lists, or the wrong one for the method, is 422). Weights
are integers from 1 to 1,000,000; exact amounts are decimal strings that must
add up to `amount`. Shares are apportioned to whole cents with the
largest-remainder method, ties to the lowest user id. `ExpenseResponse` carries
`split_method` and each split's `weight` (null unless `shares`). A PATCH that
changes only `amount` re-apportions `equal` and `shares` splits; for an `exact`
split it needs new `splits` too (422 otherwise). Switching methods without
`splits` keeps the participants (weights start at 1).

`BalanceResponse.settlement` is `{transfers, unsettled_members, minimal}`.
`suggested_settlements` is the fewest transfers found: an exact zero-sum
partition search while at most 14 members have a nonzero balance
(`minimal: true`), otherwise a greedy plan of at most n - 1 transfers
(`minimal: false`).

`TripResponse`, `ItineraryItemResponse`, `ExpenseResponse` and
`TripPlaceResponse` carry an integer `version`, also returned as an `ETag`
header on their detail and PATCH routes. A PATCH may send `If-Match: "<version>"`
(a bare number is accepted; `*` or no header skips the check). If the stored
version differs the response is `412 STALE_VERSION` and nothing is written.
A malformed header is `400 INVALID_IF_MATCH`.
