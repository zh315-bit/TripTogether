# API Inventory

## Pre-change Audit

Step 11 implementation前，直接遍历实际 FastAPI APIRoute 并阅读所有 router：
26个业务/系统操作（25个业务 + GET /health），没有 `/api/v1`、CORS 或 readiness。
除 register/login/health 外均使用 get_current_user；删除成功204无body，
其他成功均有明确response_model。以下是审查时的完整路径，不凭路线图推测。

| Method | Existing Path | Auth | Role | Request | Response | Main Errors |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /health | No | Public | None | 200 HealthResponse | None |
| POST | /auth/register | No | Public | UserRegister | 201 UserResponse | 409,422,503 |
| POST | /auth/login | No | Public | UserLogin | 200 TokenResponse | 401,422,503 |
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
| PATCH | /trips/{trip_id}/itinerary/reorder | JWT | Owner/Member | ItineraryReorderRequest | 200 ItineraryItemResponse[] | 401,404,422,503 |
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

27 documented operations: Auth3, Trips5, Members1, Invitations4, Itinerary6,
Expenses5, Balances1, System2. Counts are method/path pairs, not distinct URLs.
All official success schemas retain their original fields. All listed errors
use APIErrorResponse; generic unexpected500 and infrastructure503 can occur on
business operations. Framework unknown-path404 and wrong-method405 use the
same envelope inside `/api/v1`.

| Method | Path | Auth | Role | Request | Response | Main Errors |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /health | No | Public | None | 200 HealthResponse | None |
| GET | /ready | No | Public | None | 200 ReadinessResponse | 503 |
| POST | /api/v1/auth/register | No | Public | UserRegister | 201 UserResponse | 409,422,503 |
| POST | /api/v1/auth/login | No | Public | UserLogin | 200 TokenResponse | 401,422,503 |
| GET | /api/v1/auth/me | JWT | Current user | None | 200 UserResponse | 401,503 |
| POST | /api/v1/trips | JWT | Any user | TripCreate | 201 TripResponse | 401,422,503 |
| GET | /api/v1/trips | JWT | Owned/joined only | None | 200 TripResponse[] | 401,503 |
| GET | /api/v1/trips/{trip_id} | JWT | Owner/Member | None | 200 TripResponse | 401,404,422,503 |
| PATCH | /api/v1/trips/{trip_id} | JWT | Owner | TripUpdate | 200 TripResponse | 401,404,409,422,503 |
| DELETE | /api/v1/trips/{trip_id} | JWT | Owner | None | 204 empty | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/members | JWT | Owner/Member | None | 200 TripMemberResponse[] | 401,404,422,503 |
| POST | /api/v1/trips/{trip_id}/invitations | JWT | Owner | InvitationCreate | 201 InvitationResponse | 401,404,409,422,503 |
| GET | /api/v1/invitations | JWT | Recipient's inbox | None | 200 InvitationResponse[] | 401,503 |
| POST | /api/v1/invitations/{invitation_id}/accept | JWT | Recipient | None | 200 InvitationResponse | 401,404,409,422,503 |
| POST | /api/v1/invitations/{invitation_id}/reject | JWT | Recipient | None | 200 InvitationResponse | 401,404,409,422,503 |
| POST | /api/v1/trips/{trip_id}/itinerary | JWT | Owner/Member | ItineraryItemCreate | 201 ItineraryItemResponse | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/itinerary | JWT | Owner/Member | None | 200 ItineraryItemResponse[] | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/itinerary/{item_id} | JWT | Owner/Member | None | 200 ItineraryItemResponse | 401,404,422,503 |
| PATCH | /api/v1/trips/{trip_id}/itinerary/{item_id} | JWT | Owner/Member | ItineraryItemUpdate | 200 ItineraryItemResponse | 401,404,422,503 |
| DELETE | /api/v1/trips/{trip_id}/itinerary/{item_id} | JWT | Owner/Member | None | 204 empty | 401,404,422,503 |
| PATCH | /api/v1/trips/{trip_id}/itinerary/reorder | JWT | Owner/Member | ItineraryReorderRequest | 200 ItineraryItemResponse[] | 401,404,422,503 |
| POST | /api/v1/trips/{trip_id}/expenses | JWT | Owner/Member | ExpenseCreate | 201 ExpenseResponse | 401,404,409,422,503 |
| GET | /api/v1/trips/{trip_id}/expenses | JWT | Owner/Member | None | 200 ExpenseResponse[] | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/expenses/{expense_id} | JWT | Owner/Member | None | 200 ExpenseResponse | 401,404,422,503 |
| PATCH | /api/v1/trips/{trip_id}/expenses/{expense_id} | JWT | Owner/Member | ExpenseUpdate | 200 ExpenseResponse | 401,404,409,422,503 |
| DELETE | /api/v1/trips/{trip_id}/expenses/{expense_id} | JWT | Owner/Member | None | 204 empty | 401,404,422,503 |
| GET | /api/v1/trips/{trip_id}/balances | JWT | Owner/Member | None | 200 BalanceResponse | 401,404,409,422,503 |

## Compatibility and Documentation Routes

Every business row in the pre-change table remains reachable without `/api/v1`,
with identical role/request/success rules and legacy `{"detail": ...}` errors.
There are25 such hidden aliases, not a second set of business logic.
Runtime has52 API operations (27 official +25 legacy) and four framework
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
| 400 | BAD_REQUEST (fallback) |
| 401 | INVALID_CREDENTIALS |
| 403 | FORBIDDEN (fallback; resource policy currently uses404) |
| 404 | TRIP_NOT_FOUND, INVITATION_NOT_FOUND, INVITEE_NOT_FOUND, ITINERARY_NOT_FOUND, EXPENSE_NOT_FOUND, NOT_FOUND |
| 405 | METHOD_NOT_ALLOWED |
| 409 | USERNAME_ALREADY_EXISTS, EMAIL_ALREADY_EXISTS, TRIP_ITINERARY_CONFLICT, INVITATION_CONFLICT, EXPENSE_CURRENCY_CONFLICT, LEDGER_INCONSISTENT |
| 422 | VALIDATION_ERROR |
| 500 | INTERNAL_ERROR |
| 503 | REGISTRATION_UNAVAILABLE, AUTHENTICATION_UNAVAILABLE, TRIPS_UNAVAILABLE, INVITATIONS_UNAVAILABLE, ITINERARY_UNAVAILABLE, EXPENSES_UNAVAILABLE, BALANCES_UNAVAILABLE, DATABASE_UNAVAILABLE, NOT_READY, SERVICE_UNAVAILABLE (fallback) |

Codes are assigned at business raise sites, not inferred from English strings.
Validation uses one stable code with useful field details rather than a giant
code enumeration. See client-integration.md for complete envelope examples.
Never change a client-facing code casually without checking contract consumers.
