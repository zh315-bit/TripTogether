# Step 15 Review: Collaboration + Shared Itinerary UI

## Scope

Step 15 adds the React client for existing collaboration APIs:

- Trip member list
- Owner invitation form
- Invitation inbox with accept/reject
- Shared itinerary list grouped by calendar date
- Itinerary create, edit, delete and complete-day reorder

Expense, balance, settlement, chat and real-time collaboration UI are not part
of this step.

## Reading Order

1. `frontend/src/api/collaboration.ts` validates all Step 7/8 responses.
2. `frontend/src/types/collaboration.ts` defines member, invitation and item data.
3. `frontend/src/components/MembersPanel.tsx` loads members and sends owner invites.
4. `frontend/src/components/InvitationInbox.tsx` handles recipient decisions.
5. `frontend/src/components/ItineraryPanel.tsx` owns shared itinerary state and forms.
6. `frontend/src/pages/TripDetailPage.tsx` composes the collaboration panels.
7. `frontend/src/pages/TripsPage.tsx` refreshes trips after an accepted invitation.
8. `frontend/src/pages/Collaboration.test.tsx` covers the main UI flows.

## Architecture

The new components use `useAuth().request` and never access `fetch` directly.
The API adapter is responsible for `/api/v1` paths, JSON bodies and runtime
response validation. The backend remains the authority for owner/member and
recipient authorization; hiding the invitation form or showing read/write
controls is only presentation logic.

The itinerary UI sends the backend's complete-day reorder contract. It does not
sort or calculate positions as a source of truth. After reorder, the server
response replaces that day's items.

## Validation and Error Handling

The client validates required itinerary title/date fields and local time order.
Backend date-range, membership, invitation conflict and validation errors are
shown as safe text. Invitation and itinerary write buttons expose pending state.
Delete actions require confirmation. Malformed successful responses are rejected
by the API adapter as `INVALID_RESPONSE`.

## Verification

```bash
cd /Volumes/Elements/TripTogether/frontend
npm test
npm run lint
npm run typecheck
npm run build
```

The real backend/PostgreSQL workflow can be checked with:

```bash
cd /Volumes/Elements/TripTogether
/private/tmp/triptogether-step1-venv/bin/python frontend/scripts/verify_collaboration.py
```

For browser acceptance, create two disposable accounts. The owner should
invite the second account; the recipient should accept the invitation and see
the Trip appear in the Dashboard. Both users should see members and itinerary;
both accepted members should be able to create/edit/delete/reorder itinerary
items. Pending or rejected invitations must not grant Trip access.

## Reference Review

The existing OpenTrip trip workflow was used as a reference for keeping the
Trip detail page divided into focused areas. No external auth, invitation or
itinerary implementation was copied, and no dependency was added.
