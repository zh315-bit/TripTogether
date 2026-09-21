# TripTogether Frontend

The frontend foundation uses React, TypeScript, Vite, React Router and native
`fetch`. It provides the shell, health check and Step13 registration/login,
session restore, protected account and local logout. Trip UI is deferred.

## Setup

Use Node24 LTS and npm (verified with Node24.21.0/npm11.19.0).
Current Vite requires Node20.19+ or22.12+; this project was verified with24.
From this directory:

```bash
npm ci
cp -n .env.example .env
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Set `VITE_API_BASE_URL` to the backend origin, for example
`http://127.0.0.1:8000`. Frontend environment values are public and must not
contain database credentials or JWT secrets.
The origin must not contain credentials, query parameters or `/api/v1`.
`/health` is public; future business calls explicitly use `/api/v1/...`.
Missing/invalid configuration displays Unavailable, not a hardcoded fallback.

In a second terminal start the existing backend:

```bash
cd /Volumes/Elements/TripTogether/backend
source /private/tmp/triptogether-step1-venv/bin/activate
CORS_ORIGINS='["http://127.0.0.1:5173","http://localhost:5173"]' \
  python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:5173`. Expect Connected. Stop the backend and refresh
to see Unavailable; restart it and Retry connection to recover.
`/missing` shows Not Found. Check keyboard focus and a mobile-width viewport.
Both processes stop with Ctrl+C. If a port is occupied, use a free port and
update the API URL/CORS origin accordingly; do not kill unrelated servers.

Vite loads `frontend/.env`, not the root backend `.env`. Configuration is
embedded in a build; editing a deployed `.env` does not change built JavaScript.
There is no database readiness or automatic health polling in this step.

Authentication needs a valid backend JWT_SECRET_KEY and migrated PostgreSQL.
Check backend `/ready`, then `/register` -> `/login` -> `/account`.
Reload should restore through `/api/v1/auth/me`; Logout should return home;
anonymous `/account` redirects to login. Passwords are not stored; only the
access token uses sessionStorage. Same-origin JavaScript/XSS can read it.
There is no refresh token or server-side logout revocation.

Live verification (from this directory with the existing backend environment):

```bash
/private/tmp/triptogether-step1-venv/bin/python scripts/verify_auth.py
```

This opt-in check creates/cleans a random PostgreSQL user and runs frontend
flows over actual HTTP in jsdom. The normal test command skips that live case.
No real credentials are needed or printed. Browser visual acceptance is separate.

## Checks

```bash
npm run test
npm run typecheck
npm run lint
npm run build
```

The build produces `dist/`; it does not deploy it. A future SPA host must
serve `index.html` for application paths. No deployment configuration is added.
Use current browsers supporting `AbortSignal.any` and `AbortSignal.timeout`.
