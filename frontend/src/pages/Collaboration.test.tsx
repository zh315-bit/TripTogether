import { render, screen, waitFor } from '@testing-library/react'
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
  start_time: '09:30:00', end_time: null, notes: null, place_id: null, position: 1,
  created_by_user_id: 7,
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
      if (url.endsWith('/api/v1/trips')) return json([trip])
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

  it('reorders with the shown order and reloads after a conflict without retrying', async () => {
    const second = { ...item, id: 10, title: 'Dinner', position: 2 }
    const latest = [{ ...second, position: 1 }, { ...item, position: 2 }, { ...item, id: 11, title: 'Late', position: 3 }]
    let conflicted = false
    let loadsAfterConflict = 0
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (url.endsWith('/health')) return json({ status: 'ok' })
      if (url.endsWith('/me')) return json(user)
      if (url.endsWith('/itinerary/reorder')) {
        conflicted = true
        return json({ error: {
          code: 'ITINERARY_CONFLICT', message: 'The itinerary order changed; review it and retry', details: [],
        } }, 409)
      }
      if (url.endsWith('/itinerary') && method === 'GET') {
        if (conflicted) loadsAfterConflict += 1
        return json(conflicted ? latest : [item, second])
      }
      if (url.endsWith('/api/v1/trips')) return json([trip])
      if (url.endsWith('/trips/12')) return json(trip)
      return json([])
    })
    mount('/trips/12', fetcher)
    await userEvent.click(await screen.findByRole('tab', { name: 'Itinerary' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Move Temple down' }))
    expect(await screen.findByText(/changed by another member/)).toBeInTheDocument()
    expect(await screen.findByText('Late')).toBeInTheDocument()
    const reorders = fetcher.mock.calls.filter(([url]) => String(url).endsWith('/reorder'))
    expect(reorders).toHaveLength(1)
    expect(JSON.parse(String(reorders[0][1]?.body))).toEqual({
      date: '2027-06-10', item_ids: [10, 9], expected_item_ids: [9, 10],
    })
    // The panel reloads its list and tells the map to redraw; neither retries.
    await waitFor(() => expect(loadsAfterConflict).toBe(2))
  })

  it('shows a moved row at once, keeps the server order, and puts it back if saving fails', async () => {
    const second = { ...item, id: 10, title: 'Dinner', position: 2 }
    let finish: (response: Response) => void = () => undefined
    let fail = false
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (url.endsWith('/health')) return json({ status: 'ok' })
      if (url.endsWith('/me')) return json(user)
      if (url.endsWith('/itinerary/reorder')) {
        if (fail) return json({ error: { code: 'INTERNAL_ERROR', message: 'Could not save the order', details: [] } }, 500)
        return new Promise<Response>((resolve) => { finish = resolve })
      }
      if (url.endsWith('/itinerary') && method === 'GET') return json([item, second])
      if (url.endsWith('/api/v1/trips')) return json([trip])
      if (url.endsWith('/trips/12')) return json(trip)
      return json([])
    })
    const order = () => screen.getAllByRole('article').map((row) => row.querySelector('strong')?.textContent)
    mount('/trips/12', fetcher)
    await userEvent.click(await screen.findByRole('tab', { name: 'Itinerary' }))
    expect(await screen.findByRole('button', { name: 'Drag Temple to reorder' })).toBeEnabled()
    await userEvent.click(screen.getByRole('button', { name: 'Move Temple down' }))
    // Optimistic: the new order shows while the request is still open, and moves are locked.
    expect(order()).toEqual(['Dinner', 'Temple'])
    expect(screen.getByRole('button', { name: 'Drag Temple to reorder' })).toBeDisabled()
    finish(json([{ ...second, position: 1 }, { ...item, position: 2 }]))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Drag Temple to reorder' })).toBeEnabled())
    expect(order()).toEqual(['Dinner', 'Temple'])

    fail = true
    await userEvent.click(screen.getByRole('button', { name: 'Move Temple up' }))
    expect(await screen.findByText('Could not save the order')).toBeInTheDocument()
    expect(order()).toEqual(['Dinner', 'Temple'])
  })

  it('cannot drag the only item of a day', async () => {
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (url.endsWith('/health')) return json({ status: 'ok' })
      if (url.endsWith('/me')) return json(user)
      if (url.endsWith('/itinerary') && method === 'GET') return json([item])
      if (url.endsWith('/api/v1/trips')) return json([trip])
      if (url.endsWith('/trips/12')) return json(trip)
      return json([])
    })
    mount('/trips/12', fetcher)
    await userEvent.click(await screen.findByRole('tab', { name: 'Itinerary' }))
    expect(await screen.findByRole('button', { name: 'Drag Temple to reorder' })).toBeDisabled()
  })

  it('links an itinerary item to a pool place, following the place name for location', async () => {
    const places = [
      { id: 1, trip_id: 12, proposed_by_user_id: 7, name: 'Senso-ji', address: null, latitude: 35.7,
        longitude: 139.8, provider: 'manual', provider_place_id: null, note: null,
        created_at: item.created_at, updated_at: item.created_at },
      { id: 2, trip_id: 12, proposed_by_user_id: 8, name: 'Tokyo Tower', address: null, latitude: 35.6,
        longitude: 139.7, provider: 'manual', provider_place_id: null, note: null,
        created_at: item.created_at, updated_at: item.created_at },
    ]
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (url.endsWith('/health')) return json({ status: 'ok' })
      if (url.endsWith('/me')) return json(user)
      if (url.endsWith('/places')) return json(places)
      if (url.endsWith('/itinerary') && method === 'GET') return json([{ ...item, place_id: 1, location: 'Senso-ji' }])
      if (url.endsWith('/itinerary') && method === 'POST') {
        return json({ ...item, id: 10, ...JSON.parse(String(init?.body)), position: 2 }, 201)
      }
      if (url.endsWith('/api/v1/trips')) return json([trip])
      if (url.endsWith('/trips/12')) return json(trip)
      return json([])
    })
    mount('/trips/12', fetcher)
    await userEvent.click(await screen.findByRole('tab', { name: 'Itinerary' }))
    expect(await screen.findByText('Place: Senso-ji')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Title'), 'Views')
    const select = screen.getByLabelText('Linked place')
    await userEvent.selectOptions(select, 'Senso-ji')
    expect(screen.getByLabelText('Location')).toHaveValue('Senso-ji')
    // Switching places follows the new name while the text was not hand-edited.
    await userEvent.selectOptions(select, 'Tokyo Tower')
    expect(screen.getByLabelText('Location')).toHaveValue('Tokyo Tower')
    await userEvent.clear(screen.getByLabelText('Location'))
    await userEvent.type(screen.getByLabelText('Location'), 'Main deck')
    await userEvent.selectOptions(select, 'Senso-ji')
    expect(screen.getByLabelText('Location')).toHaveValue('Main deck')
    await userEvent.selectOptions(select, 'Tokyo Tower')
    await userEvent.click(screen.getByRole('button', { name: 'Add item' }))
    const post = fetcher.mock.calls.find(([url, init]) => String(url).endsWith('/itinerary') && init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ title: 'Views', place_id: 2, location: 'Main deck' })
    // "None" unlinks.
    await userEvent.selectOptions(select, 'None')
    expect(select).toHaveValue('')
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
