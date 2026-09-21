# AGENT.md

## 1. Project Overview

TripTogether is a full-stack collaborative travel planning web application.

The application allows small groups to:

- Create shared trips
- Invite collaborators
- Maintain shared itineraries
- Record group expenses
- Calculate expense balances
- Receive settlement suggestions (not actual payments)

The backend MVP (Steps 1-11) is complete. The planned full-stack MVP uses:

- React / TypeScript / Vite for the web client (foundation and authentication UI accepted)
- Python / FastAPI for the backend
- PostgreSQL for persistent storage
- SQLAlchemy for database access
- JWT for authentication

The current direction is Backend -> React Web Frontend -> Deployment -> Demo.
HarmonyOS development is deferred; a native/mobile client is potential future
work, not the current MVP requirement. This is a priority change to support a
browser-accessible portfolio demo, not a judgment against the platform.

The project is developed by a single developer.

Therefore, simplicity, maintainability, testability, and learning value are more important than unnecessary architectural complexity.

---

## 2. Primary Development Principle

Do not optimize for the maximum number of features.

Optimize for:

1. Correctness
2. Understandable architecture
3. Maintainable code
4. Testability
5. A complete end-to-end user workflow

The MVP must remain small enough for one developer to understand the entire system.

---

## 3. MVP Scope

The agent MUST prioritize only the following features:

1. User registration and login
2. JWT authentication
3. Trip CRUD
4. Trip membership
5. Invitations to registered users with acceptance/rejection (no public codes)
6. Shared itinerary CRUD
7. Shared expense tracking
8. Equal expense splitting
9. Member balance calculation and settlement suggestions
10. React web client integration
11. Testing
12. Deployment

Features outside this list should not be implemented unless explicitly requested by the developer.

---

## 4. Out-of-Scope Features

Do NOT implement the following during the MVP without explicit approval:

- AI itinerary generation
- LLM integration
- Recommendation systems
- Real-time chat
- Social feeds
- Payment processing
- Hotel booking
- Flight booking
- Complex map navigation
- Microservices
- Kubernetes
- Event-driven architecture
- Unnecessary message queues
- Unnecessary caching infrastructure

Do not introduce technology simply to make the project appear more sophisticated.

---

## 5. Architecture Rules

Use a modular monolith.

Do NOT convert the backend into microservices.

Preferred architecture:

```text
React + TypeScript Web Client (foundation implemented)
       ↓
 REST / JSON /api/v1
       ↓
 FastAPI API Layer
       ↓
 Service Layer
       ↓
 SQLAlchemy
       ↓
  PostgreSQL
```

Each layer should have a clear responsibility.

---

## 6. Backend Structure

Preferred structure:

This is guidance, not a request to create empty folders. Current routers are
in `app/api/`; `main.py` composes `/api/v1` without a separate v1 directory.
The repository layer is optional, and Docker belongs to Step18, not this task.

```text
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   ├── core/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── repositories/
│   ├── db/
│   └── main.py
│
├── tests/
├── migrations/
├── requirements.txt
└── Dockerfile
```

### `api/`

Responsible for HTTP request handling.

Should:

- Validate incoming requests
- Call service functions
- Return HTTP responses

Should NOT contain complex business logic.

### `services/`

Responsible for business logic.

Examples:

- Joining a trip
- Validating permissions
- Calculating expense splits
- Calculating member balances

### `models/`

Contains database models.

### `schemas/`

Contains request and response schemas.

### `repositories/`

Contains database access logic when abstraction is useful.

Avoid unnecessary repository abstractions for trivial operations.

### `core/`

Contains application-wide configuration such as:

- Environment settings
- Authentication
- Security utilities

---

## 7. Coding Rules

### General

Prefer readable code over clever code.

Functions should have one clear responsibility.

Avoid premature abstraction.

Avoid large functions.

Avoid duplicated business logic.

Use descriptive names.

Do not introduce design patterns unless they solve a real problem in the project.

### Python

Use:

- Type hints
- Pydantic models
- Clear exception handling
- Async FastAPI endpoints where appropriate

Follow standard Python conventions.

Avoid:

- Global mutable state
- Wildcard imports
- Deeply nested control flow
- Unnecessary metaprogramming

---

## 8. Database Rules

PostgreSQL is the source of truth.

Core tables:

- `users`
- `trips`
- `trip_members`
- `trip_invitations`
- `itinerary_items`
- `expenses`
- `expense_splits`

Relationships must be explicitly defined.

Use foreign keys.

Use appropriate unique constraints.

Use timestamps where useful.

Database schema changes must use reviewed Alembic migrations.
Preserve applied migrations; do not use create_all as a migration substitute.

Do not manually modify production database structure.

---

## 9. Authentication & Authorization

Authentication and authorization must be treated separately.

Authentication answers:

> Who is the user?

Authorization answers:

> Is this user allowed to perform this action?

All protected endpoints must verify authentication.

Trip-related operations must verify trip membership.

Sensitive operations may require trip ownership.

Never trust a user ID supplied by the client when the authenticated user's identity should be used.

Passwords must never be stored in plaintext.

---

## 10. Expense Calculation Rules

Expense logic is an important business component and must remain independently testable.

For the MVP:

- One member pays an expense
- Multiple members may participate
- Expenses are split equally among selected participants

Example:

```text
Alice pays $90.

Participants:
- Alice
- Bob
- Charlie

Each share = $30.

Alice paid: $90
Alice owes: $30

Net balance:
Alice: +$60
Bob:   -$30
Charlie: -$30
```

Financial calculations must NOT use binary floating-point values.

Use `Decimal` or an integer representation of the smallest currency unit.

Expense calculation logic must have unit tests.

---

## 11. API Design Rules

Use RESTful conventions.

Example:

```text
GET    /api/v1/trips
POST   /api/v1/trips
GET    /api/v1/trips/{trip_id}
PATCH  /api/v1/trips/{trip_id}
DELETE /api/v1/trips/{trip_id}
```

Step11's contract is the source of truth:25 versioned business operations plus
`/health` and `/ready`,27 formal operations in total. Original business paths
are compatibility aliases only. See `docs/api-inventory.md`, OpenAPI and
`docs/client-integration.md`; do not create a second API for the frontend.

Use appropriate HTTP status codes.

Examples:

```text
200 OK
201 Created
204 No Content
400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict
422 Unprocessable Entity
```

Return consistent error structures.

The formal error shape is `{"error":{"code":"...","message":"...","details":[]}}`.
Keep stable codes and field/reason details; never echo sensitive raw inputs.
Preserve hidden404 authorization and existing money-string success contracts.

Do not expose internal exceptions to clients.

---

## 12. Testing Requirements

Tests are part of the feature, not optional cleanup.

Priority areas:

1. Authentication
2. Authorization
3. Trip membership
4. Invitation logic
5. Expense splitting
6. Balance calculation

For important business logic:

> **No test = not complete.**

Every bug fix should include a regression test when practical.

---

## 13. Security Rules

Never commit:

- Passwords
- API keys
- Database credentials
- JWT secrets
- Cloud credentials

Use environment variables.

Maintain:

```text
.env.example
```

Do not commit:

```text
.env
```

Validate all user input.

Check resource ownership and membership before modification.

---

## 14. Git Rules

Prefer small, focused commits.

Good examples:

```text
feat: add user registration
feat: implement trip creation
feat: add trip invitation flow
feat: implement equal expense split
test: add expense calculation tests
fix: prevent non-member trip access
docs: update API documentation
```

Avoid commits such as:

```text
update
fix stuff
changes
final
```

---

## 15. Agent Behavior

The coding agent is an assistant, not the project owner.

Before implementing a feature, the agent should:

1. Inspect the existing code
2. Identify the relevant modules
3. Explain the planned change
4. Implement the smallest reasonable change
5. Add or update tests
6. Run relevant tests
7. Summarize the result
8. Update `RECORD.md`

The agent must NOT silently redesign the architecture.

The agent must NOT add major dependencies without explaining why.

The agent must NOT implement unrelated features.

The agent must NOT implement future roadmap features unless explicitly requested.

---

## 16. Learning Requirement

This project is intended to demonstrate the developer's engineering ability.

The agent should not hide important implementation details.

For significant changes, explain:

- What changed
- Why it changed
- Which files are important
- How data flows through the feature
- What the developer should understand
- How the implementation can be tested manually

The developer should be able to explain every major component during a technical interview.

---

## 17. RECORD.md Requirement

After completing a meaningful development step, update `RECORD.md`.

Each entry should follow this structure:

```markdown
## YYYY-MM-DD — Feature Name

### What Was Implemented

Brief description of the completed work.

### Files to Review

- `path/to/file.py`
- `path/to/another_file.py`

### Key Code to Understand

Explain the most important implementation logic.

### Architecture Concept

Explain the engineering concept demonstrated by this feature.

### How to Test

Provide commands and manual testing steps.

### Problems Encountered

Describe bugs, design issues, or implementation challenges.

### What I Learned

Summarize the important concepts learned during this step.

### Next Step

Specify exactly one recommended next development task.
```

The purpose of `RECORD.md` is to ensure that the developer understands the code rather than only generating it.

---

## 18. Definition of Done

A feature is complete only when:

- Implementation is finished
- Validation is handled
- Authorization is handled when applicable
- Error cases are handled
- Relevant tests pass
- Documentation is updated when necessary
- `RECORD.md` is updated for meaningful milestones

Do not mark partially implemented functionality as complete.

For visual frontend steps, passing automated tests alone is insufficient:
provide startup commands, the browser URL, manual steps and expected results.
Have the user verify the browser experience; explicitly state when that
acceptance is still pending or screenshots are needed.

---

## 19. Development Order

This current web roadmap supersedes the original mobile-oriented plan.
Historical Step1-11 numbering/results in RECORD.md must not be rewritten.

```text
Step 1-11  Backend MVP                                  COMPLETE
Step 12    React + TypeScript Frontend Foundation        COMPLETE; USER ACCEPTED
Step 13    Authentication UI + API Integration           COMPLETE; USER ACCEPTED
Step 14    Trip Dashboard + Trip Management              IMPLEMENTED; USER ACCEPTANCE PENDING
Step 15    Collaboration + Shared Itinerary UI           IMPLEMENTED; USER ACCEPTANCE PENDING
Step 16    Expense + Balance UI                         IMPLEMENTED; USER ACCEPTANCE PENDING
Step 17    Frontend Polish + E2E Integration             NOT STARTED
Step 18    Docker + Deployment                          NOT STARTED
Step 19    GitHub README + Live Demo                     NOT STARTED
Step 20    Resume + Interview Preparation               NOT STARTED
```

Do not skip ahead or automatically enter the next step. This documentation
migration starts none of Steps12-20. Step19 polishes the final demo presentation;
documentation and testing remain required throughout development.

---

## 20. Current Priority

The current priority should always be determined by:

1. Checking the latest entry in `RECORD.md`
2. Checking unfinished MVP requirements
3. Selecting the next smallest logical development step

The backend Steps1-11, Step12 and Step13 are complete and user-accepted. Step14,
Step15 and Step16 are implemented with browser acceptance pending. After
acceptance, the next recommended task is Step17, Frontend Polish + E2E
Integration, only when requested.
Do not rebuild the backend or begin advanced features to support the new client.

---

## 21. Completion Reporting

After every development task, the agent must provide a concise completion report containing:

### Completed

What was completed.

### Files Changed

Which files were created or modified.

### Important Code

Which code the developer should read carefully.

### Tests

What tests were executed and whether they passed.

### Manual Verification

How the developer can verify the feature manually.

### Next Step

Exactly one recommended next development task.

Do not automatically begin the next task unless explicitly instructed.

---

## 22. Frontend Technology and Directory

Framework: React. Language: TypeScript. Build tool: Vite.
Do not substitute Next.js, Angular, Vue or Svelte, or introduce Redux, MobX,
GraphQL, Firebase or Supabase without an explicit requirement and decision.
Additional dependencies must solve a concrete need; explain them before adding.

Future frontend code belongs in `frontend/`:

```text
frontend/
├── src/
│   ├── api/
│   ├── components/
│   ├── pages/
│   ├── hooks/
│   ├── types/
│   ├── utils/
│   └── assets/
├── public/
└── ...
```

This is a future structure, not permission to create directories or install
Node dependencies during the roadmap migration.

## 23. Frontend API and Domain Boundaries

Use a centralized `frontend/src/api/` layer:
React component -> API layer -> /api/v1 -> FastAPI -> Service -> SQLAlchemy
-> PostgreSQL. Do not scatter fetch calls across components.
The client must not connect directly to PostgreSQL, bypass services, rewrite
the backend or create a parallel API.

Frontend responsibilities: UI, interaction, form state, loading/empty/error
states, API communication and display. Backend responsibilities: authentication,
authorization, business rules, expense splitting, balances, settlement
suggestions and database consistency. UI permission hints never replace server
authorization.

Use explicit TypeScript request/response types, including User, Trip, TripMember,
Invitation, ItineraryItem, Expense, ExpenseSplit, Balance, SettlementSuggestion
and ApiError as needed. Avoid pervasive any and unchecked type assumptions.
Treat the backend OpenAPI and contract tests as authoritative.

Money remains JSON strings such as "120.00". Do not use parseFloat to perform
financial business calculations. Collect and format input/display values;
GET /api/v1/trips/{trip_id}/balances supplies the authoritative results.
Do not duplicate splitting or settlement algorithms in React.

Read error.code, error.message and error.details. Never identify errors by
English substring matching. Handle network/non-JSON failures and empty204
responses. Preserve the existing no-blind-write-retry guidance.

## 24. Frontend Authentication and Environment

Centralize authentication state and Bearer header injection:
Auth layer -> API client -> Authorization: Bearer <token>.
Pages must not each read token storage or API functions repeat header assembly.
Step13 uses sessionStorage for the tab's access token and verifies it through
/auth/me on startup. It remains accessible to same-origin JavaScript and XSS.
Do not silently switch storage or authentication mechanisms.
No refresh endpoint or server-side logout revocation currently exists.

Configure API base URL centrally through frontend environment configuration
for development and production, not hardcoded host strings across files.
Browser-delivered configuration is public: never include DATABASE_URL,
JWT_SECRET_KEY or other server secrets in frontend settings or bundles.
Use existing backend CORS with explicit origins; browser CORS is not auth.

## 25. Frontend State, UX and Accessibility

Prefer React state, Context and custom hooks. Evaluate a global state library
only when demonstrated complexity warrants it.

Every main data page must consider Loading, Success, Empty and Error states,
including appropriate recovery actions. Avoid hiding failures behind an
indefinite spinner or making an empty list appear broken.

Build a desktop-first responsive web application that also supports tablet
and mobile-width browsers. Do not introduce a complex UI framework merely
for responsive layout.

Use semantic HTML, associated form labels, correct button semantics, keyboard
usability, sufficient contrast and basic ARIA where needed. Keep accessibility
practical; do not build unnecessary infrastructure.

## 26. Frontend Testing and Development Workflow

Gradually test critical components, authentication flow, API contract handling
and important user workflows. Optimize for useful regression evidence, not
coverage numbers. Keep the backend regression commands:

```bash
cd backend
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
```

For each future frontend step:

1. Read AGENT.md and the latest RECORD.md entry.
2. Read the relevant backend API contract.
3. Study relevant OpenTrip design, without copying code.
4. Implement only the requested step.
5. Run appropriate automated tests.
6. Run locally and provide startup commands and access URL.
7. Provide manual browser steps and expected results for user acceptance;
   explicitly request screenshots if needed and record pending acceptance.
8. Update RECORD.md with actual results, not assumed success.
9. Stop; do not automatically begin the next step.

## 27. Reference and Future Work

Reference: https://github.com/stvlynn/OpenTrip.git
Study page organization, navigation, trip/itinerary/expense UX, component
boundaries and information hierarchy. Study architecture and product ideas;
do not copy source code. Preserve TripTogether's own data model, API contract,
backend architecture, authorization, expense logic and design decisions.

Potential future work, not current MVP additions: native/mobile client,
real-time collaboration, maps, AI itinerary assistance, notifications,
multiple currencies/FX, payment integration, refresh tokens, email verification,
password reset, pagination and rate limiting. Listing a limitation does not
authorize implementing it or changing the current step.
