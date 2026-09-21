# Authorization Matrix

Step 11 audit, September 20, 2026. Formal business paths start with `/api/v1`.
Permissions apply identically to legacy aliases. Authentication is a verified
Bearer JWT plus a current User lookup; authorization is a separate SQL/service
check, not a role value supplied by the client.

| Resource / Operation | Owner | Member | Pending invitee | Other user | Anonymous |
| --- | --- | --- | --- | --- | --- |
| Trip detail | Yes | Yes | 404 | 404 | 401 |
| Trip PATCH / DELETE | Yes | 404 | 404 | 404 | 401 |
| Trip invitation create | Yes | 404 | 404 | 404 | 401 |
| Trip members list | Yes | Yes | 404 | 404 | 401 |
| Itinerary create/list/detail/update/delete/reorder | Yes | Yes | 404 | 404 | 401 |
| Expense create/list/detail/update/delete | Yes | Yes | 404 | 404 | 401 |
| Balance read | Yes | Yes | 404 | 404 | 401 |

`Owner` means `trips.owner_id == current_user.id`. `Member` means an accepted
membership row, not merely a pending invitation. A member may edit/delete
another participant's itinerary or expense: this is intentional collaboration,
not creator-only ownership.

## Operations Not Determined by Trip Role

| Operation | Rule |
| --- | --- |
| POST /auth/register, POST /auth/login | Public; validation still applies |
| GET /auth/me | Current authenticated user only |
| POST /trips | Any authenticated user; server sets owner and owner membership |
| GET /trips | Any authenticated user; SQL returns owned/joined trips only |
| GET /invitations | Authenticated recipient's own invitation history only |
| POST /invitations/{id}/accept or /reject | Authenticated recipient only; pending state required |
| GET /health, GET /ready | Public system probes, no resource data |
| Documentation routes | Public in current MVP |

For invitation responses, a Trip owner cannot act for its recipient. A wrong
recipient or missing invitation gets the same 404. Repeating a decision returns
409; accepting atomically creates membership and updates invitation state.
Accepted/rejected invitations are still visible in the recipient's inbox.

Missing and inaccessible Trip/item/expense resources are hidden with 404.
Invalid authentication is 401 with `WWW-Authenticate: Bearer`. A client must
not interpret hidden404 as proof that a resource has been deleted.
These guarantees concern resource existence, not schema validation: malformed
path/body data may independently produce 422.

## Code and Coverage

- `app/api/dependencies.py`: token validation before database lookup, shared
  `get_current_user`; all 23 protected formal operations audited.
- `app/services/trips.py`: `accessible_to` uses Owner OR EXISTS membership;
  `get_owned_trip` is stricter. SQL filters apply before rows are returned.
- Invitation, itinerary and expense services scope child IDs to their Trip.
- `tests/test_api_contract.py`: all 23 protected operations reject anonymous
  callers before DB access; real v1 workflow checks pending/outsider/member/
  recipient/owner boundaries.
- Existing Step 6-10 suites retain full role, cross-trip child-ID, rollback
  and concurrency regression coverage. Same service functions serve both paths.

Member responses intentionally include `email` for participants. This is an
existing product policy, not a leak of password hashes; revisit disclosure
before broadening the membership or public-sharing model.
