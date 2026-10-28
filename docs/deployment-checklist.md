# TripTogether Production Deployment Checklist

This is a manual runbook. It intentionally contains no real URL,
credential, account, or deployment command that creates cloud resources.

## Configuration matrix

| Variable | Vercel frontend | Render backend | Secret | Example |
| --- | --- | --- | --- | --- |
| `VITE_API_BASE_URL` | Yes, build-time | No | No | `https://<render-service>.onrender.com` |
| `DATABASE_URL` | No | Yes | Yes | Neon **direct** (non-pooler) connection string |
| `JWT_SECRET_KEY` | No | Yes | Yes | generated secure random value |
| `JWT_ALGORITHM` | No | Yes | No | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Yes | No | `30` |
| `APP_ENV` | No | Yes | No | `production` |
| `CORS_ORIGINS` | No | Yes | No | `["https://<vercel-project>.vercel.app"]` |
| `RATE_LIMIT_LOGIN` | No | Optional | No | `10/60` (default), attempts per client per window, or `off` |
| `RATE_LIMIT_REGISTER` | No | Optional | No | `5/60` (default) or `off` |
| `TRUST_PROXY_HEADERS` | No | Optional | No | default `1` in production: client address from `X-Forwarded-For` |
| `LOG_FORMAT` | No | Optional | No | default `json` in production, `text` otherwise |
| `DEMO_MODE` | No | Optional | No | `1` enables `POST /auth/demo` and the landing page's **Try the demo**; the seeded trip rebuilds every 6 h |
| `GEOCODER_PROVIDER` | No | Optional | No | `disabled` (default) or `nominatim` |
| `GEOCODER_USER_AGENT` | No | Required if `nominatim` | No | `TripTogether/1.0 (contact: ops@<your-domain>)` |
| `GEOCODER_BASE_URL` | No | Optional | No | default `https://nominatim.openstreetmap.org` |
| `VITE_MAP_TILE_URL` | Yes, build-time | No | No | `https://<tile-provider>/{z}/{x}/{y}.png` |
| `VITE_MAP_TILE_ATTRIBUTION` | Required with a custom tile URL | No | No | `© <Provider> © OpenStreetMap contributors` |

`VITE_API_BASE_URL` must be the backend **origin only**. The current client adds
`/api/v1/...` itself; do not append `/api/v1` to this variable.

What the defaults mean:

- `GEOCODER_PROVIDER` unset = `disabled`: place search is off (`/geocode`
  returns 503 `GEOCODER_DISABLED`) and users add places manually. This is a
  safe default. `nominatim` requires `GEOCODER_USER_AGENT` (app name plus a
  monitored contact), or production startup fails. `fake` always fails
  production startup.
- `GEOCODER_BASE_URL` unset = public Nominatim; it must be HTTPS in production.
  Using the public service means accepting its usage policy (one request per
  second for the whole app, no autocomplete).
- `VITE_MAP_TILE_URL` unset = public OpenStreetMap tiles. That is acceptable
  only for development and light demos; **set it to a commercial or
  self-hosted tile service before real traffic.** A custom URL also needs
  `VITE_MAP_TILE_ATTRIBUTION` (plain text); without it the app falls back to
  OSM tiles and logs a warning. Both are build-time values, so redeploy Vercel
  after changing them.

## Manual deployment order

1. Review `git status` and `git ls-files`; confirm no `.env`, database URL, JWT
   secret, `node_modules`, `dist`, cache, or AppleDouble metadata is staged.
2. Push the reviewed repository to GitHub yourself. Do not include local `.env`
   files.
3. Create the database in Neon (PostgreSQL 15+, region close to the Render
   service: production uses `aws-us-east-2` with Render in Ohio), with a
   dedicated application role. In Render, create a Python Web Service. Use
   Neon's **direct** connection string, not the `-pooler` host (see "PostgreSQL
   choice").
4. Configure the Render Web Service: root directory `backend`, runtime `Python
   3`, build command `pip install -r requirements.txt`, and start command
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
5. Add backend environment values: `DATABASE_URL`, `JWT_SECRET_KEY`,
   `JWT_ALGORITHM=HS256`, `ACCESS_TOKEN_EXPIRE_MINUTES=30`,
   `APP_ENV=production`, and a temporary valid HTTPS `CORS_ORIGINS` value.
   Generate the JWT value locally without saving it to the repository:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

6. For a new database or schema change, run `APP_ENV=production python -m alembic
   upgrade head` exactly once as a controlled release step before validating
   business traffic. On a Render plan with a Pre-Deploy Command, configure this
   as the single migration command. Render Free has no Pre-Deploy Command, so
   run it manually from a trusted environment using the Render database URL;
   do not store that URL in the repository or shell history. Then run
   `python -m alembic current` and confirm `0010 (head)` for this release. Never
   put migrations in the web start command or run them in each worker. For an
   existing production database, follow "Releasing a schema change" below.
7. Set Render's HTTP health check path to `/ready`. It verifies JWT
   configuration, PostgreSQL connectivity, that the database revision matches
   the application's single Alembic head, and that all nine core tables
   exist. `/health` is liveness only and never accesses the database. A 503
   means readiness checks failed.
8. After Render reports healthy, record its HTTPS `onrender.com` API origin.
9. In Vercel, import the repository with root directory `frontend`. Vercel will
   use Node `24.x`, `npm run build`, and `dist`; `frontend/vercel.json` supplies
   the SPA rewrite needed for direct route access.
10. Set Vercel Production `VITE_API_BASE_URL` to the recorded Render HTTPS
    origin, then deploy the frontend. Do not put database or JWT values in
    Vercel.
11. Record the Vercel production URL. Update Render `CORS_ORIGINS` to a JSON
    array containing that exact HTTPS origin, without a trailing slash, then
    redeploy/restart the backend.
12. Open the Vercel URL and perform the smoke test below. Recheck Render
    `/health` and `/ready` after any configuration change.

## PostgreSQL choice

**PostgreSQL must be version 15 or newer.** Migration 0006 uses
`ON DELETE SET NULL (place_id)`, which older servers reject; the migration
checks the server version and stops before running any DDL. Check it with
`SHOW server_version;`.

Production uses **Neon** (project `triptogether`, `aws-us-east-2`, PostgreSQL
18.6, database `triptogether`, role `triptogether_app`). It was migrated from
Render PostgreSQL on 2026-10-18.

Use Neon's **direct** connection string (host without `-pooler`) for the
backend, for Alembic migrations and for `pg_dump`/`pg_restore`. The backend
keeps its own SQLAlchemy pool on a single Render instance, and migrations and
dumps need a real session rather than a transaction-pooled one. Keep the
query parameters Neon provides (`sslmode=require` and friends). The backend
normalizes `postgres://`/`postgresql://` to its psycopg driver.

Neon Free plan limits that matter here (review Neon's live pricing page before
relying on them):

- **1 GB** storage for the branch;
- **100 CU-hours per month** of compute;
- the compute **suspends after 5 minutes idle**, so the first query after a
  pause takes a moment to wake it (on top of Render Free's own cold start);
- **point-in-time restore covers only the last 6 hours**, so it is not a backup
  strategy. Keep your own `pg_dump` files (see below).

## Releasing a schema change (Render Free + auto-deploy)

Use this order for a release that includes migrations, such as 0006/0007 for
the collaborative map, when Render auto-deploys `main` and there is no
Pre-Deploy Command:

1. Confirm the Neon PostgreSQL version is at least 15 (`SHOW server_version;`).
2. **The owner backs up the database on their own machine, in their own
   terminal**, before every release with a schema change:
   `pg_dump -Fc` (client major version ≥ server, currently 18) to
   `~/Backups/TripTogether/`, then check it with `pg_restore -l` and in Finder.
   Neon's 6-hour point-in-time restore does not replace this.
3. In Render, temporarily change the Web Service health check path from
   `/ready` to `/health`.
4. From a trusted environment with the production `DATABASE_URL`, run
   `APP_ENV=production python -m alembic upgrade head` using the **new** code,
   then `python -m alembic current` and confirm `0010 (head)`.
5. Merge to `main` and wait for the Render and Vercel auto-deploys to finish.
6. Check that `https://<render-service>/ready` returns 200, then change the
   health check path back to `/ready`.
7. Run the production smoke test below, including the map steps.

Why this order:

- `/ready` requires the database revision to equal the **running code's**
  Alembic head. The old backend only accepts `0009`, and the new backend only
  accepts `0010`. Whichever runs first, one of them would fail readiness
  during the switch-over; using `/health` for that window keeps Render from
  treating the healthy old service, or the incoming new deploy, as failed.
- The migration runs before the code ships because the new backend needs the
  new tables. It is safe to run while the old backend is serving: 0006 and
  0007 only **add** tables, a nullable column, a foreign key and an index. The
  old backend was verified against a 0007 schema: register, trips,
  invitations, itinerary edits and reorder, expenses, balances and trip
  deletion all work; only its `/ready` returns 503, as expected.

Rollback: redeploy the previous commit first (the old backend runs on the new
schema; keep the health check on `/health`, since its `/ready` will be 503).
Run `python -m alembic downgrade 0005` only if the schema itself must go; it
deletes all saved places. Then set the health check back to `/ready`.

## Production smoke test

1. Load the landing page, then refresh `/login`, `/register`, `/trips`,
   `/account`, and `/trips/<id>` to confirm Vercel SPA routing.
2. Register two disposable users and log in as the first.
3. Create a trip, invite the second user, accept the invitation, and verify
   membership visibility and owner/member permissions.
4. Create, edit, reorder, and delete itinerary items.
5. Create, edit, and delete an equal-split expense. Confirm the exact backend
   balances and settlement suggestion are displayed without client rounding.
6. Log out, refresh a protected route, then use an invalid JWT/session to
   confirm redirect and error behavior.
7. Inspect browser network requests for HTTPS API traffic and a successful CORS
   preflight. Test at a narrow mobile viewport as well as desktop.
8. Open a trip's **Map** tab. Tiles load with the configured provider's credit.
   Search (or, with search disabled, add a manual place), link it to an
   itinerary item, view the day route, suggest an order, and apply it.
