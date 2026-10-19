import { act, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { TOKEN_KEY } from '../auth/tokenStorage'

// Hold the lazy workspace chunk open so the Suspense fallback is observable.
let release: () => void = () => undefined
const gate = new Promise<void>((resolve) => { release = resolve })
vi.mock('./TripWorkspace', async () => {
  await gate
  return { default: () => <p>Workspace chunk loaded</p> }
})

const stamp = '2026-09-20T00:00:00Z'
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

describe('lazy workspace', () => {
  it('shows the top bar at once and a fallback until the map chunk arrives', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
    window.history.replaceState(null, '', '/trips/12')
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/health')) return json({ status: 'ok' })
      if (url.endsWith('/me')) return json({ id: 7, username: 'reader', email: 'r@example.com', created_at: stamp })
      if (url.endsWith('/api/v1/trips')) return json([{
        id: 12, name: 'Tokyo', destination: 'Japan', start_date: '2027-06-10', end_date: '2027-06-12',
        owner_id: 7, created_at: stamp, updated_at: stamp,
      }])
      return json([])
    }))
    render(<App />)
    expect(await screen.findByLabelText('Current trip')).toHaveValue('12')
    expect(screen.getByRole('status')).toHaveTextContent('Loading map...')
    await act(async () => release())
    expect(await screen.findByText('Workspace chunk loaded')).toBeInTheDocument()
  })
})
