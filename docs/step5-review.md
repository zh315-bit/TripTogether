# Step 5: Login and JWT Authentication

## OpenTrip Reference Review

Before implementation, checked the current remote HEAD of stvlynn/OpenTrip:
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`, unchanged from Step 4.
The temporary reference checkout was inspected directly, not copied.

| Source | Observed design |
| --- | --- |
| `apps/api/src/infrastructure/auth/auth.ts` | Better Auth configuration, email/password, verification and bearer plugins |
| `apps/api/src/interfaces/http/app.ts` | getSession populates user/session context, `/api/auth/*` delegation, missing-session 401 guard |
| `apps/web/src/shared/auth/index.ts` and `AuthForm.tsx` | auth client, signIn.email, sign-in errors and email OTP flow |
| Prisma User, Account and Session definitions | unique user email; provider/credentials in Account; persisted Session token and expiry |
| `docs/backend/api/auth-session.md` | browser cookies and native-client Bearer session credentials |
| HTTP `errors.ts` and `response.ts` reviewed in Step 4 | expected-error boundaries and explicit public data selection |

Borrowed: isolate auth, centralize current-user resolution, reject unauthenticated
requests at a protected boundary, return safe user projections, and separate
HTTP errors from services. Better Auth/Hono/Prisma do not fit this Python stack.
We did not adopt session storage, Account providers, OAuth, OTP, verification,
RBAC or frontend workflows. A Bearer header alone does not imply JWT.
No project-owned JWT login implementation was found in the inspected reference.
Better Auth's internal password verification and complete error filtering were
not independently verified; no claims are made about their precise internals.

TripTogether uses FastAPI + SQLAlchemy + PostgreSQL with Argon2id and PyJWT.
PyJWT performs standard JWT encoding, signing and validation; it does not query
users, verify passwords, decide HTTP statuses or implement authorization.
The PyJWT official API documentation was consulted; tested version is 2.14.0.
The sole new dependency is `PyJWT>=2.10.1,<3.0`.

## Flows and Boundaries

```text
JSON login -> UserLogin normalization -> authenticate_user -> SELECT User
-> verify_password(plaintext input, stored Argon2id encoding)
-> create_access_token(user.id) -> TokenResponse -> 200

Authorization: Bearer token -> HTTPBearer -> get_token_user_id
-> PyJWT signature/expiry/required-claim validation -> bounded User ID
-> get_db -> find_current_user -> PostgreSQL User -> /auth/me -> UserResponse
```

The server temporarily receives the submitted password but never needs to
recover the original password from the stored hash. Rehashing and comparing
strings would be wrong because salts produce different encodings.
Unknown email and wrong password return the same message and 401/header.
Unknown email still verifies against a process-generated dummy Argon2 hash.
This removes an obvious timing shortcut, not every timing difference or every
enumeration route; the existing registration conflict behavior is unchanged.

FastAPI Depends calls prerequisite functions and passes their results onward.
The token-validation dependency precedes get_db so invalid tokens do not
trigger a database query. get_current_user returns an actual current database
User, not a user manufactured from client data. The session is request-local,
then closed by the existing yielding dependency.

## Six Files to Read

1. `backend/app/schemas/user.py`: UserLogin owns shared email/password validation;
   UserRegister inherits it and keeps its eight-character minimum. TokenResponse
   defines exactly two output fields; UserResponse remains the safe whitelist.
2. `backend/app/services/authentication.py`: authenticate_user queries and verifies;
   find_current_user checks existence. SQL errors become safe service errors.
3. `backend/app/core/security.py`: existing Argon2 helpers plus token issue/decode.
   Follow UTC expiry, required claims, explicit algorithm list, and strict subject
   conversion. The positive ID must fit PostgreSQL's existing INTEGER column.
4. `backend/app/core/config.py`: process environment first, root dotenv fallback,
   lazy JWT settings, hidden secret repr, allowed algorithm and bounded lifetime.
   DATABASE_URL behavior remains unchanged.
5. `backend/app/api/dependencies.py`: HTTPBearer extracts credentials;
   get_token_user_id authenticates the token; get_current_user loads the user.
   Client credential failures become 401; server configuration failures become 503.
6. `backend/app/api/auth.py`: thin login/me routes, safe response schemas,
   cache headers and service error translation. Registration is preserved.

Then read test_jwt.py for direct security tests and test_authentication.py for
the complete register/login/me lifecycle and failure cases.

## JWT Concepts

JWT has three dot-separated components: Header.Payload.Signature.
The header identifies HS256; the payload contains `sub` and `exp`; the signature
authenticates the encoded header and payload with the server's secret.
Encoding is not encryption: clients can read claims without the secret.
Never include a password, hash, connection URL or secret.

HS256 uses a shared signing/verification secret. Changing sub from "1" to "2"
changes the signed content; the old signature no longer verifies. An attacker
without the secret cannot generate a matching signature. The decoder's allowed
algorithm comes from server configuration, never from trusting the token header.

sub is str(user.id): a stable primary key rather than a changeable email.
exp is an integer Unix timestamp derived from aware UTC time, default 30 minutes.
Expired tokens return 401. Expiry bounds a stolen token's useful lifetime but
does not instantly revoke individual tokens. No blacklist or refresh workflow
was added. Changing the signing key invalidates all tokens signed by the old key.

Bearer means possession is sufficient: a stolen valid token can be replayed.
HTTPS and careful client storage are necessary outside localhost.
Successful token/current-user responses request no storage, but this does not
prevent a caller or proxy from deliberately recording secrets.

JWT verification is stateless because no per-token server session is needed.
Our current-user lookup still queries PostgreSQL: token authenticity and current
user existence are separate questions. Deleted users must not retain access.
Future disabled/status fields are not implemented speculatively.

Authentication asks "Who are you?" and yields User 1. Authorization asks whether
User 1 may modify a particular Trip. This step only implements authentication.
Future membership/ownership checks must not be replaced by trusting a client ID.

Environment variables keep deployment-specific settings out of code. `.env`
holds local secrets and is ignored; `.env.example` contains safe placeholders.
A 32-byte minimum cannot prove entropy: use a cryptographic random generator.
The supported algorithm is HS256 and allowed expiry is 1-1440 minutes.
JWT configuration is lazy so /health and registration remain independent.

## Verification and Limits

README contains installation, startup, register/login, Swagger and test commands.
POST /auth/register returns 201; POST /auth/login returns 200 with access_token
and token_type; GET /auth/me returns 200 with id/username/email/created_at.
Wrong or missing credentials return 401 with WWW-Authenticate: Bearer.
No schema changes, new migrations or changes to revision 0001 were needed.
No tokens are persisted.

Tests use newly generated signing keys, never the developer's real key.
Real PostgreSQL tests reuse the established private schema, outer transaction,
and request savepoint fixture; they do not substitute SQLite or pollute users.
Default tests explicitly skip these opt-in cases. Exact final results and manual
verification limitations are recorded in the Step 5 RECORD entry.
Rate limiting, refresh/revocation, HTTPS deployment and client secure storage
are not implemented here; this is not a complete production security review.

## Interview Questions

1. What is JWT? A signed claims format; TripTogether issues it after password login.
2. What's inside it? Header HS256, payload sub/exp, and a signature.
3. Is it encrypted? No. Our claims are readable, so no credentials go in them.
4. How is modification detected? PyJWT verifies the signature with JWT_SECRET_KEY;
   changing sub without a new valid signature fails.
5. Why expire tokens? Our 30-minute default limits replay time, but is not
   immediate selective revocation.
6. Why ID rather than email in sub? users.id is stable; an email may change.
7. Authentication versus authorization? get_current_user identifies the user;
   future Trip permissions determine allowed actions.
8. Why query after JWT verification? The user may have been deleted; PostgreSQL
   remains the source of truth.
9. Why identical login errors? Unknown email and wrong password must not expose
   different account-existence messages; both return 401.
10. Why not commit the secret? Anyone possessing it could sign forged tokens.
11. Is this stateless despite SQL queries? Signature validation needs no session
   store; current-user existence is a separate database check.
12. Why not hash the input and compare strings? Argon2 uses random salts;
   verify_password checks the supplied password against the stored encoding.
13. What does Depends do? FastAPI resolves token and session prerequisites,
   passes the User to the endpoint and closes the session after the request.
14. How are real integration tests isolated? Private schema plus outer
   transaction and savepoints survive endpoint commits, then roll back.

## Next Step

Step 6: Trip CRUD. Not implemented in this task.
