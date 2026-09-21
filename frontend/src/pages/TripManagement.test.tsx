import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { TOKEN_KEY } from '../auth/tokenStorage'

const user = { id: 7, username: 'reader', email: 'reader@example.com', created_at: '2026-09-20T00:00:00Z' }
const ownerTrip = {
  id: 12,
  name: 'Tokyo',
  destination: 'Japan',
  start_date: '2027-06-10',
  end_date: '2027-06-15',
  owner_id: 7,
  created_at: '2026-09-20T00:00:00Z',
  updated_at: '2026-09-20T00:00:00Z',
}
const memberTrip = { ...ownerTrip, id: 13, name: 'Paris', destination: 'France', owner_id: 99 }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const failure = (status: number, message: string) =>
  json({ error: { code: 'TRIP_NOT_FOUND', message, details: [] } }, status)

function mount(path = '/trips') {
  sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
  window.history.replaceState(null, '', path)
  return render(<App />)
}

function authAnd(...responses: Response[]) {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    void init
    if (url.endsWith('/health')) return json({ status: 'ok' })
    if (url.endsWith('/me')) return json(user)
    if (url.endsWith('/invitations') || url.includes('/members') || url.endsWith('/itinerary')) {
      return json([])
    }
    if (url.endsWith('/expenses')) return json([])
    if (url.endsWith('/balances')) return json({ trip_id: 12, currency: null, members: [], suggested_settlements: [] })
    return responses.shift() ?? json([])
  })
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}

describe('Trip dashboard and management', () => {
  it('loads owned and joined trips into the dashboard', async () => {
    authAnd(json([ownerTrip, memberTrip]))
    mount()
    expect(await screen.findByRole('heading', { name: 'Trips' })).toBeInTheDocument()
    expect(await screen.findByText('Tokyo')).toBeInTheDocument()
    expect(await screen.findByText('Paris')).toBeInTheDocument()
  })

  it('validates a create form before sending a write', async () => {
    const fetcher = authAnd(json([]))
    mount()
    await screen.findByRole('heading', { name: 'Trips' })
    await userEvent.click(screen.getByRole('button', { name: 'Create trip' }))
    await userEvent.click(screen.getByRole('button', { name: 'Create trip' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Please check')
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('creates a trip and opens its detail page', async () => {
    const created = { ...ownerTrip, id: 14, name: 'Seoul' }
    const responses = [json([]), json(created, 201), json(created)]
    authAnd(...responses)
    mount()
    await screen.findByRole('heading', { name: 'Trips' })
    await userEvent.click(screen.getByRole('button', { name: 'Create trip' }))
    await userEvent.type(screen.getByLabelText('Trip name'), 'Seoul')
    await userEvent.type(screen.getByLabelText('Destination'), 'Korea')
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2027-06-10' } })
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2027-06-15' } })
    await userEvent.click(screen.getByRole('button', { name: 'Create trip' }))
    expect(await screen.findByRole('heading', { name: 'Seoul' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/trips/14')
  })

  it('shows owner controls and safely handles a failed delete', async () => {
    authAnd(json(ownerTrip), failure(404, 'Trip was already deleted.'))
    mount('/trips/12')
    expect(await screen.findByRole('heading', { name: 'Tokyo' })).toBeInTheDocument()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await userEvent.click(screen.getByRole('button', { name: 'Delete trip' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Trip was already deleted.')
    expect(screen.getByRole('button', { name: 'Delete trip' })).toBeInTheDocument()
  })

  it('keeps member trips view-only', async () => {
    authAnd(json(memberTrip))
    mount('/trips/13')
    expect(await screen.findByRole('heading', { name: 'Paris' })).toBeInTheDocument()
    expect(screen.getByText('Member')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit trip' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete trip' })).not.toBeInTheDocument()
  })

  it('updates an owner trip through the edit form', async () => {
    const updated = { ...ownerTrip, name: 'Updated Tokyo' }
    const fetcher = authAnd(json(ownerTrip), json(updated))
    mount('/trips/12')
    await screen.findByRole('heading', { name: 'Tokyo' })
    await userEvent.click(screen.getByRole('button', { name: 'Edit trip' }))
    const name = screen.getByLabelText('Trip name')
    await userEvent.clear(name)
    await userEvent.type(name, 'Updated Tokyo')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByRole('heading', { name: 'Updated Tokyo' })).toBeInTheDocument()
    expect(fetcher.mock.calls).toContainEqual([
      'http://backend.test/api/v1/trips/12',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({
          name: 'Updated Tokyo',
          destination: 'Japan',
          start_date: '2027-06-10',
          end_date: '2027-06-15',
        }),
      }),
    ])
  })
})
