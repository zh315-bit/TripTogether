# Known Limitations

This document records the known gaps of the implemented MVP surface. It is not
a claim that the service is production secure or feature complete.

## Identity and Security

- No refresh token, selective logout blacklist/revocation, password reset,
  email verification, OAuth, account deletion or password-change workflow.
- A stolen Bearer token remains valid until expiry (or global key rotation).
  JWT is signed, not encrypted; never place it in a URL, log or repository.
- Secret validation rejects missing, short, blank and the example placeholder
  keys; it cannot prove entropy. Operators must generate a random key.
- Registration duplicate errors and inviting registered emails disclose account
  existence. Login uses one generic credential error and dummy hash verification,
  but this is not a formal constant-time or enumeration-proof guarantee.
- No rate limiting, request-size policy, abuse infrastructure or load testing.
  Argon2 work requires resource limits before public exposure.
- CORS is browser policy, not authentication or a network access firewall.
  Native clients/non-browser tools can send requests without an Origin header.
- Public `/docs`, `/openapi.json`, `/redoc`, `/health`, `/ready` remain enabled.
  HTTPS, proxy trust, network exposure and restricted DB credentials are
  deployment/operator responsibilities.

## Collaboration and Money

- Live updates are Server-Sent Events fanned out by an in-process broker:
  correct for one API instance, not across several (that needs PostgreSQL
  LISTEN/NOTIFY or Redis behind the same interface). Events say *what*
  changed, not the new values; clients refetch. A slow consumer gets one
  `resync` instead of the backlog. No offline sync or idempotency keys.
- Conflict detection is opt-in per request: a PATCH without `If-Match` is
  still Last Write Wins. Versions are per row; a reorder bumps the versions of
  the moved items. Deletes do not check `If-Match`.
- No member removal/leave/ownership transfer. Historical expense identity needs
  a deliberate design before adding those flows.
- Invitations target existing registered users; no public code/link or email
  delivery. Accept/reject is a one-way decision; repeats return409.
- Trips use hard deletion, not archive/soft delete; related records cascade.
- One currency in the current expense ledger, no exchange rates or conversion.
  With no expenses, currency is null. A sole expense can be relabeled, not
  converted. Trip has no separate currency column.
- Currency is three uppercase letters, not an official registry. All accounting
  uses two decimal places, including currencies whose real minor units differ.
- Equal split only; deterministic remainder by ascending user ID. No custom
  weights/percentages. Balances use stored exact shares.
- Settlement suggestions are derived calculations, not payment processing,
  repayment history or a globally minimum-number-of-transfers guarantee.
- Itinerary DATE/time are local schedule values without timezone identity;
  no overnight item. Expense dates may precede the trip.

## Scale and Operations

- Trip, invitation, member, itinerary and expense lists are unpaginated.
  Add bounded list contracts before large-scale usage; trips/invitations/
  expenses are first candidates. Daily reorder must still validate the complete
  day, and balances must aggregate the full ledger, not a display page.
- Constant query count is not constant cost. Large lists, ledger aggregates,
  individual SQL statements and lock waits remain unbounded by a global
  statement timeout; no benchmark/capacity claim is made.
- Writes serialize on a parent Trip row to preserve current invariants. This
  is deliberate for small groups, not a high-throughput design.
- Production startup checks configuration, not database reachability.
  `/ready` checks JWT configuration and SELECT1, not schema version, permissions
  for every business table, backups, external services or available capacity.
- PostgreSQL connect/pool wait timeouts are five seconds; readiness still
  consumes a database connection. Do not probe it at extreme frequency.
- Logging is intentionally minimal: no request access log, raw traceback or
  user input. This avoids obvious credential disclosure but limits diagnosis;
  there is no durable log aggregation, correlation ID or alerting.
- The safe error middleware cannot replace a response once its headers have
  started. Existing routes are nonstreaming; streaming would need new review.
- Standard CORS preflight rejection is a plaintext400 transport response,
  outside the JSON business error contract. Proxy/server errors may also be
  non-JSON. Clients must handle transport failure.
- Legacy paths remain available with legacy `detail` errors; no removal date
  has been set. New clients must never depend on these aliases.
- No Docker/deployment pipeline, secret manager, dependency lockfile, dependency
  vulnerability scan, migration rollout/backups/restore drill or TLS setup
  was added. Existing dependency ranges are not a reproducible deployment lock.
- DB engine/factory settings are cached; restart after changing configuration.
  JWT keys must be stable and shared across workers.

## Place Search (Map P3)

- Public Nominatim is best-effort with no SLA; access may be withdrawn and the
  usage policy may change. Larger usage needs a commercial provider or a
  self-hosted instance (swap the provider; the API contract stays the same).
- The one-request-per-second limit is enforced across all workers/instances by
  the single `geocoder_throttle` row. Excess searches get 429 immediately
  instead of queueing, so one heavy user can delay others; there is no
  per-user fairness.
- The result cache is per process (24 h TTL, 1000 entries) and is lost on
  restart; only the throttle is shared.
- No automatic retries. Upstream 403/429 starts a 60-second shared cooldown.
- Results use Nominatim's default language; Accept-Language is not forwarded.
- Saved search results are trusted as submitted: the server validates
  coordinate ranges and identifier format but does not re-verify the
  coordinates against the provider.

## Routes and Optimization (Map P4)

- Distances are straight-line (great-circle) kilometres between consecutive
  located items. They are not road, walking or transit distance or time, and a
  shorter straight line does not guarantee a faster real trip.
- Optimization is nearest neighbour plus 2-opt from every first stop. It is a
  heuristic, not a guaranteed shortest route; on seeded random tests it matched
  the exact optimum in about 98% of small cases and was within 12% otherwise.
- Timed items, unlocated items and (by default) the first item are fixed;
  only runs between them are reordered. There are no time windows, opening
  hours or durations, and no fixed final stop other than a following anchor.
- At most 50 items per day can be optimized.
- Itinerary `location` is a text snapshot taken when a place is linked; later
  place renames do not update it.

## Web Map (Map P5)

- Default tiles come from the public OpenStreetMap tile service, which is
  best-effort, has no SLA and forbids heavy use, prefetching and offline
  download. It is not suitable for production traffic: before launch, set
  `VITE_MAP_TILE_URL` to a commercial or self-hosted tile service together
  with `VITE_MAP_TILE_ATTRIBUTION` (that provider's required credit, plain
  text). A custom URL without a credit falls back to OSM tiles with one
  console warning. Custom credits cannot contain links because they are
  escaped; both values are build-time and need a frontend rebuild.
- react-leaflet was evaluated and not used: react-leaflet 5.0.0 and
  @react-leaflet/core 3.0.0 are Hippocratic-2.1 (not OSI-approved). The app
  wraps Leaflet (BSD-2-Clause) directly in `LeafletMap.tsx`.
- The map is not live: other members' changes appear after reload or after an
  action that refetches (apply, delete). Conflicts are detected, not merged.
- Map-click picking needs a pointer; keyboard and screen-reader users enter
  coordinates in the manual form instead. Markers are focusable and named, and
  every map fact is also listed in text.
- The map does not refit when you pan unless the set of plotted positions
  changes; showing a suggestion refits to include the dashed line.
- With five tabs, the Trip workspace tab strip scrolls horizontally on narrow
  phones (it already used `overflow-x: auto`).
- The pre-existing `source-map-js` advisory (GHSA-68fv-2mgg-jv7q, build-tool
  chain only: vite/postcss and jsdom) was fixed with a non-breaking
  `npm audit fix` (1.2.1 → 1.2.2, lockfile only); `npm audit` now reports 0.
- Saving a search result requires `provider` to match the running
  `GEOCODER_PROVIDER`. This is application policy, not a database constraint:
  places saved under an earlier provider stay valid after a switch. With search
  disabled, only manual places can be added.

## Client Status

The React + TypeScript + Vite client covers authentication, trip management,
members and invitations, the shared itinerary, the collaborative map, expenses
and balances; it is deployed and user-accepted.
The client uses centralized base URL/API/auth layers and typed contracts.
Tokens are held in sessionStorage, which same-origin JavaScript/XSS can read.
Refresh restores through /me, but there is no refresh token, token revocation,
OAuth, MFA, password reset or email verification. Logout removes a client-held
token only. Tab duplication/restoration may preserve or copy session state.
The UI reacts to rejected authenticated requests; it does not continuously
poll for token expiration. Backend authorization remains mandatory. The
financial UI remains dependent on backend-calculated results and does not
provide payment processing.
This document records constraints, not permission to implement them now.
