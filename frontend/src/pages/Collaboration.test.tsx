import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { TOKEN_KEY } from '../auth/tokenStorage'

const user = { id: 7, username: 'reader', email: 'reader@example.com', created_at: '2026-09-20T00:00:00Z' }
const trip = {
  id: 12, name: 'Tokyo', destination: 'Japan', start_date: '2027-06-10', end_date: '2027-06-15',
  owner_id: 7, created_at: '2026-09-20T00:00:00Z', updated_at: '2026-09-20T00:00:00Z',
}
const member = {
  user_id: 8, username: 'friend', email: 'friend@example.com', role: 'member',
  joined_at: '2026-09-20T00:00:00Z',
}
const item = {
  id: 9, trip_id: 12, title: 'Temple', location: 'Asakusa', date: '2027-06-10',
  start_time: '09:30:00', end_time: null, notes: null, position: 1, created_by_user_id: 7,
  created_at: '2026-09-20T00:00:00Z', updated_at: '2026-09-20T00:00:00Z',
}
const invitation = {
  id: 4, trip_id: 12, inviter_id: 8, invitee_id: 7, status: 'pending',
  created_at: '2026-09-20T00:00:00Z', responded_at: null,
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

function mount(path: string, fetcher: ReturnType<typeof vi.fn>) {
  sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
  window.history.replaceState(null, '', path)
  vi.stubGlobal('fetch', fetcher)
  render(<App />)
}

describe('collaboration and itinerary UI', () => {
  it('shows members and shared itinerary, then creates an item', async () => {
    const created = { ...item, id: 10, title: 'Dinner', position: 2 }
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (url.endsWith('/health')) return json({ status: 'ok' })
      if (url.endsWith('/me')) return json(user)
      if (url.endsWith('/members')) return json([member])
      if (url.endsWith('/itinerary') && method === 'GET') return json([item])
      if (url.endsWith('/itinerary') && method === 'POST') return json(created, 201)
      if (url.endsWith('/trips/12')) return json(trip)
      return json([])
    })
    mount('/trips/12', fetcher)
    await userEvent.click(await screen.findByRole('tab', { name: 'Members' }))
    expect(await screen.findByText('friend@example.com')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Itinerary' }))
    expect(await screen.findByText('Temple')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Title'), 'Dinner')
    await userEvent.click(screen.getByRole('button', { name: 'Add item' }))
    expect(await screen.findByText('Dinner')).toBeInTheDocument()
    expect(fetcher.mock.calls).toContainEqual([
      'http://backend.test/api/v1/trips/12/itinerary',
      expect.objectContaining({ method: 'POST' }),
    ])
  })

  it('accepts a pending invitation from the dashboard inbox', async () => {
    const accepted = { ...invitation, status: 'accepted', responded_at: invitation.created_at }
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/health')) return json({ status: 'ok' })
      if (url.endsWith('/me')) return json(user)
      if (url.includes('/invitations/') && (init?.method ?? 'GET') === 'POST') return json(accepted)
      if (url.endsWith('/invitations')) return json([invitation])
      if (url.endsWith('/trips')) return json([])
      return json([])
    })
    mount('/trips', fetcher)
    expect(await screen.findByText('Trip #12')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Accept' }))
    expect(await screen.findByText('accepted')).toBeInTheDocument()
  })
})
