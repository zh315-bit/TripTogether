import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { DEMO_KEY, TOKEN_KEY } from '../auth/tokenStorage'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const mika = { id: 31, username: 'mika_demo', email: 'mika@demo.triptogether.app', created_at: '2026-09-20T00:00:00Z' }
const trip = {
  id: 44, name: 'Kyoto long weekend', destination: 'Kyoto, Japan', start_date: '2027-04-02', end_date: '2027-04-04',
  owner_id: 31, created_at: '2026-09-20T00:00:00Z', version: 1, updated_at: '2026-09-20T00:00:00Z',
}

function server(member = 'mika', status = 200) {
  const fetcher = vi.fn(async (input: string, init?: RequestInit) => {
    const path = new URL(input).pathname
    if (path.endsWith('/auth/demo')) {
      if (status !== 200) return json({ error: { code: 'DEMO_DISABLED', message: 'The demo is not enabled', details: [] } }, status)
      const body = JSON.parse(String(init?.body))
      return json({ access_token: `demo-${body.member}`, token_type: 'bearer', member: body.member, username: `${body.member}_demo`, trip_id: 44 })
    }
    if (path.endsWith('/auth/me')) return json({ ...mika, username: `${member}_demo` })
    if (path === '/health') return json({ status: 'ok' })
    if (path === '/api/v1/trips') return json([trip])
    if (path === '/api/v1/trips/44') return json(trip)
    if (path.endsWith('/itinerary/route')) return json({ date: '2027-04-02', stops: [], legs: [], total_distance_km: 0, unlocated_item_ids: [] })
    if (path.endsWith('/balances')) return json({ trip_id: 44, currency: null, members: [], suggested_settlements: [], settlement: { transfers: 0, unsettled_members: 0, minimal: true } })
    return json([])
  })
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}

describe('demo sign-in', () => {
  it('opens the shared trip as Mika from the landing page', async () => {
    const fetcher = server()
    window.history.replaceState(null, '', '/')
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Try the demo' }))
    await waitFor(() => expect(window.location.pathname).toBe('/trips/44'))
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe('demo-mika')
    expect(sessionStorage.getItem(DEMO_KEY)).toBe('mika')
    const call = fetcher.mock.calls.find(([url]) => String(url).endsWith('/auth/demo'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ member: 'mika' })
  })

  it('opens /demo?as=jonas as Jonas without clicking anything', async () => {
    const fetcher = server('jonas')
    window.history.replaceState(null, '', '/demo?as=jonas')
    render(<App />)
    await waitFor(() => expect(window.location.pathname).toBe('/trips/44'))
    expect(sessionStorage.getItem(DEMO_KEY)).toBe('jonas')
    expect(fetcher.mock.calls.filter(([url]) => String(url).endsWith('/auth/demo'))).toHaveLength(1)
  })

  it('explains when the server has no demo and leaves no session behind', async () => {
    server('mika', 404)
    window.history.replaceState(null, '', '/')
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Try the demo' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The demo is not enabled on this server.')
    expect(window.location.pathname).toBe('/')
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
  })
})
