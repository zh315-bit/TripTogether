import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { TOKEN_KEY } from '../auth/tokenStorage'

// The real Leaflet map is covered elsewhere; here only the workspace shell matters.
vi.mock('../components/map/LeafletMap', () => ({ LeafletMap: () => <div data-testid="map" /> }))

const stamp = '2026-09-20T00:00:00Z'
const user = { id: 7, username: 'reader', email: 'reader@example.com', created_at: stamp }
const tokyo = {
  id: 12, name: 'Tokyo', destination: 'Japan', start_date: '2027-06-10', end_date: '2027-06-15',
  owner_id: 7, created_at: stamp, version: 1, updated_at: stamp,
}
const paris = { ...tokyo, id: 13, name: 'Paris', destination: 'France', owner_id: 99 }
const invitation = { id: 4, trip_id: 20, inviter_id: 99, invitee_id: 7, status: 'pending', created_at: stamp, responded_at: null }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const failure = (status: number, code: string, message: string) => json({ error: { code, message, details: [] } }, status)

type Override = (path: string, method: string, init: RequestInit) => Response | undefined

function backend({ trips = [tokyo, paris], invitations = [] as unknown[], override = (() => undefined) as Override } = {}) {
  const fetcher = vi.fn(async (input: string, init: RequestInit = {}) => {
    const path = new URL(input).pathname
    const method = init.method ?? 'GET'
    const custom = override(path, method, init)
    if (custom) return custom
    if (path === '/health') return json({ status: 'ok' })
    if (path.endsWith('/auth/me')) return json(user)
    if (path === '/api/v1/trips' && method === 'GET') return json(trips)
    if (path === '/api/v1/invitations') return json(invitations)
    if (path.endsWith('/balances')) return json({ trip_id: 12, currency: null, members: [], suggested_settlements: [] })
    if (path.endsWith('/itinerary/route')) {
      return json({ date: '2027-06-10', stops: [], legs: [], total_distance_km: 0, unlocated_item_ids: [] })
    }
    return json([])
  })
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}

function mount(path: string) {
  sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
  window.history.replaceState(null, '', path)
  return render(<App />)
}

async function openDetails() {
  await userEvent.click(await screen.findByRole('tab', { name: 'Trip details' }))
  return screen.findByRole('heading', { name: 'Trip details' })
}

describe('signed-in workspace', () => {
  it('opens the first trip from /trips and lists owned and joined trips in the switcher', async () => {
    backend()
    mount('/trips')
    const switcher = await screen.findByLabelText('Current trip')
    await waitFor(() => expect(window.location.pathname).toBe('/trips/12'))
    expect(switcher).toHaveValue('12')
    expect(within(switcher).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Tokyo · 06-10 – 06-15', 'Paris · 06-10 – 06-15',
    ])
    expect(await screen.findByTestId('map')).toBeInTheDocument()
  })

  it('switches trips through the dropdown and remembers the last one', async () => {
    backend()
    const view = mount('/trips/12')
    await userEvent.selectOptions(await screen.findByLabelText('Current trip'), 'Paris · 06-10 – 06-15')
    expect(window.location.pathname).toBe('/trips/13')
    await waitFor(() => expect(localStorage.getItem('triptogether:last-trip')).toBe('13'))
    view.unmount()
    mount('/trips')
    await waitFor(() => expect(window.location.pathname).toBe('/trips/13'))
  })

  it('shows a clear message for a trip that is not in the list', async () => {
    backend()
    mount('/trips/999')
    expect(await screen.findByText(/This trip isn't available/)).toBeInTheDocument()
    expect(screen.queryByTestId('map')).not.toBeInTheDocument()
  })

  it('invites first-time users to create a trip and opens it on the map', async () => {
    const seoul = { ...tokyo, id: 14, name: 'Seoul', destination: 'Korea' }
    const fetcher = backend({
      trips: [],
      override: (path, method) => path === '/api/v1/trips' && method === 'POST' ? json(seoul, 201) : undefined,
    })
    mount('/trips')
    expect(await screen.findByRole('heading', { name: 'Where to first?' })).toBeInTheDocument()
    // Validation runs before any write.
    await userEvent.click(screen.getByRole('button', { name: 'Create trip' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Please check')
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)
    await userEvent.type(screen.getByLabelText('Trip name'), 'Seoul')
    await userEvent.type(screen.getByLabelText('Destination'), 'Korea')
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2027-06-10' } })
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2027-06-15' } })
    await userEvent.click(screen.getByRole('button', { name: 'Create trip' }))
    await waitFor(() => expect(window.location.pathname).toBe('/trips/14'))
    expect(await screen.findByLabelText('Current trip')).toHaveValue('14')
  })

  it('creates another trip from the top bar', async () => {
    const lisbon = { ...tokyo, id: 15, name: 'Lisbon', destination: 'Portugal' }
    backend({ override: (path, method) => path === '/api/v1/trips' && method === 'POST' ? json(lisbon, 201) : undefined })
    mount('/trips/12')
    const toggle = await screen.findByRole('button', { name: 'New trip' })
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const dialog = screen.getByRole('dialog', { name: 'Create a trip' })
    await userEvent.type(within(dialog).getByLabelText('Trip name'), 'Lisbon')
    await userEvent.type(within(dialog).getByLabelText('Destination'), 'Portugal')
    fireEvent.change(within(dialog).getByLabelText('Start date'), { target: { value: '2027-06-10' } })
    fireEvent.change(within(dialog).getByLabelText('End date'), { target: { value: '2027-06-15' } })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create trip' }))
    await waitFor(() => expect(window.location.pathname).toBe('/trips/15'))
    expect(screen.queryByRole('dialog', { name: 'Create a trip' })).not.toBeInTheDocument()
  })

  it('closes top-bar popovers with Escape', async () => {
    backend()
    mount('/trips/12')
    await userEvent.click(await screen.findByRole('button', { name: 'New trip' }))
    expect(screen.getByRole('dialog', { name: 'Create a trip' })).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Create a trip' })).not.toBeInTheDocument()
  })

  it('counts pending invitations and lets the user answer them from the bell', async () => {
    backend({ invitations: [invitation] })
    mount('/trips/12')
    const bell = await screen.findByRole('button', { name: 'Invitations, 1 pending' })
    await userEvent.click(bell)
    const dialog = screen.getByRole('dialog', { name: 'Invitations' })
    expect(await within(dialog).findByText('Trip #20')).toBeInTheDocument()
  })

  it('offers account and log out from the avatar menu', async () => {
    backend()
    mount('/trips/12')
    await userEvent.click(await screen.findByRole('button', { name: 'Account menu for reader' }))
    const menu = screen.getByRole('dialog', { name: 'Account' })
    expect(within(menu).getByText('reader@example.com')).toBeInTheDocument()
    await userEvent.click(within(menu).getByRole('button', { name: /log out/i }))
    await waitFor(() => expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull())
  })

  it('edits an owner trip from Trip details and updates the switcher', async () => {
    const fetcher = backend({
      override: (path, method, init) => path === '/api/v1/trips/12' && method === 'PATCH'
        ? json({ ...tokyo, ...JSON.parse(String(init.body)) }) : undefined,
    })
    mount('/trips/12')
    await openDetails()
    await userEvent.click(screen.getByRole('button', { name: 'Edit trip' }))
    const name = screen.getByLabelText('Trip name')
    await userEvent.clear(name)
    await userEvent.type(name, 'Updated Tokyo')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByRole('option', { name: 'Updated Tokyo · 06-10 – 06-15' })).toBeInTheDocument()
    expect(fetcher.mock.calls).toContainEqual(['http://backend.test/api/v1/trips/12', expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ name: 'Updated Tokyo', destination: 'Japan', start_date: '2027-06-10', end_date: '2027-06-15' }),
    })])
  })

  it('confirms deletion in the page and keeps the trip when the delete fails', async () => {
    const confirm = vi.spyOn(window, 'confirm')
    backend({
      override: (path, method) => path === '/api/v1/trips/12' && method === 'DELETE'
        ? failure(404, 'TRIP_NOT_FOUND', 'Trip was already deleted.') : undefined,
    })
    mount('/trips/12')
    await openDetails()
    await userEvent.click(screen.getByRole('button', { name: 'Delete trip' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('removed for everyone')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete trip' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Trip was already deleted.')
    expect(screen.getByRole('button', { name: 'Delete trip' })).toBeInTheDocument()
    expect(confirm).not.toHaveBeenCalled()
  })

  it('deletes a trip and moves on to the next one', async () => {
    backend({
      override: (path, method) => path === '/api/v1/trips/12' && method === 'DELETE' ? new Response(null, { status: 204 }) : undefined,
    })
    mount('/trips/12')
    await openDetails()
    await userEvent.click(screen.getByRole('button', { name: 'Delete trip' }))
    await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete trip' }))
    await waitFor(() => expect(window.location.pathname).toBe('/trips/13'))
  })

  it('keeps member trips view-only', async () => {
    backend()
    mount('/trips/13')
    await openDetails()
    expect(screen.getByText('Trip member')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit trip' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete trip' })).not.toBeInTheDocument()
  })

  it('sends signed-in visitors of the landing page to their map', async () => {
    backend()
    mount('/')
    await waitFor(() => expect(window.location.pathname).toBe('/trips/12'))
  })
})
