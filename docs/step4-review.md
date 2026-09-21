# Step 4 Review Notes

## OpenTrip Reference Review

Reviewed a read-only checkout of `https://github.com/stvlynn/OpenTrip.git`,
commit `cfc78a04d0eeba3daaec4b755b110d89938ae4fc`, before changing TripTogether.
No reference implementation code was copied.

Files inspected:

- `apps/api/src/infrastructure/auth/auth.ts`: Better Auth configuration,
  email/password signup, email verification, optional social providers,
  database hooks, and authentication plugins.
- `apps/api/src/interfaces/http/app.ts`: Hono mounts Better Auth on
  `/api/auth/*` separately from guarded business routes; explicit `inviteActor`
  projection selects id, name, email and image.
- `apps/api/src/interfaces/http/errors.ts` and `response.ts`: central HTTP
  error translation and response envelopes, including conflict handling.
- `apps/api/prisma/schema.prisma`: User has unique email; Account contains
  credential/provider fields separately. The inspected User has `name`, not
  a unique `username` field.
- `apps/web/src/features/auth/AuthForm.tsx`: frontend calls `signUp.email`
  and proceeds to email verification.
- `apps/api/src/application/user/profile-projection-service.ts`: trims and
  bounds display names on the profile-update path. This is not evidence of
  the exact signup validation policy.
- `apps/api/package.json`: Hono, Better Auth, Prisma and Zod dependencies.

Borrowed principles: separate HTTP handling, validation and application logic;
explicit safe response fields; keep credentials out of public user data;
translate expected conflicts into client errors.

Not adopted: TypeScript/Hono/Prisma/Better Auth, separate credential-account
tables, OAuth, OTP, email verification, sessions, two-factor, Cloudflare rate
limit infrastructure, profile projections, sample-trip provisioning, and
additional user fields. They exceed this task and do not match the small
FastAPI/SQLAlchemy backend.

Limits of the review: signup is delegated to Better Auth. No project-owned
signup duplicate-check or password-hashing function was found in the inspected
code. The precise dependency-internal signup error/status/hash implementation
and all auth response filtering were not independently verified. An Account
field named `password` does not itself prove plaintext storage. The explicit
public projection inspected excludes credentials, but is not a security audit
of every OpenTrip route. No RBAC implementation was adopted or assumed.

## Important Code

Read these six files, in this order:

1. `backend/app/schemas/user.py`: UserRegister accepts a SecretStr password,
   strips username edges, validates email with EmailStr, and lowercases it.
   UserResponse whitelists four public fields via `from_attributes=True`.
2. `backend/app/api/auth.py`: the thin synchronous router gets a request-local
   Session from `Depends(get_db)`, delegates registration, maps service errors,
   and returns UserResponse with HTTP 201.
3. `backend/app/services/registration.py`: pre-checks, hash call, ORM creation,
   add/commit/refresh, rollback, SQLSTATE/constraint-based conflict conversion.
4. `backend/app/core/security.py`: Argon2id hash/verify wrappers using the
   library's RFC 9106 low-memory profile and automatic random salts.
5. `backend/app/api/errors.py`: removes raw input/context from validation
   responses; missing fields and malformed JSON can otherwise expose a body.
6. `backend/tests/test_registration.py`: real PostgreSQL API registration,
   salted hash verification, safe output, duplicates, and deterministic
   simulation of pre-check races followed by actual UNIQUE violations.

## Registration Flow

FastAPI parses the HTTP JSON body into UserRegister. Pydantic checks usernames,
email syntax, password type/length/encoding, and rejects unexpected fields.
`get_db` supplies a separate Session for that request. Validation failure
returns 422 without querying or hashing.

The router calls `register_user`. It queries for the normalized username/email.
Duplicates return 409. Otherwise `hash_password` consumes the secret value;
User receives only `password_hash`, not plaintext. `db.add` makes the instance
pending, `db.commit` flushes INSERT and commits the transaction, and
`db.refresh` loads persisted/default fields. UserResponse then exposes only id,
username, email and created_at. Closing the dependency releases DB resources.

If INSERT races with another request, PostgreSQL UNIQUE decides the winner.
The service catches IntegrityError, rolls back, and maps only SQLSTATE 23505
for the two known constraint names to a duplicate error. Other database or
hashing failures return a generic 503; they are not mislabeled as duplicates
and raw exceptions are neither returned nor logged.

## Password Security

Uses argon2-cffi (tested 25.1.0) and RFC_9106_LOW_MEMORY: Argon2id, 64 MiB memory,
3 iterations, parallelism 4, random 16-byte salt, 32-byte derived hash.
The encoded value includes algorithm, parameters and salt for verification.
It fits the existing VARCHAR(255); no schema change is needed.

Argon2id makes each guess consume memory and compute. Plain SHA-256 is fast
and not an appropriate standalone password-storage scheme. Encryption can be
reversed with a key; passwords need verification, not recovery, so a one-way
password hash is used. Random salt makes two hashes of the same password
different and prevents sharing precomputed cracking work across accounts.
Salt is not secret and is not a substitute for strong passwords.

Argon2 does not have bcrypt's 72-byte password limitation. The API imposes an
8-128 Unicode-character policy, at most 512 UTF-8 bytes, rejects lone surrogate
characters, and never silently truncates or trims passwords. A test changes
the final character of a long multibyte password to verify it still matters.
SecretStr masks routine representations but cannot erase immutable Python
strings from memory. No request-body logging is enabled, and validation errors
drop input/context rather than relying on SecretStr alone.

Email lowercasing is a product policy, including the local part; it deliberately
treats case variants as one address, though not every theoretical mail system
has that rule. It does not remove plus tags or dots. All app writes must use
this canonical form; existing case-sensitive DB constraints do not enforce
normalization for arbitrary direct SQL writes. No existing noncanonical rows
were present at verification.

Username remains case-sensitive, is trimmed, and allows only ASCII letters,
digits and underscore to keep identifiers simple and avoid invisible/control
characters. No complex password composition policy or username framework.

Reference used for the hashing API:
`https://argon2-cffi.readthedocs.io/en/stable/api.html` (25.1.0 documentation).
Production deployment still needs HTTPS, resource limits and abuse controls;
this step does not implement those or claim deployment readiness.

## Interview Questions

1. Why hash instead of encrypt? TripTogether only needs to verify a password;
   a reversible encrypted password would expose every password if its key leaks.
2. Why Argon2id instead of plain SHA-256? Argon2id makes guessing consume memory
   and CPU; SHA-256 is designed to be fast.
3. Why do equal passwords have different hashes? The library creates a fresh
   random salt per call; the encoded hash stores what verification needs.
4. Why never return password_hash? It is sensitive offline-guessing material,
   and clients need only the four fields in UserResponse.
5. How do the three models differ? UserRegister handles client input/password,
   User maps database rows/password_hash, UserResponse whitelists public output.
6. Why both SELECT checks and UNIQUE? Two requests can both see no row;
   PostgreSQL UNIQUE enforces the final invariant during INSERT.
7. What if commit fails? The service rolls back; known duplicate constraints
   become 409, other infrastructure failures become credential-safe 503.
8. Does add save a user permanently? No. It makes the ORM object pending;
   commit flushes and commits, refresh rereads defaults, rollback abandons work.
9. What does Depends(get_db) do? FastAPI supplies one Session to the request
   and closes it afterward, rather than sharing a global Session.
10. Why 201/409/422? They distinguish created users, conflicting identifiers,
    and invalid request bodies; infrastructure unavailability is separate (503).
11. How are tests isolated despite commit? Per-request Sessions use savepoints
    within an outer transaction in a unique PostgreSQL schema; teardown rolls
    back the entire schema and its data.
12. Was the race test truly simultaneous? No: pre-check results are forced to
    report no user, then real PostgreSQL UNIQUE rejects INSERT. This tests
    the conflict/rollback path deterministically, not concurrent load.
