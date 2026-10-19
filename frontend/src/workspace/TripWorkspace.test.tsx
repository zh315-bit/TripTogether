import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { TOKEN_KEY } from '../auth/tokenStorage'
import type { LatLng, MapLine, MapMarker } from '../components/map/LeafletMap'

// jsdom cannot lay out a real Leaflet map; this stand-in exposes what would be drawn.
vi.mock('../components/map/LeafletMap', () => ({
  LeafletMap: ({ markers, lines, onPick }: {
    markers: MapMarker[]; lines: MapLine[]; onPick?: (position: LatLng) => void
  }) => <div data-testid="map">
    <ul aria-label="Map markers">{markers.map((marker) => <li key={marker.id} data-kind={marker.kind}
      data-color={marker.color}>{marker.label}|{marker.tooltip}</li>)}</ul>
    {lines.map((line) => <span key={line.id} data-testid={`line-${line.id}`}
      data-dashed={String(Boolean(line.dashed))}>{line.positions.length}</span>)}
    {onPick && <button type="button" onClick={() => onPick([35.123456, 139.654321])}>Simulate map click</button>}
  </div>,
}))

const stamp = '2026-09-20T00:00:00Z'
const user = { id: 7, username: 'reader', email: 'reader@example.com', created_at: stamp }
const trip = {
  id: 12, name: 'Tokyo', destination: 'Japan', start_date: '2027-06-10', end_date: '2027-06-12',
  owner_id: 7, created_at: stamp, updated_at: stamp,
}
const members = [
  { user_id: 7, username: 'reader', email: 'reader@example.com', role: 'owner', joined_at: stamp },
  { user_id: 8, username: 'friend', email: 'friend@example.com', role: 'member', joined_at: stamp },
]
const place = (id: number, name: string, proposer: number, extra = {}) => ({
  id, trip_id: 12, proposed_by_user_id: proposer, name, address: null, latitude: 35.7, longitude: 139.7 + id / 100,
  provider: 'manual', provider_place_id: null, note: null, created_at: stamp, updated_at: stamp, ...extra,
})
const item = (id: number, title: string, position: number, placeId: number | null, startTime: string | null = null) => ({
  id, trip_id: 12, title, location: null, date: '2027-06-10', start_time: startTime, end_time: null, notes: null,
  place_id: placeId, position, created_by_user_id: 7, created_at: stamp, updated_at: stamp,
})
const stop = (itemId: number, placeId: number, name: string, longitude: number) => ({
  item_id: itemId, place_id: placeId, name, latitude: 35.7, longitude,
})
const route = {
  date: '2027-06-10',
  stops: [stop(9, 1, 'Senso-ji', 139.71), stop(11, 2, 'Tower', 139.72), stop(13, 3, 'Park', 139.73)],
  legs: [
    { from_item_id: 9, to_item_id: 11, distance_km: 1.822 },
    { from_item_id: 11, to_item_id: 13, distance_km: 12.5 },
  ],
  total_distance_km: 14.322,
  unlocated_item_ids: [10],
}
const proposedRoute = { ...route, stops: [route.stops[0], route.stops[2], route.stops[1]], total_distance_km: 9.1 }
const plan = {
  date: '2027-06-10', keep_first: true, changed: true,
  original_item_ids: [9, 10, 11, 13], proposed_item_ids: [9, 10, 13, 11], anchored_item_ids: [9, 10],
  original_route: route, proposed_route: proposedRoute,
}
const error = (code: string, message: string, status: number, details: unknown[] = [], headers?: HeadersInit) =>
  new Response(JSON.stringify({ error: { code, message, details } }), { status, headers })
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

type Handler = (url: URL, init: RequestInit) => Response | Promise<Response> | undefined

function server(handler: Handler = () => undefined) {
  const state = {
    places: [place(1, 'Senso-ji', 8), place(2, 'Tower', 7)],
    items: [item(9, 'Temple', 1, 1), item(10, 'Lunch', 2, null, '12:00:00'), item(11, 'Tower visit', 3, 2), item(13, 'Park walk', 4, 3)],
  }
  const fetcher = vi.fn(async (input: string, init: RequestInit = {}) => {
    const url = new URL(input)
    const method = init.method ?? 'GET'
    const custom = await handler(url, init)
    if (custom) return custom
    if (url.pathname === '/health') return json({ status: 'ok' })
    if (url.pathname.endsWith('/me')) return json(user)
    if (url.pathname === '/api/v1/trips' && method === 'GET') return json([trip])
    if (url.pathname === '/api/v1/trips/12') return json(trip)
    if (url.pathname.endsWith('/members')) return json(members)
    if (url.pathname.endsWith('/places') && method === 'GET') return json(state.places)
    if (url.pathname.endsWith('/places') && method === 'POST') {
      const body = JSON.parse(String(init.body))
      const created = place(50, body.name, 7, body)
      return json(created, 201)
    }
    if (url.pathname.endsWith('/itinerary') && method === 'GET') return json(state.items)
    if (url.pathname.endsWith('/itinerary/route')) return json(route)
    return json([])
  })
  return { fetcher, state }
}

function calls(fetcher: ReturnType<typeof vi.fn>, path: string, method = 'GET') {
  return fetcher.mock.calls.filter(([url, init]) =>
    new URL(String(url)).pathname === path && ((init as RequestInit | undefined)?.method ?? 'GET') === method)
}

function body(call: unknown[]) {
  return JSON.parse(String((call[1] as RequestInit).body))
}

/** Opening a trip *is* the map; sidebar panels are tabs beside it. */
async function openMap(fetcher: ReturnType<typeof vi.fn>, panel = 'Places') {
  sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
  window.history.replaceState(null, '', '/trips/12')
  vi.stubGlobal('fetch', fetcher)
  render(<App />)
  await screen.findByTestId('map')
  if (panel !== 'Places') await userEvent.click(screen.getByRole('tab', { name: panel }))
  await waitFor(() => expect(screen.queryByText('Loading trip data...')).not.toBeInTheDocument())
}

describe('map workspace', () => {
  it('opens on the map with keyboard-navigable sidebar tabs kept in the URL', async () => {
    const { fetcher } = server()
    await openMap(fetcher)
    const places = screen.getByRole('tab', { name: 'Places' })
    expect(places).toHaveAttribute('aria-selected', 'true')
    places.focus()
    await userEvent.keyboard('{ArrowDown}')
    const itinerary = screen.getByRole('tab', { name: 'Itinerary' })
    expect(itinerary).toHaveAttribute('aria-selected', 'true')
    expect(itinerary).toHaveFocus()
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'panel-tab-itinerary')
    expect(window.location.search).toBe('?panel=itinerary')
    await userEvent.keyboard('{End}')
    expect(screen.getByRole('tab', { name: 'Trip details' })).toHaveAttribute('aria-selected', 'true')
    await userEvent.keyboard('{Home}')
    expect(screen.getByRole('tab', { name: 'Places' })).toHaveFocus()
  })

  it('reopens the panel named in the URL', async () => {
    const { fetcher } = server()
    sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
    window.history.replaceState(null, '', '/trips/12?panel=members')
    vi.stubGlobal('fetch', fetcher)
    render(<App />)
    expect(await screen.findByRole('tab', { name: 'Members' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows the place pool with member colours, names and markers', async () => {
    const { fetcher } = server()
    await openMap(fetcher)
    const pool = screen.getByRole('region', { name: /Place pool/ })
    expect(within(pool).getByText('Senso-ji')).toBeInTheDocument()
    expect(screen.getByText('Proposed by friend')).toBeInTheDocument()
    const legend = screen.getByRole('list', { name: 'Member colours' })
    expect(within(legend).getByText('reader')).toBeInTheDocument()
    const markers = within(screen.getByRole('list', { name: 'Map markers' })).getAllByRole('listitem')
    const sensoji = markers.find((marker) => marker.textContent?.includes('Senso-ji — proposed by friend'))
    const tower = markers.find((marker) => marker.textContent?.includes('Tower — proposed by reader'))
    expect(sensoji?.textContent?.startsWith('F|')).toBe(true)
    // Colour follows member-list order: reader first, friend second.
    expect(tower).toHaveAttribute('data-color', '#1c6fc2')
    expect(sensoji).toHaveAttribute('data-color', '#d71f1f')
  })

  it('searches only on explicit submit and saves results with their provider identity', async () => {
    const { fetcher } = server((url, init) => {
      if (url.pathname === '/api/v1/geocode') return json([{
        provider: 'nominatim', provider_place_id: 'N123', name: 'Kaminarimon', address: 'Asakusa, Tokyo',
        latitude: 35.711, longitude: 139.796,
      }])
      if (url.pathname.endsWith('/places') && init.method === 'POST' && calls(fetcher, url.pathname, 'POST').length > 1) {
        return error('PLACE_DUPLICATE', 'This place is already in the trip', 409)
      }
    })
    await openMap(fetcher)
    const input = screen.getByLabelText('Place name or address')
    await userEvent.type(input, 'Kaminarimon')
    expect(calls(fetcher, '/api/v1/geocode')).toHaveLength(0)
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByText('Kaminarimon')).toBeInTheDocument()
    const searches = calls(fetcher, '/api/v1/geocode')
    expect(searches).toHaveLength(1)
    expect(new URL(String(searches[0][0])).searchParams.get('q')).toBe('Kaminarimon')
    expect(screen.getAllByText(/OpenStreetMap/).length).toBeGreaterThan(0)

    await userEvent.click(screen.getByRole('button', { name: 'Add Kaminarimon to the place pool' }))
    expect(await screen.findByText('Kaminarimon added to the place pool.')).toBeInTheDocument()
    expect(body(calls(fetcher, '/api/v1/trips/12/places', 'POST')[0])).toEqual({
      name: 'Kaminarimon', address: 'Asakusa, Tokyo', latitude: 35.711, longitude: 139.796,
      provider: 'nominatim', provider_place_id: 'N123',
    })
    await userEvent.click(screen.getByRole('button', { name: 'Add Kaminarimon to the place pool' }))
    expect(await screen.findByText('Kaminarimon is already in the place pool.')).toBeInTheDocument()
  })

  it('disables search while a request is in flight', async () => {
    let release: (response: Response) => void = () => undefined
    const { fetcher } = server((url) => url.pathname === '/api/v1/geocode'
      ? new Promise<Response>((resolve) => { release = resolve }) : undefined)
    await openMap(fetcher)
    await userEvent.type(screen.getByLabelText('Place name or address'), 'Tokyo{Enter}')
    const button = await screen.findByRole('button', { name: 'Searching...' })
    expect(button).toBeDisabled()
    await userEvent.keyboard('{Enter}')
    expect(calls(fetcher, '/api/v1/geocode')).toHaveLength(1)
    await act(async () => release(json([])))
    expect(await screen.findByRole('button', { name: 'Search' })).toBeEnabled()
  })

  it('counts down after GEOCODER_BUSY using Retry-After', async () => {
    const { fetcher } = server((url) => url.pathname === '/api/v1/geocode'
      ? error('GEOCODER_BUSY', 'Place search is busy; retry shortly', 429, [], { 'Retry-After': '1' }) : undefined)
    await openMap(fetcher)
    await userEvent.type(screen.getByLabelText('Place name or address'), 'Tokyo{Enter}')
    expect(await screen.findByRole('button', { name: 'Retry in 1s' })).toBeDisabled()
    expect(screen.getByText(/busy for everyone/)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Search' }, { timeout: 2500 })).toBeEnabled()
    expect(calls(fetcher, '/api/v1/geocode')).toHaveLength(1)
  })

  it.each([
    ['GEOCODER_DISABLED', /turned off\. Add places manually/],
    ['GEOCODER_UNAVAILABLE', /temporarily unavailable/],
  ])('explains %s', async (code, text) => {
    const { fetcher } = server((url) => url.pathname === '/api/v1/geocode'
      ? error(code, 'Place search problem', 503) : undefined)
    await openMap(fetcher)
    await userEvent.type(screen.getByLabelText('Place name or address'), 'Tokyo{Enter}')
    expect(await screen.findByText(text)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Search' })).toBeEnabled()
  })

  it('adds a manual place from a map click', async () => {
    const { fetcher } = server()
    await openMap(fetcher)
    await userEvent.click(screen.getByRole('button', { name: 'Pick on map' }))
    await userEvent.click(screen.getByRole('button', { name: 'Simulate map click' }))
    expect(screen.getByLabelText('Latitude')).toHaveValue('35.123456')
    expect(screen.getByLabelText('Longitude')).toHaveValue('139.654321')
    // Picking ends after one click.
    expect(screen.queryByRole('button', { name: 'Simulate map click' })).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Name'), 'Hotel')
    await userEvent.click(screen.getByRole('button', { name: 'Add place' }))
    expect(await screen.findByText('Hotel added to the place pool.')).toBeInTheDocument()
    expect(body(calls(fetcher, '/api/v1/trips/12/places', 'POST')[0])).toEqual({
      name: 'Hotel', latitude: 35.123456, longitude: 139.654321,
    })
  })

  it('validates typed coordinates before sending', async () => {
    const { fetcher } = server()
    await openMap(fetcher)
    await userEvent.type(screen.getByLabelText('Name'), 'Hotel')
    await userEvent.type(screen.getByLabelText('Latitude'), '91')
    await userEvent.type(screen.getByLabelText('Longitude'), '139.1234567')
    await userEvent.click(screen.getByRole('button', { name: 'Add place' }))
    expect(await screen.findByText(/at most six decimals/)).toBeInTheDocument()
    expect(calls(fetcher, '/api/v1/trips/12/places', 'POST')).toHaveLength(0)
  })

  it('edits a place name and note', async () => {
    const { fetcher } = server((url, init) => url.pathname === '/api/v1/trips/12/places/1' && init.method === 'PATCH'
      ? json(place(1, 'Asakusa Temple', 8, { note: 'Go early' })) : undefined)
    await openMap(fetcher)
    await userEvent.click(screen.getByRole('button', { name: 'Edit Senso-ji' }))
    const name = screen.getByDisplayValue('Senso-ji')
    await userEvent.clear(name)
    await userEvent.type(name, 'Asakusa Temple')
    await userEvent.type(screen.getByLabelText('Note'), 'Go early')
    await userEvent.click(screen.getByRole('button', { name: 'Save place' }))
    expect(await screen.findByText('Asakusa Temple saved.')).toBeInTheDocument()
    expect(body(calls(fetcher, '/api/v1/trips/12/places/1', 'PATCH')[0])).toEqual({
      name: 'Asakusa Temple', note: 'Go early',
    })
  })

  it('confirms deletion in the page and explains unlinking', async () => {
    const confirm = vi.spyOn(window, 'confirm')
    const { fetcher } = server((url, init) => url.pathname === '/api/v1/trips/12/places/1' && init.method === 'DELETE'
      ? new Response(null, { status: 204 }) : undefined)
    await openMap(fetcher)
    await userEvent.click(screen.getByRole('button', { name: 'Delete Senso-ji' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent(/linked to it will be unlinked automatically; their location text stays/)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Keep it' }))
    expect(calls(fetcher, '/api/v1/trips/12/places/1', 'DELETE')).toHaveLength(0)
    await userEvent.click(screen.getByRole('button', { name: 'Delete Senso-ji' }))
    const routeLoads = calls(fetcher, '/api/v1/trips/12/itinerary/route').length
    await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete place' }))
    expect(await screen.findByText(/1 itinerary item was unlinked; location text was kept/)).toBeInTheDocument()
    expect(calls(fetcher, '/api/v1/trips/12/itinerary/route').length).toBe(routeLoads + 1)
    expect(confirm).not.toHaveBeenCalled()
  })

  it('shows the day route as straight-line legs with unlocated items', async () => {
    const { fetcher } = server()
    await openMap(fetcher, 'Itinerary')
    expect(screen.getByText('Straight-line distance, not actual travel distance or time.')).toBeInTheDocument()
    const stops = within(await screen.findByRole('list', { name: 'Route stops' })).getAllByRole('listitem')
    expect(stops.map((stop) => stop.textContent)).toEqual([
      '1TempleSenso-ji', '↓ 1.82 km2Tower visitTower', '↓ 12.5 km3Park walkPark',
    ])
    expect(screen.getByText('14.3 km')).toBeInTheDocument()
    expect(screen.getByText('Not on the map (no linked place):').nextElementSibling).toHaveTextContent('Lunch')
    expect(screen.getByTestId('line-route')).toHaveTextContent('3')
    const route = calls(fetcher, '/api/v1/trips/12/itinerary/route')[0]
    expect(new URL(String(route[0])).searchParams.get('date')).toBe('2027-06-10')
    await userEvent.selectOptions(screen.getByLabelText('Day'), '2027-06-11')
    await waitFor(() => expect(calls(fetcher, '/api/v1/trips/12/itinerary/route').map(
      ([url]) => new URL(String(url)).searchParams.get('date'))).toContain('2027-06-11'))
  })

  it('previews a suggested order and applies it with the expected order', async () => {
    const { fetcher } = server((url) => {
      if (url.pathname.endsWith('/optimize')) return json(plan)
      if (url.pathname.endsWith('/reorder')) return json([])
    })
    await openMap(fetcher, 'Itinerary')
    await userEvent.click(screen.getByRole('button', { name: 'Suggest shorter order' }))
    const preview = await screen.findByRole('region', { name: 'Suggested order preview' })
    expect(body(calls(fetcher, '/api/v1/trips/12/itinerary/optimize', 'POST')[0])).toEqual({
      date: '2027-06-10', keep_first: true,
    })
    expect(preview).toHaveTextContent('5.22 km shorter in straight-line distance (14.3 km → 9.10 km)')
    // Lunch is fixed because it has no place (it is also timed); Temple is the kept start.
    expect(within(preview).getAllByText('Fixed · no place')).toHaveLength(2)
    expect(within(preview).getAllByText('Fixed · start')).toHaveLength(2)
    expect(screen.getByTestId('line-suggested')).toHaveAttribute('data-dashed', 'true')
    const itineraryLoads = calls(fetcher, '/api/v1/trips/12/itinerary').length
    await userEvent.click(within(preview).getByRole('button', { name: 'Apply suggested order' }))
    expect(await screen.findByText('Suggested order applied.')).toBeInTheDocument()
    expect(body(calls(fetcher, '/api/v1/trips/12/itinerary/reorder', 'PATCH')[0])).toEqual({
      date: '2027-06-10', item_ids: [9, 10, 13, 11], expected_item_ids: [9, 10, 11, 13],
    })
    // One reload for the map's titles, one for the itinerary list beneath it.
    expect(calls(fetcher, '/api/v1/trips/12/itinerary').length).toBe(itineraryLoads + 2)
    expect(screen.queryByTestId('line-suggested')).not.toBeInTheDocument()
  })

  it('cancel discards the preview without writing', async () => {
    const { fetcher } = server((url) => url.pathname.endsWith('/optimize') ? json(plan) : undefined)
    await openMap(fetcher, 'Itinerary')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Keep the first item as the start' }))
    await userEvent.click(screen.getByRole('button', { name: 'Suggest shorter order' }))
    expect(body(calls(fetcher, '/api/v1/trips/12/itinerary/optimize', 'POST')[0]).keep_first).toBe(false)
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('region', { name: 'Suggested order preview' })).not.toBeInTheDocument()
    expect(calls(fetcher, '/api/v1/trips/12/itinerary/reorder', 'PATCH')).toHaveLength(0)
  })

  it('says when the current order is already short', async () => {
    const { fetcher } = server((url) => url.pathname.endsWith('/optimize')
      ? json({ ...plan, changed: false, proposed_item_ids: plan.original_item_ids, proposed_route: route }) : undefined)
    await openMap(fetcher, 'Itinerary')
    await userEvent.click(screen.getByRole('button', { name: 'Suggest shorter order' }))
    expect(await screen.findByText('The current order is already a short route (straight-line).')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Apply suggested order' })).not.toBeInTheDocument()
  })

  it('handles a stale apply by reloading without retrying', async () => {
    const { fetcher } = server((url) => {
      if (url.pathname.endsWith('/optimize')) return json(plan)
      if (url.pathname.endsWith('/reorder')) {
        return error('ITINERARY_CONFLICT', 'The itinerary order changed; review it and retry', 409)
      }
    })
    await openMap(fetcher, 'Itinerary')
    await userEvent.click(screen.getByRole('button', { name: 'Suggest shorter order' }))
    const routeLoads = calls(fetcher, '/api/v1/trips/12/itinerary/route').length
    await userEvent.click(await screen.findByRole('button', { name: 'Apply suggested order' }))
    expect(await screen.findByText(/changed by another member/)).toBeInTheDocument()
    expect(calls(fetcher, '/api/v1/trips/12/itinerary/reorder', 'PATCH')).toHaveLength(1)
    await waitFor(() => expect(calls(fetcher, '/api/v1/trips/12/itinerary/route').length).toBe(routeLoads + 1))
    expect(screen.queryByRole('region', { name: 'Suggested order preview' })).not.toBeInTheDocument()
  })

  it('shows the server reason when a day is too large to optimize', async () => {
    const { fetcher } = server((url) => url.pathname.endsWith('/optimize') ? error('VALIDATION_ERROR',
      'Request validation failed', 422, [{
        loc: ['body'], msg: 'Route optimization supports at most 50 items per day', type: 'value_error',
      }]) : undefined)
    await openMap(fetcher, 'Itinerary')
    await userEvent.click(screen.getByRole('button', { name: 'Suggest shorter order' }))
    expect(await screen.findByText('Route optimization supports at most 50 items per day')).toBeInTheDocument()
  })
})

describe('day route panel anchors', () => {
  it('labels why each anchored item stays in place', async () => {
    const { DayRoutePanel } = await import('../components/map/DayRoutePanel')
    const items = new Map([
      [9, item(9, 'Hotel', 1, 1)], [10, item(10, 'Dinner booking', 2, 2, '19:00:00')], [11, item(11, 'Rest', 3, null)],
    ])
    const anchored = { ...plan, original_item_ids: [9, 10, 11], proposed_item_ids: [9, 10, 11],
      anchored_item_ids: [9, 10, 11], original_route: { ...route, unlocated_item_ids: [11] } }
    render(<DayRoutePanel days={['2027-06-10']} day="2027-06-10" onDay={() => undefined} route={route}
      plan={anchored} itemsById={items} keepFirst onKeepFirst={() => undefined} pending={null} message=""
      onSuggest={() => undefined} onApply={() => undefined} onCancel={() => undefined} />)
    const current = screen.getByRole('heading', { name: /Current/ }).nextElementSibling as HTMLElement
    expect([...current.querySelectorAll('li')].map((li) => li.textContent)).toEqual([
      'HotelFixed · start', 'Dinner bookingFixed · timed', 'RestFixed · no place',
    ])
  })
})
