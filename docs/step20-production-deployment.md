# Step 20A — Production Deployment Runbook

TripTogether is deployed on Vercel, Render Web Service, and Render PostgreSQL.
Use this runbook for controlled releases and new database setup. The project
owner confirmed production registration and Alembic `0005 (head)` after the
September 2026 missing-table incident.

## Production architecture

```text
Browser → Vercel React SPA → HTTPS → Render FastAPI → Render PostgreSQL
```

The Vercel build contains the public API origin only. Render owns all backend
runtime configuration and secrets. PostgreSQL remains the source of truth for
trips, memberships, itineraries, expenses, balances, and settlements.

## Render PostgreSQL and backend

1. In Render, create a PostgreSQL database and a Python Web Service in the
   same region. Do not add test users or seed data.
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

   Generate the JWT value locally; never save it in the repository:

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

The backend accepts provider-standard `postgres://` and `postgresql://` URLs,
normalizing them internally to the existing `postgresql+psycopg` SQLAlchemy
driver. Local development URLs are unchanged.

## Controlled migration

After `DATABASE_URL` is configured, run this exactly once per release before
starting or scaling API workers:

```bash
cd backend
APP_ENV=production python -m alembic upgrade head
```

Render Free has no Pre-Deploy Command. For that plan, run the migration manually
from a trusted local environment with the Render database's external URL in
`DATABASE_URL`, then unset it. Do not save the URL in the repository or shell
history. On a plan that supports it, use a single pre-deploy release command.
Check `python -m alembic current` after the migration; this release expects
`0005 (head)`. Do not put `alembic upgrade head` in the web-service start
command, because multiple workers could race to migrate.

Set Render's health check path to `/ready`. It verifies JWT configuration,
PostgreSQL connectivity, the Alembic head, and the seven core tables. `/health`
is liveness-only and stays 200 even when the schema is not ready.

## Vercel frontend

1. In Vercel, import the same GitHub repository and set **Root Directory** to
   `frontend`.
2. Confirm **Node.js Version** is `24.x`, **Build Command** is `npm run build`,
   and **Output Directory** is `dist`.
3. Set the Vercel Production environment variable:

   | Name | Value | Secret |
   | --- | --- | --- |
   | `VITE_API_BASE_URL` | `https://<render-service>.onrender.com` | No |

   Use the HTTPS backend origin only—do not append `/api/v1`, credentials, or a
   trailing path. Vite embeds this value at build time, so redeploy after it
   changes.
4. Deploy. `frontend/vercel.json` rewrites all routes to `index.html`, allowing
   direct visits and refreshes at `/login`, `/register`, `/trips`, `/account`,
   and `/trips/:id`.

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

## Troubleshooting

- **Backend won't start:** verify `APP_ENV=production`, a reachable
  `DATABASE_URL`, and a JWT key of at least 32 bytes. Inspect Render logs; do
  not paste secrets into logs or tickets.
- **`/ready` returns 503:** confirm the one controlled Alembic migration has
  completed (`alembic current` is `0005 (head)`), all core tables exist, and
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
