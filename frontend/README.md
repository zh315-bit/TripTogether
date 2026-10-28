# TripTogether Frontend

React 19 + TypeScript + Vite single-page app for TripTogether. See the [root README](../README.md) for the full project overview, architecture and screenshots.

## Setup

Node 24 LTS and npm. From this directory:

```bash
npm ci
cp -n .env.example .env     # VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

## Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Vite dev server with HMR |
| `npm test` | Vitest + Testing Library (jsdom) |
| `npm run lint` | ESLint with zero warnings allowed |
| `npm run typecheck` | `tsc -b` across app and node configs |
| `npm run build` | Type-check then produce `dist/` |
| `npm run preview` | Serve the production build locally |

## Structure

```text
src/
  api/          typed fetch client, base URL and error contract
  auth/         AuthContext, session restore, protected routes
  pages/        landing, register, login, trips, account
  workspace/    TripWorkspace: map + sidebar panels (places, itinerary, expenses, balances, members, trip)
  components/   shared UI; components/map wraps Leaflet directly (LeafletMap, PlacePool, useTripMap)
  types/        contracts mirroring backend schemas
  utils/        formatting helpers
  test/         test setup
```

## Configuration

Only `VITE_API_BASE_URL` is read, at build time, and it is embedded in the bundle. Never put secrets in `VITE_*` variables. Optional `VITE_MAP_TILE_URL` and `VITE_MAP_TILE_ATTRIBUTION` switch the map to a custom tile provider for production traffic.

The session token is held in `sessionStorage`; the backend remains the authority for every authorisation decision.
