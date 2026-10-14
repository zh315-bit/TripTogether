# Collaborative Map P5: Web Map Tab

P5 adds a lazily loaded **Map** tab to the Trip workspace: place search, a
shared place pool with per-member colours, linking places to itinerary items,
each day's straight-line route, and a reviewed "suggest shorter order" flow.
It uses only endpoints from P2-P4 plus three small P5.0 fixes.

## P5.0 Fixes (commit a6626ec)

1. Backend `update_item`: switching `place_id` to a different place without
   sending `location` now refreshes `location` to the new place name.
   Re-sending the same place, unlinking with `null`, or sending `location`
   (including `null`) keeps what was given or stored.
2. Web client parses `place_id` (`number | null`) on itinerary items.
3. The itinerary panel's up/down reorder sends the displayed order as
   `expected_item_ids`. On 409 `ITINERARY_CONFLICT` it explains that another
   member changed the day and reloads, without retrying.

## Dependencies

| Package | Version | Licence | Why |
| --- | --- | --- | --- |
| `leaflet` | ^1.9.4 (2023-05) | BSD-2-Clause | Map rendering |
| `@types/leaflet` | ^1.9.22 (dev) | MIT | Types (pulls `@types/geojson`, MIT) |

**react-leaflet was deliberately not added.** react-leaflet 5.0.0 (React 19
compatible) and its `@react-leaflet/core` 3.0.0 are licensed Hippocratic-2.1,
which is not OSI-approved and adds ethical-use conditions some compliance
processes reject. With the developer's agreement, `LeafletMap.tsx` wraps
Leaflet directly (about 120 lines).

## Architecture

```text
TripDetailPage ──lazy()──▶ MapPanel (default export; own chunk + CSS)
                              ├─ PlaceSearch     GET /geocode (submit only)
                              ├─ PlacePool       places CRUD, manual add, in-page delete confirm
                              ├─ DayRoutePanel   GET /route, POST /optimize, preview, apply
                              └─ LeafletMap      the only module importing leaflet
ItineraryPanel ── "Linked place" select ── GET /places (main bundle, no Leaflet)
```

- **Imperative bridge.** `LeafletMap` creates the map once in an effect,
  keeps one `LayerGroup`, and redraws markers and polylines when props change.
  It refits bounds only when the set of plotted positions changes, so redraws
  don't fight the user's panning. React owns state; Leaflet owns its DOM.
- **XSS boundary.** Place names come from other members. Marker labels and
  tooltips are built with `textContent` and passed to Leaflet as elements,
  never as HTML strings. A real-Leaflet jsdom test injects
  `<img onerror=...>` and asserts nothing is parsed. Attribution HTML is a
  static constant.
- **No broken default icons.** All markers are `divIcon`s (member initial or
  stop number), which sidesteps the Vite/Leaflet default-icon path problem.
  Stop numbers are offset via `iconAnchor`, because Leaflet positions icons
  with an inline `transform` that CSS cannot override.
- **Tiles.** `VITE_MAP_TILE_URL` (HTTPS with `{z}/{x}/{y}`, else the default
  `https://tile.openstreetmap.org/{z}/{x}/{y}.png`). Leaflet's attribution
  control shows "© OpenStreetMap contributors"; search results show a separate
  Nominatim/OSM credit.
- **Member colours.** Colour = index in `GET /members` (stable across pages)
  from an 8-colour palette chosen by script so every colour has ≥4.5:1
  contrast with the white initial and ≥3:1 with the dark ink `#17233a`. A unit
  test checks these ratios; it caught an initial fallback grey at 2.78:1.
  Colour is never the only cue: initials on markers, names in tooltips, list
  and legend.
- **Search.** One request per submit; the button is disabled in flight and
  shows "Retry in Ns" after 429 using `ApiError.retryAfter`. The backend now
  sends `Access-Control-Expose-Headers: Retry-After`; without it a
  cross-origin browser reads `null`.
- **Optimize.** Preview lists Current and Suggested side by side with totals,
  the km saved, and why each anchor is fixed (start / timed / no place); the
  map overlays the suggestion as a dashed line. Apply sends `proposed_item_ids`
  with `expected_item_ids = original_item_ids`; on 409 it shows the conflict
  and reloads route and itinerary without retrying. 422 shows the server
  reason (e.g. the 50-item cap). `changed: false` says the order is already short.
- **Itinerary form.** "Linked place" select (None + pool). Choosing a place
  fills Location with its name unless the user typed their own text. The add
  and edit forms' `initial` values are memoized so the asynchronous place load
  cannot reset what the user is typing.

## Bundle Size (`npm run build`)

| Asset | Before P5 | After P5 |
| --- | --- | --- |
| Main JS `index-*.js` | 312.26 kB (gzip 94.17 kB) | 317.14 kB (gzip 95.52 kB) |
| Main CSS `index-*.css` | 14.69 kB (gzip 3.89 kB) | 14.69 kB (unchanged) |
| Lazy `MapPanel-*.js` (incl. Leaflet) | — | 168.67 kB (gzip 49.93 kB) |
| Lazy `MapPanel-*.css` (incl. Leaflet CSS) | — | 19.61 kB (gzip 7.66 kB) |

Main JS grew by 4.9 kB (1.35 kB gzip) for the itinerary place select,
`api/places.ts` and `Retry-After` parsing. The main bundle does not contain
the tile URL string, which confirms Leaflet is only in the lazy chunk.

## Tests

- `src/components/map/MapPanel.test.tsx` (mocks `LeafletMap` only): tab
  keyboard/ARIA, colours and names, search only on submit, in-flight disable,
  429 countdown, 503 disabled/unavailable, provider fields on save, 409
  duplicate, manual add via map click, coordinate validation, edit, in-page
  delete (no `window.confirm`) with unlink message, route legs/total/
  disclaimer/unlocated list, optimize preview, `keep_first` toggle, apply body,
  cancel without write, `changed: false`, 409 reload without retry, 422 cap,
  anchor labels.
- `src/components/map/LeafletMap.test.tsx` (real Leaflet in jsdom): HTML
  injection rendered as text, OSM attribution, polylines redrawn without
  duplicates, picking on/off, tile URL validation.
- `src/pages/MapTabLazy.test.tsx`: Suspense fallback held open by a gated mock.
- `src/api/places.test.ts`, `src/utils/memberColors.test.ts`, `client.test.ts`
  (`Retry-After`), `collaboration.test.ts` / `Collaboration.test.tsx`
  (`place_id`, linked-place select, guarded manual reorder and conflict).
- Backend: place-switch location refresh, CORS exposes `Retry-After`, and a
  geocode → save round trip.

Results: frontend lint 0 warnings, typecheck clean, **141 passed** (1 opt-in
real-auth test skipped as before), build OK; backend with PostgreSQL
**780 passed**.

## Manual Browser Walkthrough

Vite dev server plus local FastAPI with `GEOCODER_PROVIDER=fake` (no requests
to public Nominatim). Two random disposable local accounts; trip seeded through
the API, then driven in the browser at 1280×900 and 375×812:

1. Map tab lazy-loaded; OSM tiles and attribution shown; Bob's places red "B".
2. Typing sent no request; Enter sent exactly one `/geocode`.
3. Added Senso-ji and Tokyo Tower (blue "A"); re-adding showed "already in the
   place pool". **Found a real bug here:** saving a `fake` result returned 422,
   because the place schema accepted only `nominatim`. Unit tests used mocked
   `nominatim` data and missed it. Fixed by accepting every provider `/geocode`
   can return, with a new search → save round-trip test.
4. Added a hotel manually by coordinates; linked Senso-ji through the
   itinerary edit form (Location auto-filled).
5. Day route: numbered stops, per-leg km, 32.7 km total, disclaimer, lunch
   listed as unlocated.
6. Suggest: 32.7 → 19.3 km preview with anchor labels and dashed line; Apply
   gave one `PATCH /reorder` 200. Suggest again: "already a short route".
7. Real conflict: Bob reordered via API after Alice's preview; Apply gave one
   409, the conflict message, and a reload of Bob's order, with no retry.
8. Deleted Tokyo Tower via the in-page confirmation: "1 itinerary item was
   unlinked; location text was kept."
9. Mobile 375 px: stacked layout, no horizontal page scroll
   (`scrollWidth == clientWidth`), preview columns stacked; Cancel wrote nothing.

Screenshots (`docs/screenshots/`): `map-desktop-route.jpg`,
`map-desktop-optimize-preview.jpg`, `map-desktop-applied.jpg`,
`map-desktop-conflict.jpg`, `map-desktop-delete-confirm.jpg`,
`map-mobile-overview.jpg`, `map-mobile-optimize-preview.jpg`.

User browser acceptance is still pending, as for Steps 14-16.

## How to Run Locally

```bash
# terminal 1 (repository root, migrated database)
cd backend
GEOCODER_PROVIDER=fake CORS_ORIGINS='["http://127.0.0.1:5173"]' \
  ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# terminal 2
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173`, sign in, open a trip, then choose the **Map** tab.
`fake` search knows Senso-ji, Tokyo Tower, Shibuya Crossing, Kyoto Station
and Eiffel Tower.
