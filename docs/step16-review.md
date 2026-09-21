# Step 16 Review: Expense + Balance UI

## Scope

Step 16 adds the React client for the existing Step 9/10 APIs:

- Shared expense list
- Equal-split expense create, edit and delete
- Server-calculated split display
- Trip member balances
- Suggested settlements

Expense and balance arithmetic remains on the backend. Step 17 frontend polish
and broader E2E work are not part of this step.

## Reading Order

1. `frontend/src/api/finance.ts` validates money strings, expenses and balances.
2. `frontend/src/types/finance.ts` defines the finance contract.
3. `frontend/src/components/ExpensePanel.tsx` owns expense form and list state.
4. `frontend/src/components/BalancePanel.tsx` renders server balances and suggestions.
5. `frontend/src/pages/TripDetailPage.tsx` refreshes balances after expense writes.
6. `frontend/src/components/Finance.test.tsx` covers key finance interactions.

## Architecture

The components use `useAuth().request` through the centralized API adapter.
The browser sends decimal strings such as `"100.00"` and displays the exact
split values returned by FastAPI. It never uses floating-point arithmetic or
reimplements equal splitting, balance calculation or settlement matching.

An expense write increments the detail page's balance refresh key. The balance
panel then fetches a fresh authoritative result. Suggested settlements are
shown as recommendations, not as payment actions.

## Validation and Authorization

The form validates description length, positive decimal amount, uppercase
three-letter currency, payer, date and at least one participant. The backend
still validates membership, currency consistency, split conservation and
authorization. Any accepted Trip member can edit or delete shared expenses,
matching the existing authorization matrix.

## Verification

```bash
cd /Volumes/Elements/TripTogether/frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Real PostgreSQL/FastAPI verification:

```bash
cd /Volumes/Elements/TripTogether
/private/tmp/triptogether-step1-venv/bin/python frontend/scripts/verify_finance.py
```

For browser acceptance, create a Trip with two accepted members, add a
100.00 expense split across them, verify the server-provided shares and
balances, edit the expense, then delete it. Confirm the balance panel refreshes
and that settlement suggestions are clearly presented as non-payment guidance.

## Reference Review

The existing Trip detail and Step 15 shared-data panels were used as the local
UI pattern. No new dependency, payment workflow, client-side money algorithm or
backend change was added.
