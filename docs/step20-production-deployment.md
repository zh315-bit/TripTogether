# Step 20A — Production Deployment Runbook

TripTogether is deployed on Vercel, Render Web Service, and Render PostgreSQL.
Use this runbook for controlled releases and new database setup. The project
owner confirmed production registration and Alembic `0005 (head)` after the
September 2026 missing-table incident. The collaborative-map release adds
migrations 0006 and 0007 and expects `0007 (head)`; release it with
[Releasing a schema change](#releasing-a-schema-change-render-free--auto-deploy).

## Production architecture

```text
Browser → Vercel React SPA → HTTPS → Render FastAPI → Render PostgreSQL
```

The Vercel build contains the public API origin only. Render owns all backend
runtime configuration and secrets. PostgreSQL remains the source of truth for
trips, memberships, itineraries, expenses, balances, and settlements.

## Render PostgreSQL and backend

1. In Render, create a PostgreSQL database (**version 15 or newer**;
   migration 0006 refuses older servers) and a Python Web Service in the same
   region. Do not add test users or seed data.
2. For the Web Service, select the GitHub repository and set **Root Directory**
   to `backend`.
3. Set **Build Command** to `pip install -r requirements.txt`.
4. Set **Start Command** to:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

   Render supplies `PORT`; do not add `--reload` or replace it with a fixed
   production port.
5. Add the following backend environment values in Render's secret/config UI:

   | Name | Value | Secret |
   | --- | --- | --- |
   | `DATABASE_URL` | Render PostgreSQL internal URL | Yes |
   | `JWT_SECRET_KEY` | unique, securely generated random value | Yes |
   | `JWT_ALGORITHM` | `HS256` | No |
   | `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | No |
   | `APP_ENV` | `production` | No |
   | `CORS_ORIGINS` | temporary exact HTTPS frontend origin JSON array | No |
   | `GEOCODER_PROVIDER` | optional; `disabled` (default) or `nominatim` | No |
   | `GEOCODER_USER_AGENT` | **required when `nominatim`**: app name plus a monitored contact | No |
   | `GEOCODER_BASE_URL` | optional; default `https://nominatim.openstreetmap.org`, HTTPS only | No |

   Geocoding defaults: unset `GEOCODER_PROVIDER` means place search is off.
   `/geocode` answers 503 `GEOCODER_DISABLED` and members add places manually,
   which is a safe default. Choosing `nominatim` means accepting the public
   [usage policy](https://operations.osmfoundation.org/policies/nominatim/)
   (one request per second for the whole app, enforced by the
   `geocoder_throttle` table; no autocomplete). It also requires a compliant
   `GEOCODER_USER_AGENT`, or startup fails. `fake` is development-only and
   fails production startup. Changing these values needs a restart, not a
   release.

   Generate the JWT value locally; never save it in the repository:

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

The backend accepts provider-standard `postgres://` and `postgresql://` URLs,
normalizing them internally to the existing `postgresql+psycopg` SQLAlchemy
driver. Local development URLs are unchanged.

## Controlled migration

For a new database or schema change, run this exactly once as a controlled
release step before validating business traffic or starting/scaling API workers:

```bash
cd backend
APP_ENV=production python -m alembic upgrade head
```

Render Free has no Pre-Deploy Command. For that plan, run the migration manually
from a trusted environment with the Render database URL supplied as
`DATABASE_URL`; do not save the URL in the repository or shell history. On a
Render plan that supports Pre-Deploy Command, configure this as the one
controlled migration command. Check `python -m alembic current` after the
migration; this release expects `0007 (head)`. Do not put `alembic upgrade head`
in the web-service start command or run it independently in each worker.

Set Render's health check path to `/ready`. It verifies JWT configuration,
PostgreSQL connectivity, that the database revision matches the application's
single Alembic head, and that all nine core tables exist. `/health` is
liveness-only, never accesses the database, and stays 200 even when the schema
is not ready. `/ready` returns 503 when any readiness check fails.

## Vercel frontend

1. In Vercel, import the same GitHub repository and set **Root Directory** to
   `frontend`.
2. Confirm **Node.js Version** is `24.x`, **Build Command** is `npm run build`,
   and **Output Directory** is `dist`.
3. Set the Vercel Production environment variable:

   | Name | Value | Secret |
   | --- | --- | --- |
   | `VITE_API_BASE_URL` | `https://<render-service>.onrender.com` | No |
   | `VITE_MAP_TILE_URL` | HTTPS `{z}/{x}/{y}` template of a commercial or self-hosted tile service | No |
   | `VITE_MAP_TILE_ATTRIBUTION` | **required with a custom tile URL**: that provider's credit, plain text | No |

   Leaving `VITE_MAP_TILE_URL` unset uses the public OpenStreetMap tile
   servers. That is fine for development and light demos but **not for real
   traffic**: their policy forbids heavy use and offers no SLA. A custom URL
   without `VITE_MAP_TILE_ATTRIBUTION` falls back to OSM tiles and logs a
   console warning. The credit is escaped, so it cannot contain links.

   Use the HTTPS backend origin only—do not append `/api/v1`, credentials, or a
   trailing path. Vite embeds this value at build time, so redeploy after it
   changes.
4. Deploy. `frontend/vercel.json` rewrites all routes to `index.html`, allowing
   direct visits and refreshes at `/login`, `/register`, `/trips`, `/account`,
   and `/trips/:id`.

## Releasing a schema change (Render Free + auto-deploy)

Render Free has no Pre-Deploy Command, and Render and Vercel auto-deploy
`main`. For a release with migrations (for the map release: 0006 and 0007),
follow this order exactly:

1. **Check the PostgreSQL version.** Run `SHOW server_version;` against
   production and confirm it is at least 15. Stop here if it is not.
2. **Back up the database** from a trusted machine (for example `pg_dump`).
   Render Free PostgreSQL has no backups of its own.
3. **Switch the Render health check to `/health`** (Web Service → Settings →
   Health Check Path) for the duration of the release.
4. **Migrate manually with the new code.** From a trusted checkout of the
   release branch, with the production `DATABASE_URL` supplied as an
   environment variable (never committed or kept in shell history):

   ```bash
   cd backend
   APP_ENV=production python -m alembic upgrade head
   python -m alembic current   # expect: 0007 (head)
   ```

5. **Merge to `main`.** Wait for the Render backend deploy and the Vercel
   frontend deploy to finish.
6. **Restore readiness.** When `https://<render-service>.onrender.com/ready`
   returns 200 (`{"status":"ready"}`), set the health check path back to
   `/ready`.
7. **Smoke test production** with the acceptance checklist below, including
   the Map tab.

### Why this order

- `/ready` only passes when the database revision equals the **running
  code's** single Alembic head. The old backend accepts only `0005` and the
  new backend accepts only `0007`, so during the switch-over one of them always
  fails readiness. With the health check on `/ready`, Render would mark the
  live old service unhealthy right after the migration, or block the new
  deploy before it. `/health` is liveness-only and stays green for both.
- The schema goes first because the new backend needs the new tables from its
  first request. It is safe while the old backend is still serving: 0006 and
  0007 only **add** tables (`trip_places`, `geocoder_throttle`), a nullable
  `itinerary_items.place_id`, a foreign key and an index. Before this release
  the old `main` backend was run against a 0007 schema: registration, trips,
  invitations, itinerary create/edit/reorder, expenses, balances and trip
  deletion all worked, and only its `/ready` returned 503.
- The DDL takes brief locks on `itinerary_items`; run it at a quiet time.

### Rollback

1. Keep the health check on `/health` and redeploy the previous commit. The
   old backend runs correctly on the new schema; its `/ready` stays 503 while
   the database is at `0007`.
2. Only if the schema itself must be removed, run
   `python -m alembic downgrade 0005`. This drops `trip_places` and
   `geocoder_throttle` and the `place_id` column. Itinerary rows and their
   `location` text survive, but **all saved places and links are lost**, so
   restore from the backup if they matter.
3. Once the revision matches the deployed code, set the health check back to
   `/ready`.

## Final CORS sequence

1. Deploy the backend with a valid temporary HTTPS origin if needed to get its
   public URL.
2. Build/deploy Vercel using that Render URL as `VITE_API_BASE_URL`.
3. Copy the final Vercel production URL exactly, for example
   `https://<project>.vercel.app`.
4. Set Render `CORS_ORIGINS` to a JSON array containing only that exact origin:

   ```text
   ["https://<project>.vercel.app"]
   ```

5. Redeploy the Render service and verify both `/health` and `/ready` over
   HTTPS. Never use `*`; production configuration rejects non-HTTPS origins.

## Production acceptance checklist

- Verify Render `/health` returns `{"status":"ok"}` and `/ready` returns
  `{"status":"ready"}`.
- Open the Vercel URL; register two disposable users, log in, create a trip,
  invite/accept, and verify member roles.
- Create, edit, reorder, and delete itinerary items.
- Create/edit/delete an equal-split expense; verify backend-provided balances
  and settlement suggestions without client-side rounding.
- Log out, refresh a protected route, try an invalid session, and confirm
  routing and error handling remain correct.
- Refresh every SPA route; inspect HTTPS API requests and successful CORS
  preflight; check a narrow mobile viewport.
- Log in again and confirm the created data persists.
- Open a trip's **Map** tab: tiles load with the configured provider's credit;
  search (or add a manual place when search is disabled), link a place to an
  itinerary item, view the day route, suggest an order, and apply it.

## Troubleshooting

- **Backend won't start:** verify `APP_ENV=production`, a reachable
  `DATABASE_URL`, and a JWT key of at least 32 bytes. Inspect Render logs; do
  not paste secrets into logs or tickets.
- **`/ready` returns 503:** confirm the one controlled Alembic migration has
  completed (`alembic current` is `0007 (head)`), all nine core tables exist, and
  the database is reachable; `/health` distinguishes API liveness from
  dependency readiness.
- **Browser CORS error:** confirm `CORS_ORIGINS` is valid JSON with the exact
  Vercel HTTPS origin, no trailing slash or wildcard, then redeploy Render.
- **Frontend reaches localhost:** replace `VITE_API_BASE_URL` in Vercel with
  the Render HTTPS origin and redeploy; Vite does not change already-built
  bundles.
- **Vercel deep route 404:** keep `frontend/vercel.json` in the repository and
  ensure `frontend` is the project Root Directory.

For the shorter platform checklist, see [deployment-checklist.md](deployment-checklist.md).
