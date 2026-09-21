import { StrictMode } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'
import { TOKEN_KEY } from './tokenStorage'

const user = { id: 1, username: 'reader', email: 'reader@example.com', created_at: '2026-09-20T00:00:00Z' }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const denied = () => json({ error: { code: 'INVALID_CREDENTIALS', message: 'Invalid credentials', details: [] } }, 401)

function Harness() {
  const { state, logout, restore, request, login } = useAuth()
  return <>
    <p role="status">{state.status}</p>
    {state.user && <p>{state.user.username}</p>}
    {state.status === 'error' && <p role="alert">{state.message}</p>}
    <button onClick={logout}>Exit</button>
    <button onClick={() => void restore()}>Restore</button>
    <button onClick={() => void request('/api/v1/auth/me').catch(() => {})}>Request</button>
    <button onClick={() => void login({ email: user.email, password: 'test-only-input' },
      new AbortController().signal).catch(() => {})}>Login</button>
  </>
}

function mount() { return render(<StrictMode><AuthProvider><Harness /></AuthProvider></StrictMode>) }

describe('Auth state', () => {
  it('has no authenticated user when no token exists', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    mount()
    expect(await screen.findByText('anonymous')).toBeInTheDocument()
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('restores via me and removes token and user on logout', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json(user)))
    mount()
    expect(await screen.findByText('reader')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Exit'))
    expect(screen.getByRole('status')).toHaveTextContent('anonymous')
    expect(screen.queryByText('reader')).not.toBeInTheDocument()
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it('clears an invalid or expired token on restore 401', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'invalid-test-token')
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => denied()))
    mount()
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('anonymous'))
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it.each([503, 0])('does not treat infrastructure failure %s as invalid credentials', async (status) => {
    sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => {
      if (!status) throw new TypeError()
      return json({ error: { code: 'AUTHENTICATION_UNAVAILABLE', message: 'Try again later', details: [] } }, status)
    }))
    mount()
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('error'))
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe('opaque-test-token')
    expect(screen.queryByText('reader')).not.toBeInTheDocument()
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json(user)))
    fireEvent.click(screen.getByText('Restore'))
    expect(await screen.findByText('reader')).toBeInTheDocument()
  })

  it('clears the session on a subsequent authenticated request 401', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json(user)))
    mount()
    await screen.findByText('reader')
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => denied()))
    fireEvent.click(screen.getByText('Request'))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('anonymous'))
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it('does not restore a user from a late me response after logout', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
    let resolve!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((done) => { resolve = done })))
    mount()
    fireEvent.click(screen.getByText('Exit'))
    await act(async () => resolve(json(user)))
    expect(screen.getByRole('status')).toHaveTextContent('anonymous')
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it('does not authenticate on token response alone and clears failed me candidate', async () => {
    const fetcher = vi.fn().mockImplementation(async (url: string) => url.endsWith('/login')
      ? json({ access_token: 'candidate-token', token_type: 'bearer' }) : denied())
    vi.stubGlobal('fetch', fetcher)
    mount()
    fireEvent.click(screen.getByText('Login'))
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull())
    expect(screen.queryByText('reader')).not.toBeInTheDocument()
  })

  it('handles denied sessionStorage without crashing or granting access', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('Denied') })
    mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('Browser session storage is unavailable.')
    expect(screen.getByRole('status')).toHaveTextContent('error')
  })

  it('does not persist a late login response after logout', async () => {
    let resolve!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((done) => { resolve = done })))
    mount()
    fireEvent.click(screen.getByText('Login'))
    fireEvent.click(screen.getByText('Exit'))
    await act(async () => resolve(json({ access_token: 'late-token', token_type: 'bearer' })))
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('anonymous')
  })

  it('fails closed if storing the token is denied', async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ access_token: 'candidate-token', token_type: 'bearer' }))
    vi.stubGlobal('fetch', fetcher)
    const storageWrite = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Denied') })
    mount()
    fireEvent.click(screen.getByText('Login'))
    await waitFor(() => expect(storageWrite).toHaveBeenCalledTimes(1))
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('status')).toHaveTextContent('anonymous')
  })

  it('does not log out for a protected request 503', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'opaque-test-token')
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json(user)))
    mount()
    await screen.findByText('reader')
    const fetcher = vi.fn().mockResolvedValue(json({ error: { code: 'SERVICE_UNAVAILABLE', message: 'Try later', details: [] } }, 503))
    vi.stubGlobal('fetch', fetcher)
    fireEvent.click(screen.getByText('Request'))
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('status')).toHaveTextContent('authenticated')
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe('opaque-test-token')
  })
})
