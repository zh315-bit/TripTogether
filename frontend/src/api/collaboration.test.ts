import { describe, expect, it, vi } from 'vitest'
import {
  acceptInvitation, createInvitation, createItineraryItem, deleteItineraryItem,
  listInvitations, listItinerary, listMembers, rejectInvitation, reorderItinerary,
  updateItineraryItem,
} from './collaboration'

const member = {
  user_id: 7, username: 'reader', email: 'reader@example.com', role: 'owner',
  joined_at: '2026-09-20T00:00:00Z',
}
const invitation = {
  id: 4, trip_id: 12, inviter_id: 7, invitee_id: 8, status: 'pending',
  created_at: '2026-09-20T00:00:00Z', responded_at: null,
}
const item = {
  id: 9, trip_id: 12, title: 'Temple', location: 'Asakusa',
  date: '2027-06-10', start_time: '09:30:00', end_time: null, notes: null,
  position: 1, created_by_user_id: 7,
  created_at: '2026-09-20T00:00:00Z', updated_at: '2026-09-20T00:00:00Z',
}

describe('collaboration API adapters', () => {
  it('uses the versioned member and invitation paths', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce([member])
      .mockResolvedValueOnce(invitation)
      .mockResolvedValueOnce([invitation])
      .mockResolvedValueOnce({ ...invitation, status: 'accepted', responded_at: invitation.created_at })
      .mockResolvedValueOnce({ ...invitation, status: 'rejected', responded_at: invitation.created_at })

    await expect(listMembers(request, '12')).resolves.toEqual([member])
    await expect(createInvitation(request, '12', 'invitee@example.com')).resolves.toEqual(invitation)
    await expect(listInvitations(request)).resolves.toEqual([invitation])
    await expect(acceptInvitation(request, 4)).resolves.toMatchObject({ status: 'accepted' })
    await expect(rejectInvitation(request, 4)).resolves.toMatchObject({ status: 'rejected' })
    expect(request.mock.calls.map(([path]) => path)).toEqual([
      '/api/v1/trips/12/members',
      '/api/v1/trips/12/invitations',
      '/api/v1/invitations',
      '/api/v1/invitations/4/accept',
      '/api/v1/invitations/4/reject',
    ])
  })

  it('supports itinerary CRUD and complete-day reorder', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce([item])
      .mockResolvedValueOnce(item)
      .mockResolvedValueOnce({ ...item, title: 'Updated Temple' })
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce([item])

    await expect(listItinerary(request, '12')).resolves.toEqual([item])
    await expect(createItineraryItem(request, '12', {
      title: item.title, date: item.date, location: item.location,
      start_time: '09:30', end_time: null, notes: null,
    })).resolves.toEqual(item)
    await expect(updateItineraryItem(request, '12', 9, { title: 'Updated Temple' }))
      .resolves.toMatchObject({ title: 'Updated Temple' })
    await expect(deleteItineraryItem(request, '12', 9)).resolves.toBeUndefined()
    await expect(reorderItinerary(request, '12', item.date, [9])).resolves.toEqual([item])
    expect(request.mock.calls.map(([path]) => path)).toEqual([
      '/api/v1/trips/12/itinerary',
      '/api/v1/trips/12/itinerary',
      '/api/v1/trips/12/itinerary/9',
      '/api/v1/trips/12/itinerary/9',
      '/api/v1/trips/12/itinerary/reorder',
    ])
  })

  it('rejects malformed member and itinerary responses', async () => {
    const request = vi.fn().mockResolvedValue([{ ...member, user_id: '7' }])
    await expect(listMembers(request, '12')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })
})
