# Known Limitations

Step 11 hardens the implemented MVP surface. It is not a claim that the service
is production secure, production deployed, or that the full-stack web MVP is done.

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

- No live push, WebSocket, offline sync, version/ETag conflict detection or
  idempotency keys. Same-field writes are Last Write Wins.
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
- All repository files were untracked when Step 11 was reviewed; no commit was
  made by this task. `.gitignore` protects local secrets and AppleDouble files.

## Client Status

The React + TypeScript + Vite foundation and Step13 authentication UI are
user-accepted. Step14 Trip management and Step15 collaboration/itinerary UI are
implemented and integration-tested; their user browser acceptance is pending.
Step12 covers the foundation; Step13 covers authentication UI/API integration
and a web-security-informed token storage decision; subsequent steps add the
business screens, E2E polish, deployment and demo. Steps14-16 are implemented;
Steps17-20 are NOT STARTED.
The client uses centralized base URL/API/auth layers and typed contracts.
Tokens are held in sessionStorage, which same-origin JavaScript/XSS can read.
Refresh restores through /me, but there is no refresh token, token revocation,
OAuth, MFA, password reset or email verification. Logout removes a client-held
token only. Tab duplication/restoration may preserve or copy session state.
The UI reacts to rejected authenticated requests; it does not continuously
poll for token expiration. Backend authorization remains mandatory. Step14/15
provide Trip management, members, invitations, shared itinerary, expenses and
balances. The financial UI remains dependent on backend-calculated results and
does not provide payment processing.
HarmonyOS is deferred to potential native/mobile future work.
This document records constraints, not permission to implement them now.
