# Step 14 Review: Trip Dashboard + Trip Management

## Scope

Step 14 adds the authenticated web workflow for listing accessible trips,
creating a trip, viewing its details, editing an owned trip and deleting an
owned trip. It does not add membership, invitation, itinerary, expense or
balance screens.

## Reading Order

1. `frontend/src/api/trips.ts` validates the existing `/api/v1/trips` contract.
2. `frontend/src/types/trip.ts` defines the client-side trip shapes.
3. `frontend/src/pages/TripsPage.tsx` owns dashboard loading and creation.
4. `frontend/src/pages/TripDetailPage.tsx` owns detail, owner actions and errors.
5. `frontend/src/components/TripForm.tsx` handles input validation and writes.
6. `frontend/src/auth/AuthContext.tsx` supplies the authenticated request boundary.
7. `frontend/src/pages/TripManagement.test.tsx` covers the user workflows.

## Architecture

Pages do not call `fetch` directly. They call trip adapters with
`useAuth().request`, which adds the current Bearer token and clears an invalid
session on a protected 401. The backend remains the source of truth for
membership and owner authorization; hiding owner controls is only a UI
convenience.

The dashboard accepts the backend's owned and joined trip list. The detail page
compares `owner_id` with the authenticated user's id to choose between owner
controls and member view-only mode. All writes use the existing REST contract.

## Validation and Error Handling

The form checks required fields, maximum lengths and date ordering before a
request. Backend validation errors are mapped back to fields. A malformed
successful response becomes `INVALID_RESPONSE`. Delete confirmation prevents an
accidental write, while delete failures remain visible on the detail page.

## Verification

```bash
cd /Volumes/Elements/TripTogether/frontend
npm test
npm run lint
npm run typecheck
npm run build
```

With migrated PostgreSQL available:

```bash
cd /Volumes/Elements/TripTogether
/private/tmp/triptogether-step1-venv/bin/python frontend/scripts/verify_trips.py
```

Manual browser acceptance is still required: run backend and Vite, log in,
create a trip, inspect its detail page, edit it, delete it, and confirm a
member account can view but not edit or delete a joined trip.

## Reference Review

The OpenTrip reference was reviewed for the trip list, trip card, create form
and detail workflow. This implementation keeps the useful separation between
list/detail/form responsibilities while retaining TripTogether's existing
REST API, visual system, auth boundary and minimal scope.
