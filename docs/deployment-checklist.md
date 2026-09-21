# TripTogether Production Deployment Checklist

This is a manual runbook for Step 19B. It intentionally contains no real URL,
credential, account, or deployment command that creates cloud resources.

## Configuration matrix

| Variable | Vercel frontend | Render backend | Secret | Example |
| --- | --- | --- | --- | --- |
| `VITE_API_BASE_URL` | Yes, build-time | No | No | `https://<render-service>.onrender.com` |
| `DATABASE_URL` | No | Yes | Yes | Render internal PostgreSQL URL |
| `JWT_SECRET_KEY` | No | Yes | Yes | generated secure random value |
| `JWT_ALGORITHM` | No | Yes | No | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Yes | No | `30` |
| `APP_ENV` | No | Yes | No | `production` |
| `CORS_ORIGINS` | No | Yes | No | `["https://<vercel-project>.vercel.app"]` |

`VITE_API_BASE_URL` must be the backend **origin only**. The current client adds
`/api/v1/...` itself; do not append `/api/v1` to this variable.

## Manual deployment order

1. Review `git status` and `git ls-files`; confirm no `.env`, database URL, JWT
   secret, `node_modules`, `dist`, cache, or AppleDouble metadata is staged.
2. Push the reviewed repository to GitHub yourself. Do not include local `.env`
   files.
3. In Render, create a PostgreSQL instance and a Python Web Service in the same
   region. Prefer the database's internal connection URL for the backend.
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

6. Run `alembic upgrade head` once before normal traffic. On a paid Render Web
   Service, configure it as the pre-deploy command. On a free service, shell and
   one-off jobs are unavailable; use an intentionally controlled migration
   release process after choosing a plan, rather than placing migration in the
   web start command.
7. Set Render's HTTP health check path to `/ready`. It verifies both JWT
   configuration and PostgreSQL connectivity; `/health` is liveness only.
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

For a persistent portfolio demo, use a paid Render PostgreSQL plan in the same
region as the Render backend. Render's free PostgreSQL database expires after
30 days, has a 1 GB limit, and has no backups, so it is unsuitable for a stable
public demo. For a no-cost prototype, Neon Postgres is a simple alternative;
its free plan is aimed at prototypes/side projects and has current resource
allowances, so review its live limits before relying on it. A Neon external URL
also works because the backend normalizes standard `postgres://` and
`postgresql://` URLs to the existing psycopg driver.

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
